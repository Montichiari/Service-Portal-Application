"""Who may call this API cross-origin (T-AUTH-3; requirements XC-12).

Its own module rather than part of ``middleware.py`` because two very different
places need the same decision: the ``CORSMiddleware`` registration, which
covers almost every response, and the catch-all ``500`` handler in
``errors.py``, which covers the one response that never travels back through
that middleware (see ``cors_headers_for``). Both import from here; neither
imports the other, so there is no cycle to work around.
"""

from __future__ import annotations

from starlette.requests import Request

from app.config import settings

# XC-12: one explicit configured origin, never a wildcard. This is not the
# usual "just allow `*`" shortcut being resisted on principle — the CORS spec
# makes a wildcard origin incompatible with credentialed requests, and every
# call this API serves carries cookies, so `*` would simply not work.
ALLOWED_ORIGINS: tuple[str, ...] = (settings.FRONTEND_ORIGIN,)


def cors_headers_for(request: Request) -> dict[str, str]:
    """The CORS headers a response to ``request`` needs, if any.

    Only the catch-all ``500`` handler calls this, and only because of where
    Starlette puts that handler. The middleware stack is built as
    ``ServerErrorMiddleware`` -> user middleware (``CORSMiddleware`` included)
    -> ``ExceptionMiddleware`` -> router, and a handler registered for
    ``Exception`` *is* ``ServerErrorMiddleware``'s handler — the outermost
    layer of all. Its response is therefore created outside ``CORSMiddleware``
    and never passes through it. Every other error response — ``401``,
    ``403``, ``422``, and the framework's own ``404``/``405`` — comes from
    ``ExceptionMiddleware``, inside CORS, and is decorated the normal way.

    That placement is deliberate and tested (XC-14: the handler must sit
    outside the user middleware stack so an exception raised *in* that stack
    still produces the envelope), so the fix is to add the headers here rather
    than to move the handler inward.

    XC-12 names ``500`` among the error responses that must carry these
    headers, and the reason is concrete: without them a browser hands `fetch`
    an opaque network failure instead of a readable status and envelope body,
    so the frontend cannot tell a crash from an unreachable server.
    """
    origin = request.headers.get("origin")
    if not origin or origin not in ALLOWED_ORIGINS:
        # No ``Origin`` at all (a same-origin call, curl, the test client) or
        # one that isn't allowed. Emitting nothing is exactly what
        # ``CORSMiddleware`` does in the same situation; the browser is what
        # blocks the read.
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        # The response genuinely varies by request ``Origin``, so a shared
        # cache must not hand one origin's copy to another.
        "Vary": "Origin",
    }
