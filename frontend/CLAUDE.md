# frontend/CLAUDE.md

Persistent context for Claude Code sessions working in `frontend/`. Read
this before starting any task from `specs/frontend-phase/tasks.md`.

## Project context

Internal IT service portal, capstone project. This phase builds 6 pages of
UI only — **no live or mocked backend service.** Forms validate fully and
either simulate success (reset + banner) or navigate; list/detail pages
render hardcoded data. Do not add a fetch client, MSW, or any network call
in this phase — see Non-goals below.

## Spec files (source of truth — do not restate their contents inline in

code comments, reference them instead)

- `specs/frontend-phase/design-tokens.md` — color, type, layout tokens
- `specs/frontend-phase/design.md` — routing, nav, component inventory, per-page
  data strategy
- `specs/frontend-phase/requirements.md` — field lists, validation rules,
  EARS-style behavior per page
- `specs/frontend-phase/tasks.md` — the 6 ordered tasks and their acceptance
  criteria

## Tech stack

React + TypeScript + Vite · `react-hook-form` + `zod` · `shadcn/ui` ·
`react-router` for routing. No TanStack Query yet (nothing to fetch).

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
  schemas/          # zod schemas, one file per form. Built from
                    # requirements.md this phase; no openapi.yaml in the
                    # repo yet — ignore that mirroring note until one is
                    # added in a later phase, then reconcile (see Form
                    # pattern)
  context/
    AuthContext.tsx  # role state only, no real auth
  data/              # hardcoded mock objects/arrays used by read-only pages
  routes.tsx         # route table + auth guard
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
  the color directly.
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
  - Detail views: 720px — same pattern, class added with Task 6.
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

## Form pattern

Every form: `react-hook-form` + a `zod` schema colocated in `schemas/`,
named after the resource it mirrors. Where `requirements.md` fully
specifies a form's fields and validation (current state for all forms in
this phase — there is no `openapi.yaml` in the repo yet), build the schema
directly from `requirements.md`. If `openapi.yaml` is added in a later
phase, schemas should be reconciled against it then. This is what prevents
a schema rewrite when Phase 3 wires up the real backend. On valid submit:
reset form, show success state, no network call, no console-logged "would
submit" stub.

## Auth guard pattern

`AuthContext` holds only a `role: 'user' | 'admin' | null`. Route guard in
`routes.tsx` redirects to `/login` if `role` is null. This guard is
**cosmetic only** — comment it as such at the point it's implemented. It
will never be the real enforcement layer; that's server-side in Phase 3.

## Naming

PascalCase components, camelCase functions/variables, one component per
file, filename matches component name.

## Task workflow

One task from `tasks.md` per session. Implement, verify against that task's
acceptance criteria checklist, stop — do not start the next task in the same
session. `/clear` before starting the next task.

## Non-goals for this phase

- No fetch calls, no MSW, no mock server, no TanStack Query
- No real authentication or password checking
- No Landing/Home page, no Admin page (out of scope — see `tasks.md`)
- No persistence of any kind across page reloads
