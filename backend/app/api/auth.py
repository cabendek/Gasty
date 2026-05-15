import secrets
import urllib.parse
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory CSRF state store (no Redis in Phase 1)
_STATE_STORE: dict[str, str] = {}

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@router.get("/gmail/start")
def gmail_start(current_user: User = Depends(get_current_user)):
    state = secrets.token_urlsafe(32)
    _STATE_STORE[state] = str(current_user.id)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.backend_url}/auth/gmail/callback",
        "response_type": "code",
        "scope": " ".join(_GMAIL_SCOPES),
        "access_type": "offline",
        "state": state,
        "prompt": "consent",
    }
    url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


@router.get("/gmail/callback")
async def gmail_callback(code: str, state: str, db: Session = Depends(get_db)):
    user_id = _STATE_STORE.pop(state, None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": f"{settings.backend_url}/auth/gmail/callback",
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange OAuth code")

    tokens = resp.json()

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.gmail_access_token = tokens["access_token"]
    if "refresh_token" in tokens:
        user.gmail_refresh_token = tokens["refresh_token"]
    user.gmail_connection_status = "connected"

    # Register Gmail push watch
    try:
        creds = Credentials(
            token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            token_uri=_GOOGLE_TOKEN_URL,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        gmail = build("gmail", "v1", credentials=creds)
        watch_resp = (
            gmail.users()
            .watch(
                userId="me",
                body={
                    "topicName": f"projects/{settings.google_project_id}/topics/gmail-notifications",
                    "labelIds": ["INBOX"],
                },
            )
            .execute()
        )
        user.gmail_watch_expiry = datetime.utcnow() + timedelta(days=7)
    except Exception:
        # Watch failure is non-fatal for the OAuth flow; status remains connected
        user.gmail_watch_expiry = datetime.utcnow() + timedelta(days=7)

    db.commit()
    return {"status": "connected"}


class ExpoPushTokenRequest(BaseModel):
    expo_push_token: str


@router.post("/expo-token")
def set_expo_token(
    body: ExpoPushTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.expo_push_token = body.expo_push_token
    db.commit()
    return {"status": "ok"}
