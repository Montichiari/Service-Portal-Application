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

### T-DEBT-5

Both gaps `T-SR-1` left open at the Group 2 checkpoint, closed. All three
acceptance criteria pass, verified live against the running stack at both
widths.

**The title cap.** `submitRequestSchema`'s `title` went 100 → 200, matching
`SR-7`, with the message updated to agree. The docstring had carried a
paragraph arguing both maxima were deliberately stricter than the API's;
that was only ever true of `description` (`design.md §4` names its 10000 an
abuse backstop and keeps the 1000-character UX cap on purpose, and is
silent on `title`). The paragraph now says that, rather than grouping the
two under one rationale that fitted only one of them. Confirmed through the
real form: a 150-character title submits and lands on the dashboard, a
201-character one is refused with `fields.title` populated and the input
marked invalid. There is no `maxlength` attribute on the input, so the
schema is the only cap — worth knowing, because a `maxlength` would have
silently truncated at 100 and made the old limit look like a passing test.

**The requestor column.** Rendered only when `user.role === 'admin'`, from
each item's embedded `requestor` — no new fetch, no backend change, as
scoped. It is **absent from the DOM** for a regular user rather than
CSS-hidden, the same rule `CM-7`'s internal-comment checkbox will follow.
Verified as a promoted admin (direct `UPDATE` again — no promotion
endpoint, by design) against a list holding two different requestors, so
the column is provably per-row data and not the viewer's own name repeated:
a single-requestor fixture would have passed while rendering the wrong
field.

**One extraction, not deferred.** `fullName` lived inside
`RequestDetailsPage`; the new column made the dashboard its second caller.
Duplicating it is precisely the failure `frontend/CLAUDE.md` records
against the three `Field` copies, so it moved to `src/lib/names.ts` — the
one place a `UserSummary` becomes a name, the same shape as `datetime.ts`.
It exports `fullName` alone. A `fullNameOr(user, fallback)` was written and
then removed before landing: `RequestDetailsPage` handles the `null`
assignee inline with its own comment, so the helper would have shipped with
no caller, and what to show in place of a missing name is the page's call,
not the module's.

**A layout observation, not a defect in this change.** The first live check
used a 150-character title made of one unbroken 140-character token, which
cannot wrap — it blew the Title column out and pushed the other four
columns out of view. Re-checked with a realistic 150-character title (the
same length, with spaces) all five columns fit at ~1280px with the title
wrapping over two lines. The table wrapper is `overflow-x: auto` and the
page body does not overflow horizontally at either width, so even the
pathological case scrolls inside its own container rather than breaking the
page. This behaviour predates the new column and is a property of an
unbreakable string, not of the column count — recorded because the first
screenshot looks alarming and someone re-running this check deserves to
know it was chased down rather than missed.

At ~375px the requestor column collapses with priority and date via the
existing `hidden md:table-cell`, leaving Title and Status for both roles —
no new mobile treatment was needed, and none was invented.

The existing 12-spec Playwright suite still passes. No new specs were
added: this task's acceptance criteria name live checks at two widths, not
regression coverage, and unlike `T-SR-1` no criterion here describes a
behaviour a future edit could silently undo without a visible column
disappearing. If the requestor column ever gains a role-dependent test, it
belongs alongside `CM-7`'s DOM-absence spec in Group 3.

---

## Group 3 — Comments

### T-CM-0

**Complete.** 228 tests total (32 new comment tests + 1 new service-request
test on top of the 195 baseline), mutation-tested — 13 deliberate defects,
all caught for the right reason, clean tree asserted afterward. No
migration needed — the `Comment` model already existed from the ORM
phase, confirming `backend/CLAUDE.md`'s standing prediction for the whole
API phase.

**The load-bearing finding**: `CM-9` requires the `404` for an invisible
parent to fire before `is_internal`/body are evaluated at all. FastAPI
validates a declared request body during parameter binding, ahead of any
code inside the handler — so a visibility check written as the handler's
first statement runs _after_ that validation has already happened. A
malformed body sent to an invisible parent then returns `422` instead of
`404`, breaking `XC-7`'s guarantee that an invisible resource is
indistinguishable regardless of what else is wrong with the request. The
check has to be a `Depends()`, not a handler-body statement — that's the
only thing that runs early enough to preempt it. Pinned by
`test_create_404_precedes_body_validation`. Generalized into
`backend/CLAUDE.md` as its own convention ("Visibility checks on nested
resources") and folded into `T-SC-0`'s scope directly, since `SC-2`/`SC-8`
have the identical shape.

**One refactor, done proactively rather than deferred**:
`_visibility_conditions`/`_parse_uuid`/`_load_visible` moved out of
`service_requests.py` into a new `app/api/visibility.py`. `CM-4`/`CM-9`
say "matching `SR-12`" explicitly, and a second copy of that predicate is
exactly the shape where one copy gets tightened later and the other
doesn't — the comment tests assert the two routes' `404` bodies are
byte-identical to the parent route's, which only means something if
there's one predicate to drift from. `T-SC-0` will import the same
module for `SC-2`/`SC-8`.

**Acceptance criteria, all confirmed**:

- `CM-2`/`CM-3`: asserted against `response.text` (not parsed keys) so
  serialization quirks can't hide a leak, and that `total` is `1` not
  `2` — a row that's fetched then hidden by the response layer would
  still inflate the count if the exclusion happened after counting
- `CM-7`: the `403` envelope, `fields` absent (reserved for
  `VALIDATION_ERROR` per `design.md §1`, so its presence here would
  itself be a contract violation), and a `COUNT` of `0` after rollback
- `CM-8`: parametrized over `true`/`false`, plus the omitted-defaults-
  to-`false` case, checked against both the response and the stored row
- `T-DEBT-4`'s two items: the service-request `401` coverage already
  existed from `T-SR-0` — `T-DEBT-4`'s original text predates that
  discovery, written on the assumption of a gap that turned out to be
  already closed on one side. The comment-route equivalent was added.
  The filtered-`total` test is new (`test_total_respects_filters_as_well_as_scope`)
  — existing filter tests covered it only incidentally; this one
  exercises scope and filter together, which is where a count bug that
  only breaks on the combination would actually hide

**Notes carried into `T-CM-1`'s scope directly** (not left here only):
`CommentOut` carries `is_internal` on every row regardless of caller role
(always `false` for a non-admin), so the frontend needs no second
response shape — only the composer's checkbox is role-gated. Comments are
ordered `created_at ASC`, the opposite of the dashboard's `SR-15` order —
deliberate, not an inconsistency to fix.

### T-CM-1

**Complete.** 4 new Playwright specs (16 total, all green), each verified by
removing the thing it names and watching it go red — 6 deliberate defects,
all caught, all restored. `T-SR-1`'s `Async` pattern was reused unchanged;
no second loading or empty-state shape was introduced.

**An admin now exists in the e2e suite** (`promoteToAdmin` in
`fixtures.ts`). Three of this phase's behaviours only appear for an
`admin` — `SR-2`'s all-requests list, `CM-3`'s internal comments, `CM-8`'s
internal composer — and until now every one of them had been checked by
hand against a manually promoted account (`task-log.md#t-sr-1`,
`#t-debt-5`). A hand-maintained account is exactly the fixture this suite
refuses, so promotion is automated instead: `docker compose exec db psql`
issuing the same `UPDATE users SET role = 'admin'` a person would. That
this works at all is a property of `deps.py`, which re-reads `role` off
the user row on every request rather than trusting the token's claim —
promotion lands on the caller's very next request, so a test only has to
promote before signing the browser in. The helper asserts `UPDATE 1`,
because `UPDATE 0` is a _successful_ psql command that changed nothing and
would leave the admin tests passing as a regular user.

`registerViaApi` gained an optional name, for the same reason: every
seeded user was `Playwright Runner`, so a requestor column rendering the
viewer's name instead of the row's would have matched either way. The
regression test seeds `Ada Lovelace` and `Grace Hopper` and asserts
neither row carries the admin viewer's own name — and the mutation pass
confirmed it: with the column switched to `fullName(user)`, Ada's row read
`Sam Supervisor`.

**The no-reload criterion needed its own assertion, and the mutation pass
proved it.** "Posting a comment appends it to the visible list without a
full page reload" — asserting the comment becomes visible does not test
that at all: a `window.location.reload()` after the POST also ends with
the comment visible. The spec sets a `window` sentinel before posting and
re-reads it afterwards, which only survives if the document did. Mutated
both ways: dropping the append turned the visibility assertion red, and
reloading instead turned the _sentinel_ red while visibility stayed green.
Same family as this project's recurring failure — a test that passes, and
keeps passing, without the thing it names being true.

**Posted comments are held locally rather than refetched.** A refetch
returns the list to `pending`, and `AsyncSection` would replace the whole
thread with a loading line — the user would watch what they just wrote
take the conversation away with it. What is appended is the server's own
`201` body, so nothing is invented client-side. The local list is keyed by
request _and_ page: after either changes, the server's response already
accounts for those comments and keeping them would show them twice.

**`Pagination` was extracted** from `RequestsDashboardPage` into
`components/ui/Pagination.tsx`. `GET /service-requests/{id}/comments` is
paginated (`CM-1`, `XC-10`), so a thread past 20 comments would otherwise
have stopped dead with nothing indicating the rest existed — the exact gap
`T-SR-1` closed for the dashboard. A second caller appearing is
`frontend/CLAUDE.md`'s stated trigger to extract rather than copy, the
same rule that produced `Field`, `ErrorBanner` and `names.ts`. The
comments list renders it only when there is a second page; the dashboard
still shows it unconditionally, because a table is a thing you page
through and a three-comment thread under a disabled Previous button is
noise. Verified live with a 22-comment thread: `Showing 1–20 of 22`, Next
to `Showing 21–22 of 22`, Next then disabled. The dashboard's own
pagination spec still passes unchanged.

**Two judgement calls worth naming**:

- The comments card is mounted _inside_ the request's `ready` branch, so
  the sub-resource is only asked for once its parent is known visible.
  `CM-4` answers an invisible parent with the same `404` `SR-12` gives,
  so firing both at once would put two error surfaces in a race to
  explain one fact — and the not-found panel already says it properly.
  The cost is one round trip of serialisation; `frontend/CLAUDE.md`'s
  "two resources, two `Async` values" rule is about not sharing a pending
  flag, which this doesn't.
- The internal checkbox is laid out inline rather than through `Field`,
  which stacks its label above the control. It is the app's only
  checkbox; a `Checkbox` primitive extracts the moment there is a second,
  the same reasoning that keeps `FilterField` local to the dashboard.

**The one criterion no test can carry**: "renders keyed by real `id`, not
array index". A React key is invisible in the DOM, so nothing a Playwright
spec can assert distinguishes the two — confirmed by reading the code
(`key={comment.id}`, `CommentItem`), not by a test. Making it observable
would have meant inventing a DOM attribute for the test's benefit.

**Checked at ~1280px and ~375px**, including the admin composer and the
`Internal` badge, with no horizontal overflow at either. `CM-6`'s
boundaries confirmed live through the form: empty rejected client-side,
5001 characters rejected, 5000 accepted end-to-end.

**Scope note for the Group 3 checkpoint**: comments have no edit or delete
path, because the API has none (`design.md §6` defines only `GET` and
`POST`). Nothing in the UI implies otherwise.

---

## Group 4 — Status history

### T-SC-0

**Complete.** 267 tests total (39 new), mutation-tested — 13 deliberate
defects, all caught, applied as revertible patches with a clean tree
verified afterward. No model changed, no migration needed — confirming
`backend/CLAUDE.md`'s standing prediction once more. Visibility reuses
`app/api/visibility.py`'s shared predicate (`T-CM-0`) — no second copy of
`SR-12`'s logic.

**The load-bearing decision**: `SC-4` and `SC-8` genuinely conflict for a
`user`-role caller with no visibility into the parent request — `SC-4`
says `403`, `SC-8` says `404`, and only one status can be sent. Resolved
by declaring the visibility dependency before the role gate, so that
overlapping case answers `404`. Three reasons, all pointing the same way:
`SC-8` names this exact case; it keeps the route's `404`s byte-identical
to `SR-12`'s; and a `403` there would itself leak that the request
exists, which is precisely what `XC-7` exists to prevent. `SC-4`'s own
case — a user posting to a request they _can_ see — still answers `403`
once visibility passes. This generalizes `T-CM-0`'s `CM-9` finding one
step further: visibility isn't just ordered ahead of body validation, it
has to run ahead of every other check that could leak the resource's
existence, role checks included. Pinned by
`test_user_posting_to_an_invisible_parent_gets_the_visibility_answer` —
swapping the two dependencies' order breaks nothing else, so this is the
only test protecting the decision. Generalized into `backend/CLAUDE.md`'s
"Visibility checks on nested resources."

**Two mutations caught for a different reason than predicted**:

- `M9` (removing the list route's auth gate) didn't initially produce a
  valid mutation — a non-default parameter ended up after a defaulted
  one, a Python syntax error, not a semantic one. Fixed into a valid
  mutation and re-verified it was then caught by the right tests (the
  `401` test and three visibility tests going red) rather than counting
  the compile failure itself as a catch. A mutation that can't run
  doesn't test anything about the suite.
- `M13` (`changed_by_id=None`) left `test_status_change_shape_matches_the_contract`
  green, because that test seeds its row directly rather than posting
  through the endpoint — it validates serialization, not the write path
  that populates the field. Two other tests caught the mutation, so the
  suite as a whole is fine, but the shape test's own coverage of that
  field is illusory. A "shape"/contract test that seeds its fixture
  directly can only prove the response serializes correctly, never that
  the write logic populating it is correct.

**A fifth instance of the project's recurring "passes without the thing
it names being true" pattern**, and a new mechanism: the two atomicity
tests both create their parent through the real API rather than a raw
fixture insert. A fixture row created directly lives inside the test's
own rollback savepoint — the same one the sabotaged write's failure
would also unwind — so asserting "nothing changed" afterward can pass
vacuously regardless of whether the code's atomicity logic works, because
there's no way to distinguish a correctly-scoped rollback from the whole
test's teardown rolling everything back anyway. Creating the parent
through the API commits it independently, so the later sabotaged write
has a real, persisted base state to fail against. The two atomicity
tests are also complementary, not redundant: sabotaging the history
insert only catches a handler that commits the parent update first, and
sabotaging the parent update only catches the mirror image — neither
alone is sufficient.

**Naming note**: this task's own report referred to the shared visibility
lookup as `get_visible_parent_request`, where prior entries in this log
and `backend/CLAUDE.md` name it `_load_visible`. Not reconciled here —
worth confirming against the actual function name in
`app/api/visibility.py` before the next task that touches it, and
correcting whichever side is stale.

_(No further groups — this closes Group 4's backend half. `T-SC-1` is
the frontend half and the final task of the phase.)_
