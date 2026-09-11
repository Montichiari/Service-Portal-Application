# API Layer — Task Log

> The retrospective half of every completed task in `tasks.md`: what
> actually happened, what broke, what got corrected in the specs, and why.
> `tasks.md` keeps only what a session needs before starting a task —
> Goal, Covers, Scope, Acceptance criteria — with a pointer here. This
> file is for understanding the reasoning behind a past decision, not for
> starting the next one. Split out of `tasks.md` at the Group 2
> checkpoint, once that file passed 1,100 lines with 6 of 14 tasks still
> ahead of it. Sections below are in the same order as `tasks.md`, keyed
> by the same task IDs.

---

## Group 1 — Auth

### T-AUTH-0

**Complete — zero drift found.** All five files matched
`frontend-contract.md` exactly. Findings folded into `T-AUTH-5`'s scope and
`frontend/CLAUDE.md` (the `routes.tsx` absence, the snake_case casing
decision) rather than left in this task's own notes.

### T-AUTH-1

**Complete.** 38 new tests, all passing, mutation-tested (14 deliberate
defects, all caught) per `backend/CLAUDE.md`'s "verify a test can actually
fail" rule. One real gap the mutation pass surfaced worth knowing about
generically, not just for this task: a tamper test that corrupts a token's
encoding (rather than its _meaning_) can pass for the wrong reason — it
fails before reaching the check you actually meant to test. Worth
remembering next time you write a tamper/corruption test anywhere in this
project: corrupt something that's still well-formed, or you're not testing
what you think you're testing.

### T-AUTH-2

**Complete.** 90 tests total (39 new), mutation-tested per the same
"verify it can fail" rule as `T-AUTH-1`. Corrections folded back into
`requirements.md`/`design.md` rather than left as implementation-only
notes: `XC-9` now exempts `HEAD`/`OPTIONS` (not just `GET`) and checks
header _presence_, not an exact value; a new `XC-12` covers CORS, which
was missing from the original spec entirely and would have silently
broken `T-AUTH-4`; `XC-4` now explicitly covers framework-raised errors
(an unmatched route), not only Pydantic validation failures.

Built via a `create_app()` factory in `main.py` — tests construct the same
app the server runs, not a hand-assembled lookalike that could drift from
it. `require_role` is rank-based against the two-role hierarchy (`XC-6`
already said "minimum required role" — this confirms the spec, doesn't
change it): an admin passes a `require_role("user")` gate.

**Resolved**: `get_current_user` loads the full user row from the database
on every protected request, rather than trusting the JWT's `role` claim
alone. This reverses `design.md`'s originally stated rationale for
embedding `role` in the token (avoiding a DB hit per request) — kept
deliberately, not by default; `design.md`'s JWT claims section and
`requirements.md`'s new `XC-13` carry the final wording.

`db_session` was promoted to a top-level `tests/conftest.py` during this
task already (this task's own tests needed it from `tests/api/`) — the
prerequisite originally written into `T-AUTH-3` was done here first; that
task verified it rather than redoing it.

### T-AUTH-3

**Complete.** 147 tests total (52 new), mutation-tested — 31 deliberate
defects, all caught. That pass found a real hole in the tests themselves:
the cookie-expiry assertion derived its expected value from the same TTL
constant it was testing, so changing the access token to 30 days kept it
green. Now pinned to literal `3600`/`2592000` from `AUTH-6`. Worth
generalizing: **a test that computes its expectation from the code under
test asserts only self-consistency, not correctness** — the same class of
error as `T-AUTH-1`'s tamper test passing for the wrong reason.

Three decisions folded back into the specs rather than left as
implementation notes: `AUTH-17` (email case-folding, previously
unspecified), the `design.md` logout contradiction fixed in favor of
`AUTH-13`'s idempotency, and `XC-12`'s documented `ServerErrorMiddleware`
exception for the `500` path. `AUTH-18` records the login-timing decoy
as a deliberate blind spot — implemented but not test-enforced, since a
wall-clock assertion would be flaky.

Also added `email-validator` to `requirements.txt` (Pydantic's `EmailStr`
needs it), and auth tests use `@example.com` rather than the DB fixtures'
`@example.test`, which `email-validator` rejects as a reserved TLD.

### T-AUTH-4

**Complete.** Verified in a real Chromium page against the running
backend, so `credentials: 'include'`, CORS, and the `httpOnly`/`Secure`
cookies were genuinely exercised rather than mocked — including the
`XC-12` error-path CORS behavior specced during `T-AUTH-3`, which is
exactly the thing a mocked test would have missed.

The concurrency finding is worth remembering past this task: deduping
concurrent refreshes with a shared in-flight promise **looks** correct
and isn't. A `401` landing just after a refresh settles was generated
against the already-replaced token; retrying it starts a second,
redundant refresh — which, given `AUTH-11`'s family revocation, is one
arrival-order shift away from signing the user out of everything. The fix
reframes the question from "is a refresh running?" to "was this `401`
produced by a token that's already been replaced?" — a stale-response
problem in concurrency clothing.

Exports are thin per-endpoint functions (`register`/`login`/`getMe`/
`logout`); the underlying wrapper stays module-private so `T-AUTH-5`
can't accidentally grow a second client alongside it.

Two dev-database users exist from this task's live testing
(`t-auth-4.<timestamp>@example.com`) — usable as seeded logins for
`T-AUTH-5`, or delete them.

### T-AUTH-5

**Complete.** Verified live in Chromium against the running backend.
`AUTH-7`'s non-enumeration guarantee now holds end-to-end: identical
banner text for a wrong password on a real account and for an
unregistered address — a backend guarantee that a careless UI could
easily have undone by distinguishing them at the presentation layer.

Error routing by status is working as designed: a `422` lands inline on
the offending field via `fields`, a `409` surfaces as a page-level banner
because `ConflictError` deliberately carries no `fields` map. That split
is the `error.code`-not-`error.message` branching rule paying off.

**Carried debt out of this task** (both tracked in `tasks.md`, neither
blocking): `SubmitRequestPage` still held its own local `Field` copy
(`T-DEBT-1`, closed by `T-SR-1`), and routes remained unguarded
(`T-DEBT-2`).

### T-DEBT-2

**Complete.** The pending-state criterion was verified by removing the
`isLoading` branch and confirming the failure: without it, a signed-in
user isn't briefly flashed the login page — they're bounced there
permanently, 8/8 samples, never getting back. Worth recording how much
worse the real failure was than the predicted one, and how it would
otherwise have been found: only by hard-reloading while signed in, which
rarely happens during development.

**Structural decision worth carrying forward**: routes are guarded as a
group, not with per-route wrappers. A per-route wrapper makes protection
something you must remember to add, so a future route ships unguarded by
omission; guarding the block makes it the default, so a route ships
unguarded only deliberately. Same principle as `XC-8` (server-controlled
fields never accepted from clients) and sub-resources over embedded
collections — make the safe thing structural rather than a thing to
remember.

Also verified: the redirect uses `replace`, not `push`, so Back doesn't
trap the user in a redirect loop. Not-found is public and outside the
guard on purpose, so a mistyped URL says so in both session states rather
than silently becoming a login page. Pending renders `null` rather than a
spinner — the loading pattern is established once, in `T-SR-1`, and
inventing a second one here first is what that rule exists to prevent.

Deliberately out of scope: active-link styling (a design decision, never
specified) and return-to-intended-destination after login (login still
always lands on `/`).

### T-DEBT-3

**Complete.** 5 specs, green against the real stack via `npm run test:e2e`.

**The verification step caught a real defect — in the test, not the app.**
The first version of the concurrency test passed _with the guard
removed_. Its route handler keyed a delay on a shared mutable counter and
read it back after an `await`, so a later request could increment it
mid-handler; the hold never applied, both `401`s arrived together, and the
shared in-flight promise alone sufficed to dedupe them. The test was
passing without exercising the thing it was named after. Fixed by
capturing the call index at handler entry, plus an
`expect(meCalls).toBe(4)` guard so it fails loudly if the delayed call
ever stops `401`-ing rather than silently proving nothing.

**Third occurrence of the same failure family in this project** —
`T-AUTH-1`'s tamper test corrupted encoding rather than meaning;
`T-AUTH-3`'s expiry assertion computed its expectation from the constant
under test; this one let a shared counter race. Different mechanisms, one
pattern: the test passed, and would have kept passing, without the thing
it named ever being true. All three were surfaced only by removing the
thing under test and watching for red. That's the argument for the rule,
not a footnote to it.

Setup notes worth keeping: the concurrency spec imports `api.ts` by its
dev-server URL (`/src/lib/api.ts`) — the same URL the app imports, so
it's the app's own client instance, not a copy. Building a page that
fires two simultaneous calls would have tested the scaffolding instead.
Session expiry is simulated by dropping the `access_token` cookie while
keeping `refresh_token` — a real expiry as far as the client can tell.
Runs serially (`workers: 1`) on purpose: one real backend and database,
and readable failures beat saving a few seconds.

### Group 1 checkpoint

Backend (`T-AUTH-1` through `T-AUTH-3`) and frontend (`T-AUTH-4`,
`T-AUTH-5`) both built, reviewed, and integrated.

**Checkpoint decisions, both resolved**: build the route guard
(`T-DEBT-2`) and stand up Playwright (`T-DEBT-3`) before `T-SR-0` opens
Group 2. Run them in that order — the guard first, so Playwright's first
tests cover the finished auth surface rather than one that's about to
change underneath them.

What the slice validated, worth noting before repeating the pattern three
more times: building vertically surfaced problems a backend-then-frontend
split would have hidden until much later — `XC-12`'s error-path CORS gap,
the refresh-concurrency bug, the `422`-vs-`409` error routing split. None
of those are visible until both halves exist and talk to each other.

---

## Group 2 — Service Requests

### T-SR-0

**Complete.** 192 tests total (45 new), mutation-tested — 23 deliberate
defects, all caught (the six required, plus 17 more).

**The mutation pass found a real defect — in the test, not the app**, and
it's the most instructive one this project has produced. The N+1 test
passed with all three `joinedload` calls removed, for two independent
reasons, either of which alone would have made the assertion meaningless:

1. The test seeded its rows through the same session the handler used, so
   every related row was already in SQLAlchemy's identity map and a lazy
   many-to-one load never emitted SQL. **Production cannot reproduce
   this** — `get_db` yields a fresh session per request — so the fixture
   was the only reason the assertion held. Fixed with `expunge_all()`
   before each measured call.
2. Every row shared one requestor and one status, which makes an N+1
   self-limit at two queries regardless of row count. Fixed by giving
   each row its own requestor and assignee, with statuses spread across
   all four.

Generalising, and now recorded in `backend/CLAUDE.md`'s Testing section:
**an N+1 test that shares a session with the code under test measures the
fixture, not the query** — and homogeneous fixture data hides the growth
even when the session doesn't. Neither is visible from reading the test.
This is the fourth instance of the project's recurring pattern, after
`T-AUTH-1`, `T-AUTH-3`, and `T-DEBT-3`.

**Process finding**: a harness run was killed by a shell pipeline
truncation and left mutation 13 applied in the working tree. The full
suite caught it (`test_create_ignores_client_supplied_server_fields` went
red) and it was restored — but that's a good suite rather than a control.
`backend/CLAUDE.md` now requires a clean-tree assertion at the end of a
mutation pass and forbids piping a long harness run through a truncating
command.

**Spec problems found and fixed rather than worked around**:

- `SR-14` and `SR-15` did not exist in `requirements.md` — written in.
  `SR-14` is load-bearing, not a nicety: `SC-3` forbids the frontend
  synthesising history rows, so without it `T-SC-1`'s stepper shows a
  brand-new request with no step reached and no legitimate fix.
- `design.md §4` was silent on list ordering, on the initial history row,
  and on a missing `'open'` row — all three now documented.
- `design.md §1`'s "Role enforcement" paragraph was stale, still saying
  the dependency reads `role` off the validated JWT claim, which `XC-13`
  reversed during `T-AUTH-2`. Corrected — it's the paragraph someone
  adding a gated route would find first.
- `XC-10` ("paginate every list endpoint") contradicted `ST-2`
  (`/statuses` is deliberately unpaginated). Resolved in favour of the
  more specific `ST-2`, and `XC-10` amended to name the exception rather
  than leaving the contradiction resolved only in someone's head.

No migration needed, no model changed.

### T-SR-1

**Complete.** 12 e2e tests green (7 new) via `npm run test:e2e`, each of the
7 verified by removing the behaviour it names and observing red, then
restoring — clean tree asserted at the end of the pass.

**The loading/empty-state pattern, as actually built** (this is the part
Groups 3 and 4 inherit — `T-CM-1` and `T-SC-1` reuse it rather than
re-deciding it; also documented directly in `frontend/CLAUDE.md`'s Async
state section):

- `src/lib/async.ts` holds both halves: the `Async<T>` union and a
  `useAsyncData(load, deps)` hook that owns the effect. Putting the hook
  next to the type is what makes reuse the easy path — a page that wants
  data calls one function and cannot forget the cleanup, which is the
  failure the union alone doesn't prevent.
- `src/components/ui/AsyncSection.tsx` renders pending and error; the
  caller renders ready. **Empty is deliberately not handled there**: only
  the caller knows what empty means. The dashboard needs three different
  sentences for it (filtered-and-matched-nothing, user-with-no-requests,
  admin-with-an-empty-system), and folding empty into the shared component
  would have forced one sentence to cover all three.
- `ErrorBanner` was extracted from `LoginPage`/`RegisterPage` in the same
  change. `frontend/CLAUDE.md` forbids a second banner component, and this
  task needed one in three more places — so the choice was extract now or
  have four copies. Same trigger as `Field.tsx`, applied before the copies
  existed rather than after, which is how `SubmitRequestPage` kept its own
  `Field` for a whole phase.

**Two wire vocabularies moved into `api.ts`** (`Priority`, `StatusName`),
with `PriorityPill`/`StatusPill` importing them. They were previously
declared in the pill components, which meant the presentation layer owned
the contract's value set — the same shape as `frontend-contract.md
§9-#8`'s two-non-matching-status-enums problem. The pills now own only how
a value looks.

**Spec conflict found, resolved rather than worked around**:
`RequestStatusPage` imports `mockRequestDetail` — a fact this task's scope
paragraph didn't mention, and which made "no page imports from
`src/data/`" and "`T-SC-1` owns `RequestStatusPage`" mutually
unsatisfiable. Resolved in favour of `T-SC-1`'s ownership: the fixture is
deleted, and that page's heading now shows the request id alone instead of
the mock's title. Fetching the real request just for the heading was
rejected — a real title above an invented timeline reads as more
trustworthy than it is, and half-converting a page another task owns is
worse than leaving it visibly unconverted. `mockStatusHistory.ts` is now
the only surviving fixture, and its docstring says why. **`T-SC-1`'s scope
now carries a note to restore the title once real data backs the page.**

**Spec ambiguity, flagged not silently resolved**: `submitRequestSchema`
capped `title` at 100 characters where `SR-7` allows 200. `design.md §4`
explicitly preserved the frontend's 1000-character `description` cap and
said nothing about `title`, so the prototype's 100 was left standing —
raising it would retire a written `frontend-phase/requirements.md` rule by
inference. Note this is **not** the `AUTH-16` hazard: both limits are
measured the same way on both sides, so nothing this form accepts can fail
server-side. **Resolved at the Group 2 checkpoint via `T-DEBT-5`: raised
to 200, matching `SR-7`.**

**One partially-verifiable criterion, stated plainly**: the admin
empty-state copy has two variants and only one is observable. The filtered
variant ("No requests match these filters") was confirmed live as an admin;
the unfiltered admin variant ("No requests have been submitted yet")
requires an empty database, which the shared dev database can't be. Both
regular-user variants and the admin heading were confirmed live, the latter
against a user promoted with a direct `UPDATE` (there is no promotion
endpoint by design).

**A real leftover the greps caught**: `src/lib/utils.ts` registered
`status-draft` in its `tailwind-merge` class group. Deleting the token and
the `STATUS_CONFIG` entry would have left that behind — invisible, since a
class group naming a nonexistent utility is silently inert, and exactly the
kind of residue that makes a retired status look revivable. **`T-SC-1`'s
scope now carries this as a general rule** for retiring
`StatusHistoryState`/`STATUS_HISTORY_LABELS`: grep for the literal string
across the tree, not just typed usages.

**Deliberately out of scope, so the next reader doesn't think it was
missed**: no requestor column on the admin dashboard. `SR-2` means an admin
sees other people's requests with no column saying whose, which is a real
gap — but this task's scope named "role-dependent heading and empty-state
text" specifically, and a column is a design decision rather than a copy
fix. **Resolved at the Group 2 checkpoint via `T-DEBT-5`: column added.**

---

_(Groups 3 and 4 have not run yet — no entries here until they do.)_
