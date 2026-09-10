"""Pydantic request/response schemas, one module per resource.

The split mirrors ``app/api/routes/`` (backend/CLAUDE.md): ``auth.py`` here
serves ``routes/auth.py``, and so on. Nothing is re-exported from this
``__init__`` — unlike ``app/db/models``, which re-exports so that one import
registers every model on ``Base.metadata``, these have no such side effect to
centralise, and importing every resource's schemas to reach one of them would
only invite cycles as the API grows.

SQLAlchemy models are never used as response models directly: a ``User`` row
carries ``password_hash``, and AUTH-5 says no response body contains it ever.
The response schemas here are what enforces that.
"""
