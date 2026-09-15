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

    # --- the assistant's model (T-CHAT-1; specs/chatbot/design.md §2) --------
    #
    # Optional, unlike JWT_SECRET_KEY. An instance with no key still starts,
    # serves every other route, and answers POST /chat/messages with XC-14's
    # 500 — which is the same state T-CHAT-0 shipped and the right one for a
    # deployment that doesn't want the assistant. Making it required would
    # turn one unset variable into a backend that refuses to boot.
    ANTHROPIC_API_KEY: str | None = None
    # This deployment is a Microsoft Foundry resource (decision 8), which is
    # wire-compatible with the direct endpoint. Left unset, the SDK falls back
    # to its own api.anthropic.com default — so a direct Console key can
    # replace this deployment later by deleting a line, not by editing code.
    # Never validated against the `sk-ant-` prefix: this deployment's key does
    # not look like that and is equally valid.
    ANTHROPIC_BASE_URL: str | None = None
    # design.md decision 1 (revised): the only model deployed on the provided
    # resource. Here rather than in app/chat/ for the same reason
    # JWT_ALGORITHM is here — it differs per deployment, and the deployment is
    # the thing that decides which models exist.
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    # Not a contract number and not per-environment either, strictly — but a
    # ceiling on what one reply may cost is the kind of thing an operator
    # turns down under load, so it reads from the environment with a default
    # that suits a chat widget: long enough for a paragraph and a tool call,
    # far short of anything that could hold the request open for minutes.
    ANTHROPIC_MAX_TOKENS: int = 2048

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
