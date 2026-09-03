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
