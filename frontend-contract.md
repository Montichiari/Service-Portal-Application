# Frontend Contract (as-is)

What the frontend **currently assumes** about each entity, extracted from
source under `frontend/src/` on branch `feature/backend` (frontend last touched
by `d027439`, Task 6). This is a description, not a proposal — nothing here is
reconciled against the backend models, and internal contradictions are flagged
rather than resolved.

Every claim cites the file it came from. Where an entity's shape is *absent*
from the code, that absence is recorded as the finding.

---

## 0. Scope note: there is no API layer

Before the per-entity sections, the single most important fact about this
contract: **the frontend makes no network calls and has no API client.**

- Zero `fetch(`, `axios`, or `XMLHttpRequest` occurrences in `frontend/src/`
  (verified by grep across all `.ts`/`.tsx`).
- No `src/api/`, no `src/services/`, no `src/types/` directory exists. Entity
  shapes live in `src/data/*.ts` fixtures and in two UI components.
- No TanStack Query, SWR, or any data-fetching dependency in
  [package.json](frontend/package.json) — `dependencies` are React, router,
  react-hook-form, zod, Radix Select, Tailwind, lucide, fontsource only.
- `VITE_API_URL` **is declared and configured but never read.** It is typed in
  [vite-env.d.ts:4](frontend/src/vite-env.d.ts#L4), set to
  `http://localhost:8000` in both `frontend/.env` and `frontend/.env.example`,
  and documented in [frontend/README.md](frontend/README.md) — but
  `import.meta.env` appears nowhere in `src/`.

This is deliberate and enforced by
[frontend/CLAUDE.md:127](frontend/CLAUDE.md#L127) ("No fetch calls, no MSW, no
mock server, no TanStack Query"). Consequence for this document: **there are no
URL patterns, HTTP verbs, request/response envelopes, or error-body shapes to
extract.** Sections below marked *"No assumption encoded"* mean the code
commits to nothing, not that it commits to a default.

---

## 1. User

### 1.1 There is no `User` type

No interface, type alias, or fixture named `User` exists anywhere in
`frontend/src/`. The frontend has never modelled a user as an entity. What
exists instead is three disconnected fragments:

| Fragment | Source | Fields |
| --- | --- | --- |
| Session identity | [AuthContext.tsx:16](frontend/src/context/AuthContext.tsx#L16) | `role: 'user' \| 'admin' \| null` — and nothing else |
| Registration input | [registerSchema.ts:10-20](frontend/src/schemas/registerSchema.ts#L10-L20) | `fullName`, `email`, `password`, `confirmPassword` |
| Login input | [loginSchema.ts:15-18](frontend/src/schemas/loginSchema.ts#L15-L18) | `username`, `password` |

### 1.2 Session shape

```ts
// context/AuthContext.tsx:16-21
export type Role = 'user' | 'admin' | null

interface AuthContextValue {
  role: Role
  setRole: (role: Role) => void
}
```

The **entire** authenticated-session surface is one nullable string union. There
is no user id, no display name, no email, no permissions array, no token, no
expiry. `null` role is the signed-out state.

State is plain `useState` ([AuthContext.tsx:26](frontend/src/context/AuthContext.tsx#L26)),
so the session is in-memory and lost on reload — stated explicitly at
[AuthContext.tsx:5-8](frontend/src/context/AuthContext.tsx#L5-L8).

### 1.3 Registration field constraints

From [registerSchema.ts](frontend/src/schemas/registerSchema.ts):

| Field | Type | Constraints | Message |
| --- | --- | --- | --- |
| `fullName` | string | `.trim().min(1)` | "Enter your full name" |
| `email` | string | `z.email()` (zod v4 top-level email) | "Enter a valid email address" |
| `password` | string | `.min(8)` — **not trimmed** | "Password must be at least 8 characters" |
| `confirmPassword` | string | `.min(1)`, plus object-level `.refine` for exact equality with `password`, error pathed to `confirmPassword` | "Re-enter your password" / "Passwords do not match" |

Note what is **not** constrained: no max length on any field, no password
complexity rule beyond length, no email normalization/lowercasing, no username
field, no role selection at registration, no terms checkbox.

`fullName` is a **single combined name field** — no `first_name`/`last_name`
split is assumed anywhere in the frontend.

### 1.4 ⚠️ Inconsistency: register collects `email`, login authenticates `username`

The two auth forms do not share an identifier field:

- Register asks for `email` ([registerSchema.ts:13](frontend/src/schemas/registerSchema.ts#L13)),
  input `type="email"` with `autoComplete="email"`
  ([RegisterPage.tsx:90-96](frontend/src/pages/RegisterPage.tsx#L90-L96)).
- Login asks for `username` ([loginSchema.ts:16](frontend/src/schemas/loginSchema.ts#L16)),
  input with `autoComplete="username"`, **no** `type="email"` and no format
  validation ([LoginPage.tsx:78-83](frontend/src/pages/LoginPage.tsx#L78-L83)).

Nothing in the frontend maps one to the other. The schema's own header comment
at [loginSchema.ts:3-13](frontend/src/schemas/loginSchema.ts#L3-L13) flags this
as a deliberate divergence from `requirements.md` section 1 (which specifies an
email) made for the demo credential check — but the divergence is real in the
code and unresolved. **Flagged, not resolved.**

### 1.5 ⚠️ `role` is written but never read

`useAuth()` is consumed in exactly one file, `LoginPage`, and only for its
setter ([LoginPage.tsx:23](frontend/src/pages/LoginPage.tsx#L23) destructures
`{ setRole }` alone). No component anywhere reads `role`. Grep for `useAuth`
across `src/` returns only `AuthContext.tsx` and `LoginPage.tsx`.

So the `'user' | 'admin'` distinction currently has **no observable effect** on
any rendered output — no conditional nav, no admin-only UI, no guard.

### 1.6 ⚠️ `frontend/CLAUDE.md` documents a `routes.tsx` that does not exist

[frontend/CLAUDE.md:54](frontend/CLAUDE.md#L54) and
[:108-112](frontend/CLAUDE.md#L108-L112) describe `src/routes.tsx` holding a
route table plus a role-based guard redirecting to `/login`. **That file is not
in the repo.** Routing is inline in [App.tsx:29-36](frontend/src/App.tsx#L29-L36)
and every route is unguarded. [App.tsx:20-24](frontend/src/App.tsx#L20-L24)
confirms Task 3 was never landed. Treat the CLAUDE.md description as intent,
not as current state.

---

## 2. Auth / RefreshToken

### 2.1 No token model exists — at all

Grep across `frontend/src/` for `token`, `Bearer`, `refresh`, `localStorage`,
`sessionStorage`, `Authorization` returns **only prose in code comments**
(e.g. "no credentials, no token, no persistence" at
[AuthContext.tsx:6](frontend/src/context/AuthContext.tsx#L6)) and unrelated
Tailwind design-token comments. There is no:

- access token or refresh token field, type, or storage
- token expiry / `expires_at` / TTL concept
- `Authorization` header construction
- refresh-on-401 interceptor or retry
- logout call, token revocation, or session-clear path (there is no sign-out
  control in `AppShell` at all — its nav is exactly two links,
  [AppShell.tsx:26-29](frontend/src/components/shell/AppShell.tsx#L26-L29))

**No assumption encoded.** The frontend imposes zero constraints on a
RefreshToken shape because it has never represented one.

### 2.2 What "login" actually does

Two independent, unrelated sign-in paths exist on the same page:

**Path A — credential form** ([LoginPage.tsx:31-40](frontend/src/pages/LoginPage.tsx#L31-L40)):

```ts
const DEMO_USERNAME = 'username'   // LoginPage.tsx:18
const DEMO_PASSWORD = 'password'   // LoginPage.tsx:19

if (values.username === DEMO_USERNAME && values.password === DEMO_PASSWORD) {
  setRole('user')
  navigate('/requests/new')
  return
}
setRejected(true)
```

Plain `===` against two module constants. Always yields role `'user'`. Lands on
`/requests/new`.

**Path B — demo role buttons** ([LoginPage.tsx:45-48](frontend/src/pages/LoginPage.tsx#L45-L48),
rendered [:108-124](frontend/src/pages/LoginPage.tsx#L108-L124)):

```ts
function continueAs(role: Role) {
  setRole(role)
  navigate('/')
}
```

"Continue as User" / "Continue as Admin" set the role directly and land on `/`.
This path **bypasses the credential check entirely** and is the only way to
obtain the `'admin'` role.

⚠️ The two paths disagree on post-login destination (`/requests/new` vs `/`) —
flagged as an internal inconsistency.

### 2.3 What "register" actually does

Nothing is created or stored. On valid submit
([RegisterPage.tsx:40-44](frontend/src/pages/RegisterPage.tsx#L40-L44)) it only
sets `submitted`, which shows a banner and schedules
`navigate('/login')` after `REDIRECT_DELAY_MS = 1500`
([RegisterPage.tsx:16](frontend/src/pages/RegisterPage.tsx#L16),
[:28-38](frontend/src/pages/RegisterPage.tsx#L28-L38)). The collected
`fullName`/`email`/`password` values are **discarded** — they are never read out
of the form. Registration does not set a role, so a newly "registered" user is
still signed out.

---

## 3. ServiceRequest

### 3.1 ⚠️ Two different shapes for the same entity

The list view and the detail view use **separate, non-overlapping-in-part**
interfaces. Neither is derived from the other and there is no shared base type.

**List shape** — [mockRequests.ts:14-19](frontend/src/data/mockRequests.ts#L14-L19):

```ts
export interface MockRequest {
  id: string
  title: string
  status: Status
  lastUpdated: string
}
```

**Detail shape** — [mockRequestDetail.ts:25-34](frontend/src/data/mockRequestDetail.ts#L25-L34):

```ts
export interface MockRequestDetail {
  id: string
  title: string
  status: Status
  request_type: 'general'
  priority: Priority
  description: string
  submittedDate: string
  comments: RequestComment[]
}
```

Field-by-field comparison:

| Field | List (`MockRequest`) | Detail (`MockRequestDetail`) |
| --- | --- | --- |
| `id` | ✅ string | ✅ string |
| `title` | ✅ string | ✅ string |
| `status` | ✅ `Status` | ✅ `Status` |
| `lastUpdated` | ✅ string | ❌ **absent** |
| `submittedDate` | ❌ **absent** | ✅ string |
| `priority` | ❌ absent | ✅ `Priority` |
| `description` | ❌ absent | ✅ string |
| `request_type` | ❌ absent | ✅ `'general'` |
| `comments` | ❌ absent | ✅ nested array |

⚠️ The two views share **no timestamp field whatsoever**. The list knows only
when a request was last updated; the detail knows only when it was submitted.
A single API response satisfying both would need both fields, and the frontend
never states that.

### 3.2 `id` is a numeric-looking string

Fixture values are `'4271'`, `'4268'`, `'4259'`, `'4245'`, `'4238'`
([mockRequests.ts:21-52](frontend/src/data/mockRequests.ts#L21-L52)) — quoted
strings of 4 digits, **not** numbers and **not** UUIDs.

Used as:
- URL segment: `` navigate(`/requests/${request.id}`) ``
  ([RequestsDashboardPage.tsx:62](frontend/src/pages/RequestsDashboardPage.tsx#L62))
- React list key ([RequestsDashboardPage.tsx:61](frontend/src/pages/RequestsDashboardPage.tsx#L61))
- Displayed to the user with a `#` prefix: `Request #{requestId}`
  ([RequestDetailsPage.tsx:34](frontend/src/pages/RequestDetailsPage.tsx#L34))

The `#`-prefixed display strongly implies a human-facing sequential ticket
number rather than an opaque id, but the type is only `string`.

### 3.3 ⚠️ Mixed naming convention inside one interface

`MockRequestDetail` mixes snake_case and camelCase in adjacent fields
([mockRequestDetail.ts:25-34](frontend/src/data/mockRequestDetail.ts#L25-L34)):

- `request_type` — snake_case
- `submittedDate` — camelCase
- `lastUpdated` (sibling interface) — camelCase

`request_type` is also the snake_case name used in the file's own prose and in
`STATUS_HISTORY_LABELS`-adjacent commentary. This is the only snake_case field
in the frontend codebase. Flagged as-is.

### 3.4 All dates are pre-formatted display strings

No `Date` object, ISO-8601 string, epoch number, or date parsing exists
anywhere in the frontend. Every temporal value is a human-readable string
rendered verbatim:

| Field | Example value | Source |
| --- | --- | --- |
| `lastUpdated` | `'2h ago'`, `'1d ago'`, `'1w ago'` | [mockRequests.ts:26](frontend/src/data/mockRequests.ts#L26), [:38](frontend/src/data/mockRequests.ts#L38), [:50](frontend/src/data/mockRequests.ts#L50) |
| `submittedDate` | `'4 Sep 2026'` | [mockRequestDetail.ts:42](frontend/src/data/mockRequestDetail.ts#L42) |
| comment `timestamp` | `'4 Sep 2026, 14:10'` | [mockRequestDetail.ts:57](frontend/src/data/mockRequestDetail.ts#L57) |
| history `timestamp` | `'4 Sep 2026, 09:12'` | [mockStatusHistory.ts:38](frontend/src/data/mockStatusHistory.ts#L38) |

Note the three **distinct formats** (relative / date-only / date-with-time) for
what are all nominally timestamps. Both fixture headers call this out as
intentional for the phase ([mockRequests.ts:10-12](frontend/src/data/mockRequests.ts#L10-L12),
[mockRequestDetail.ts:16-18](frontend/src/data/mockRequestDetail.ts#L16-L18)) —
there is no formatting layer to move them to.

### 3.5 No user relation on a request

There is **no** `requester`, `submitted_by`, `owner`, `assignee`,
`assigned_to`, or any user-bearing field on either request shape. Nothing in
the frontend links a request to a user.

The only hint of assignment lives in a hardcoded UI label —
`assigned: 'Assigned to IT Service Desk'`
([mockStatusHistory.ts:31](frontend/src/data/mockStatusHistory.ts#L31)) — where
the team name is baked into the label string, not carried as data.

### 3.6 `request_type` is a single-member literal union

Typed as `request_type: 'general'`
([mockRequestDetail.ts:29](frontend/src/data/mockRequestDetail.ts#L29)) — a
literal, not an enum with alternatives.

- Its label map lives in the **page**, not the data module:
  `const REQUEST_TYPE_LABELS = { general: 'General' } as const`
  ([RequestDetailsPage.tsx:23](frontend/src/pages/RequestDetailsPage.tsx#L23)) —
  inconsistent with `Status`/`Priority`, whose label maps live beside their
  types in the pill components.
- On the submit form it is rendered as a **disabled** Radix Select with
  `defaultValue="general"` and exactly one item, deliberately excluded from
  form state and from the zod schema
  ([SubmitRequestPage.tsx:100-117](frontend/src/pages/SubmitRequestPage.tsx#L100-L117)).
- [submitRequestSchema.ts:12-18](frontend/src/schemas/submitRequestSchema.ts#L12-L18)
  explicitly warns this is a temporary simplification and specifically warns
  against "fixing" it with a metadata/JSONB field.

### 3.7 Detail page ignores the `:id` route param for data

[RequestDetailsPage.tsx:26-28](frontend/src/pages/RequestDetailsPage.tsx#L26-L28):

```ts
const { id } = useParams()
const request = mockRequestDetail       // always the same object
const requestId = id ?? request.id      // param used for link hrefs only
```

The param is read **only** to keep outgoing links pointed at the current URL.
`/requests/9999` renders request 4268's content under the heading
"Request #9999". Same pattern in
[RequestStatusPage.tsx:30-31](frontend/src/pages/RequestStatusPage.tsx#L30-L31).

Consequence: **no 404 / not-found path is exercised or implemented** for a
missing request.

---

## 4. Status (enum)

### 4.1 ⚠️ Two different status enums exist, and they do not match

This is the sharpest internal inconsistency in the frontend.

**`Status`** — [StatusPill.tsx:11](frontend/src/components/ui/StatusPill.tsx#L11):

```ts
export type Status = 'open' | 'in_progress' | 'resolved' | 'closed' | 'draft'
```

**`StatusHistoryState`** — [mockStatusHistory.ts:16-21](frontend/src/data/mockStatusHistory.ts#L16-L21):

```ts
export type StatusHistoryState =
  | 'submitted' | 'assigned' | 'in_progress' | 'resolved' | 'closed'
```

| Value | In `Status` | In `StatusHistoryState` |
| --- | --- | --- |
| `open` | ✅ | ❌ |
| `draft` | ✅ | ❌ |
| `submitted` | ❌ | ✅ |
| `assigned` | ❌ | ✅ |
| `in_progress` | ✅ | ✅ |
| `resolved` | ✅ | ✅ |
| `closed` | ✅ | ✅ |

Neither type is assignable to the other in either direction. A
`StatusHistoryEntry.status` cannot be handed to `<StatusPill>` (would fail on
`submitted`/`assigned`), and a request's `status` cannot be looked up in
`STATUS_HISTORY_LABELS` (would fail on `open`/`draft`). Nothing in the code
attempts either, so the mismatch is currently latent.

### 4.2 ⚠️ `draft` is declared but never used, and contradicts its own comment

`Status` declares five values, but
[mockRequests.ts:6-8](frontend/src/data/mockRequests.ts#L6-L8) states the
fixtures "span all **four** request states from design-tokens.md (open,
in_progress, resolved, closed)". `draft` appears only in the type and in
`STATUS_CONFIG` ([StatusPill.tsx:24-27](frontend/src/components/ui/StatusPill.tsx#L24-L27));
no fixture, page, or form ever produces it.

### 4.3 Presentation coupling (informative)

`STATUS_CONFIG` ([StatusPill.tsx:13-28](frontend/src/components/ui/StatusPill.tsx#L13-L28))
fixes the display labels the UI expects to show for each value:

| Value | Label | Treatment |
| --- | --- | --- |
| `open` | "Open" | filled |
| `in_progress` | "In progress" | filled |
| `resolved` | "Resolved" | filled |
| `closed` | "Closed" | outline |
| `draft` | "Draft" | outline |

[StatusPill.tsx:9-10](frontend/src/components/ui/StatusPill.tsx#L9-L10) states
these values "mirror the convention the backend `statuses` field is expected to
use" — note the **plural** `statuses`, hinting at a lookup table rather than a
column, though the frontend models status as a bare inline string either way
(no id, no nested `{ id, name }` object).

---

## 5. Priority (enum)

Declared **twice, independently**, with no type-level link between them:

- `Priority = 'low' | 'medium' | 'high'`
  ([PriorityPill.tsx:9](frontend/src/components/ui/PriorityPill.tsx#L9))
- `z.enum(['low', 'medium', 'high'], { error: 'Select a priority' })`
  ([submitRequestSchema.ts:34](frontend/src/schemas/submitRequestSchema.ts#L34))

The values happen to agree exactly — this is the one enum pair in the frontend
that is consistent — but the agreement is maintained by hand; the zod enum does
not derive from `Priority` nor vice versa, so drift would not be caught by the
compiler.

Labels: `Low` / `Medium` / `High`
([PriorityPill.tsx:11-21](frontend/src/components/ui/PriorityPill.tsx#L11-L21)),
matching the `SelectItem`s on the form
([SubmitRequestPage.tsx:161-163](frontend/src/pages/SubmitRequestPage.tsx#L161-L163)).

`priority` is **absent from the list shape** — the dashboard never displays it
(§3.1), so it is detail-only in current frontend usage. There is no default
priority: `defaultValues` sets it to `undefined`
([SubmitRequestPage.tsx:47](frontend/src/pages/SubmitRequestPage.tsx#L47)) and
the field is required.

---

## 6. Comment

### 6.1 Shape

[mockRequestDetail.ts:19-23](frontend/src/data/mockRequestDetail.ts#L19-L23):

```ts
export interface RequestComment {
  author: string
  text: string
  timestamp: string
}
```

Three strings. Notably **absent**: `id`, `request_id`, `author_id`, any user
object, `created_at`/`updated_at` as real timestamps, `is_internal`/visibility
flag, edit or delete affordance.

### 6.2 Relation is a nested array, not ids

Comments are embedded directly on the request object as
`comments: RequestComment[]`
([mockRequestDetail.ts:33](frontend/src/data/mockRequestDetail.ts#L33)) — the
detail view assumes **one payload carries the request and its comments
together**. There is no separate comment collection, no id list to resolve, and
no second fetch point.

### 6.3 ⚠️ `author` fuses identity and role into one display string

Fixture values ([mockRequestDetail.ts:52](frontend/src/data/mockRequestDetail.ts#L52),
[:60](frontend/src/data/mockRequestDetail.ts#L60)):

```
'Priya Nair — IT Service Desk'
'Daniel Osei — Requester'
```

Two conceptual fields (person, and their role/team on this request) concatenated
with an em dash into a single pre-rendered string, printed verbatim at
[RequestDetailsPage.tsx:93-95](frontend/src/pages/RequestDetailsPage.tsx#L93-L95).
The frontend has no way to render name and role separately.

### 6.4 No stable key

The comment list is keyed by array index —
`request.comments.map((comment, index) => <li key={index}>` 
([RequestDetailsPage.tsx:89-90](frontend/src/pages/RequestDetailsPage.tsx#L89-L90)) —
because no `id` exists on the shape.

### 6.5 Read-only: no create path

There is no comment input, textarea, or submit button on the details page. The
omission is deliberate and documented at
[RequestDetailsPage.tsx:82-87](frontend/src/pages/RequestDetailsPage.tsx#L82-L87):
commenting is reserved for a separate admin-only page that is out of scope. So
the frontend encodes **no request shape for creating a comment** — no field
constraints, no max length, no verb.

---

## 7. StatusHistory

### 7.1 Shape

[mockStatusHistory.ts:23-27](frontend/src/data/mockStatusHistory.ts#L23-L27):

```ts
export interface StatusHistoryEntry {
  status: StatusHistoryState
  /** Pre-formatted display string, or null if this step is not yet reached. */
  timestamp: string | null
}
```

Two fields. **Absent**: `id`, `request_id`, `changed_by`/actor, `from_status`,
`note`/comment, real timestamp type.

### 7.2 ⚠️ Not an audit log — a fixed 5-step template with placeholders

This is the most consequential modelling assumption in the frontend, and it is
not obvious from the type alone.

`null` in `timestamp` does **not** mean "time unknown". It means *"this step has
not happened yet"* — documented at
[mockStatusHistory.ts:9-13](frontend/src/data/mockStatusHistory.ts#L9-L13) and
confirmed by the fixture
([mockStatusHistory.ts:37-43](frontend/src/data/mockStatusHistory.ts#L37-L43)):

```ts
{ status: 'submitted',   timestamp: '4 Sep 2026, 09:12' },
{ status: 'assigned',    timestamp: '4 Sep 2026, 14:05' },
{ status: 'in_progress', timestamp: '8 Sep 2026, 06:30' },
{ status: 'resolved',    timestamp: null },   // future step
{ status: 'closed',      timestamp: null },   // future step
```

So the array the frontend consumes contains rows for transitions **that have not
occurred**. A conventional append-only history table would contain three rows
here, not five. The page renders dated entries as filled dots and `null` ones as
hollow with the literal meta text `'Pending'`
([RequestStatusPage.tsx:33-37](frontend/src/pages/RequestStatusPage.tsx#L33-L37),
[Timeline.tsx:34-43](frontend/src/components/ui/Timeline.tsx#L34-L43)).

### 7.3 Ordering is positional and unenforced

The array is assumed chronological oldest-first and is mapped straight to
Timeline order with **no sort applied**
([RequestStatusPage.tsx:33](frontend/src/pages/RequestStatusPage.tsx#L33)); the
assumption is stated at
[mockStatusHistory.ts:8-9](frontend/src/data/mockStatusHistory.ts#L8-L9) and
[RequestStatusPage.tsx:21-24](frontend/src/pages/RequestStatusPage.tsx#L21-L24).
Timeline also keys by index ([Timeline.tsx:30](frontend/src/components/ui/Timeline.tsx#L30)),
since entries have no id.

### 7.4 Labels carry hardcoded org detail

`STATUS_HISTORY_LABELS`
([mockStatusHistory.ts:29-35](frontend/src/data/mockStatusHistory.ts#L29-L35))
maps each state to display text, including
`assigned: 'Assigned to IT Service Desk'` — a specific team name embedded in a
presentation constant rather than carried as data (§3.5).

### 7.5 Not linked to a request

`mockStatusHistory` is a standalone module-level array imported directly by the
page. It carries no `request_id`, and the page renders it for any `:id`
(§3.7). The association to request 4268 exists **only in a comment**
([mockStatusHistory.ts:1-2](frontend/src/data/mockStatusHistory.ts#L1-L2)).

---

## 8. Cross-cutting assumptions

### 8.1 Pagination — none

No pagination concept exists in any form:

- `mockRequests` is a bare `MockRequest[]` of 5 items, rendered in full with
  `.map()` ([RequestsDashboardPage.tsx:59-90](frontend/src/pages/RequestsDashboardPage.tsx#L59-L90)).
- No `page`, `limit`, `offset`, `cursor`, `total`, `has_next`, or page-size
  value anywhere.
- No pagination, sort, filter, or search controls in the dashboard UI.
- **No response envelope is assumed.** The list *is* the array — the frontend
  has no `{ items: [...], total: n }` wrapper type. A paginated backend
  response would not fit the current consumption without a shape change.

### 8.2 Loading states — none

- No `isLoading`/`isPending`/`isFetching` flag, no spinner, no skeleton
  component exists in `frontend/src/`.
- All data is imported synchronously at module scope
  (e.g. [RequestsDashboardPage.tsx:13](frontend/src/pages/RequestsDashboardPage.tsx#L13)),
  so it is present on first render and no async boundary exists.
- The only time-based state is cosmetic banner fade-in via
  `requestAnimationFrame` ([SubmitRequestPage.tsx:52-58](frontend/src/pages/SubmitRequestPage.tsx#L52-L58),
  [RegisterPage.tsx:28-38](frontend/src/pages/RegisterPage.tsx#L28-L38)).
- ⚠️ In-flight submit locking is inconsistent: `RegisterPage` disables its
  button with `disabled={submitted}`
  ([RegisterPage.tsx:127](frontend/src/pages/RegisterPage.tsx#L127)) — a
  post-success lock, not an in-flight one — while `SubmitRequestPage`'s button
  has **no** disabled state at all
  ([SubmitRequestPage.tsx:170-172](frontend/src/pages/SubmitRequestPage.tsx#L170-L172)),
  and is re-submittable immediately.

### 8.3 Error handling — two surfaces, neither server-shaped

**No server-error contract is encoded anywhere.** No error boundary, no
status-code mapping, no `{ detail: ... }` / `{ errors: [...] }` body type, no
retry, no toast system. Only two error surfaces exist:

1. **Field-level validation errors** — zod messages surfaced through
   react-hook-form's `formState.errors` and rendered by a local `Field` wrapper
   as `<p role="alert" className="text-meta text-danger">`. Fields also get
   `aria-invalid` when errored.

   ⚠️ That `Field` component is **duplicated verbatim in three pages** —
   [LoginPage.tsx:145-172](frontend/src/pages/LoginPage.tsx#L145-L172),
   [RegisterPage.tsx:147-174](frontend/src/pages/RegisterPage.tsx#L147-L174),
   [SubmitRequestPage.tsx:184-211](frontend/src/pages/SubmitRequestPage.tsx#L184-L211).
   All three are byte-identical and each is deliberately left unexported; the
   shared-primitive gap is explicitly deferred in each file's comment.

2. **One form-level error** — `LoginPage`'s `rejected` boolean rendering
   "Incorrect username or password"
   ([LoginPage.tsx:59-66](frontend/src/pages/LoginPage.tsx#L59-L66)). It is a
   local `boolean`, **not a message from a response** — so no error-body shape
   is assumed even here. It clears on any edit to either field
   ([LoginPage.tsx:43](frontend/src/pages/LoginPage.tsx#L43)).

All three forms use `noValidate` and rely entirely on zod
([LoginPage.tsx:70](frontend/src/pages/LoginPage.tsx#L70),
[RegisterPage.tsx:69](frontend/src/pages/RegisterPage.tsx#L69),
[SubmitRequestPage.tsx:97](frontend/src/pages/SubmitRequestPage.tsx#L97)).
Default RHF mode (`onSubmit`) is used throughout — no `mode` is configured, so
validation fires on submit and re-validates on change thereafter.

### 8.4 Empty states — none

If `mockRequests` were empty the dashboard would render a table header over an
empty `<tbody>`; there is no "no requests yet" branch
([RequestsDashboardPage.tsx:58-91](frontend/src/pages/RequestsDashboardPage.tsx#L58-L91)).
Same for `comments` ([RequestDetailsPage.tsx:88-104](frontend/src/pages/RequestDetailsPage.tsx#L88-L104))
and status history.

### 8.5 No 404 route

[App.tsx:29-36](frontend/src/App.tsx#L29-L36) declares six routes with **no
catch-all** (`path="*"`). An unmatched URL renders nothing.

### 8.6 Route → entity map (URL patterns the frontend already commits to)

These are client routes, not API endpoints — but they are the only URL shapes
in the codebase and they fix where an id appears:

| Route | Page | Entity |
| --- | --- | --- |
| `/` | RequestsDashboardPage | ServiceRequest (list) |
| `/requests/new` | SubmitRequestPage | ServiceRequest (create form) |
| `/requests/:id` | RequestDetailsPage | ServiceRequest + Comments |
| `/requests/:id/status` | RequestStatusPage | StatusHistory |
| `/login` | LoginPage | auth |
| `/register` | RegisterPage | User (create form) |

⚠️ [AppShell.tsx:68-75](frontend/src/components/shell/AppShell.tsx#L68-L75) uses
plain `<a href>` for its two nav links, not router `<Link>` — so sidebar
navigation triggers a **full page reload**, which wipes the in-memory `role`
(§1.2). Acknowledged at [AppShell.tsx:23-25](frontend/src/components/shell/AppShell.tsx#L23-L25).

### 8.7 Submit-request form: the only "write" shape encoded

[submitRequestSchema.ts:23-35](frontend/src/schemas/submitRequestSchema.ts#L23-L35):

| Field | Constraints | Message |
| --- | --- | --- |
| `title` | `.trim().min(1).max(100)` | "Enter a title" / "Title must be 100 characters or fewer" |
| `description` | `.trim().min(1).max(1000)` | "Enter a description" / "Description must be 1000 characters or fewer" |
| `priority` | `z.enum(['low','medium','high'])` | "Select a priority" |

`request_type` is deliberately **not** in the schema (§3.6). No `status` is
sent — the form encodes no opinion about the initial status of a new request.
No verb or URL: on valid submit the handler only calls `reset(...)` and sets a
banner ([SubmitRequestPage.tsx:60-68](frontend/src/pages/SubmitRequestPage.tsx#L60-L68));
the fixture list is not appended to, so a submitted request never appears on the
dashboard.

⚠️ The `max` lengths (100 / 1000) are the **only** length constraints in the
frontend — the register form has no max on any field (§1.3).

---

## 9. Summary of internal inconsistencies flagged

Unresolved, as requested — listed for the reconciliation pass, not fixed here.

| # | Inconsistency | Where |
| --- | --- | --- |
| 1 | Register collects `email`, login authenticates `username`; nothing maps them | §1.4 |
| 2 | `role` is written but never read by any component | §1.5 |
| 3 | `CLAUDE.md` documents `routes.tsx` + auth guard; file does not exist, no route is guarded | §1.6 |
| 4 | Two sign-in paths land on different pages (`/requests/new` vs `/`); demo buttons bypass credentials | §2.2 |
| 5 | List and detail request shapes share **no** timestamp field (`lastUpdated` vs `submittedDate`) | §3.1 |
| 6 | `request_type` is snake_case among otherwise camelCase fields, in one interface | §3.3 |
| 7 | Three different date formats across four timestamp-ish fields; all pre-formatted strings | §3.4 |
| 8 | `Status` and `StatusHistoryState` are two non-matching enums for one lifecycle; mutually unassignable | §4.1 |
| 9 | `draft` declared in `Status` but unused, contradicting the "four states" comment | §4.2 |
| 10 | `Priority` and its zod enum are declared independently with no compile-time link | §5 |
| 11 | `Comment.author` fuses person + role into one display string | §6.3 |
| 12 | `StatusHistory` includes rows for transitions that have not happened (`timestamp: null`) | §7.2 |
| 13 | `REQUEST_TYPE_LABELS` lives in a page while `Status`/`Priority` label maps live beside their types | §3.6 |
| 14 | `Field` component duplicated byte-identically across three pages | §8.3 |
| 15 | Submit-lock behaviour differs between Register (post-success) and SubmitRequest (none) | §8.2 |
| 16 | `VITE_API_URL` typed, configured, and documented — never read | §0 |
| 17 | `AppShell` nav uses `<a href>` not `<Link>`, forcing reloads that clear auth state | §8.6 |
| 18 | No entity carries a user reference; only a hardcoded team name in a label | §3.5 |

---

## 10. Files scanned

Complete list of `frontend/src/` sources reviewed for this document:

`App.tsx` · `main.tsx` · `vite-env.d.ts` ·
`components/shell/{AppShell,AuthShell}.tsx` ·
`components/ui/{Button,Card,PriorityPill,Select,StatusPill,Table,TextInput,Textarea,Timeline}.tsx` ·
`components/ui/buttonVariants.ts` · `context/AuthContext.tsx` ·
`data/{mockRequests,mockRequestDetail,mockStatusHistory}.ts` · `lib/utils.ts` ·
`pages/{Login,Register,RequestDetails,RequestStatus,RequestsDashboard,SubmitRequest}Page.tsx` ·
`schemas/{loginSchema,registerSchema,submitRequestSchema}.ts`

Plus `frontend/package.json`, `frontend/.env`, `frontend/.env.example`,
`frontend/README.md`, `frontend/CLAUDE.md`.

Spec files under `specs/frontend-phase/` were **not** used as sources — this
document reports what the code does. Where a code comment cites a spec, the
comment is quoted as evidence of intent, not as the contract.
