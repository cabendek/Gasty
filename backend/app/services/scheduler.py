import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings
from app.db import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

scheduler = BackgroundScheduler()


def _renew_gmail_watches() -> None:
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() + timedelta(days=2)
        users = (
            db.query(User)
            .filter(
                User.gmail_connection_status == "connected",
                User.gmail_watch_expiry <= cutoff,
            )
            .all()
        )

        for user in users:
            try:
                creds = Credentials(
                    token=user.gmail_access_token,
                    refresh_token=user.gmail_refresh_token,
                    token_uri=_GOOGLE_TOKEN_URL,
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                )
                gmail = build("gmail", "v1", credentials=creds)
                gmail.users().watch(
                    userId="me",
                    body={
                        "topicName": (
                            f"projects/{settings.google_project_id}/topics/gmail-notifications"
                        ),
                        "labelIds": ["INBOX"],
                    },
                ).execute()
                user.gmail_watch_expiry = datetime.utcnow() + timedelta(days=7)
                db.commit()
                logger.info("Renewed Gmail watch for user %s", user.id)
            except Exception as exc:
                logger.error("Failed to renew watch for user %s: %s", user.id, exc)
                try:
                    import sentry_sdk

                    sentry_sdk.capture_exception(exc)
                except ImportError:
                    pass
    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(
        _renew_gmail_watches,
        trigger="cron",
        hour=3,
        minute=0,
        id="renew_gmail_watches",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler stopped")
