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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False


settings = Settings()
