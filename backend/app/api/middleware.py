"""Cross-cutting request middleware (T-AUTH-2, T-AUTH-3; requirements XC-9,
XC-12).

Two entries: the CSRF header check (XC-9) and CORS (XC-12). Both are
middleware rather than dependencies, per backend/CLAUDE.md — a dependency
would have to be remembered on every future non-``GET`` route, and the one
that got forgotten would be the one that mattered.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.cors import ALLOWED_ORIGINS
from app.api.errors import ErrorCode, error_response

CSRF_HEADER = "X-Requested-With"

# XC-9 says "every non-GET request"; HEAD and OPTIONS are exempt alongside GET
# for concrete reasons rather than as a loosening:
#   * HEAD is GET without a body — same read-only semantics, and a client that
#     can HEAD can already GET.
#   * OPTIONS is the CORS preflight. The browser sends it itself and will not
#     attach a custom header to it; rejecting it would fail every cross-origin
#     POST *before* the real request is ever attempted, disabling the frontend
#     rather than protecting it.
# Neither method changes state, so neither is a CSRF vector.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

CSRF_ERROR_MESSAGE = f"The {CSRF_HEADER} header is required on this request."


class RequireCustomHeaderMiddleware(BaseHTTPMiddleware):
    """Reject state-changing requests that don't carry ``X-Requested-With``.

    The CSRF protection is in the header being *custom*, not in its value: a
    cross-site ``<form>`` post can set neither, and any script that tries must
    first clear a CORS preflight this API never approves. So presence is what
    gets checked — pinning the value to ``XMLHttpRequest`` would add no
    security while breaking any client that spells it differently.

    This is the lightweight scheme design.md §1 chose over double-submit
    cookies, and it is explicitly marked there as "revisit before any real
    deployment beyond the capstone demo".
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method.upper() not in SAFE_METHODS and not request.headers.get(
            CSRF_HEADER
        ):
            # Answered here, in middleware, so it lands before routing, before
            # body parsing and before any auth dependency runs — XC-9's
            # "before evaluating any other request content". A request that
            # fails this never has its cookies looked at.
            return error_response(403, ErrorCode.FORBIDDEN, CSRF_ERROR_MESSAGE)
        return await call_next(request)


# Every method the API serves. Listed rather than wildcarded so that adding a
# verb is a visible decision; unlike the origin, a wildcard here would be
# valid, just less informative.
CORS_ALLOWED_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]

# The only two headers the frontend client sends: a JSON content type, and
# XC-9's CSRF header. Naming the latter here rather than re-spelling the
# string keeps it to one definition — and it has to be allowed explicitly or
# the preflight would reject the very header that makes a write legal.
CORS_ALLOWED_HEADERS = ["Content-Type", CSRF_HEADER]


def register_middleware(app: FastAPI) -> None:
    """Attach every middleware above. Called once, from ``create_app``."""
    app.add_middleware(RequireCustomHeaderMiddleware)
    # Added *last* on purpose. Starlette inserts each new middleware at the
    # front of the stack, so the last one registered is the outermost — which
    # puts CORS outside the CSRF check and outside `ExceptionMiddleware`.
    # Both placements matter for XC-12's "error responses too": a 403 from the
    # check above, and a 401/422 from an exception handler, are only readable
    # cross-origin because their responses pass back out through here.
    # Reversing these two lines would leave those responses bare, and no
    # success-path test would notice (see tests/api/test_cors.py).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        # Cookies are the entire auth transport (design.md §1), so a
        # credential-less CORS policy would allow the request and drop the
        # session.
        allow_credentials=True,
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=CORS_ALLOWED_HEADERS,
    )
