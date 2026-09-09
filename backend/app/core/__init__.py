"""Framework-agnostic application core.

Cross-cutting primitives that aren't tied to a single API resource — currently
just ``security`` (password hashing, JWTs, auth cookies, refresh-token
storage). Route modules under ``app/api/`` import from here; nothing here
imports from there.
"""
