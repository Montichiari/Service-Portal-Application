"""The chat assistant: FAQ config, tool definitions, tool execution and the
conversation it all hangs off (specs/chatbot/, Phase 5).

Split from ``app/api/`` deliberately. The routes in ``app/api/routes/chat.py``
are thin — read the body, resolve the caller, hand off, return the reply — and
everything that is actually *about* the assistant lives here, where it can be
exercised without an HTTP request. That matters more than usual for this
feature: the one dependency that cannot be pinned down (the model itself) is
reached through a single seam in ``client.py``, so the rest stays as
deterministic as the rest of the codebase.
"""
