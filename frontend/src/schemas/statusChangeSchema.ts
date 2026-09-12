import { z } from 'zod'

/**
 * Status-change composer shape, reconciled against
 * specs/api-phase/requirements.md (SC-5 to SC-7) in T-SC-1 — the permanent
 * source of truth for these constraints, there being no openapi.yaml in the
 * repo.
 *
 *   - status_id — required, an id from `GET /statuses`
 *   - note      — optional, no maximum
 *
 * `status_id` is checked for presence only. Which ids are *valid* is the
 * `statuses` table's answer, not this file's: the route resolves the id against
 * that table for exactly the reason SR-3's filter does, and a list of four ids
 * on this side would be a second source of truth that a later seeded row could
 * contradict. The form's Select is populated from the endpoint anyway, so the
 * only way to submit an unknown id is to go around the UI — which SC-6 answers
 * with a `422` carrying `fields.status_id`.
 *
 * `note` has **no `.max()`** on purpose. SC-7 enforces none (the column is
 * unbounded TEXT), and a client-side cap the server doesn't have would reject
 * a note the API would have accepted — the mirror image of the false guarantee
 * T-AUTH-5 refused for the password field.
 *
 * Both names keep the wire's snake_case per frontend/CLAUDE.md's Naming
 * exception — this object is posted as-is.
 */
export const statusChangeSchema = z.object({
  status_id: z.string().min(1, 'Select a status'),
  // Trimmed, so a note of nothing but whitespace is the same as no note. The
  // page turns the empty string into an omitted field; SC-7 stores what it is
  // given verbatim, and '   ' is not something anyone meant to record.
  note: z.string().trim(),
})

export type StatusChangeValues = z.infer<typeof statusChangeSchema>
