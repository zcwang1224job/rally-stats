# Rally Stats API

FastAPI backend for Rally Stats. See `specs/architecture.md` (repo root) for the
full system design, and `specs/001-create-manage-group/` for the currently
implemented feature.

## Prerequisites

- Python 3.12
- PostgreSQL 16+ running locally (or via `infra/docker-compose.yml`)

## Local setup

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
# edit .env: at minimum set JWT_SECRET and PASSWORD_ENCRYPTION_KEY to real
# random values (see comments in .env.example for how), and ABLY_API_KEY if
# you want realtime events to actually deliver.

createdb rally_stats   # requires local Postgres; adjust DATABASE_URL to match
export $(grep -v '^#' .env | xargs)
alembic upgrade head
```

## Running

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`. Interactive API docs at
`http://localhost:8000/docs`.

## Tests

Tests run against a **separate** `rally_stats_test` database (created
automatically by the test suite via Alembic on first run):

```bash
createdb rally_stats_test
source .venv/bin/activate
python -m pytest tests/ -v
```

## Linting & type checking

```bash
source .venv/bin/activate
ruff check app/ tests/
mypy app/
```

Both are treated as blocking checks (constitution principle I — strict type
safety).

## Project layout

```
app/
├── main.py                 # FastAPI app factory, CORS, exception handlers, lifespan
├── core/                   # Cross-cutting: db, config, errors, turnstile, realtime, rate_limit
├── domains/group/          # 001-create-manage-group: models/schemas/service/router/security
├── scheduler/               # APScheduler: 1-hour idle auto-disband sweep
└── system_config/           # Tunable system parameters (e.g. max_group_members)
tests/
├── unit/                    # Service-layer and scheduler unit tests
├── contract/                 # Per-endpoint request/response contract tests
└── integration/               # End-to-end lifecycle tests
```
