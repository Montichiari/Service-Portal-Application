# Phase 2 — Frontend Requirements (EARS-style)

Scope: 6 pages, no live/mock backend. Validation is fully real; submission
outcomes are simulated per `design.md`'s per-page data strategy.

---

## 1. Login (`/login`)

**Fields:** Email (text), Password (text, masked)

**Validation**

- WHEN the user submits, THE SYSTEM SHALL require Email to be a non-empty,
  valid email format.
- WHEN the user submits, THE SYSTEM SHALL require Password to be non-empty.
- IF either field is invalid, THEN THE SYSTEM SHALL display an inline error
  under that field and SHALL NOT navigate away.
  **Success behavior**
- Standard submit is never actually validated against real credentials —
  no account check exists. Treat any valid-format submit as informational
  only; the primary path through this page is the demo shortcuts below.
  **Demo shortcuts**
- WHEN the user selects "Continue as User", THE SYSTEM SHALL set role=user
  in the auth context and navigate to `/` without field validation.
- WHEN the user selects "Continue as Admin", THE SYSTEM SHALL set role=admin
  in the auth context and navigate to `/` without field validation.

---

## 2. Register (`/register`)

**Fields:** Full name, Email, Password, Confirm password

**Validation**

- WHEN the user submits, THE SYSTEM SHALL require Full name to be non-empty.
- WHEN the user submits, THE SYSTEM SHALL require Email to be a valid email
  format.
- WHEN the user submits, THE SYSTEM SHALL require Password to be at least 8
  characters.
- WHEN the user submits, THE SYSTEM SHALL require Confirm password to match
  Password exactly.
- IF any field is invalid, THEN THE SYSTEM SHALL display an inline error
  under that field and SHALL NOT proceed.
  **Success behavior**
- WHEN all fields are valid, THE SYSTEM SHALL display a success banner
  ("Account created — please sign in") and navigate to `/login` after a
  brief delay. No account is persisted anywhere.

---

## 3. Submit Service Request (`/requests/new`)

**Fields:** Request type (select, disabled), Title, Description, Priority
(select)

**Note:** `request_type` is fixed to `"general"` for this demo — the full
set of request types and their type-specific metadata fields has not yet
been decided (Phase 1 JSONB `metadata` design is still open). The Request
Type field is shown but **disabled**, displaying "General" as its only
option — a visible placeholder for the type selector this will become once
additional types are designed, rather than an interactive field. This is a
deliberate, temporary simplification — see `specs/phase-2/tasks.md` Task 4
note.

**Validation**

- Request type is disabled and always has the value `general` — it is
  excluded from validation and from user interaction entirely.
- WHEN the user submits, THE SYSTEM SHALL require Title to be non-empty,
  max 100 characters.
- WHEN the user submits, THE SYSTEM SHALL require Description to be
  non-empty, max 1000 characters.
- WHEN the user submits, THE SYSTEM SHALL require Priority to be selected
  from `low`, `medium`, `high`.
- IF any field is invalid, THEN THE SYSTEM SHALL display an inline error
  under that field and SHALL NOT clear the form.
  **Success behavior**
- WHEN all fields are valid, THE SYSTEM SHALL clear the form and display a
  success banner ("Request submitted"). No request is persisted or added to
  the Requests Dashboard.

---

## 4. Requests Dashboard (`/`)

**Data:** Hardcoded array, 4-5 requests, statuses varied across Open, In
Progress, Resolved, Closed.

**Behavior**

- THE SYSTEM SHALL display each request's title, status (as `StatusPill`),
  and last-updated relative time in a table row.
- WHEN the user selects a row, THE SYSTEM SHALL navigate to
  `/requests/:id` for that request.
- WHEN the user selects "New request", THE SYSTEM SHALL navigate to
  `/requests/new`.
- No validation on this page (read-only view).

---

## 5. View Request Details (`/requests/:id`)

**Data:** Hardcoded single request object, including 2 read-only comments.

**Behavior**

- THE SYSTEM SHALL display request title, current status (`StatusPill`),
  type, priority (`PriorityPill`), description, submitted-date, and
  comments list.
- WHEN the user selects "View full history", THE SYSTEM SHALL navigate to
  `/requests/:id/status`.
- THE SYSTEM SHALL NOT provide an add-comment control on this page (reserved
  for the separate admin-only page, out of scope for these 6).
- No validation on this page (read-only view).

---

## 6. Track Request Status (`/requests/:id/status`)

**Data:** Hardcoded `status_history` array (status, timestamp) for one
request.

**Behavior**

- THE SYSTEM SHALL render each history entry as a step in a vertical
  `Timeline`, in chronological order.
- THE SYSTEM SHALL mark reached steps as filled and the current/pending
  step(s) as hollow.
- WHEN the user selects "Back to request details", THE SYSTEM SHALL
  navigate to `/requests/:id`.
- No validation on this page (read-only view).

---

## Cross-cutting

- THE SYSTEM SHALL apply `design-tokens.md` color/type/layout values
  consistently across all 6 pages.
- THE SYSTEM SHALL guard all in-app routes (`/`, `/requests/*`) and redirect
  to `/login` IF no role is set in the auth context. This guard is cosmetic
  only — no server exists yet to enforce it.
- THE SYSTEM SHALL use `zod` schemas mirroring the corresponding
  `openapi.yaml` request-body schema for every form where such a schema
  exists, even though no request is sent, so Phase 3 requires no schema
  rewrite. `openapi.yaml` does not currently exist in the repo — Login and
  Register schemas are built directly from this document's field lists
  instead. The Submit Service Request schema (section 3) reflects a
  deliberately minimal, temporary field set pending the full request-type
  design.
