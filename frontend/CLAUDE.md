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
                    # StatusPill, PriorityPill, Timeline
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
                    # tasks.md is done is a bug, not a leftover
  lib/
    api.ts           # the one sanctioned fetch client (built T-AUTH-4).
                    # Exports thin per-endpoint functions; the fetch
                    # wrapper itself is module-private by design.
  routes.tsx         # CONFIRMED NOT PRESENT. Documented in the prototype
                    # spec below (Auth guard pattern) as if it existed,
                    # but Task 3 was never landed — routing is inline in
                    # App.tsx instead, unguarded. Don't treat this entry
                    # as current; kept here as a record of the gap.
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
  (`frontend-contract.md §8.2`/§8.4) — establish the pattern once, in the
  first task that needs it (`T-SR-1`), then reuse everywhere. Don't invent
  a second pattern later.

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

Prototype spec (above, retained for history): route guard in `routes.tsx`
redirects to `/login` if `role` is null, commented as cosmetic-only since
real enforcement is server-side.

**Confirmed: `routes.tsx` does not exist.** Routing is inline in `App.tsx`
and unguarded — the prototype spec above described intent, not what got
built (Task 3 debt). `specs/api-phase/tasks.md` deliberately does not build
or fix this in the current phase: every real authorization check happens
server-side (`XC-6`, `SC-4`, `CM-7` in `specs/api-phase/requirements.md`),
so the missing client-side guard is a UX gap, not a security one. `T-AUTH-0`
no longer needs to re-verify this specific fact — it's settled — but should
still check the rest of its scope (the five auth-related files) fresh.

## Error surfacing

Use the `error.fields` map from a `422` to drive react-hook-form's
`setError` per field, matching the existing `Field` wrapper component
pattern (duplicated verbatim across `LoginPage`, `RegisterPage`,
`SubmitRequestPage` per `frontend-contract.md §8.3`). **If a task touches
two of those three pages, extract the shared component in that same task**
— don't schedule the cleanup separately once you're already there.

For a `401` / `403` / `404` / `409` / `500` that isn't a field-level
validation error, surface `error.message` as a page-level banner — reuse
whatever banner pattern `RegisterPage`'s existing post-submit banner
established, don't invent a second banner component.

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

## Non-goals for this phase

- No fetch calls outside `src/lib/api.ts`; still no MSW, no mock server,
  no TanStack Query
- No `routes.tsx` route guard work — it doesn't exist (confirmed), and
  this phase doesn't build it (see Auth guard pattern)
- No client-side caching or optimistic updates
- No Landing/Home page, no dedicated Admin page — out of scope, per
  `specs/api-phase/tasks.md`

~~No real authentication or password checking~~ — **retired this phase**,
see Auth state.
~~No persistence of any kind across page reloads~~ — **retired this
phase**, session now persists via `GET /auth/me`.
