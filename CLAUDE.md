# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Gasty is a personal expense-tracking mobile app for Chile that auto-captures transactions from bank emails (Tenpo, Tarjeta Líder BCI, Banco de Chile) via Gmail Push, classifies them, and shows real-time budget progress. Target scale: 1–10 users, < $10 USD/month operational cost.

The repo is currently in the planning phase. The authoritative implementation guide is `guia-proyecto-gasty-v2.md` (v2 corrects architectural mistakes from `guia-proyecto-gasty.md`). The detailed PRD is `gasty-prd.md`.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.11+), SQLAlchemy, Alembic |
| Database | Supabase (Postgres 500MB free) |
| Auth | Supabase Auth + Google Sign-In (same GCP account as Gmail) |
| Email capture | Gmail API + Google Cloud Pub/Sub push subscription |
| Task queue | FastAPI `BackgroundTasks` (no Redis — volume doesn't justify it) |
| LLM fallback | Claude Haiku (default) → Sonnet (escalation if confidence < 0.7) |
| Mobile | React Native + Expo SDK 52+ with **development build** (not Expo Go — no iOS push since SDK 53) |
| Mobile state | TanStack Query + Expo Router (file-based) |
| Hosting | Fly.io (~$3–5/month, always-on) |
| CI/CD | GitHub Actions: `ruff` + `pytest` (testcontainers) + `flyctl deploy --remote-only` on main |
| Observability | Sentry free + `/health` + `/admin/health` |
| Backups | GitHub Actions cron + Cloudflare R2 (`pg_dump`, 30-day retention) |
| Token encryption | Fernet via SQLAlchemy `TypeDecorator` (`EncryptedString`), key in Fly secret `ENCRYPTION_KEY` |
| Dev tunnel | ngrok or cloudflared (required to receive Pub/Sub webhooks locally) |

## Development commands

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # or: uv sync / poetry install

# Run locally
uvicorn app.main:app --reload

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Tests (uses testcontainers, requires Docker)
pytest
pytest tests/parsers/test_tenpo.py  # single test file

# Lint
ruff check .
ruff format .

# Expose webhook endpoint for local Pub/Sub testing
ngrok http 8000
```

### Mobile

```bash
cd mobile
npm install

# Start dev server (requires Expo development build installed on device)
npx expo start

# Type check
npx tsc --noEmit

# Lint
npx eslint .

# Build development client (first time or after native dep changes)
eas build --profile development --platform ios
```

### Infrastructure

```bash
# Deploy backend
flyctl deploy --remote-only

# Check status
flyctl status
flyctl logs

# Connect to Supabase Postgres
psql $DATABASE_URL
```

## Planned project structure

```
Gasty/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers (webhooks.py is critical)
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic (auth.py, classification)
│   │   └── parsers/       # One class per bank source (BaseParser subclasses)
│   ├── alembic/
│   ├── tests/fixtures/    # .eml files per bank: tenpo/, lider/, bdc/
│   ├── Dockerfile
│   ├── fly.toml
│   └── pyproject.toml
├── mobile/
│   ├── app/               # Expo Router file-based routing
│   │   ├── (tabs)/        # Dashboard, Transactions, Config
│   │   ├── transaction/   # Detail screen
│   │   └── classify/      # Classification modal
│   ├── components/
│   ├── hooks/
│   └── services/          # API client, auth (auth.ts is critical)
├── .github/workflows/     # backend-ci.yml, mobile-ci.yml, backup-db.yml
└── docker-compose.yml     # Local dev only (not production)
```

## Architecture: critical design decisions

### Email → transaction flow

```
Gmail push → GCP Pub/Sub → POST /webhooks/gmail → BackgroundTask
  → gmail.users().history().list() → fetch email → parser router
  → BaseParser.can_parse() / parse() → INSERT ON CONFLICT DO NOTHING
  → push notification to Expo token
```

The webhook (`backend/app/api/webhooks.py`) is the system's heart:
- Must verify OIDC JWT from Google before processing (iss, aud, signature via JWKS)
- Must check `processed_pubsub_message` table for idempotency (Pub/Sub delivers at-least-once)
- Returns HTTP 200 immediately; heavy work runs in `BackgroundTask`

### Parser architecture

Three-tier fallback — do not skip levels:
1. **Regex parser** (per bank): `TenpoParser`, `LiderParser`, `BancodeChileParser` — each extends `BaseParser` with `can_parse()` and `parse()`
2. **Claude Haiku**: only when regex returns `None`; accept if `confidence > 0.7`
3. **Claude Sonnet**: only when Haiku confidence < 0.7; if still fails → `ParseError` + Sentry

Parser TDD: write tests against `.eml` fixtures in `tests/fixtures/<bank>/` **before** implementing the regex. This is mandatory because Gmail isn't available during development.

### Auth architecture

- Supabase Auth handles Google Sign-In on mobile — same Google account that will connect Gmail
- Backend verifies Supabase JWT via `SUPABASE_JWT_SECRET` (no Supabase SDK call on every request)
- Gmail OAuth tokens stored encrypted (`EncryptedString` TypeDecorator with Fernet)
- `User.gmail_connection_status` enum (`connected` | `needs_reauth` | `never_connected`) — never crash on revoked token, surface it to user

### Data model key constraints

- `Transaction.source_email_id`: UNIQUE — idempotency at email level
- `Transaction.is_duplicate_of`: nullable UUID — **never delete duplicates**, only mark them (supports undo from UI)
- `processed_pubsub_message(message_id PK, processed_at)`: idempotency at Pub/Sub message level
- `BudgetAlert`: UNIQUE on `(user_id, category_id, month, threshold)` — prevents push spam
- `ParseError`: TTL via GitHub Action (delete `resolved=true AND created_at < now() - 90 days`)

### Classification learning

`MerchantRule` drives auto-classification:
- `hit_count >= 3` → auto-classify with confidence 0.95 (no push needed)
- `hit_count < 3` → auto-classify with confidence 0.80 (send push to confirm)
- Manual classification always creates/updates the exact-match rule

### Deduplication (Phase 5c only — do not implement earlier)

`ENABLE_CROSS_SOURCE_DEDUP` feature flag, disabled by default until one month of real data is reviewed. Criteria: **exact amount + same merchant + ≤30 min apart + different sources + Levenshtein < 0.3**. Approximate matching = false positives = hidden expenses.

## Key operational constraints

- **100 test-user hard cap** on Google OAuth (app stays in "Testing" state). Adding family members requires manually adding them in GCP Console. Exceeding 100 requires CASA Tier 2 assessment (~$2–4k/year) — out of scope.
- **Supabase free pauses** after 7 days with no traffic. Daily Gmail webhooks prevent this in practice.
- **Expo Go does not support iOS push notifications** since SDK 53. Always use development builds.
- **Fly.io has no real free tier** — budget ~$3–5/month for backend hosting.
