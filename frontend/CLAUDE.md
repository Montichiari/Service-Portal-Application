# frontend/CLAUDE.md

Persistent context for Claude Code sessions working in `frontend/`. Read
this before starting any task from `specs/frontend-phase/tasks.md` (prior
phase, complete) or `specs/api-phase/tasks.md` (current phase).

## Project context

Internal IT service portal, capstone project. The prototype phase (6 pages
of UI, no backend) is complete. **A real backend now exists** — this phase
wires the prototype up to it, one vertical slice at a time
(`specs/api-phase/tasks.md`). Fetch calls are now permitted, but **only**
through `src/lib/api.ts` — see Non-goals and API client conventions below.
Don't add a second fetch client, don't call `fetch` directly from a
component.

## Spec files (source of truth — do not restate their contents inline in

code comments, reference them instead)

Prototype phase:

- `specs/frontend-phase/design-tokens.md` — color, type, layout tokens
- `specs/frontend-phase/design.md` — routing, nav, component inventory,
  per-page data strategy
- `specs/frontend-phase/requirements.md` — field lists, validation rules,
  EARS-style behavior per page
- `specs/frontend-phase/tasks.md` — the 6 ordered prototype tasks

API phase (current):

- `specs/api-phase/design.md` — endpoint shapes, auth flow, error format
- `specs/api-phase/requirements.md` — EARS-style, per-endpoint, IDs
  referenced by `tasks.md` acceptance criteria
- `specs/api-phase/tasks.md` — the ordered task groups (Auth, ServiceRequest,
  Comments, StatusHistory) and their acceptance criteria
- `specs/api-phase/task-log.md` — the retrospective for each completed
  task (what actually happened, spec corrections made). `tasks.md` points
  here rather than repeating it; read this when you want the reasoning
  behind a past decision, not before starting a new one.

There is still no `openapi.yaml` in the repo. `specs/api-phase/design.md`
and `requirements.md` are the durable source of truth for request/response
shapes and validation — build and reconcile zod schemas against those, not
against a generated spec that doesn't exist.

## Tech stack

React + TypeScript + Vite · `react-hook-form` + `zod` (v4 — `z.email()`
top-level form is correct for this version, don't "fix" it to the older
`z.string().email()` form) · `shadcn/ui` · `react-router-dom` for routing. **No TanStack Query** — decided explicitly in
`specs/api-phase/tasks.md`'s conventions section, not merely deferred for
lack of something to fetch (there now is). A hand-rolled `src/lib/api.ts`
fetch wrapper covers this phase's needs (no caching or background refetch
required by any current requirement); add TanStack Query later only with
its own concrete justification.

## Folder structure

```
frontend/src/
  components/
    ui/            # Button, TextInput, Select, Textarea, Card, Table,
                    # StatusPill, PriorityPill, Timeline, Field,
                    # ErrorBanner, AsyncSection, Timestamp, Pagination
                    # (Pagination moved here from RequestsDashboardPage in
                    # T-CM-1, when the comments thread became its second
                    # caller — see Error surfacing's extract-on-second-
                    # caller rule, which is not only about error UI)
    shell/          # AppShell, AuthShell
  pages/
    LoginPage.tsx
    RegisterPage.tsx
    RequestsDashboardPage.tsx
    SubmitRequestPage.tsx
    RequestDetailsPage.tsx
    RequestStatusPage.tsx
  schemas/          # zod schemas, one file per form. Reconciled against
                    # specs/api-phase/requirements.md this phase (see Form
                    # pattern)
  context/
    AuthContext.tsx  # real session, backed by GET /auth/me — see Auth
                    # state below (prototype phase: role state only)
  data/              # hardcoded mock objects/arrays — being retired page
                    # by page as each is wired to the real API; a page
                    # still importing from here after its Group in
                    # tasks.md is done is a bug, not a leftover.
                    # T-SR-1 deleted mockRequests + mockRequestDetail;
                    # only mockStatusHistory survives, and T-SC-1 retires
                    # it. Delete the folder when it goes.
  lib/
    api.ts           # the one sanctioned fetch client (built T-AUTH-4).
                    # Exports thin per-endpoint functions; the fetch
                    # wrapper itself is module-private by design.
    async.ts         # Async<T> + useAsyncData (T-SR-1) — see Async state
    datetime.ts      # the one date formatter (T-SR-1)
    names.ts         # the one UserSummary -> display name (T-DEBT-5);
                    # was local to RequestDetailsPage until the admin
                    # requestor column made the dashboard a second caller
  routes.tsx         # route table + cosmetic auth guard + catch-all.
                    # Built in T-DEBT-2 (it did NOT exist through the
                    # whole prototype phase and Group 1 — Task 3 was
                    # never landed; App.tsx held routing inline).
  e2e/               # Playwright specs (T-DEBT-3), run against the real
                    # stack — see Testing below.
  styles/
    tokens.css        # CSS variables from design-tokens.md
```

## Token usage

All colors/type/spacing come from CSS variables defined once in
`styles/tokens.css`, matching `design-tokens.md` exactly. **No inline hex
values or magic numbers in components.** If a value isn't in tokens.css, add
it there first, don't hardcode it in a component.

## Component conventions

- `StatusPill` / `PriorityPill` take a single `status` / `priority` prop
  and internally map to token colors — never let a page component choose
  the color directly. `Status` values change this phase (`open` /
  `in_progress` / `resolved` / `closed` only, per the locked backend
  enum) — update `STATUS_CONFIG` to match; `draft` is dropped.
- **When retiring a value from an enum or config (e.g. a dropped
  `Status`), grep its literal string across the whole tree, not just
  typed declarations.** Some registrations are untyped strings —
  `T-SR-1` found `status-draft` still registered in `src/lib/utils.ts`'s
  `tailwind-merge` class-group config after the type and
  `STATUS_CONFIG` entry were both deleted. A TypeScript usages search
  never surfaces this kind of registration, and a class group naming a
  nonexistent utility is silently inert — exactly the residue that makes
  a retired value look revivable later. `T-SC-1`'s retirement of
  `StatusHistoryState`/`STATUS_HISTORY_LABELS` is the next place this
  matters.
- Cards are flat: hairline border, no shadow, ≤4px radius.
- `AppShell` wraps all in-app pages (post-login); `AuthShell` wraps only
  Login/Register. Don't reuse one for the other.
- Content width and alignment follow `design-tokens.md`'s "Content width"
  table: every in-app content type is **centered** in the content area at
  its own max-width — one alignment rule, differing only by width. Use the
  shared `.content-*` classes (`index.css`, backed by `--content-*` tokens);
  don't re-solve alignment per page.
  - Single-action forms: 640px — `.content-form`.
  - Tables / dashboard: 1040px — `.content-dashboard`.
  - Detail views: 720px — `.content-detail`.
  - Never full-viewport. Even space on both sides above the max-width is
    expected, not a bug.
- Responsive is mobile-first off one breakpoint: `--bp-mobile` (768px) is
  wired to Tailwind's `md` variant (`--breakpoint-md` in `index.css`), so
  bare utilities target < 768px and `md:` targets ≥ 768px. Below the
  breakpoint `AppShell` collapses the sidebar to a top bar with a menu
  toggle and drops its own content padding from 32px to 16px (`AppShell`
  owns that padding — pages don't add their own), and the max-widths above
  go fluid. See `design-tokens.md` Breakpoints.
- **Check every page at both a desktop (~1280px) and mobile (~375px) width
  before considering a task done** — not optional polish, it's part of every
  task's acceptance criteria going forward.
- Loading and empty states didn't exist in the prototype
  (`frontend-contract.md §8.2`/§8.4). **The pattern is now established
  (`T-SR-1`) — reuse it, don't invent a second one.** See Async state below.

## Async state

Established in `T-SR-1`, used by every page that fetches. Two files:

- `src/lib/async.ts` — the `Async<T>` union
  (`pending` | `error` | `ready`) **and** the `useAsyncData(load, deps)`
  hook that owns the effect. Import the hook, don't hand-roll a
  `useEffect` + `useState` pair; the hook is where the cleanup lives.
- `src/components/ui/AsyncSection.tsx` — renders pending and error; the
  caller supplies ready via a render prop.

**Empty is not a fourth union member.** It's `ready` with an empty array
and the caller branches on length, because only the caller knows what
empty means — "no requests match these filters", "you haven't submitted
one yet" and "nobody has" are three different sentences on one page.
`AsyncSection` deliberately doesn't handle it.

**Every async effect invalidates its in-flight result on cleanup**, and
`useAsyncData` does both halves: an `AbortController` aborted in cleanup,
_and_ a `current` flag checked before every `setState`. The flag is not
redundant belt-and-braces — it covers the window the controller can't, a
promise that already resolved whose `.then` is queued behind a cleanup
that has since run. Same family as `T-AUTH-4`'s `sessionGeneration`
finding: the question is "was this response produced by a request I still
care about?", answered at response handling, not at dispatch. Verified by
removing it and watching a table show results contradicting its own
filter controls.

**After a successful write, append the server's response locally — don't
refetch** (`T-CM-1`). A refetch returns the list to `pending` and
`AsyncSection` replaces it with a loading line, so the user watches what
they just submitted take the whole list away with it. What gets appended is
the `201` body itself, so nothing is invented client-side. Key the local
additions by whatever the fetch is keyed on (`T-CM-1` uses request *and*
page): once that changes, the server's next response already accounts for
them and keeping them shows them twice. `T-SC-1`'s "updates the stepper
without a full reload" is the same shape — the answer is this, not a
reload and not a second pending flash.

**Two resources on one page get two `Async` values, never one shared
pending flag.** The dashboard's request list and its `/statuses` filter
options have independent failure modes, and a slow `/statuses` must never
blank a table that already arrived.

Timestamps go through `src/lib/datetime.ts` (the one formatter) via the
`Timestamp` component, which is what guarantees the `<time dateTime={iso}>`
wrapper. No date library; `Intl.DateTimeFormat` covers it.

`Priority` and `StatusName` live in `src/lib/api.ts`, not in the pill
components — they're wire values, so the contract owns the vocabulary and
`StatusPill`/`PriorityPill` own only how it looks. Don't redeclare either
next to a component.

## Form pattern

Every form: `react-hook-form` + a `zod` schema colocated in `schemas/`,
named after the resource it mirrors. Build/reconcile the schema directly
from `specs/api-phase/requirements.md` this phase — there is still no
`openapi.yaml` in the repo; that forward-reference from the prototype
phase is retired, `requirements.md` is the permanent source of truth for
field constraints, not a placeholder for something else later.

On valid submit: call the matching `src/lib/api.ts` function, surface
`error.fields` per-field via `setError` on validation failure (see Error
surfacing), reset + success state on real success. The prototype's
"simulate success, no network call" behavior is retired page by page as
each is wired up in `tasks.md`.

## API client conventions

One module, `src/lib/api.ts`, not one file per resource — resources are
cheap to add as functions within it (`getServiceRequests()`,
`createComment()`, etc.); the cross-cutting behavior (`credentials:
'include'`, the `X-Requested-With` header on non-`GET` calls, a single
silent refresh-and-retry on `401`) is what needs centralizing, and
splitting by resource would mean re-implementing that per file.

Every function returns the parsed success body or throws a typed error
carrying `error.code` / `error.message` / `error.fields`. Callers branch on
`code`, never on `message` string content — messages can reword without
that being a breaking change; codes are the contract.

Exports are thin per-endpoint functions (`register`, `login`, `getMe`,
`logout`, and so on as later slices add them). The underlying fetch
wrapper stays module-private — that's what prevents a second client
growing alongside this one.

**Refresh-on-401 has a concurrency rule that must not be simplified away**
(learned in `T-AUTH-4`): concurrent `401`s must produce exactly one
refresh. A shared in-flight promise is _not_ enough — a `401` arriving
just after a refresh settles was generated against the already-replaced
token, and retrying it kicks off a second refresh. The client tracks a
session generation counter: a call captures it before sending, and a
`401` carrying a superseded generation retries directly rather than
refreshing again. This isn't premature optimization — the backend's
single-use token rotation (`AUTH-9`) plus family revocation on replay
(`AUTH-11`) means a redundant refresh can sign the user out of every
session for doing nothing wrong.

`/auth/login` and `/auth/refresh` are both excluded from refresh-retry.
`login` reads no cookie, so a refresh can't change whether a password is
correct, and firing one would rotate a signed-in user's tokens on someone
else's failed sign-in attempt.

## Auth state

`AuthContext` no longer owns `role` as local truth — it's a cache of what
`GET /auth/me` last returned, refreshed on mount and after login/logout.
Don't reintroduce a demo/bypass path "for testing" — if manual testing
needs a fast path, use a seeded test user through the real login flow, not
a code branch that skips it. (The prototype's "Continue as Admin" button
was exactly this kind of bypass, added for demo convenience — it's being
removed in `T-AUTH-5`, not carried forward in a new form.)

## Auth guard pattern

`routes.tsx` holds the route table plus a guard redirecting to `/login`
when there's no session, built in `T-DEBT-2`. `/login` and `/register` are
public; everything else requires a session.

**This guard is cosmetic only** — comment it as such at its definition.
Every real authorization check is server-side (`XC-6`, `XC-13`, `SR-1`,
`SC-4`, `CM-7` in `specs/api-phase/requirements.md`). The guard exists to
give signed-out users a login redirect instead of a screenful of `401`
errors, and for nothing else. Never let its presence become a reason to
weaken a server-side check, and never add a client-side check as the
_only_ gate on anything.

**The session has three states, not two.** `AuthContext` bootstraps via
`GET /auth/me`, so on first mount it is _pending_ — not yet known either
way. A guard that treats pending as signed-out doesn't merely flash the
login page: it bounces the signed-in user to `/login` and leaves them
there, since the bootstrap result arrives after the redirect has already
happened. Verified in `T-DEBT-2` by removing the guard clause and watching
it fail exactly that way. Render `null` while pending; only act once the
answer is known.

**Routes are guarded as a group, not with per-route wrappers**
(`routes.tsx`). A route added inside the guarded block is protected by
construction. Per-route wrappers invert that — protection becomes
something you must remember, and a future route ships unguarded by
omission. Don't refactor toward per-route wrappers for flexibility;
if one route genuinely needs different treatment, pull it out explicitly.

Redirects use `replace`, not `push` — a pushed redirect traps the user in
a Back-button loop.

**Not implemented, if it ever comes up**: there's no
return-to-intended-destination after login. A signed-out user deep-linking
to `/requests/abc` is bounced to `/login` and lands on `/` after signing
in, not back at `/requests/abc`. Deliberate omission, not an oversight —
add it as its own task if it's wanted, don't bolt it onto an unrelated
one.

## Error surfacing

`Field` (`components/ui/Field.tsx`) is the one shared wrapper driving
`error.fields` from a `422` into react-hook-form's `setError` per field —
extracted in `T-AUTH-5` from what was duplicated verbatim across
`LoginPage`/`RegisterPage`/`SubmitRequestPage` (`frontend-contract.md
§8.3`), with `SubmitRequestPage`'s copy retired in `T-SR-1`. Import it;
never redeclare it locally, however small the page's own diff looks.

For a `401` / `403` / `404` / `409` / `500` that isn't a field-level
validation error, surface `error.message` via `ErrorBanner`
(`components/ui/ErrorBanner.tsx`) — extracted in `T-SR-1` from
`RegisterPage`'s original post-submit banner once a second and third page
needed the same pattern. Import it; don't invent a second banner
component.

**If a task touches two pages that both need one of these patterns,
extract (or confirm the existing extraction covers it) in that same
task** — don't schedule the cleanup separately once you're already there.
This is how `Field` and `ErrorBanner` both got made; it's also exactly
the rule `SubmitRequestPage`'s local `Field` copy violated for a whole
phase before `T-SR-1` closed it.

## Naming

PascalCase components, camelCase functions/variables, one component per
file, filename matches component name.

**Exception, decided during `T-AUTH-0` review**: zod schemas and TS types
that mirror an API request or response body directly use **snake_case**
field names, matching the wire format exactly (`first_name`, `last_name`)
— no translation layer at the `api.ts` boundary. Everything else (local
component state, function names, non-API-shaped props) stays camelCase per
the rule above. If a schema is API-shaped, it's the exception; if it's
purely local, it isn't — don't let the exception creep into local-only
types "for consistency."

## Task workflow

One task from `tasks.md` per session (prototype or API phase, per whichever
is current). Implement, verify against that task's acceptance criteria
checklist, stop — do not start the next task in the same session. `/clear`
before starting the next task.

## Testing

Playwright (`e2e/`, set up in `T-DEBT-3`), run against the real running
stack — not mocks. This is deliberate, not a stopgap: `httpOnly` cookies
are invisible to JavaScript by design, so a mocked client cannot
meaningfully exercise the auth behavior that matters. MSW stays ruled out
(see Non-goals).

Test behavior, not implementation — what a user experiences, not which
functions got called. The exception is network-level assertions where the
behavior _is_ the network pattern: the refresh-concurrency rule is
verified by asserting one `/auth/refresh` for concurrent `401`s, because
that's the actual guarantee.

Apply `backend/CLAUDE.md`'s rule here too: **a test never observed to fail
is not verified, only written.** Remove the thing under test, confirm the
test goes red, restore it.

This has now caught a real defect three times, in three different
disguises — a tamper test that corrupted encoding rather than meaning
(`T-AUTH-1`), an assertion that computed its expectation from the constant
it was testing (`T-AUTH-3`), and a route handler that read a shared
counter back after an `await`, so the delay it existed to impose never
applied (`T-DEBT-3`). The pattern is always the same: **the test passes,
and keeps passing, without the thing it names ever being true.** Nothing
about reading the test reveals this — only removing the subject and
watching for red does. Treat the rule as load-bearing, not ceremonial;
this is especially true for any test involving timing, concurrency, or
shared mutable state in a route handler, where the failure mode is
invisible by construction.

Run with `npm run test:e2e`. Specs live in `src/e2e/`, with
`tsconfig.e2e.json` for Node types (and `src/e2e` excluded from
`tsconfig.app.json`, or the app build typechecks Node code). Runs
serially (`workers: 1`) — one real backend and database, and readable
failures beat a few saved seconds.

To exercise `api.ts` directly (no page fires two simultaneous calls),
import it by its dev-server URL `/src/lib/api.ts` — the same URL the app
imports, so it's the app's own client instance rather than a second copy.
Hold that URL in a variable or TS tries to resolve it as a module path.
To simulate an expired session without waiting an hour, drop the
`access_token` cookie from the browser context and keep `refresh_token`.

Tests seed their own data — register a fresh user per run rather than
depending on a hand-maintained account, which rots silently.

**An `admin` comes from `promoteToAdmin` (`e2e/fixtures.ts`), never from a
hand-promoted account.** There is no admin-promotion endpoint and
deliberately none (`AUTH-4` ignores a `role` in the register body), so the
helper runs the same `UPDATE users SET role = 'admin'` a person would, via
`docker compose exec db psql` from the repo root. It works because
`deps.py` re-reads `role` off the user row on every request rather than
trusting the token's claim — so promote *before* signing the browser in
(`AuthContext` caches what login returned) and it takes effect on the next
request. Built in `T-CM-1`; `SR-2`, `CM-3` and `CM-8` had all been checked
by hand against a manually promoted row until then. `registerViaApi` takes
an optional name for the same reason — every seeded user being
`Playwright Runner` would have let a column rendering the wrong person's
name pass.

**Asserting that something became visible is not asserting how.** `T-CM-1`'s
"appends without a full page reload" criterion is invisible to a
visibility assertion — a `window.location.reload()` after the POST ends
with the comment on screen too. The spec sets a `window` sentinel before
posting and re-reads it after; only a document navigation clears it.
Whenever a criterion names a *mechanism* rather than an outcome, find the
assertion that fails when the mechanism changes and the outcome doesn't.

## Non-goals for this phase

- No fetch calls outside `src/lib/api.ts`; still no MSW, no mock server,
  no TanStack Query
- No client-side caching or optimistic updates
- No Landing/Home page, no dedicated Admin page — out of scope, per
  `specs/api-phase/tasks.md`

~~No real authentication or password checking~~ — **retired this phase**,
see Auth state.
~~No persistence of any kind across page reloads~~ — **retired this
phase**, session now persists via `GET /auth/me`.
~~No `routes.tsx` route guard work~~ — **retired at the Group 1
checkpoint**, built in `T-DEBT-2`.
