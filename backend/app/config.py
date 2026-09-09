from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    # Dedicated database for the automated schema-contract test suite
    # (backend/tests/db/). Same docker-compose Postgres service as
    # DATABASE_URL, a separate database — the suite creates it and migrates
    # it itself. Must never equal DATABASE_URL; conftest.py enforces that.
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg2://portal:portal@localhost:5433/service_portal_test"
    )
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Token lifetimes and cookie attributes deliberately live in
    # app/core/security.py, not here: they're contract decisions from
    # specs/api-phase/design.md §1, not per-environment configuration
    # (backend/CLAUDE.md, "Cookies and JWT"). The skeleton phase's
    # ACCESS_TOKEN_EXPIRE_MINUTES=30 and COOKIE_SECURE=false placeholders were
    # never read by any code and contradicted that design (1 hour, Secure), so
    # they were removed in T-AUTH-1 rather than left as a second source of
    # truth. `extra="ignore"` above means a stale .env keeping those keys is
    # harmless.


settings = Settings()
