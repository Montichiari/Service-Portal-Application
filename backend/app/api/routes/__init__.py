"""One router per resource, mirroring ``app/db/models``' one-model-per-file rule.

Each module here exposes a ``router`` carrying its own resource prefix
(``/auth``, ``/service-requests``, ...). The ``/api/v1`` prefix from XC-1 is
applied once, where the routers are mounted in ``app/main.py``'s
``create_app()`` — never spelled into an individual route path
(backend/CLAUDE.md).
"""
