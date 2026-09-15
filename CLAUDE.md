# CLAUDE.md

Read this first, before `backend/CLAUDE.md` or `frontend/CLAUDE.md`,
regardless of which directory a session is working in. This file's job is
orientation across phases — which phase is active, where its specs live,
and what the original brief actually asked for. Implementation
conventions (testing discipline, error envelope shape, component
patterns, and so on) live in the two phase-specific files below; nothing
here duplicates them, and nothing there should duplicate this.

## The original brief

`PROJECT_BRIEF.md`, verbatim, six phases, unedited since the project
started. Every phase's own `requirements.md` is a derivation of one
section of it. If a session needs to check whether current work still
satisfies what was originally asked for, that's the document to check
against — not the derived spec, which can itself have gaps the brief
wouldn't.

## Phase → spec map

| Brief phase                         | Spec directory          | Status      |
| ----------------------------------- | ----------------------- | ----------- |
| 1 — Foundations & Project Setup     | `specs/backend-phase/`  | Complete    |
| 2 — Frontend Development            | `specs/frontend-phase/` | Complete    |
| 3 — Backend Development             | `specs/api-phase/`      | In progress |
| 4 — DevOps & Cloud Deployment       | `specs/devops-phase/`   | In progress |
| 5 — AI-Powered Chat Integration     | `specs/chatbot/`        | In progress |
| 6 — Integration, Testing & Capstone | —                       | Not started |

Within an active phase, that phase's own `requirements.md` / `design.md`
/ `tasks.md` are the authoritative, checkable spec — this map exists so a
session can find them quickly, not to restate what's in them.

## Traceability against the brief

One row per requirement line in `PROJECT_BRIEF.md`, for phases that have
actually started. **Update this table as gaps close, and add a phase's
rows the day that phase starts** — don't let it go stale the way the
original requirements review did, which is the exact failure this table
exists to catch earlier next time.

Last verified against the running code on 2026-09-13 (branch
`feature/api-sc`): `backend` 267 pytest tests green against the
docker-compose Postgres, `frontend` 19 Playwright tests green against the
live stack, `npm run build` and `oxlint` clean, and the generated
`/openapi.json` read directly. Rows below say what was checked, not what
the task checklists claim — `specs/backend-phase/tasks.md` and
`specs/frontend-phase/tasks.md` still have 58 unticked acceptance boxes
between them despite both phases being complete and verified here, so
those checkmarks are not evidence in either direction.

### Phase 1 — Foundations & Project Setup

| Requirement                                                           | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Set up project structure (Frontend, Backend, Database)                | Done. `frontend/` (Vite + React 19 + TS), `backend/` (FastAPI + SQLAlchemy 2.0 + Alembic), `docker-compose.yml` (Postgres 16). One cosmetic gap: root `README.md` is a one-line UTF-16 stub containing only the repo name — the real setup instructions live in `backend/README.md` and `frontend/README.md`, and nothing at the top level points at them                                                                                                                                             |
| Design DB schema (users, service requests, comments, status tracking) | Done. All four concerns plus `statuses` (reference) and `refresh_tokens`, in `alembic/versions/7436359d2d5b` + the `80919378ee7a` seed. Verified live, not just read: `tests/db/` exercises every `CHECK`, all three `ON DELETE` behaviours, the four seeded status rows and an `upgrade head` → `downgrade base` round-trip against real Postgres                                                                                                                                                    |
| Configure local development environment                               | Done — Docker Compose Postgres (healthy, port 5433), `.env.example` in both app directories, per-directory READMEs. Confirmed end-to-end: `/health/db` answers `{"status":"ok","db":"connected"}` and both test suites run from a cold shell                                                                                                                                                                                                                                                          |
| Implement authentication and role definitions (User/Admin)            | **Partial — the previous "done at the schema level" reading was too generous.** The `role` column, its `CHECK`, and runtime enforcement (`deps.require_role`, `is_admin`, `ROLE_RANK`) all exist and are tested. What does not exist is any way to *create* an admin: `AUTH-4` makes `/auth/register` ignore a `role` in the body, and there is no promotion endpoint, no seed migration and no CLI. A freshly migrated database has zero admins and no supported path to one — `frontend/src/e2e/fixtures.ts` gets there by shelling `UPDATE users SET role = 'admin'` into the docker-compose container. Deliberate (`backend/CLAUDE.md` non-goals), but the brief's line is not met |

### Phase 2 — Frontend Development

| Requirement                                                                                               | Status                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Responsive UI (brief allowed React or Angular; React was used)                                            | Done, and responsive in substance rather than by virtue of importing Tailwind: `AppShell` collapses to an `aria-expanded` hamburger below `md`, `RequestsDashboardPage` drops three columns via `hidden md:table-cell` rather than maintaining a second stacked layout, filters reflow `flex-col` → `md:flex-row`, and `Table` wraps in `overflow-x-auto`                                                        |
| Pages: Login/Register, Submit Service Request, View Request Details, Track Request Status, User Dashboard | Done — all five, plus a not-found page, wired through `routes.tsx` (`/login`, `/register`, `/requests/new`, `/requests/:id`, `/requests/:id/status`, `/`) behind a `RequireSession` guard that distinguishes pending from signed-out                                                                                                                                                                             |
| Form validations and navigation                                                                           | Done. All five forms use `react-hook-form` + `zodResolver` against real schemas (`src/schemas/`), including cross-field password confirmation and a byte-length rule matching bcrypt's 72-byte limit; navigation is `react-router` `<Link>` throughout with a `*` catch-all                                                                                                                                      |
| _Deliverable: "UI integrated with mock data"_                                                             | Exceeded, not outstanding. The mock objects were replaced by real API calls during Phase 3 (T-SR-1 / T-CM-1 / T-SC-1); only two stale code comments still name them. 19 Playwright specs pass against the real backend, Postgres and `httpOnly` cookies — no mocked client anywhere                                                                                                                              |

### Phase 3 — Backend Development

| Requirement                                | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| REST APIs: Authentication                  | Done. `register` / `login` / `me` / `refresh` / `logout`, with bcrypt-12 hashing, 1 h access JWT + 30 d opaque refresh, rotation with reuse-detection family revocation, and uniform-timing login failure via a decoy hash                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| REST APIs: Service Request CRUD operations | Partial — **C and R only, across the whole resource family.** `POST` / `GET` list / `GET` detail on `/service-requests`; comments and status-changes are likewise create + list. No `PATCH` and no `DELETE` on any of the three. Two consequences beyond the missing verbs: `assignee_id` and `request_metadata` are columns in the schema and fields in `ServiceRequestOut`, but no endpoint can ever set either, so `assignee` is permanently `null`; and `request_type` is pinned to `'general'` in route code. `PATCH` and assignment are named non-goals in `backend/CLAUDE.md`; `DELETE` is still undecided in either direction                                                                                                 |
| REST APIs: Status updates and comments     | Done. `GET` / `POST /service-requests/{id}/status-changes` (admin-gated write, history insert and `current_status_id` update in one transaction) and `GET` / `POST /service-requests/{id}/comments` (internal comments filtered in the `WHERE` clause, on the page *and* the count)                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Integrate database                         | Done                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Security                                   | Mostly done, and stronger than the previous row credited: ownership is a `WHERE` clause rather than a post-fetch check, invisible rows 404 rather than 403, CSRF runs as middleware ahead of routing and body parsing, CORS is pinned to one origin with credentials, and `validation_error_fields` copies only `msg` so a rejected plaintext password cannot ride out inside `ctx`. Four open items: (1) `backend/.env`'s `JWT_SECRET_KEY` is byte-identical to `.env.example`'s `change-me-to-a-long-random-secret` (md5-verified), so every token this instance issues is forgeable by anyone who has read the repo; (2) no rate limiting or lockout on `/auth/login` (named non-goal); (3) no security response headers at all — no HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options` or `Referrer-Policy` middleware exists; (4) `COOKIE_SECURE = True` is a hardcoded constant, correct for production and fine on localhost, but it makes plain-HTTP operation on any other host a source edit |
| Logging                                    | Barely started — "not started" was slightly unfair. One call exists: `logger.exception` in `unhandled_exception_handler` (`app/api/errors.py`), which satisfies the only logging line the API spec itself states (`XC-14`) and is covered by `tests/api/test_internal_error.py`. Everything else is absent, and the absence is worse than it looks: there is **no logging configuration anywhere** — no `dictConfig`, no `basicConfig`, no level, handler or formatter — so under uvicorn the root logger has zero handlers at `WARNING`, and that one traceback reaches stderr only through Python's `lastResort` fallback, carrying no timestamp, level name or logger name; anything logged below `WARNING` would be discarded silently. To call this done: a logging config invoked from `create_app()`; request logging with method, path, status, duration and a per-request correlation id echoed into the error envelope so a reported 500 is findable; auth-event logging (login outcome, refresh rotation, and especially `AUTH-11` family revocation, a security event that currently leaves no trace at all); and a redaction rule making the "never log passwords or raw refresh tokens" convention enforceable rather than prose in docstrings |
| API documentation (Swagger/OpenAPI)        | **Done (T-DOCS-0)**, and verified by parsing the generated document rather than by reading the code that writes it. `/docs`, `/redoc` and `/openapi.json` return 200 (OpenAPI 3.1.0) and all 15 routes appear. Every documented 422 is now XC-4's envelope — `HTTPValidationError` and `ValidationError` are gone from `components.schemas`, and the string `detail` appears in no error schema anywhere in the document. Error statuses are derived from each route's own dependency tree and path, so they match the code rather than a plausible-looking list: 401 on all 8 routes behind `get_current_user` (and *not* on `POST /auth/logout`, which AUTH-13 makes idempotent), 403 on all 7 writes, 404 on all 5 path-parameter routes, 409 on `/auth/register` alone, 500 on all 15. The spurious 422 FastAPI attached to `GET /service-requests/{id}` is removed — that route answers 404 for a malformed id by design (SR-13). `components.securitySchemes` describes both session cookies and is applied to every protected route; `X-Requested-With` is a required header parameter on every write *and* is named in the API description Swagger UI renders first. `info.version` is `1.0.0`, `/health/db`'s 503 is documented with its own non-envelope body, and the document is checked in as `backend/openapi.json` (JSON, not the `openapi.yaml` the old design.md header anticipated), regenerated by `python -m app.api.openapi` and pinned against the served one by `tests/api/test_openapi.py`. Documentation only: no response body or status code changed, and all 267 pre-existing backend tests plus 19 e2e tests passed unmodified |

### Phase 5 — AI-Powered Chat Integration

Rows added 2026-09-14, the day the phase began (`T-CHAT-0`), sourced from
`PROJECT_BRIEF.md`'s own bullets; re-verified 2026-09-15 after `T-CHAT-1`.
**Four tasks of five are done**, and the fifth — the frontend widget
(`T-CHAT-2`) — has not started. Verified against the running code: 367
backend pytest tests green against the docker-compose Postgres (12
deliberate defects caught in `T-CHAT-0`, 5 in `T-CHAT-0b`, 6 in
`T-CHAT-1`), and `/openapi.json` unchanged since `T-CHAT-0b` — neither
later task touched a route.

**Verified against a live model**, not only against stubs: `claude-sonnet-5`
on the Foundry deployment files a real service request for the authenticated
caller and answers in natural language, and an FAQ question is answered in
one round trip with no tool call. (The first credential provided for that
resource was invalid — `401` on every route, indistinguishable from a wrong
key — so most of `T-CHAT-1` was built and verified before any model
answered. A replacement key works.)

**One open finding, deliberately left failing.** The eval set shows that an
explicit "please open a ticket" does not reliably produce a
`create_service_request` call: the assistant sometimes runs one round of
troubleshooting questions first, which is what `prompt.py` tells it to do,
and the conflict resolves differently from run to run. It is a prompt
decision rather than a defect — see `specs/chatbot/tasks.md`, T-CHAT-1.

| Requirement                            | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Integrate AI chatbot using OpenAI"     | **Deliberately not OpenAI.** `specs/chatbot/design.md` supersedes this line with the Anthropic Messages API (`claude-sonnet-5`, via a Microsoft Foundry deployment — decisions 1 and 8, both revised), which changes the shape of the work rather than just the vendor: there is no `tool` role, so a tool call is a `tool_use` block in an assistant message and its result a `tool_result` block in the next user message. Recorded here rather than silently — the brief's word is "OpenAI" and the code says Anthropic. The call is wired as of `T-CHAT-1`: `get_model_client` resolves a real SDK client, `app/chat/anthropic_client.py` is the only module that imports the vendor or reads the key, and the history sent with each call is capped at 20 messages at a boundary the API will accept. Unverified end to end — see the qualification above |
| Supports: FAQs                         | Done at the backend (`T-CHAT-0b`). The ten Q&A pairs `design.md §7` fixes, in `app/chat/faq.py` (a module, never a table — CHAT-12), inlined into the system prompt unconditionally — decision 4 closed on a hand-maintained set, so the entry-count threshold and the FAQ-search tool `T-CHAT-0` built are removed outright rather than left unreachable. Verified against the document rather than a second copy of itself: `tests/chat/test_faq.py` parses the ten entries out of `design.md` and asserts the module matches, order included. CHAT-20's grounding boundary is in the prompt and asserted as the literal string reaching the client                                                                                                                                                                                                                                                                                                                     |
| Supports: Service request creation     | Done at the backend. The `create_service_request` tool calls the same `app/services/service_requests.py` function `POST /service-requests` calls — extracted in this task so there is one insert, not two. The request is always filed for the authenticated caller; an identity-shaped argument from the model is ignored (CHAT-7), tested against a payload carrying four of them                                                                                                                                                                                          |
| Supports: Ticket status lookup         | Done at the backend. `get_request_status` resolves visibility through `app/api/visibility.py`'s `load_visible_service_request` — the same function the detail endpoint uses, asserted by a spy rather than by agreement — so admins reach any request and users only their own (CHAT-9)                                                                                                                                                                                                                                                                                  |
| Supports: Basic troubleshooting guidance | Partial. The finalized ten entries cover the standard first steps (password, VPN, printer, wifi, power, email sync), and CHAT-20 now tells the model to decline rather than improvise past them. `T-CHAT-1` built the eval set that checks it — `backend/evals/test_tool_choice.py`, seven cases asserting a tool *choice* and never a phrasing, one of them a question outside the FAQ entirely. It runs on demand and has never produced a result, for the credential reason above                                                                                                                                                                                                                                                                                                                                                |
| Connect chatbot to backend APIs        | Done, and deliberately *not* over HTTP: tool execution calls the service layer and the shared visibility loader in-process, so there is no second network hop and no second copy of the ownership rule. `POST`/`GET /api/v1/chat/messages` are mounted, authenticated by the existing cookie session (CHAT-13), and carry no conversation id in either URL (CHAT-2)                                                                                                                                                                                                          |
| _Deliverable: "AI assistant available within the portal"_ | Not yet, and now for two separate reasons. There is no widget (`T-CHAT-2`), so nothing in the portal surfaces the assistant. And `POST /chat/messages` still answers XC-14's `500` in this deployment — no longer because no client exists, but because the configured credential is rejected by the resource it points at. The first is work; the second is a key                                                                                                                                                                                                     |

**Known gaps inside the finished half**, so they are not rediscovered as
surprises: a failed model call answers XC-14's generic `500`, which is
indistinguishable to the widget from a bug in the backend — a dedicated
status and error code for "the assistant is unreachable" is a new
requirement rather than an implementation detail, and belongs with Phase
6's hardening; CHAT-18 defers rate limiting on `/chat/messages` to Phase 6,
which matters more here than on `/auth/login` because every message is a
metered API call; and the Phase 3 logging gap below applies to this
surface too — a chat exchange that fails mid-loop leaves nothing in a log
that says which tool or which user.

### Phase 4 — DevOps & Cloud Deployment

Rows added 2026-09-15, the day the phase began (`T-DO-0`), sourced from
`PROJECT_BRIEF.md`'s own bullets; re-verified 2026-09-16 after `T-DO-1`.
**Two tasks of nine are done**, and they are the two smallest: no pipeline
exists and nothing is deployed, so every row below except the first is
still "not started" and says so. The table is here now rather than when
there is something to report, because that is the mistake this table
exists to stop repeating.

Verified against the running code: 376 backend pytest tests green against
the docker-compose Postgres (unchanged by `T-DO-1`, which adds no Python),
`/health`'s two bodies read out of a live uvicorn process rather than a
`TestClient` — once per broken connection string, and once across a
database that goes away and comes back — and, new in `T-DO-1`, a built
backend image exercised end to end against that same Postgres: register →
login → `/auth/me` → file a request → list it, all through the container.

**The image's "no secrets" claim was verified with a control, not by
looking.** `docker save` was unpacked and all ten layers (404 MB) grepped
for the three live values in `backend/.env`: zero hits. On its own that
proves nothing — a broken grep also finds nothing — so the same scan was
run against a deliberately poisoned image built with `COPY .env`, which
hit. Separately, that poisoned `COPY` *fails outright* against the real
context: `.dockerignore` removes `.env` before the builder sees it, so
baking the secret in is not something a later edit can do by accident.

| Requirement                                                   | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Containerize application using Docker                         | **Backend done (`T-DO-1`); frontend (`T-DO-2`) and the prod-like stack (`T-DO-3`) not started.** `backend/Dockerfile` is a two-stage build on `python:3.14-slim` (matching the interpreter dev runs, deliberately), running as uid 10001, 371 MB. DO-3 and DO-4 are met and were checked rather than assumed: with no env injected the container refuses to start naming both `DATABASE_URL` and `JWT_SECRET_KEY`, and pydantic-settings reports `input_value={}` — proof no `.env` was found inside the image, not merely that none was copied; `docker diff` on a container that has served traffic is empty, so the "no log file" half of DO-4 rests on an observation rather than on the absence of a `FileHandler` in the source. Access lines go to stdout, uvicorn's startup and error lines to stderr. **No `HEALTHCHECK`, on purpose**: `/health` is a readiness probe (DO-22) whose whole job is answering 503 when the database is unreachable, and Docker/ECS read a failing `HEALTHCHECK` as liveness — wiring the two together turns a database blip into a restart storm instead of the ALB quietly pulling the task from rotation. The reasoning is recorded in the Dockerfile so a later pass doesn't add one back. Still open, and a gap against DO-1's word "reproducible": `requirements.txt` is unpinned, so the image resolved eight packages to versions ahead of the dev venv (alembic 1.20.0 vs 1.19.1, anthropic 1.6.0 vs 1.5.0, sqlalchemy 2.0.53 vs 2.0.52, uvicorn 0.53.0 vs 0.52.4, and four more). The build is reproducible in structure, not in dependency versions — pinning affects dev and CI too, so it is a decision to take, not a silent fix. The existing `docker-compose.yml` still containerizes Postgres only; `T-DO-3` is what makes a built-image stack exist |
| Create CI/CD pipeline (GitHub Actions/Azure DevOps)           | Not started (`T-DO-5`). No `.github/workflows/` directory. DO-15's smoke-test step now has something to call, which is the whole of what `T-DO-0` contributes here                                                                                                                                                                                                                                                                                                                                            |
| Configure development and production environments             | Not started (`T-DO-4`). Local Docker Compose is the only environment and is deliberately the only non-production one (DO-16); nothing is provisioned in AWS                                                                                                                                                                                                                                                                                                                                                   |
| Deploy application to cloud platform (Azure/AWS)              | Not started (`T-DO-4`, `T-DO-7`). AWS by decision 1; nothing provisioned                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| _Deliverable: "Automated deployment pipeline and live application"_ | Not yet — neither half exists                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

**`DO-22` maps to no bullet in the brief**, and that is worth recording
rather than filing under one that nearly fits. `GET /health` is a
precondition for two things the brief does ask for — the pipeline's
smoke test (DO-15) and the ALB target group's own checks (DO-5) — not a
deliverable of its own. It is done: unauthenticated, `200` only after a
live `SELECT 1` comes back, `503` otherwise, with no connection string,
driver text or traceback in either body. Verified against a real server
started with a dead port, a wrong password, a missing database and an
unresolvable host, and against a database cut mid-life and restored —
`pool_pre_ping` is what makes that last one recover rather than latch.
It replaced a pair: the old memory-only `/health` and `/health/db` are
one route now, because a probe that can answer `200` without reaching
the database is the failure DO-22 exists to prevent, and leaving it
mounted beside the real one is how an ALB ends up polling it.

### Phase 6

Not started. Add a phase's rows the day it begins, sourced from
`PROJECT_BRIEF.md`'s own requirement bullets for that phase — don't
pre-fill them from a guess at what the work will look like.
