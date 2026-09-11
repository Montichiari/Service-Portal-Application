"""The API's one error shape (T-AUTH-2; design.md §1, requirements XC-4).

Every error response the API emits — validation failures, auth failures,
not-found, and unhandled crashes alike — is rendered here, through
``error_response``:

```json
{ "error": { "code": "...", "message": "...", "fields": {...} } }
```

Route code never builds this by hand and never wraps itself in ``try/except``
to produce it (backend/CLAUDE.md): it raises an ``APIError`` subclass and the
handlers registered by ``register_exception_handlers`` do the rendering. That
is what keeps the shape from drifting one route at a time.

``fields`` appears only on ``VALIDATION_ERROR`` (design.md §1), so a client can
treat its presence as meaningful rather than checking for an empty map.

The ``code`` values are closed: they are exactly design.md §1's error table.
A new error case needs a new row in that table in the same change — never an
undocumented string invented at a call site.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.cors import cors_headers_for

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """The `code` enum from design.md §1's error table. Closed set."""

    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# The 500 message is deliberately content-free. An unhandled exception's text
# routinely carries a SQL fragment, a file path or a connection string, and
# design.md §1 requires that `message` never leaks internals — the traceback
# goes to the log, not to the client.
INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."
VALIDATION_ERROR_MESSAGE = "One or more fields are invalid."


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    fields: Mapping[str, list[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Render the error envelope. The only place its shape is written down."""
    error: dict[str, Any] = {"code": code.value, "message": message}
    if fields is not None:
        error["fields"] = dict(fields)
    return JSONResponse(
        status_code=status_code, content={"error": error}, headers=dict(headers or {})
    )


# --- Raisable errors ---------------------------------------------------------


class APIError(Exception):
    """Base for errors that render as the envelope.

    Deliberately not a subclass of ``HTTPException``: FastAPI's built-in
    handler for that class emits ``{"detail": ...}``, and inheriting from it
    invites a future handler-ordering change to silently route these back
    through the default shape.
    """

    status_code: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    default_message: str = INTERNAL_ERROR_MESSAGE

    def __init__(
        self,
        message: str | None = None,
        *,
        fields: Mapping[str, list[str]] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.fields = fields
        super().__init__(self.message)


class UnauthenticatedError(APIError):
    """401 — no usable session (XC-5)."""

    status_code = 401
    code = ErrorCode.UNAUTHENTICATED
    # Says only that authentication is needed, never why the token was
    # rejected: "expired" vs. "bad signature" vs. "no such user" are all
    # information a caller without a valid session hasn't earned.
    default_message = "Authentication required."


class ForbiddenError(APIError):
    """403 — authenticated, but not allowed (XC-6, XC-9)."""

    status_code = 403
    code = ErrorCode.FORBIDDEN
    default_message = "You do not have permission to perform this action."


class NotFoundError(APIError):
    """404 — no such resource, *or* one the caller may not see (XC-7).

    Deliberately one class for both. XC-7 requires the two to be
    indistinguishable, and the reliable way to keep two responses identical is
    for there to be one response: a caller who is told "403" learns that the
    id exists and belongs to someone else, which is exactly what a 404 for an
    invisible row exists to withhold. The default message names nothing about
    what was looked up for the same reason.
    """

    status_code = 404
    code = ErrorCode.NOT_FOUND
    default_message = "The requested resource was not found."


class ValidationFailedError(APIError):
    """422 — a field is invalid, decided by code rather than by Pydantic.

    Most 422s come from ``RequestValidationError`` and never touch this class.
    This is for the ones the schema layer *cannot* decide, because the valid
    set lives in the database: SR-3's ``?status=`` filter is checked against
    the ``statuses`` table, not against a Literal. Raising this keeps such a
    failure in XC-4's envelope, with ``fields`` populated, instead of inventing
    a second shape for the same class of error.
    """

    status_code = 422
    code = ErrorCode.VALIDATION_ERROR
    default_message = VALIDATION_ERROR_MESSAGE


class ConflictError(APIError):
    """409 — the request collides with existing state (AUTH-2).

    The message names the colliding field and stops there. AUTH-2 allows the
    caller to learn "this email is taken" and nothing further, and design.md
    §1 reserves ``fields`` for ``VALIDATION_ERROR``, so this carries none.
    """

    status_code = 409
    code = ErrorCode.CONFLICT
    default_message = "That request conflicts with existing data."


# --- RequestValidationError -> `fields` --------------------------------------

# Pydantic prefixes each error's `loc` with where the value came from —
# ("body", "email"), ("query", "page_size"). XC-4's `fields` map is keyed by
# field name, so the prefix is stripped.
_LOCATION_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})

# Fallback key for an error with no usable location at all.
_UNKNOWN_FIELD = "__root__"

# A body that isn't valid JSON reports *the character offset where parsing
# failed* as its location — ("body", 1). That integer is not a field name, and
# treating it as one puts a bare "1" key in `fields` that looks like a list
# index. These errors are about the request as a whole, so they key on the
# location instead.
_WHOLE_LOCATION_ERROR_TYPES = frozenset({"json_invalid"})


def _field_key(loc: tuple[Any, ...], error_type: str = "") -> str:
    """Flatten a Pydantic ``loc`` tuple into one ``fields`` key.

    ``("body", "email")`` -> ``"email"``; ``("body", "items", 0, "title")`` ->
    ``"items.0.title"``; ``("body", 1)`` from unparseable JSON -> ``"body"``.
    """
    parts = list(loc)
    prefix = str(parts.pop(0)) if parts and parts[0] in _LOCATION_PREFIXES else ""
    if error_type in _WHOLE_LOCATION_ERROR_TYPES or not parts:
        return prefix or _UNKNOWN_FIELD
    return ".".join(str(part) for part in parts)


def validation_error_fields(exc: RequestValidationError) -> dict[str, list[str]]:
    """Reshape Pydantic's error list into XC-4's ``{field: [message, ...]}``.

    Only ``msg`` is carried across. The rest of a Pydantic error dict (``ctx``
    especially) can hold arbitrary Python objects — including the rejected
    input itself, which for a register call would be the plaintext password.
    Copying the whole dict into the response would leak it.
    """
    fields: dict[str, list[str]] = {}
    for error in exc.errors():
        key = _field_key(
            tuple(error.get("loc", ())), str(error.get("type", ""))
        )
        fields.setdefault(key, []).append(str(error.get("msg", "Invalid value")))
    return fields


# --- Handlers ----------------------------------------------------------------

# For HTTPExceptions raised by the framework itself (404 on an unrouted path,
# 405 on a wrong method) — our own code raises APIError instead.
_STATUS_TO_CODE = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
}


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, APIError)  # registered for APIError only
    return error_response(exc.status_code, exc.code, exc.message, exc.fields)


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(
        422,
        ErrorCode.VALIDATION_ERROR,
        VALIDATION_ERROR_MESSAGE,
        validation_error_fields(exc),
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Re-render framework-raised ``HTTPException``s into the envelope.

    Without this, a request to an unrouted path would answer with Starlette's
    ``{"detail": "Not Found"}`` — a second error shape in an API whose whole
    point (design.md §1) is having one.
    """
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_TO_CODE.get(
        exc.status_code,
        ErrorCode.INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.BAD_REQUEST,
    )
    # A 5xx detail is server-side information; a 4xx detail is the framework
    # describing the client's own mistake ("Not Found", "Method Not Allowed").
    message = (
        INTERNAL_ERROR_MESSAGE
        if exc.status_code >= 500
        else str(exc.detail or "Request could not be processed.")
    )
    # Headers matter here: a 405 carries `Allow`, and dropping it would make
    # the response non-conformant.
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort — anything that reached here is a bug (design.md §1, 500)."""
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return error_response(
        500,
        ErrorCode.INTERNAL_ERROR,
        INTERNAL_ERROR_MESSAGE,
        # Every other handler's response is decorated by `CORSMiddleware` on
        # the way out; this one is created outside it and would otherwise
        # reach a browser stripped of CORS headers, i.e. as an unreadable
        # network error rather than a 500 (XC-12). `cors_headers_for` explains
        # why the handler sits where it does.
        headers=cors_headers_for(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler above. Called once, from ``create_app``."""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
