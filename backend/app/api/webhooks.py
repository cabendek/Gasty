import base64
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.processed_message import ProcessedPubSubMessage
from app.models.user import User
from app.services.gmail_service import process_new_emails

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_GOOGLE_REQUEST = google_requests.Request()


def _verify_oidc_token(token: str) -> dict:
    audience = f"{settings.backend_url}/webhooks/gmail"
    try:
        claims = id_token.verify_oauth2_token(token, _GOOGLE_REQUEST, audience=audience)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid OIDC token: {exc}")

    if claims.get("iss") not in (
        "https://accounts.google.com",
        "accounts.google.com",
    ):
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    return claims


@router.post("/gmail")
async def gmail_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # 1. Verify OIDC JWT from Google Pub/Sub
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth_header.removeprefix("Bearer ").strip()
    _verify_oidc_token(token)

    # 2. Parse Pub/Sub envelope
    body = await request.json()
    message = body.get("message", {})
    pubsub_message_id: str = message.get("messageId", "")

    if not pubsub_message_id:
        raise HTTPException(status_code=400, detail="Missing messageId")

    # 3. Idempotency check
    try:
        record = ProcessedPubSubMessage(message_id=pubsub_message_id)
        db.add(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Pub/Sub message %s already processed, skipping", pubsub_message_id)
        return {"status": "already_processed"}

    # 4. Decode payload
    raw_data = message.get("data", "")
    try:
        payload = json.loads(base64.b64decode(raw_data).decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to decode Pub/Sub data: %s", exc)
        return {"status": "ok"}

    email_address: str = payload.get("emailAddress", "")
    history_id: str = str(payload.get("historyId", ""))

    if not email_address or not history_id:
        return {"status": "ok"}

    # 5. Find user and enqueue background processing
    user = db.query(User).filter(User.email == email_address).first()
    if not user:
        logger.warning("No user found for email %s", email_address)
        return {"status": "ok"}

    background_tasks.add_task(process_new_emails, str(user.id), history_id)

    return {"status": "ok"}
