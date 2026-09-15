# Chat / AI assistant phase — requirements

EARS-style, ID-traceable to `design.md`.

## Conversations & messages

- **CHAT-1**: When an authenticated user sends their first `POST /chat/messages`, the system shall
  create that user's `chat_conversations` row (get-or-create); subsequent calls reuse the existing
  row rather than creating a new one.
- **CHAT-2**: `POST /chat/messages` and `GET /chat/messages` shall take no conversation id — both
  always operate on the authenticated user's own conversation, so there is no cross-user id to
  validate or leak.
- **CHAT-3**: When a user posts a message to an existing conversation, the system shall persist the
  user's message to `chat_messages` before calling the Messages API.
- **CHAT-4**: The system shall include the conversation's history in every call to the Messages
  API, capped at 20 messages, choosing the earliest legal start point inside that cap rather than
  a naive most-recent-20 slice — a slice can land between a `tool_use` block and its paired
  `tool_result`, which the Messages API rejects outright. Formatted as the stored content-block
  array — design.md §10 decision 5.
- **CHAT-14**: `POST /chat/messages` shall enforce a maximum message length of 4000 characters
  (design.md §10 decision 6) to bound cost and misuse.

## Tool definitions & execution

- **CHAT-5**: The system shall define `input_schema` (JSON Schema) for `create_service_request`
  and `get_request_status`, matching design.md §4. No `search_faq` tool — FAQ content is answered
  from system-prompt content (CHAT-12).
- **CHAT-6**: When the Messages API response's `stop_reason` is `tool_use`, the system shall
  execute the corresponding internal service-layer function for each `tool_use` block before
  sending a follow-up request.
- **CHAT-7**: Tool execution shall always use `current_user.id` from the authenticated session as
  the acting/owning user; any identity-shaped argument produced by the model shall be ignored.
- **CHAT-8**: If tool execution fails (invalid arguments, resource not found), the system shall
  return a `tool_result` block with `is_error: true` and a safe, non-leaking error message rather
  than failing the whole request.
- **CHAT-9**: `get_request_status` shall follow the same scope as `GET /service-requests/{id}`:
  admins may look up any request, regular users only their own.
- **CHAT-11**: The system shall repeat the call → execute → follow-up loop until the API returns
  `stop_reason: end_turn`, and shall return only the final assistant text to the frontend.
- **CHAT-19**: The loop in CHAT-11 shall stop after `MAX_TOOL_ROUNDS = 5` rounds of tool
  execution (six Messages API calls maximum per user message); on exhaustion, the system shall
  return a fixed reply and log the conversation id, rather than raising or looping indefinitely.
- **CHAT-21**: When a user's message contains an explicit request to file or open a ticket, the
  assistant shall call `create_service_request` on that turn rather than asking a clarifying
  question first. Priority is never a valid reason to ask — it defaults to `medium` when not
  specified, since it is always judgeable from the description and always changeable afterward. A
  problem report _without_ an explicit filing request may still prompt one round of troubleshooting
  before offering to file (unchanged FAQ-style behavior). Found via eval instability (T-CHAT-1):
  two consecutive runs failed in different places because the system prompt's "try troubleshooting
  first" instruction and the tool argument description's "ask if priority is unclear" instruction
  competed with an explicit user request, with no rule to break the tie.

## Persistence

- **CHAT-10**: The system shall persist every content block exchanged (user text, assistant text,
  `tool_use`, `tool_result`) to `chat_messages`, in order, so `GET /chat/messages` can fully
  reconstruct the conversation.

## FAQ

- **CHAT-12**: FAQ content shall be sourced from a static, version-controlled config, never a
  database table. Fixed at 10 IT-support entries (design.md §7, decision 4); no `search_faq` tool
  and no entry-count-based switching mechanism.
- **CHAT-20**: The system prompt shall state that the FAQ content is the assistant's complete FAQ
  knowledge; for a question outside those 10 entries, the assistant shall say it doesn't have
  specific guidance and offer to log a ticket, rather than improvising generic troubleshooting
  advice.

## Auth & rate limiting

- **CHAT-13**: The chat message endpoint shall require the same authentication as every other
  protected endpoint (httpOnly cookie, existing `get_current_user` dependency) — no separate auth
  path for chat.
- **CHAT-18**: Rate limiting on the chat message endpoint is deferred to the Phase 6 hardening
  pass, consistent with how `/auth/login` rate limiting was deferred — flagged here rather than
  silently dropped, since each message is a real, metered API call.

## Frontend

- **CHAT-15**: The chat widget shall be mounted at the application-shell level so it persists
  across route navigation.
- **CHAT-16**: The widget shall show a distinct pending/typing state while a message is in flight.
- **CHAT-17**: A failed chat request (network error, 5xx) shall surface a retryable error state in
  the widget without losing the user's typed message.

## Coverage note

All of design.md §10's decisions are settled (1 through 8; decisions 1 and 8 both went through a
revision that was itself later corrected — see their status text for what changed and why).
CHAT-19, CHAT-20, and CHAT-21 were all added after implementation surfaced something the original
requirements didn't cover: an undocumented tool-loop ceiling, the FAQ grounding boundary, and —
found only through repeated live eval runs, not deterministic testing — a real tie-breaking gap
between "troubleshoot first" and an explicit filing request. Same pattern each time, the same way
`T-SR-0`'s findings added `SR-14`/`SR-15` mid-implementation: build first, the spec catches up
with what was actually learned, not the other way around. `T-CHAT-1` is complete as of this
revision — all of Phase 5's chat feature is now built and live-verified end to end.
