import { z } from 'zod'

/**
 * Comment composer shape, reconciled against specs/api-phase/requirements.md
 * (CM-5, CM-6) in T-CM-1 — the permanent source of truth for these
 * constraints, there being no openapi.yaml in the repo.
 *
 *   - body        — non-empty, at most 5000 characters
 *   - is_internal — admin-only in the UI, enforced server-side by CM-7
 *
 * Both limits are the API's own, measured the same way on both sides
 * (characters, not bytes), so nothing this form accepts is rejected by the
 * server and nothing it rejects would have been accepted. Unlike
 * `submitRequestSchema`'s description there is no deliberate UX cap sitting
 * below a larger backstop here: design.md §6 names one limit and means it.
 *
 * `is_internal` keeps the wire's snake_case per frontend/CLAUDE.md's Naming
 * exception — this object is posted as-is.
 *
 * It is always present in the form's values, defaulting to `false`, and the
 * composer simply never renders the control for a regular user. A schema that
 * varied by role would put a second copy of the permission rule on the client,
 * where CM-7 already answers it server-side with a `403` — and the client's
 * copy would be the one that could be wrong.
 */
export const commentSchema = z.object({
  body: z
    .string()
    .trim()
    .min(1, 'Enter a comment')
    .max(5000, 'Comment must be 5000 characters or fewer'),
  is_internal: z.boolean(),
})

export type CommentValues = z.infer<typeof commentSchema>
