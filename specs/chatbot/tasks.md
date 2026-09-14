# Chatbot — Tasks

> Ordered Claude Code prompts for Phase 5. One task per session, `/clear` between tasks, manual
> review + commit before starting the next — per `ways-of-working`. Every acceptance criterion
> cites a `requirements.md` ID from this folder; if you need to know _why_ a criterion exists,
> that ID is where the reasoning lives, not here.

## Conventions for this file

- Builds directly on the completed API layer (`specs/api-phase/`) — the four vertical slices
  there are a dependency of this one, not a predecessor to re-derive from scratch. Tool execution
  in `T-CHAT-0` calls the same service-layer functions and reuses the same visibility
  dependencies those tasks already built; nothing here duplicates that logic.
- Split into three tasks rather than the usual backend/frontend pair — `T-CHAT-0` and `T-CHAT-1`
  divide the backend at the one seam that matters operationally: everything before the live
  Anthropic call needs no API key and is fully deterministic-testable; only `T-CHAT-1` touches a
  genuinely non-deterministic dependency and needs a real `ANTHROPIC_API_KEY`. Keeping that split
  explicit means `T-CHAT-0` can start regardless of when the key arrives.
- Retrospectives for these tasks go in the project's existing `task-log.md`, under the same
  `T-CHAT-N` IDs, alongside every other group — one running project history, not a second log
  file per spec folder.

---

### T-CHAT-0 — Backend chat schema, endpoints, tool execution (model mocked)

**Goal**: The deterministic half of the chat feature — schema, endpoints, and tool execution,
verified against fixed tool-call payloads rather than a live model response.

**Covers**: `CHAT-1`, `CHAT-2`, `CHAT-3`, `CHAT-5`, `CHAT-7`, `CHAT-8`, `CHAT-9`, `CHAT-10`,
`CHAT-12`, `CHAT-14`, `CHAT-19` (added on later review — see acceptance criteria).

**Scope**:

- Migration: `chat_conversations` (`user_id` UNIQUE FK) and `chat_messages` (`conversation_id`
  FK, `role`, `content` JSONB, `created_at`) per `design.md §6`.
- `POST /chat/messages`, `GET /chat/messages` — no conversation id in either URL; both operate on
  `current_user`'s single conversation, get-or-created on first `POST` (`design.md §8`,
  decision 2).
- Tool execution functions for `create_service_request`, `get_request_status`, `search_faq`, each
  calling the existing service-layer function directly — never a second copy of that logic.
  `get_request_status` reuses the existing visibility dependency from `GET
/service-requests/{id}` (decision 3) rather than a new predicate, the same reuse pattern
  `T-SC-0` used for `SC-2`/`SC-8` against `app/api/visibility.py`.
- Static FAQ config module (`design.md §7`) — inline content in the system prompt for now.
- 4000-character limit on `POST /chat/messages` (decision 6).
- **The Anthropic client call is mocked/stubbed in this task.** Tests supply a fixed tool-call
  payload, as if the model had already decided to call a tool, and assert the endpoint validates,
  executes against the real authenticated user, and persists correctly. No real API key needed.

**Acceptance criteria**:

- [x] `CHAT-1`: a first `POST /chat/messages` for a user creates their `chat_conversations` row;
      a second call reuses it — assert exactly one row exists after two calls, not just that the
      second call succeeds
- [x] `CHAT-2`: neither route takes a conversation id — verified from the route signature, not
      only by testing behavior
- [x] `CHAT-7`: a fixed tool-call payload carrying a spoofed `user_id`/`assignee` argument is
      ignored; the created record's owner is always `current_user.id`
- [x] `CHAT-8`: a tool call with invalid arguments (missing required field) returns a
      `tool_result` with `is_error: true`, not a 500
- [x] `CHAT-9`: a `user`-role caller's `get_request_status` call fails on another user's request;
      an `admin`-role caller's succeeds on the same request — via the reused dependency, not a
      new check
- [x] `CHAT-10`: after a full fixed exchange (user text → tool_use → tool_result → assistant
      text), `GET /chat/messages` returns every block in order
- [x] `CHAT-12`: no migration adds an FAQ table; content lives in a version-controlled module
- [x] `CHAT-14`: a message over 4000 characters returns a 422 in the existing error envelope, not
      a 500 or a silent truncation
- [x] `CHAT-19`: **added on later review** — the tool loop stops at `MAX_TOOL_ROUNDS = 5`,
      verified by `test_the_loop_stops_calling_a_model_that_never_stops`, which pins the call
      count as the literal `6`, not `MAX_TOOL_ROUNDS + 1` (so raising the constant turns the test
      red instead of silently staying green)

**Complete.** See `task-log.md#t-chat-0`. A service layer (`service_requests.py`) was extracted
from the route handler during this task — `tasks.md`'s "existing service-layer function" assumed
one already existed; it didn't. `chat_messages.created_at` uses `clock_timestamp()`, not `now()`
— the first table in this schema where a single request inserts multiple ordered rows, where
`now()`'s fixed-per-transaction value would have made row ordering fall through to an arbitrary
UUID tiebreak.

### T-CHAT-0b — Finalize FAQ content, remove the auto-switch mechanism

**Goal**: Replace the placeholder FAQ content from `T-CHAT-0` with the finalized 10-entry set,
and delete the now-unnecessary `search_faq` tool and entry-count switching logic — decision 4
resolved in favor of a fixed, hand-maintained FAQ over an auto-scaling mechanism.

**Covers**: `CHAT-12` (revised), `CHAT-20` (new).

**Scope**:

- Replace `FAQ_ENTRIES`'s placeholder content with the 10 entries in `design.md §7`, copied
  verbatim — not paraphrased, not reordered.
- Delete `search_faq_is_enabled()`, `INLINE_LIMIT`, the `search_faq` tool schema and handler, and
  the conditional branching in the system-prompt/tool-list builder that reads them. This is a
  removal, not a disable — `search_faq` should not exist anywhere in the codebase afterward,
  including its tests. Grep for the literal string `search_faq` across the whole tree once done,
  not just a typed-usages search — the same check `T-SR-1`/`T-SC-1` needed for retired status
  vocabulary, for the same reason: an untyped leftover won't surface in a symbol search.
- Add the grounding-boundary sentence from `design.md §7` to the system prompt: the 10 entries
  are the assistant's complete FAQ knowledge; anything outside them gets "I don't have specific
  guidance on that" plus an offer to log a ticket, not improvised troubleshooting advice.

**Acceptance criteria**:

- [x] `CHAT-12`: `FAQ_ENTRIES` contains exactly the 10 finalized entries, verbatim, and nothing
      else
- [x] `search_faq`, `search_faq_is_enabled`, and `INLINE_LIMIT` do not appear anywhere in the
      codebase — verified by grep, not just by a passing test suite
- [x] The system prompt is now built unconditionally — no branch on FAQ entry count anywhere
- [x] `CHAT-20`: the system prompt text includes the explicit "these 10 are everything I know"
      boundary — check the literal string sent to the model, not just that a test asserting its
      presence exists
- [x] `create_service_request` and `get_request_status`'s existing `T-CHAT-0` tests still pass
      unchanged — this task touches FAQ and prompt-building only
- [ ] Full suite green afterward, with fewer total tests than `T-CHAT-0` left (the deleted
      `search_faq` tests should be gone, not passing vacuously) — **green, count unchanged at
      344.** The seven FAQ-search and threshold tests are gone; four CHAT-20 prompt tests and
      three FAQ-content tests replaced them, which this task's own scope required. Left unticked
      rather than reworded, since the criterion as written says "fewer"

**Complete.** See `task-log.md#t-chat-0b`.

### T-CHAT-1 — Live Anthropic integration (orchestration loop)

**Goal**: Wire the actual call to the Messages API — the piece T-CHAT-0 deliberately mocked.
**This is the point where a real `ANTHROPIC_API_KEY` becomes necessary** — nothing before this
task needs it.

**Covers**: `CHAT-4`, `CHAT-6`, `CHAT-11`, and the live happy-path of `CHAT-3`.

**Scope**:

- `ANTHROPIC_API_KEY` added to `config.py` alongside `JWT_SECRET_KEY`; `.env.example` placeholder
  added — same secret-handling pattern as `T-AUTH-1`.
- The call → execute → follow-up loop from `design.md §3`: call the Messages API with `system`,
  `tools`, and the last 20 messages of history (decision 5); on `stop_reason: tool_use`, execute
  via T-CHAT-0's functions and send a follow-up; repeat until `end_turn`; persist every block.
- Model read from config as `claude-haiku-4-5` (decision 1) — never hardcoded in the client call,
  so the upgrade path to `claude-sonnet-5` is a config change, not a code change.

**Acceptance criteria**:

- [ ] `CHAT-6`/`CHAT-11`: a live message that should trigger a tool call (e.g. "create a ticket
      for my broken laptop") results in a real row in `service_requests`, owned by the test user,
      and a natural-language confirmation reply
- [ ] `CHAT-3`: the user's message is persisted before the API call is made — verify by forcing
      the API call to fail and asserting the user message still exists
- [ ] A message that doesn't need a tool (an FAQ-style question) returns a plain-text reply on
      the first round trip, with no tool call made
- [ ] Eval set (`design.md §11`): a small fixed list of example messages with an expected tool
      choice, not an expected exact reply — run manually or on a separate, not-every-push job,
      per the design's reasoning on cost and flakiness

### T-CHAT-2 — Frontend chat widget

**Goal**: The widget itself, mounted at the shell level per `design.md §9`.

**Covers**: `CHAT-15`, `CHAT-16`, `CHAT-17`.

**Scope**:

- `ChatProvider` alongside `AuthContext`; widget mounted once inside `AppShell`, not per-page.
- Calls `POST`/`GET /chat/messages` via the existing hand-written `api.ts` pattern (`T-AUTH-4`'s
  convention) — no new fetch-wrapper approach for this one feature.
- Synchronous request/response for this pass (`design.md §9`) — a pending/typing indicator while
  the request is in flight.
- A failed request (network error, 5xx) leaves the user's typed message intact and shows a
  retryable error state — reuse the frontend's existing error-handling shape, don't invent a
  second one.

**Acceptance criteria**:

- [ ] Widget open/closed state persists across route navigation (mounted at shell level, verified
      by navigating mid-conversation)
- [ ] `CHAT-16`: pending state visible during the round trip — don't let a multi-second wait look
      frozen
- [ ] `CHAT-17`: a forced network failure leaves the typed message in the input, not lost
- [ ] Checked at ~1280px and ~375px, matching the project's existing responsive-check convention

**Chat phase checkpoint** — Phase 5 complete.
