import sentry_sdk
from fastapi import FastAPI

from app.config import settings

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

app = FastAPI(title="Gasty API")


@app.get("/health")
def health():
    return {"status": "ok"}
