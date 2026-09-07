# Phase 2 — Frontend Design Spec

Scope: 6 pages for demo. No live/mock backend — hardcoded data per page
(strategy noted per page below). Visual tokens: see `design-tokens.md`.

## Routing table

| Route                  | Page                   | Auth required | Nav visible         |
| ---------------------- | ---------------------- | ------------- | ------------------- |
| `/login`               | Login                  | No            | No (centered shell) |
| `/register`            | Register               | No            | No (centered shell) |
| `/`                    | Requests Dashboard     | Yes           | Yes                 |
| `/requests/new`        | Submit Service Request | Yes           | Yes                 |
| `/requests/:id`        | View Request Details   | Yes           | Yes                 |
| `/requests/:id/status` | Track Request Status   | Yes           | Yes                 |

Auth is a cosmetic guard only (redirect to `/login` if no role in context) —
consistent with the project's server-is-sole-trust-boundary principle; there
is no server yet to actually enforce anything.

## Navigation (sidebar, in-app pages only)

Two top-level items:

- **Requests Dashboard** (`/`) — also the landing page post-login
- **Submit Request** (`/requests/new`)
  No separate "My Requests" — Requests Dashboard is the one list view.

## Component inventory

Shared (build first, task 1):

- `AppShell` — sidebar + content area wrapper (used by all in-app pages)
- `AuthShell` — centered card wrapper (Login/Register only)
- `Button` (primary / secondary variants)
- `TextInput`, `Select`, `Textarea` — form primitives, `react-hook-form`-bound
- `StatusPill` — maps a status value to the color table in `design-tokens.md`
- `PriorityPill` — same pattern, priority palette
- `Card`
- `Table` (header row + rule-separated rows, no per-row card treatment)
- `Timeline` — vertical stepper, filled/hollow dot states (Track Status page)

## Form architecture

`react-hook-form` + `zod` for every form. Schemas mirror the existing
Pydantic models from `openapi.yaml` field-for-field, even though no request
is actually sent — this is what keeps Phase 3 from requiring a schema
rewrite. Each schema lives colocated with its form component.

Forms in scope: Login, Register, Submit Service Request.
On valid submit: reset form, show success banner, no network call.

## Per-page data strategy

| Page                   | Data                           | Notes                                                          |
| ---------------------- | ------------------------------ | -------------------------------------------------------------- |
| Login                  | none                           | demo shortcut buttons set role in context, skip validation     |
| Register               | none                           | validates fully, submit → success message → redirect to Login  |
| Submit Service Request | none                           | validates fully, submit → reset + success banner               |
| Requests Dashboard     | hardcoded array (4-5 rows)     | vary status values so `StatusPill` colors are all demonstrated |
| View Request Details   | hardcoded single object        | includes 2 read-only comments                                  |
| Track Request Status   | hardcoded status_history array | drives `Timeline` component                                    |

## Page layouts

See wireframes as agreed in chat (Login, Register, Submit Service Request,
Requests Dashboard, View Request Details, Track Request Status). Structural
decision on record: Track Request Status is its own route, not a tab on View
Request Details — it represents the `status_history` audit trail and is
treated as a first-class record, not a sub-view.
