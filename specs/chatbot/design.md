# Chat / AI assistant phase — design

Supersedes the "OpenAI function-calling" note in `Project_Phases_Outline` — this phase uses the
Anthropic Messages API instead. Scope is the chat feature itself (conversation model, tool
execution, endpoints, frontend widget); deployment/observability hardening stays in Phase 6.

## 1. Goals

Per the phase brief: FAQs, service request creation, ticket status lookup, basic troubleshooting
guidance, all backed by the existing service-layer functions rather than new logic.

## 2. Model & provider

- Anthropic Messages API, via a Microsoft-Foundry-hosted deployment (§10 decision 8) —
  wire-compatible with the direct `https://api.anthropic.com` endpoint, including the auth
  handshake: the plain `Anthropic` client, given nothing but `base_url`, authenticates with
  ordinary `x-api-key` and completes a full exchange. An earlier version of this line claimed
  Foundry needed a separate `AnthropicFoundry` client class with its own header convention — that
  theory was formed while debugging a dead credential (every key, including a deliberately wrong
  one, produced an identical 401) and is now falsified with a working one. Lesson worth keeping
  past this specific mistake: a 401 is evidence about a credential, not about the transport —
  don't infer an architecture change from an auth error you can't yet test against a working key.
- Model: `claude-sonnet-5` (§10 decision 1, revised) — not a cost/latency choice this time, but
  the only model actually deployed on the provided resource. The original Haiku-4.5 reasoning
  (cost-appropriate for a small tool set, argument validation matters more than model quality)
  doesn't apply to this specific deployment; keep §5's validation regardless; it was never
  contingent on which model was calling the tools.
- Structural difference from the OpenAI pattern researched earlier: the Messages API has **no
  separate "tool" role**. A tool call is a `tool_use` content block inside an **assistant**
  message; the executed result goes back as a `tool_result` content block inside the next
  **user** message. The system prompt is a top-level `system` field, not a message in the array.
  This shapes the schema in §6. Sonnet 5 also returns signed `thinking` blocks in the content
  array on some turns — one more reason §6 stores and replays the raw block array verbatim
  rather than parsing into a narrower typed model, which would have silently dropped them and
  broken the follow-up call on every thinking turn.
- Endpoint: the client's `base_url` is a config value (`ANTHROPIC_BASE_URL`), never hardcoded —
  set to the provided Foundry resource's endpoint. Unset falls back to the SDK's own
  `api.anthropic.com` default, so nothing breaks if a direct Console key ever replaces this
  deployment later.

## 3. Conversation flow

1. Frontend posts the user's text to `POST /chat/messages` — no conversation id, since each user
   has exactly one ongoing conversation (§10).
2. Backend gets-or-creates that user's `chat_conversations` row, loads its prior messages from
   `chat_messages`, and appends the new user message.
3. Backend calls the Messages API with `system` (behavior instructions + FAQ content, §7),
   `tools` (§4), and the message history.
4. Response `stop_reason` is either `end_turn` (plain text) or `tool_use` (one or more tool
   calls).
5. For each tool call: validate arguments against the tool's schema, execute the matching
   internal service-layer function using `current_user.id` from the session — never an
   identifier the model produced — and build a `tool_result` block with the outcome (`is_error:
true` on failure).
6. Send a follow-up request with the tool results appended; repeat from step 4 until `end_turn`,
   capped at `MAX_TOOL_ROUNDS = 5` rounds (decision 7) — on exhaustion, return a fixed reply and
   log the conversation id rather than looping indefinitely against a model that keeps calling
   tools.
7. Persist every content block exchanged, in order, to `chat_messages`.
8. Return only the final assistant text to the frontend.

## 4. Tools

| Tool                     | Arguments                    | Backing call                                                                                                                                      |
| ------------------------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `create_service_request` | title, description, priority | Same function `POST /service-requests` already calls                                                                                              |
| `get_request_status`     | request_id                   | Same function `GET /service-requests/{id}` calls, including its existing scope rule: admins may look up any request, regular users only their own |

FAQ questions are answered from system-prompt content, not a tool — see §7. `search_faq` was
built and tested during `T-CHAT-0`, but with a fixed, small FAQ set it's dead code; removed in
`T-CHAT-0b` rather than left in place unreachable.

`get_request_status` requiring a `request_id` upfront is a little presumptuous — a user asking
"what's up with my ticket from yesterday" doesn't have the id handy. Worth a follow-up refinement
once basic tool calling works: allow `request_id` to be optional, and when it's omitted, list the
caller's open requests so the model can either answer directly or ask which one they mean. Not
blocking for this pass, just flagged so it doesn't get forgotten.

Each tool's `input_schema` is a JSON Schema object — the same shape already used for
Pydantic-backed request bodies elsewhere in the backend.

## 5. Trust boundary

Same rule as "role is never accepted from the client": the model's output is untrusted input.
Tool execution always uses `get_current_user`'s id from the authenticated session; any
identity-shaped argument the model produces (a `user_id`, an `assignee`) is ignored. This is
stated as a requirement (CHAT-7), not left as an implementation habit — the same way XC-13 made
"load the user from the DB, don't trust the JWT claim" explicit and testable.

## 6. Schema additions

```
chat_conversations
  id            uuid PK
  user_id       uuid FK -> users.id, UNIQUE  -- one continuous conversation per user
  created_at    timestamptz
  updated_at    timestamptz

chat_messages
  id              uuid PK
  conversation_id uuid FK -> chat_conversations.id
  role            text  -- 'user' | 'assistant'
  content         jsonb -- the raw Anthropic content-block array for this message
  created_at      timestamptz
```

Storing the content-block array as `jsonb` rather than plain `text` is the same schema
discrimination pattern already used for `service_requests.metadata` — the shape genuinely varies
per message (text vs. tool_use vs. tool_result), and JSONB lets the exact conversation be replayed
back to the API without a lossy reconstruction step.

## 7. FAQ handling

Decided (§10, decision 4): a fixed set of 10 IT-support Q&A pairs, in a version-controlled
module, always inlined into the `system` prompt — no runtime switching, no `search_faq` tool.
This isn't a scaled-down version of a bigger mechanism; it's the actual answer for a small,
hand-maintained, rarely-changing FAQ. If the FAQ ever genuinely grows past what comfortably fits
in a system prompt, that's a real, human-noticed event — add `search_faq` back as its own task
then, with its own justification, rather than keeping an auto-switch mechanism running for a
threshold that may never be crossed.

Content (copy verbatim into the FAQ module — don't paraphrase or reorder):

1. **How do I reset my password?** Use the "Forgot password" link on the sign-in page to reset it
   yourself. If you don't have access to your recovery email, submit a ticket and IT will reset
   it manually — this usually takes under an hour during business hours.
2. **My VPN won't connect. What should I try first?** Restart the VPN client, confirm you're on a
   working internet connection, and make sure your VPN app is on the latest version. If it still
   won't connect after that, submit a ticket with the error message you're seeing.
3. **How do I request new software be installed on my computer?** Submit a service request with
   the software name and a short reason for the request. Most standard business software is
   approved within a day; anything outside the approved list needs manager sign-off first.
4. **My printer isn't working. What should I check?** Confirm the printer is powered on and
   connected to the network, then try removing and re-adding it in your system's printer
   settings. If a specific print job is stuck, cancel and resend it. Still stuck? Submit a ticket
   with the printer's name or location.
5. **How do I connect to the office Wi-Fi?** Select the office network from your Wi-Fi settings
   and sign in with your usual company username and password. If it doesn't accept your
   credentials, your account may need to be added to the Wi-Fi group — submit a ticket and we'll
   sort it out.
6. **My computer won't turn on. What should I do?** Check the power cable and outlet, and hold
   the power button for about 10 seconds in case it's frozen. If there's still no response,
   submit a ticket marked high priority so we can get you a loaner while we look into it.
7. **How do I submit a new IT service request?** You can ask the assistant to create one
   directly — just describe the issue — or use the "Submit Request" page from the dashboard.
   Either way, a clear title and description helps it get picked up faster.
8. **How can I check the status of an existing ticket?** Ask the assistant for the status
   directly, or check it any time from the dashboard, where every submitted request is listed
   with its current status.
9. **What's the typical response time for a support ticket?** Most tickets get a first response
   within one business day. High-priority issues — like a completely inaccessible computer — are
   typically picked up faster; if something's urgent, say so in the description.
10. **My email isn't syncing, or I'm not receiving new messages. What should I check?** Check the
    internet connection first, then confirm the mailbox isn't near its storage limit. If neither
    explains it, submit a ticket — this is sometimes a sync issue on the server side.

Grounding boundary (ties back to the grounding principle from the very first design pass): the
system prompt must state explicitly that these 10 entries are the assistant's complete FAQ
knowledge. For a question outside them, the assistant should say it doesn't have specific
guidance and offer to log a ticket, rather than improvising generic IT troubleshooting advice. A
small, closed FAQ set makes it _easier_ to invent a plausible-sounding eleventh answer, not
harder — the boundary has to be stated, not assumed from the list being short.

## 8. Endpoints

| Endpoint              | Purpose                                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------------------- |
| `POST /chat/messages` | Send a message; gets-or-creates the caller's single conversation, runs the loop in §3, returns the reply |
| `GET /chat/messages`  | Reload the caller's conversation history (widget reopened, page refresh)                                 |

No conversation id appears in either URL — ownership is implied entirely by `current_user`. This
is a direct consequence of the one-continuous-conversation decision (§10): with no id parameter,
there's no cross-user id to validate or leak, which is simpler than the 404-vs-403 reasoning
`{id}`-based endpoints elsewhere needed. `POST /chat/conversations` and a conversations-list
endpoint are dropped for the same reason — revisit only if multi-thread support is ever added.

## 9. Frontend integration

- Widget mounts once at the `AppShell` level, not per-page, so it survives route navigation —
  same reasoning already applied to nav and auth state.
- State: a `ChatProvider` alongside the existing `AuthContext`, holding open/closed state and the
  active conversation's messages.
- Response mode: **synchronous** for this first pass — the endpoint blocks until the loop in §3
  completes; the widget shows a pending/typing indicator. Streaming (SSE) is a deliberate later
  improvement — building it alongside the tool-calling logic mixes two new concepts at once.
- Since each user has exactly one continuous conversation, the widget needs no thread list or
  "new conversation" control — reopening it always resumes the same conversation.

## 10. Decisions

| #   | Decision                                                                                                                                                                                                                                                                                                                                                                                                     | Status             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------ |
| 1   | Model: `claude-sonnet-5` — revised from the original Haiku-4.5 pick; not a cost/latency choice, but the only model deployed on the provided Foundry resource (§2)                                                                                                                                                                                                                                            | Decided (revised)  |
| 2   | Conversation model: one continuous conversation per user, not multiple threads (§6, §8)                                                                                                                                                                                                                                                                                                                      | Decided            |
| 3   | Admin scope: `get_request_status` follows `GET /service-requests/{id}`'s existing rule — any ticket for admins, own only for regular users (§4)                                                                                                                                                                                                                                                              | Decided            |
| 4   | FAQ size: fixed at 10 IT-support entries, always inlined — `search_faq` removed entirely, not just left unused (§7)                                                                                                                                                                                                                                                                                          | Decided            |
| 5   | History window: capped at the last 20 messages per request, not the full thread — a cost control, since per-token pricing scales with every call regardless of thread length or which model is deployed. A naive most-recent-20 slice can orphan a `tool_result` from its `tool_use`, which the API rejects outright — the cut point must find the earliest legal start inside the cap instead (§3)          | Decided            |
| 6   | Chat message length limit: 4000 characters (CHAT-14) — generous for a support request, cheap to raise later if it's wrong                                                                                                                                                                                                                                                                                    | Decided            |
| 7   | Tool-loop ceiling: `MAX_TOOL_ROUNDS = 5` (CHAT-19) — five rounds after the first call, six Messages API calls maximum per user message; on exhaustion, a fixed reply is returned and the conversation id is logged, rather than raising or looping indefinitely                                                                                                                                              | Decided            |
| 8   | Deployment: Microsoft Foundry (assessment-provided resource) — the plain `Anthropic` client works with nothing but `base_url` set, ordinary `x-api-key` auth, no separate client class. A prior revision of this decision added an `AnthropicFoundry`-vs-`Anthropic` selection branch based on an untestable theory formed against a dead credential; reverted once a working key proved it unnecessary (§2) | Decided (reverted) |

## 11. Testing approach

The existing test suite checks deterministic code — fixed inputs, exact outputs. An LLM's tool
selection and phrasing aren't deterministic, so the recurring "does the test actually test the
thing" lesson applies in a new way here: don't assert exact model output. Split into two kinds of
test:

- **Deterministic, as before** — given a _fixed_ tool-call payload (as if the model had already
  decided to call `create_service_request` with specific arguments), does the endpoint validate,
  execute against the real user, and persist correctly? Fully testable without ever touching the
  model.
- **Model-in-the-loop evals** — a small fixed set of example user messages with an _expected tool
  choice_, not an expected exact reply (e.g. "my laptop won't turn on" → expect a
  `create_service_request` call). Run occasionally, not on every CI push — it costs money and can
  be flaky — to catch routing regressions when the system prompt or tool schemas change.
