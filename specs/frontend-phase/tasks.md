# Phase 2 — Tasks

Each task = one Claude Code prompt = one commit, after manual review. Do not
combine tasks. `/clear` between tasks per project convention. Every task
should reference `design-tokens.md`, `design.md`, and `requirements.md`
directly rather than restating their contents in the prompt.

---

## Task 1 — Design system + app shells

**Builds:** `Button`, `TextInput`, `Select`, `Textarea`, `StatusPill`,
`PriorityPill`, `Card`, `Table`, `Timeline`, `AppShell` (sidebar + content),
`AuthShell` (centered card).

**Depends on:** nothing (foundation task).

**Acceptance criteria**

- [ ] All colors/type/spacing pulled from `design-tokens.md` tokens, no
      inline hex values or ad-hoc sizes in components.
- [ ] `StatusPill` and `PriorityPill` correctly render every state listed in
      `design-tokens.md`'s status/priority tables.
- [ ] `AppShell` renders the two-item nav (Requests Dashboard, Submit
      Request) per `design.md`'s routing table; no "My Requests" item.
- [ ] Cards are flat (hairline border, no shadow, ≤4px radius) per tokens.
- [ ] Components render correctly with no real routes/pages wired yet
      (can be verified via a temporary Storybook-style page or App.tsx stub).

---

## Task 2 — Login / Register pages

**Builds:** `/login`, `/register`, auth context (role state only, no real
auth), demo shortcut buttons.

**Depends on:** Task 1 (`AuthShell`, form primitives, `Button`).

**Acceptance criteria**

- [ ] Login and Register field lists, validation rules, and error display
      match `requirements.md` sections 1-2 exactly.
- [ ] "Continue as User" / "Continue as Admin" bypass validation and set
      role in context, per requirements.
- [ ] Register success path shows banner, then redirects to `/login`; no
      data persisted.
- [ ] Both pages use `AuthShell`, not `AppShell`.
- [ ] zod schemas mirror the relevant `openapi.yaml` request bodies.

---

## Task 3 — Routing + auth guard

**Builds:** Route table wiring (`react-router` or equivalent), cosmetic
guard redirecting unauthenticated access on in-app routes to `/login`.

**Depends on:** Task 2 (auth context must exist to guard against).

**Acceptance criteria**

- [ ] All 6 routes in `design.md`'s routing table resolve correctly.
- [ ] Visiting any `/requests/*` route or `/` without a role set redirects
      to `/login`.
- [ ] Guard logic is clearly commented as cosmetic-only / not real security,
      consistent with the project's server-is-sole-trust-boundary principle.
- [ ] No route currently exists for the two out-of-scope pages (Landing,
      Admin) — do not stub them.

---

## Task 4 — Submit Service Request

**Builds:** `/requests/new` form.

**Depends on:** Task 1 (form primitives), Task 3 (route + guard exist).

**Implementation note — disabled Request Type select:** the `Select`
primitive is built on Radix, which reads the displayed label from the
matching `SelectItem` inside `SelectContent` — `<SelectValue />` alone will
not render "General" without `<SelectItem value="general">General
</SelectItem>` present. For the disabled state, use either an uncontrolled
`defaultValue="general"` or, if react-hook-form drives it via `Controller`,
`value="general"` — both render the value correctly while `disabled`.

**Acceptance criteria**

- [ ] Field list (Request type — disabled, Title, Description, Priority)
      and validation rules match `requirements.md` section 3 exactly.
- [ ] Request Type renders as a disabled select showing "General" as its
      only option — not editable, not part of validation.
- [ ] Valid submit clears the form and shows success banner; no data is
      persisted or sent anywhere.
- [ ] zod schema covers Title, Description, Priority only (request_type
      is a fixed constant, not a validated form field) — do not add a
      `metadata`/JSONB field or conditional fields. This is a known,
      deliberate simplification pending the full request-type design from
      Phase 1; do not treat its absence as an oversight to fix.

---

## Task 5 — Requests Dashboard

**Builds:** `/` page.

**Depends on:** Task 1 (`Table`, `StatusPill`), Task 3 (route + guard).

**Acceptance criteria**

- [ ] 4-5 hardcoded requests rendered, statuses covering Open, In Progress,
      Resolved, Closed per `requirements.md` section 4.
- [ ] Row click navigates to `/requests/:id` with that request's id.
- [ ] "New request" navigates to `/requests/new`.
- [ ] Table styling matches `design.md` (rule-separated rows, not per-row
      cards).
- [ ] Content bounded to the 1040px table/dashboard max-width from
      `design-tokens.md`, left-aligned. Verified at both ~1280px and
      ~375px viewport widths — table remains usable (not overflowing
      unreadably or requiring horizontal scroll to see the primary
      columns) at mobile width.

---

## Task 6 — View Request Details + Track Request Status

**Builds:** `/requests/:id`, `/requests/:id/status`.

**Depends on:** Task 1 (`Timeline`, pills, `Card`), Task 3 (routes + guard).

**Acceptance criteria**

- [ ] Details page renders one hardcoded request with 2 read-only comments,
      per `requirements.md` section 5. No add-comment control present.
- [ ] "View full history" link navigates to `/requests/:id/status`.
- [ ] Status page renders a hardcoded `status_history` array as a vertical
      `Timeline`, filled/hollow states correct, per section 6.
- [ ] "Back to request details" link returns to `/requests/:id`.
- [ ] Both pages read-only — no form validation present.
- [ ] Content bounded to the 720px detail-view max-width from
      `design-tokens.md`, left-aligned. Verified at both ~1280px and
      ~375px viewport widths on both pages.

---

## Out of scope for this task list

Landing/Home page and the Admin demo page are excluded per current demo
scope (6 pages only) — do not let Claude Code scaffold routes or nav items
for them as a side effect of any task above.
