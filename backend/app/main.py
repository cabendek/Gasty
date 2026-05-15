import sentry_sdk
from fastapi import FastAPI

from app.config import settings

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

app = FastAPI(title="Gasty API")

# Routers
from app.api.auth import router as auth_router  # noqa: E402
from app.api.transactions import admin_router, router as tx_router  # noqa: E402
from app.api.webhooks import router as webhook_router  # noqa: E402

app.include_router(auth_router)
app.include_router(tx_router)
app.include_router(admin_router)
app.include_router(webhook_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# Scheduler lifecycle
from app.services.scheduler import start_scheduler, stop_scheduler  # noqa: E402


@app.on_event("startup")
def on_startup():
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()
