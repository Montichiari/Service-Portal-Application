# backend/CLAUDE.md

Read `specs/backend-phase/design.md`, `requirements.md`, and `tasks.md`
before writing any ORM-phase code, and `specs/api-phase/design.md`,
`requirements.md`, and `tasks.md` before writing any API-phase code. This
file holds conventions that apply across every task and every `/clear`
reset — don't re-derive them.

## ORM style

SQLAlchemy 2.0 typed declarative style only: `Mapped[...]` /
`mapped_column(...)`. Never the legacy `Column(...)` style, even in code
you're only skimming for reference elsewhere in the repo.

Every model imports `Base` from `app/db/base.py` and the relevant mixin(s)
from `app/db/mixins.py`. Never redefine `Base`, the naming convention, or
a mixin inline in a model file — if a mixin doesn't fit a table, that's a
signal to add a plain column on that one model, not to modify the shared
mixin (see `design.md`'s mixin applicability table).

## Model file structure

One model per file under `app/db/models/`, filename matching the table
name singular (`user.py` → `User`, `service_request.py` →
`ServiceRequest`). Import models from other files by string reference in
`relationship(...)` calls (`relationship("ServiceRequest", ...)`), never
by direct Python import across model files — avoids circular imports
given how interconnected this schema is.

`app/db/models/__init__.py` re-exports every model
(`from app.db.models.user import User`, etc., one line per model). Any
code that needs "every model registered on `Base.metadata`" — most
notably `alembic/env.py` — imports from this `__init__.py`, not from
each model module individually. When a new model is added, updating
`__init__.py` is part of that task, not a separate follow-up — a model
missing from `__init__.py` won't register on `Base.metadata` and won't
show up in autogenerate diffs, silently.

## Constraints

Enum-like columns (`role`, `priority`, `request_type` if it ever gets
constrained) are `VARCHAR` + `CheckConstraint` in `__table_args__`, never
a native Postgres `ENUM` type. This is a locked decision, not a default —
don't "improve" it to an `ENUM` even if it looks cleaner; `ENUM` alter is
a genuine operational cost that varchar + check avoids.

## Foreign keys

Every FK's `ondelete=` must match `design.md`'s ON DELETE table exactly.
When a `relationship()`'s FK uses `CASCADE`, pair it with
`passive_deletes=True`.

When two FKs on the same table point at the same target table (e.g.
`service_requests.requestor_id` and `assignee_id`, both → `users.id`),
every `relationship()` on both sides must pass an explicit
`foreign_keys=` argument. SQLAlchemy cannot infer which FK a relationship
means once there's more than one candidate — this fails at mapper
configuration time, not at import time, so it can pass a casual read and
still be broken. Confirm by actually instantiating the model, not by
inspection alone.

## Migrations

`alembic revision --autogenerate` only after all models for a given task
group are written — read `tasks.md` for which task groups are meant to
produce one migration together vs. separately.

Never run `alembic upgrade head` as part of generating a migration. The
generated file is a review checkpoint: present it and stop. Applying it is
a separate, explicit step the person takes after reviewing.

No new migration is expected anywhere in the API phase — every model the
API layer needs already exists from the ORM phase (the one candidate
addition, a `ticket_number` column, was decided against — see
`specs/api-phase/design.md §0`). If a task seems to need a schema change,
stop and flag it rather than assuming one is in scope. Confirmed through
`T-SR-0`: no model changed and no migration was needed.

## API-phase conventions

The sections below apply to `specs/api-phase/tasks.md` work. The ORM-phase
sections above still apply wherever they're relevant (model conventions
don't change because a new phase started) — these are additions, not
replacements.

### Route organization

One router per resource under `app/api/routes/`, mirroring the "one model
per file" rule above: `auth.py`, `statuses.py`, `service_requests.py`,
`comments.py`, `status_changes.py`. Each router is mounted in
`app/main.py` with its `/api/v1` prefix — never hardcode the prefix inside
an individual route path.

Pydantic request/response schemas live in `app/api/schemas/`, one file per
resource, matching the router split — not inline in the route files, and
not reusing SQLAlchemy models directly as response models (a `User` ORM
model has `password_hash`; a response schema must not).

Two schema modules are shared rather than resource-owned, because more
than one router needs them: `app/api/schemas/user.py`'s `UserSummary`
(embedded as `requestor`, `assignee`, `author`, `changed_by`) and
`app/api/schemas/status.py`'s `StatusOut` (embedded on every
`ServiceRequest` and every `StatusChange`). Import them; never redefine
either inside a resource's own schema file. The paginated `Page[T]`
envelope from `XC-10` lives in `app/api/schemas/common.py` as a generic
model — one envelope, not one per resource.

### Error envelope

The envelope shape is fixed by `specs/api-phase/design.md §1` and
`requirements.md XC-4`:

```json
{ "error": { "code": "...", "message": "...", "fields": {...} } }
```

Implemented via FastAPI exception handlers registered once in
`app/main.py`'s `create_app()` — never per-route `try/except`
reconstructing this shape by hand. If a new error case needs a new
`code`, add it to the `code` enum documented in `design.md §1`'s error
table and update that table in the same change; don't invent an
undocumented code inline in a route.

**Three handlers are required, not one**: `RequestValidationError` (→
`422`, `XC-4`), framework-raised `HTTPException` including an unmatched
route (→ envelope-wrapped, still `XC-4`), and a true catch-all for any
other unhandled exception (→ `500`/`INTERNAL_ERROR`, `XC-14`). The third
is the easiest to forget because nothing exercises it in normal
development — routes don't throw arbitrary exceptions on purpose — but
it's the one that matters most for never leaking a stack trace or an
internal error message to a client. The catch-all must still log the full
traceback server-side: suppressed for the client, not suppressed for the
operator.

**The trap worth knowing about** (`XC-15`, found reviewing `T-AUTH-2`):
`response_model` filtering and error handling are the same security
boundary, and only one of them looks like it. If serialization against a
`response_model` fails, FastAPI's `ResponseValidationError` carries the
offending value in its own message — and that value is precisely the
field `response_model` existed to exclude (a `User` row's
`password_hash`, say). A `500` handler doing `str(exc)` turns a careful
exclusion into a live leak, via a path no success-path test ever touches.
Never render an exception's own text into a response body. When you write
an exception-origin test, cover all four origins — route body,
dependency, response serialization, middleware stack — not just the
obvious one.

### App construction

`app/main.py` exposes a `create_app()` factory (built in `T-AUTH-2`) —
tests construct the app through this factory too, so a test run exercises
the actual app the server runs, not a hand-assembled lookalike that could
silently drift from it (missing a middleware registration, wrong handler
order). Never construct a second `FastAPI()` instance elsewhere "for
tests" or "for a script."

### Auth dependencies

`get_current_user` and `require_role(role)` live in `app/api/deps.py`,
built once in `T-AUTH-2`, and every protected route imports them from
there — never re-implements cookie-reading or role-checking inline. A
route that needs "any authenticated user" depends on `get_current_user`;
a route that needs a specific role depends on `require_role("admin")`,
which itself depends on `get_current_user` (compose, don't duplicate the
check). `require_role` is rank-based against the two-role hierarchy
(`user` < `admin`), not exact-match — an admin passes a
`require_role("user")` gate, matching `XC-6`'s "minimum required role"
wording.

**`get_current_user`'s source of truth**: loads the full user row from the
database on every protected request rather than trusting the JWT's `role`
claim alone (`requirements.md XC-13`) — decided during `T-AUTH-2`,
reversing `design.md`'s original zero-DB-hit rationale on purpose. The
token's signature/expiry check still happens first as a cheap pre-filter;
the DB row is the final word on `role` and on whether the user is still
active or exists at all.

**Every new protected route needs its own `401`-when-unauthenticated
test**, even though `XC-5` was proven generically in `T-AUTH-2`. A route
declared without its auth dependency still passes every test that uses an
authenticated client, and it will only break by side effect if the
handler happens to need the user object for something else — which is
true of the scoped service-request routes and _not_ true of routes where
the user is used only for a visibility check. Assert the gate directly
rather than relying on it failing indirectly.

### Cookies and JWT

Cookie-setting and JWT encode/decode helpers live in `app/core/security.py`
(built in `T-AUTH-1` — pick one module and keep it there, don't scatter
`jwt.encode` calls across route files). Lifetimes (1 hr access / 30 day
refresh) and cookie attributes (`httpOnly`, `Secure`, `SameSite=Lax`) are
constants defined once in that module, referenced everywhere — changing a
lifetime should be a one-line diff, not a grep-and-replace across routes.
`clear_auth_cookies` lives alongside the setters, same module — logout
needs matching attributes to actually clear a cookie, and that's the same
concern as setting one.

**Boundary with `app/config.py`**: genuinely environment-specific values
(`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `FRONTEND_ORIGIN`) stay in
`config.py`/`.env`. Everything that's a project-wide constant regardless
of environment (lifetimes, cookie attributes, `MAX_PASSWORD_BYTES`) lives
in `security.py` instead — `config.py` is for "differs per environment,"
not "differs per developer's preference for where to put a number."

Password hashing uses `bcrypt` directly, not `passlib[bcrypt]` — passlib
1.7.4 is unmaintained and its backend probe breaks against bcrypt ≥4.1
(raises `ValueError` on every hash call). Found and documented in
`security.py`'s docstring during `T-AUTH-1` — don't reintroduce passlib
later without knowing this.

`security.py` exports `MAX_PASSWORD_BYTES = 72` (bcrypt's hard limit).
`hash_password` raises rather than silently truncating an over-long
password — truncation would make every password sharing a 72-byte prefix
interchangeable, which is worse than rejecting it. Any register-schema
validation against this limit imports the constant; it is never
re-hardcoded as a literal `72` a second place.

**Known gap, not blocking dev/demo work**: `.env`/`.env.example` currently
ship the placeholder `JWT_SECRET_KEY=change-me-to-a-long-random-secret`.
Fine for local development; every token is signed with a value that's
committed to the repo, so this must be rotated to a real secret before any
real deployment.

Refresh tokens are never stored or logged raw — only `token_hash` (matching
the existing `refresh_tokens.token_hash` column). If you find yourself
about to log a raw token "just for debugging," don't; log the `id` or
`jti` instead.

### CSRF header check

The `X-Requested-With` check (`requirements.md XC-9`) is FastAPI middleware
registered in `app/main.py` via `create_app()`, applied to every
state-changing request — not a per-route dependency. It checks header
_presence_, any value, not an exact string — pinning to `XMLHttpRequest`
specifically would only break compatible clients for no security benefit.
`GET`, `HEAD`, and `OPTIONS` are exempt (`OPTIONS` because it's the
browser's CORS preflight, which can't carry a custom header). It runs
_before_ auth checks — a request failing CSRF never needs its cookie
inspected.

### CORS

`FRONTEND_ORIGIN` (from `app/config.py` — environment-specific, same
boundary as `JWT_SECRET_KEY`) is the sole allowed origin in FastAPI's
`CORSMiddleware`, with `allow_credentials=True`. Never widen this to a
wildcard `*` — CORS itself forbids combining a wildcard origin with
credentials, so it isn't even a valid shortcut, just a broken one. Wired
in `T-AUTH-3` (`XC-12`), not `T-AUTH-2` — it's backend-only but has no
consumer until the frontend client exists.

**Verify this covers error responses too**, not just `2xx` — a common
`CORSMiddleware` ordering mistake exempts error responses from getting
CORS headers, in which case the browser reports a `401`/`403`/`422`/`500`
to `fetch` as an opaque network failure instead of a readable response.
Test a failing cross-origin request explicitly; don't infer it from a
passing success-path test.

**The `500` path is a documented exception** (`T-AUTH-3`): Starlette hangs
the `Exception` catch-all off `ServerErrorMiddleware`, the outermost
layer, so that response never passes back through `CORSMiddleware`. The
handler therefore attaches CORS headers itself via `app/api/cors.py`,
using the same origin allow-list. **Don't "fix" this by moving the
exception handler inward** — it would gain CORS automatically but lose
`XC-14`'s tested guarantee that exceptions raised inside the middleware
stack are still caught. The current arrangement is the resolution of a
real tension between two requirements, not an oversight.

### OpenAPI

The served document is post-processed by `app/api/openapi.py`, wired in
`create_app()` (T-DOCS-0). FastAPI's own derivation gets three things wrong
or missing here — it documents `{"detail": [...]}` where
`register_exception_handlers` actually sends design.md §1's envelope, it
cannot see a cookie read off the raw `Request`, and it cannot see a CSRF
check that runs in middleware ahead of routing — so the fix is one pass over
the generated document rather than an annotation on each route.

**A new route gets its structural error statuses for free and must not
restate them.** `401` (behind `get_current_user`, at any dependency depth),
`403` (any non-`GET`/`HEAD`/`OPTIONS` method, and any `require_role` gate),
`404` (any path parameter), `422` (wherever one is genuinely reachable) and
`500` (everywhere) are derived from the route's own dependency tree and path.
Same reasoning as the CSRF check being middleware: the one route that forgot
to opt in would be the one that mattered.

What a route *does* declare, in its decorator:

- `summary=` — one line, always.
- `responses={<status>: {"description": "<cause fragment>"}}` for any error
  the structure can't imply: AUTH-2's `409`, AUTH-7's `401`, CM-7's `403`.
  The description is a **sentence fragment naming the cause**, not a
  sentence — `openapi.py` renders it, and composes it with the structural
  reasons for the same status rather than replacing them.
- A `responses=` entry *with* `content` if the response genuinely isn't the
  envelope. `/health`'s `503` is the only one: it is a plain
  `JSONResponse` built in the handler, so it never reaches the exception
  handlers, and documenting it as an envelope would be the same untruth this
  whole pass exists to remove. (It was `/health/db`'s `503` until T-DO-0
  merged the two probes into one `/health` — DO-22.)

Two things to know before touching it. **Every pass must stay idempotent** —
it mutates FastAPI's cached document in place, so a second call must not
append a second `X-Requested-With` parameter or re-render a description onto
itself. That is why route-declared fragments are read off `route.responses`
and never off the operation the pass has already rewritten; reading them back
silently dropped AUTH-2's `409` wording on the second pass, and was stable
from the third on, which is the kind of defect a test comparing two late
passes cannot see. And **`backend/openapi.json` is generated, never
hand-edited**: regenerate with `python -m app.api.openapi` from `backend/`,
which `tests/api/test_openapi.py` pins against the served document.

### Email handling

Email addresses are case-folded to lowercase through a single shared
`normalize_email` function, applied on both storage and lookup
(`AUTH-17`). Never fold at one and not the other, and never inline the
`.lower()` call at a call site — Postgres' unique index compares exactly,
so a single unfolded path silently creates duplicate accounts that differ
only in case.

`requirements.txt` includes `email-validator` (Pydantic's `EmailStr`
requires it as an optional extra). Note that it rejects `.test` as a
reserved TLD, so API tests use `@example.com` addresses rather than the
DB fixtures' `@example.test`.

### List endpoints

Every list endpoint follows the same four rules, established in `T-SR-0`
and reused by Comments (`CM-1`) and status changes (`SC-1`):

1. **Visibility scoping goes in the `WHERE` clause**, of both the item
   query and the `COUNT` query — never a post-fetch filter in Python. A
   post-fetch filter leaks rows into memory, makes `total` count rows the
   caller can't see, and returns pages shorter than `page_size`.
2. **The `COUNT` query carries every predicate the item query does** —
   scope _and_ filters. A count that applies scoping but not filtering
   passes every item-level assertion and breaks only `total`.
3. **Eager-load every embedded relationship.** `status`, `requestor`,
   `assignee`, `author`, `changed_by` are all many-to-one, so
   `joinedload` is correct and safe alongside `LIMIT` (a to-one join
   can't multiply parent rows — that hazard belongs to to-many
   relationships, where `selectinload` is the right tool). Lazy loading
   here is an N+1: `1 + 3n` queries for a page of `n`.
4. **Ordering must be total.** `ORDER BY` on a non-unique column alone
   gives Postgres no stability guarantee between calls, so a paging user
   can see one row twice and miss another. Always add a unique tiebreaker
   (`created_at DESC, id DESC` — `SR-15`).

Where a filter's valid value set is **static in code** (`priority`), let
the validation layer enforce it with a `Literal` query param and get the
`422` for free. Where the valid set **lives in the database**
(`status`, a lookup table), resolve the supplied value against that table
at request time and raise the `422` yourself — hardcoding an enum for it
would silently drift from the seeded rows.

`XC-11` **clamps** an oversized `page_size` rather than rejecting it, so
`Query(le=100)` is wrong here: it produces a `422`. Use `ge=1` and clamp
in the handler. `page` uses `ge=1`, and a `422` for `page=0` is intended.

`XC-7` requires "malformed id", "no such row", and "exists but not
yours" to be externally indistinguishable. Typing a path param as `UUID`
breaks this — FastAPI raises a validation error before the handler runs
and returns `422` instead of `SR-13`'s `404`. Accept the param as `str`,
parse it in the handler, and treat a parse failure exactly like a miss.
Assert the three responses are byte-identical, not merely same-status.

### Visibility checks on nested resources

Any route whose resource sits under a visibility-gated parent (comments
and status-changes under a service request, per `CM-4`/`CM-9`,
`SC-2`/`SC-8`) resolves that parent's visibility through the shared
`app/api/visibility.py` module (`_visibility_conditions`/`_parse_uuid`/
`_load_visible`, extracted in `T-CM-0` from `service_requests.py`) —
never a second copy of the predicate. `SR-12`'s scoping logic is the
single source of what "visible to this caller" means; every nested
resource must match it byte-for-byte, since a route that quietly drifts
from it either leaks a request to someone who shouldn't see it or hides
one from someone who should.

**Wire it as a dependency, never as the first statement in the handler
body.** FastAPI validates a declared request body during parameter
binding, ahead of any code inside the handler, regardless of what that
code checks first. A visibility check placed as the handler's first line
therefore runs _after_ body validation, so a malformed body sent to an
invisible parent returns `422` instead of `404` — breaking `XC-7`'s
guarantee that an invisible resource is indistinguishable regardless of
what else is wrong with the request. Only a `Depends()`-resolved check
runs early enough to preempt this. Found and pinned by a dedicated test
in `T-CM-0` (`test_create_404_precedes_body_validation`) — write the
equivalent for `T-SC-0`'s `POST` route, which has the identical shape.

**The same precedence applies against a role check, not only against body
validation.** `T-SC-0` hit a genuine conflict: `SC-4` says a `user`-role
caller posting a status change gets `403`; `SC-8` says an invisible
parent gets `404`. For a `user`-role caller posting to a parent they
can't see, both apply and only one status can be sent. Keep the
visibility dependency ordered ahead of the role gate, so that overlapping
case answers `404`, not `403` — a `403` there would itself confirm the
resource exists, which is exactly the leak `XC-7` exists to close.
`SC-4`'s `403` still governs its own case: a `user`-role caller posting
to a request they genuinely can see. The general rule this generalizes
to: **visibility is ordered ahead of every check that could leak a
resource's existence, not just body validation — role gates are one
instance of that, not the whole list, and a future nested resource may
introduce another.** Pinned by
`test_user_posting_to_an_invisible_parent_gets_the_visibility_answer` —
worth knowing this is currently the only test protecting the ordering,
since swapping the two dependencies breaks nothing else.

## Chat-phase conventions

The sections below apply to `specs/chatbot/tasks.md` work. Everything
above still applies — a new phase does not change how models, routes,
schemas or tests are written. Read `specs/chatbot/design.md`,
`requirements.md` and `tasks.md` before writing any chat code.

### The model is untrusted input

`specs/chatbot/design.md §5` puts model output on the same footing as a
request body, and CHAT-7 makes it testable rather than a habit. Two rules
follow, and neither is negotiable in a later task:

- **No tool handler takes an identity argument.** `execute_tool` is
  handed the `User` that `get_current_user` resolved and passes that;
  a `user_id`, `assignee` or `role` in the model's `input` object reaches
  a schema that has no such field and ignores unknown keys. If a tool
  ever genuinely needs to act on another user, that is a new requirement
  with its own role gate, not an argument.
- **Every tool calls the code the equivalent endpoint calls.** Creation
  goes through `app/services/service_requests.py`; the status lookup
  goes through `app/api/visibility.py`. Not a predicate that agrees with
  them — the same function. A visibility rule with two implementations
  is how one of them is tightened later and the other quietly is not,
  and here the copy would be the one facing a component that can be
  talked into asking for anything.

### `app/services/`

Created in `T-CHAT-0` because tool execution needed the insert `POST
/service-requests` performs and not a copy of it. It is **not** a layer
every route now routes through: a read that is a query plus a response
model stays in its router. A function moves here when a second caller
appears, not in anticipation of one.

The chat code must never import a route module to reach a helper — same
reason `visibility.py` exists as its own module rather than living in
`routes/service_requests.py`.

### The model client seam

`app/chat/client.py` holds the `ChatModelClient` protocol, the
`ModelResponse` shape and the `get_model_client` dependency, and contains
no SDK import at module scope, no HTTP and no `ANTHROPIC_API_KEY`. That is
the line `tasks.md` splits `T-CHAT-0` from `T-CHAT-1` at, and it is what
lets the whole feature be tested deterministically: tests override the
dependency with a stub returning fixed payloads
(`tests/api/test_chat.py`), never by monkeypatching a module attribute.

`T-CHAT-1` filled the seam without moving it. Everything vendor-specific —
the SDK import, the key, the model id, the token ceiling, the timeout, and
the conversion from typed blocks back to plain JSON — lives in
`app/chat/anthropic_client.py`, and `client.py` reaches it through an
import *inside* `_cached_client`'s body. Keep it there: a module-scope
import would make the protocol, the loop and every stubbed test depend on
the `anthropic` package being installed, and a module-level client object
would turn an unset key into a failure to start the application rather
than a failure of one route.

**The provider is a config value, not a code path.** One SDK client class
(`Anthropic`), with `base_url` passed when `ANTHROPIC_BASE_URL` is set and
`None` when it is not. The Foundry deployment is wire-compatible down to
the auth header — `x-api-key`, same as the direct endpoint — verified
against the live resource in `T-CHAT-1`, so there is no `AnthropicFoundry`
branch and nothing provider-specific to keep in step. Don't add one back
on the strength of a `401`: that symptom is a credential, not a transport
(it was, in `T-CHAT-1`, and cost a wrong hypothesis that reached the spec
before being corrected).

### Nothing under `tests/` may call a real model

Two mechanisms, and both are load-bearing:

- The live tests and the eval set live in `backend/evals/`, outside
  `pytest.ini`'s `testpaths`, so `python -m pytest` never collects them.
  Run them deliberately with `python -m pytest evals -q -s`; every run is
  billed. A marker would not have been enough — it leaves the tests one
  `-m` flag away from running in CI.
- `tests/conftest.py`'s autouse `_no_live_model` fixture unsets
  `ANTHROPIC_API_KEY` for every test in the suite, so a test that reaches
  `POST /chat/messages` without overriding `get_model_client` raises
  `ModelClientNotConfiguredError` instead of placing a call. The
  dangerous test is never the one someone puts in the wrong directory —
  it is the one that already existed and quietly started making real
  calls when `get_model_client` stopped raising.

A test that genuinely needs a client sets the key back through
`monkeypatch` and builds one without calling it
(`tests/chat/test_model_client.py`). If you ever share fixtures the other
way, import them by name: a `from tests.conftest import *` inside
`evals/conftest.py` would drag that autouse fixture in and leave the evals
skipping with "no key configured" while `.env` plainly has one.

### The history cap is not a slice

`CHAT-4`'s "most recent 20 messages" is implemented by
`conversation.history_window`, not by `messages[-20:]`. The Messages API
rejects a history whose first message carries a `tool_result` whose
`tool_use` was trimmed away, and in a tool-using conversation roughly half
the cut points do exactly that — so the naive slice fails the whole
request, and only once a thread is long enough to be trimmed. The window
is the earliest legal starting point inside the cap. Any future change to
what gets replayed has to preserve that property, and
`tests/chat/test_history_window.py` starts by proving its own fixture is a
case where the two implementations actually differ.

`ModelResponse.content` is the raw content-block array, stored and
replayed verbatim. Do not parse it into typed objects on the way in — a
conversion is where a block type this code has not heard of gets dropped,
and `chat_messages.content` exists to be replayable, not readable.

### Content blocks and roles

The Messages API has no `tool` role. A `tool_use` block rides inside an
**assistant** message and its `tool_result` inside the next **user**
message; `chat_messages.role` is `CHECK`-constrained to those two, and
the ordering between them is load-bearing rather than cosmetic — the API
rejects a `tool_result` that does not follow its `tool_use`.

**`chat_messages.created_at` defaults to `clock_timestamp()`, not
`now()`**, and this is the one place in the schema that differs. `now()`
is `transaction_timestamp()` and does not advance inside a transaction;
this is the only table that appends several rows per unit of work, so
under `now()` every row of a turn would share a timestamp and
`ORDER BY created_at` would fall through to a random-UUID tiebreaker.
Do not "regularise" it to match the other tables.

### Anything a tool writes is stored and re-sent

Every `tool_result` is persisted to `chat_messages` and replayed to the
model on every subsequent call of that conversation. So a tool's error
text is subject to the same rule as XC-4's envelope and for a sharper
reason — the audience is a model that will read the string to the user:

- Argument errors render Pydantic's `loc` and `msg` only, never `input`
  or `ctx`.
- The catch-all message is content-free; the traceback goes to the log.
- An invisible or missing request produces one message for all three of
  malformed id, no such row and someone else's row (XC-7).

### A new migration *is* expected in this phase

The API phase's "no new migration" note does not apply here: `T-CHAT-0`
added `chat_conversations` and `chat_messages`. The rule that still holds
is the one above it — generate the revision, present it, and let applying
it be a separate explicit step. The test suite migrates its own database,
so a green run is not evidence that the dev database was touched.

### Testing chat code

- **Never assert on model phrasing.** design.md §11 splits this in two:
  deterministic tests drive the endpoint with a fixed tool-call payload
  (all of `tests/api/test_chat.py`), and model-in-the-loop evals assert an
  expected *tool choice*, not an expected reply, and run occasionally
  rather than on every push.
- `tests/chat/` needs no database, like `tests/core/`. Keep it that way —
  a FAQ or tool-schema test that reaches for Postgres is arguing against
  its own subject.
- Test module basenames must be unique across the whole suite (there are
  no `__init__.py` files in `tests/`), which is why the schema contract
  test for these tables is `tests/db/test_chat_tables.py` and not
  `test_chat.py`.
- Adding a route changes the generated document: regenerate
  `backend/openapi.json` with `python -m app.api.openapi`, and expect the
  four route-count pins in `tests/api/test_openapi.py` to need updating.

## Testing

Contract tests (R10, ORM phase) run against a real Postgres test database —
never SQLite. SQLite silently accepts values a `CHECK` constraint should
reject and has no native `JSONB`, so a green SQLite test can pass while the
real schema is broken. If you catch yourself reaching for an in-memory
SQLite engine "to keep tests fast," that's the wrong trade for this
project — correctness against the actual constraint set matters more here
than test runtime. This applies to API-phase tests too — an endpoint test
against SQLite proves less than it looks like it proves.

Every test lives in a transaction rolled back at teardown (the
`db_session` fixture — originally `backend/tests/db/conftest.py`, scoped
to that package only), never manual row deletion. When adding a new
constraint-enforcement test, verify it can actually fail: temporarily
comment out the constraint, confirm the test goes red, then restore it. A
constraint test that has never been observed to fail is not verified,
only written.

**This rule has now caught a real defect eight times across this project**,
in eight different disguises: a tamper test that corrupted a token's
encoding rather than its meaning, so it failed before reaching the check
it named (`T-AUTH-1`); a cookie-expiry assertion that computed its
expected value from the constant under test, so changing that constant
kept it green (`T-AUTH-3`); a Playwright route handler that read a shared
counter back after an `await`, so the delay it existed to impose never
applied (`T-DEBT-3`); an N+1 test that passed with every `joinedload`
removed, because its fixture shared a session with the code under test
(`T-SR-0`); a "no full reload" criterion whose visibility assertion alone
couldn't tell a correct append from a page reload that also ended with
the comment on screen (`T-CM-1`); and an atomicity test whose fixture
lived inside the same rollback savepoint the assertion was observing, so
it couldn't distinguish a correctly-scoped rollback from the whole test
tearing down anyway (`T-SC-0`); a loop-ceiling test whose six rounds were
driven by a `search_faq` payload, so deleting that tool would have left it
green while exercising the unknown-tool path instead of the loop it names
(`T-CHAT-0b`, logged there and never counted here until now); and a
history-window suite whose assertions would all have held against a
conversation that happened to be trimmable at a legal point, where the
correct and the broken implementation agree — fixed by making the fixture
prove it discriminates before anything else is asserted (`T-CHAT-1`). The
pattern underneath is always the
same — **the test passes, and would keep passing, without the thing it
names ever being true** — and reading the test never reveals it. Only
removing the subject and watching for red does. Apply this hardest to
tests involving timing, concurrency, or shared mutable state, where the
failure is invisible by construction.

### Session isolation in tests

**A test that shares a session with the code under test measures the
fixture, not the query.** SQLAlchemy's identity map hands back
already-loaded objects without emitting SQL, so a lazy load inside a
handler stays completely invisible when the test seeded its rows through
that same session. Production cannot reproduce this — `get_db` yields a
fresh session per request — which means the one condition keeping the
test green is the one condition the running app can never reach. Call
`expunge_all()` before any measured call, and read assertions back
through a different session than the one that wrote. Found in `T-SR-0`,
where the N+1 assertion held with all three `joinedload` calls removed.

This generalises past query counting: any assertion about _persistence_
has the same hazard. Reading a row back through the writing session may
be observing a pending in-memory object rather than a committed row.

**Homogeneous fixture data hides relationship growth independently of the
session.** If every seeded row points at the same requestor and the same
status, an N+1 self-limits at two queries no matter how many rows exist —
the second row's lazy load finds its target already in the identity map.
Fixture rows for any relationship-count test must vary across _every_
relationship being loaded: distinct requestors, distinct assignees,
statuses spread across all four seeded rows.

**Assert the statement count is constant, not small.** A threshold
assertion (`< 10 queries`) passes forever as long as the fixture stays
small, which is the same failure family as everything above. Measure the
same endpoint at two different row counts (3 and 15) and assert the
counts are _equal_. Count via a `before_cursor_execute` event listener.

**Fixture data feeding an atomicity or rollback assertion needs to be
committed independently, not created inside the same rollback machinery
the assertion is observing.** A parent row inserted directly via a
fixture lives in the test's own savepoint — the same one a sabotaged
write's failure unwinds — so "did nothing change" can pass vacuously
regardless of whether the code's atomicity logic works, since there's no
way to tell a correctly-scoped rollback from the whole test tearing down
anyway. Create that parent through the real API instead, so it's a real,
independently persisted base state the sabotaged write can fail against.
Found in `T-SC-0`'s two `SC-5`/`SC-6` atomicity tests, and the two are
complementary rather than redundant: sabotaging the history insert only
catches a handler that commits the parent update first, and sabotaging
the parent update only catches the mirror image — neither alone is
sufficient.

**A "shape"/contract test that seeds its own fixture directly, rather
than posting through the endpoint, can only prove serialization — never
that the write path populating those fields is correct.** Found when
`T-SC-0`'s mutation pass set `changed_by_id=None`: the dedicated shape
test stayed green because it never exercised the create endpoint at all.
Two other tests caught the mutation, so the suite held — but that
specific test's coverage of the field was always illusory. If a test is
meant to validate a response contract for data the endpoint itself
writes, create that data through the endpoint.

### Mutation passes

A mutation pass edits the working tree, so it needs a mechanical
end-of-pass check, not a remembered one. `T-SR-0`'s harness run was
killed mid-pass by a shell pipeline truncation and left a mutation
applied; the full suite happened to catch it, which is a good suite
rather than a control. Two rules:

- Apply mutations as revertible patches and assert a clean tree
  (`git diff --exit-code`) once the pass finishes. A defect committed
  because a harness run died mid-pass is far worse than any defect the
  pass was looking for.
- Never pipe a long harness run through a truncating command; write the
  output to a file and read the file.

**A mutation that fails to compile or import isn't a caught mutation** —
it hasn't tested anything about the suite, only confirmed Python's own
syntax checker works. Stripping a `Depends()` parameter can easily leave
a non-default parameter after a defaulted one, which is a `SyntaxError`,
not a semantic change. If applying a mutation produces invalid code, fix
it into valid code and re-verify it's caught by the right tests for a
semantic reason before counting it. Found in `T-SC-0`.

### API-phase additions

- `db_session` was promoted to a top-level `backend/tests/conftest.py`
  during `T-AUTH-2` (needed early for that task's own tests, not deferred
  to `T-AUTH-3` as originally planned). `_prepared_database` was made
  non-autouse in the same change specifically so `tests/core/` still runs
  with no Postgres available — verified against an unreachable DB URL.
  Keep that property: a change here that makes Postgres implicitly
  required for `tests/core/` again is a regression, not a simplification.
- Any test client used for cookie-based auth flows must use
  `base_url="https://testserver"`, never an `http://` base — the auth
  cookies are `Secure`, and `httpx` silently drops `Secure` cookies
  against a non-`https` base URL. This fails in a way that looks exactly
  like a broken auth flow, not a test-config problem, so get it right
  from the start rather than debugging it as a mystery.
- Auth-flow tests need a test client that persists cookies across calls
  within one test (register → login → authenticated call, as one
  sequence) — set this up once as a fixture in
  `backend/tests/api/conftest.py`, don't hand-roll cookie jars per test.
- When a test asserts an error response, assert against the full envelope
  shape (`error.code`, `error.message` presence, `error.fields` keys where
  applicable) — not just the HTTP status code. A `422` with the wrong
  `fields` key is still a contract violation even though the status code
  is right.
- A visibility test must be positively non-empty on both sides. "User A
  sees only their own" passes vacuously if both fixtures own zero rows —
  assert on specific ids and a non-zero count for each role.
- `SC-5`/`SC-6`'s atomicity requirement needs the same "verify it can
  fail" discipline as a constraint test — force the transaction to fail
  partway and assert _neither_ write landed, not just that the endpoint
  returned an error. Same applies to `SR-14`'s create-plus-history pair.
- `requirements.txt` includes `httpx2`, not `httpx` — this Starlette
  version's `TestClient` requires that specific package. Don't "correct"
  it back to `httpx` if you see it and don't recognize the name.
- **Never derive a test's expected value from the constant under test.**
  Found in `T-AUTH-3`: the cookie-expiry assertion computed its expectation
  from `ACCESS_TOKEN_TTL`, so changing that constant to 30 days left the
  test green — it asserted self-consistency, not correctness. Pin
  expectations to the literal values the requirement states
  (`3600`/`2592000` from `AUTH-6`), with a comment explaining why the
  constant deliberately isn't imported. Same failure family as a tamper
  test that passes for the wrong reason.

## Task workflow

One task from `tasks.md` per session (ORM phase or API phase, whichever is
current). Implement, verify against that task's acceptance criteria
checklist, stop — do not start the next task in the same session. `/clear`
before starting the next task.

## Non-goals — ORM phase (historical, complete)

- No API routes, no FastAPI path operations
- No Pydantic request/response schemas
- No auth logic (password hashing, JWT issuance/validation) — models only
- No seed data beyond the four `statuses` rows specified in `requirements.md`
- No application-level logic for setting `current_status_id` on insert

All of the above are now in scope — see Non-goals below for what's still
out of scope in the current phase.

## Non-goals — API phase (complete; still in force)

- No rate limiting on `/auth/login` — explicitly deferred
  (`specs/api-phase/design.md §7`)
- No email verification at registration
- No `PATCH /service-requests/{id}` — no frontend surface needs it yet
  (`specs/api-phase/design.md §7`)
- No assignment path of any kind. `assignee` is always `null` in this
  phase; there is no endpoint that sets it and none is to be added
  speculatively.
- No `?requestor_id=me` (or equivalent) on `GET /service-requests`.
  `SR-2` gives admins everything by design. The gap is real — an admin
  cannot scope the list to their own requests — but no designed frontend
  surface consumes it yet, so it arrives with its consumer, not before.
- No sort control and no free-text search on `GET /service-requests`.
  Order is fixed by `SR-15`; filters are `status` and `priority` only.
- No `request_type` values beyond `'general'`
- No admin-promotion endpoint — role changes remain a direct DB operation

## Non-goals — chat phase (current)

- No streaming (SSE). The endpoint is synchronous for this pass
  (design.md §9) — building streaming alongside tool calling mixes two
  new mechanisms at once.
- No multi-thread conversations, no `POST /chat/conversations`, no
  conversations list. One continuous conversation per user is decision 2,
  and the UNIQUE constraint on `chat_conversations.user_id` enforces it.
- No rate limiting on `/chat/messages` — deferred to Phase 6 (CHAT-18),
  consistent with `/auth/login`, and flagged rather than dropped because
  every message is a metered API call.
- No FAQ table, ever (CHAT-12). The content is a module.
- No optional `request_id` on `get_request_status` yet. design.md §4
  flags the refinement — a user asking about "my ticket from yesterday"
  has no id to hand — as a follow-up once basic tool calling works, not
  as part of this pass.
