# frontend/CLAUDE.md

Persistent context for Claude Code sessions working in `frontend/`. Read
this before starting any task from `specs/phase-2/tasks.md`.

## Project context

Internal IT service portal, capstone project. This phase builds 6 pages of
UI only — **no live or mocked backend service.** Forms validate fully and
either simulate success (reset + banner) or navigate; list/detail pages
render hardcoded data. Do not add a fetch client, MSW, or any network call
in this phase — see Non-goals below.

## Spec files (source of truth — do not restate their contents inline in

code comments, reference them instead)

- `specs/phase-2/design-tokens.md` — color, type, layout tokens
- `specs/phase-2/design.md` — routing, nav, component inventory, per-page
  data strategy
- `specs/phase-2/requirements.md` — field lists, validation rules,
  EARS-style behavior per page
- `specs/phase-2/tasks.md` — the 6 ordered tasks and their acceptance
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
  schemas/          # zod schemas, one file per form, mirroring
                    # openapi.yaml request bodies
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

## Form pattern

Every form: `react-hook-form` + a `zod` schema colocated in `schemas/`,
named after the resource it mirrors (e.g. `submitRequestSchema.ts` mirrors
the `ServiceRequest` creation body in `openapi.yaml`). This mirroring is
required even though no request is sent — it's what prevents a schema
rewrite when Phase 3 wires up the real backend. On valid submit: reset form,
show success state, no network call, no console-logged "would submit" stub.

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
