# Service Portal — Backend

FastAPI + SQLAlchemy 2.0 backend skeleton.

## Requirements

- Python 3.11+
- A reachable PostgreSQL instance (see `DATABASE_URL` in `.env`)

## Install

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1     # PowerShell (Windows)
# source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
```

## Configure

```powershell
copy .env.example .env         # Windows
# cp .env.example .env         # macOS / Linux
```

Edit `.env` and set at least `DATABASE_URL` and `JWT_SECRET_KEY`.

## Run

```powershell
uvicorn app.main:app --reload
```

The API is then available at http://127.0.0.1:8000

- Health check: http://127.0.0.1:8000/health → `{"status": "ok"}`
- DB health check: http://127.0.0.1:8000/health/db → `{"status": "ok", "db": "connected"}`
  (returns HTTP 503 if Postgres is unreachable)
- Interactive docs: http://127.0.0.1:8000/docs

## Tests

The schema contract tests (`tests/db/`) run against a **real** Postgres
database — a dedicated `service_portal_test` database on the same
docker-compose service as the dev DB (`TEST_DATABASE_URL` in `.env` /
`app/config.py`), never SQLite.

The suite is self-provisioning: it creates that database if it doesn't exist
and runs `alembic upgrade head` into it once per run. Each test then runs
inside a transaction rolled back at teardown, so a run leaves no rows behind.

```powershell
# Postgres must be up first (from the repo root):
docker compose up -d db

cd backend
pip install -r requirements.txt
python -m pytest
```
