"""HTTP layer — routers, request/response schemas, dependencies, middleware.

Kept deliberately empty of re-exports: importing ``app.api`` should never drag
in every router as a side effect. Import from the specific module
(``app.api.deps``, ``app.api.errors``) instead.
"""
