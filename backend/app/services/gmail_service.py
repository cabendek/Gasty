import base64
import logging
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal
from app.models.parse_error import ParseError
from app.models.transaction import Transaction
from app.models.user import User
from app.parsers.router import parser_router

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _build_gmail_service(user: User):
    creds = Credentials(
        token=user.gmail_access_token,
        refresh_token=user.gmail_refresh_token,
        token_uri=_GOOGLE_TOKEN_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    return build("gmail", "v1", credentials=creds)


def _decode_email_part(part) -> str:
    """Decode a MIME part payload to a Python string."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _extract_email_data(raw_bytes: bytes, gmail_message_id: str) -> dict:
    msg = message_from_bytes(raw_bytes)
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    from_addr = msg.get("From", "")
    date_str = msg.get("Date", "")

    body_plain = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body_plain = _decode_email_part(part)
            break

    return {
        "message_id": gmail_message_id,
        "subject": subject,
        "from": from_addr,
        "date": date_str,
        "body_plain": body_plain,
    }


def process_new_emails(user_id: str, history_id: str) -> None:
    """Background task: fetch new emails via history API and persist transactions."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return

        try:
            gmail = _build_gmail_service(user)
        except Exception as exc:
            logger.error("Failed to build Gmail service for user %s: %s", user_id, exc)
            return

        # Fetch new message IDs since last known historyId
        try:
            history_resp = (
                gmail.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                )
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 401:
                user.gmail_connection_status = "needs_reauth"
                db.commit()
                logger.warning("Gmail token revoked for user %s, marked needs_reauth", user_id)
            else:
                logger.error("Gmail history error for user %s: %s", user_id, exc)
            return

        records = history_resp.get("history", [])
        message_ids: list[str] = []
        for record in records:
            for added in record.get("messagesAdded", []):
                mid = added.get("message", {}).get("id")
                if mid and mid not in message_ids:
                    message_ids.append(mid)

        for mid in message_ids:
            _process_single_message(gmail, user, mid, db)

    finally:
        db.close()


def _process_single_message(gmail, user: User, message_id: str, db) -> None:
    try:
        msg_resp = (
            gmail.users().messages().get(userId="me", id=message_id, format="raw").execute()
        )
    except HttpError as exc:
        logger.error("Failed to fetch message %s: %s", message_id, exc)
        return

    raw_b64 = msg_resp.get("raw", "")
    try:
        raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
    except Exception as exc:
        logger.error("Failed to decode message %s: %s", message_id, exc)
        return

    email_data = _extract_email_data(raw_bytes, message_id)
    parsed = parser_router(email_data)

    if parsed is not None:
        tx = Transaction(
            user_id=user.id,
            amount=parsed.amount,
            merchant=parsed.merchant,
            transaction_date=parsed.transaction_date,
            transaction_type=parsed.transaction_type,
            source=parsed.source,
            source_email_id=parsed.source_email_id,
            raw_subject=parsed.raw_subject,
            needs_review=True,
        )
        try:
            db.add(tx)
            db.commit()
            logger.info(
                "Saved transaction %s for user %s: %s $%s",
                parsed.source_email_id,
                user.id,
                parsed.merchant,
                parsed.amount,
            )
        except IntegrityError:
            db.rollback()
            logger.info("Duplicate transaction ignored: %s", parsed.source_email_id)
    else:
        err = ParseError(
            user_id=user.id,
            source_email_id=message_id,
            raw_subject=email_data.get("subject"),
            error_message="No parser could handle this email",
        )
        db.add(err)
        try:
            db.commit()
        except Exception:
            db.rollback()
