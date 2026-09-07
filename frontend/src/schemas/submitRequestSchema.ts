import { z } from 'zod'

/**
 * Submit Service Request form shape, built directly from requirements.md
 * section 3 (there is no openapi.yaml in the repo yet to mirror). It covers
 * the three validated fields only:
 *
 *   - title       — non-empty, at most 100 characters
 *   - description — non-empty, at most 1000 characters
 *   - priority    — one of low / medium / high
 *
 * `request_type` is intentionally absent. For this demo it is fixed to the
 * constant "general" and shown as a disabled, non-interactive Select (see
 * SubmitRequestPage and tasks.md Task 4). It cannot be changed, so there is
 * nothing to validate and it is not user input. This narrow field set is a
 * deliberate, temporary simplification pending the full request-type design
 * from Phase 1 — not an oversight to be "fixed" with a metadata/JSONB field
 * or conditional fields.
 *
 * Nothing is persisted or sent — a valid submit only resets the form and
 * shows a success banner (see SubmitRequestPage).
 */
export const submitRequestSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Enter a title')
    .max(100, 'Title must be 100 characters or fewer'),
  description: z
    .string()
    .trim()
    .min(1, 'Enter a description')
    .max(1000, 'Description must be 1000 characters or fewer'),
  priority: z.enum(['low', 'medium', 'high'], { error: 'Select a priority' }),
})

export type SubmitRequestValues = z.infer<typeof submitRequestSchema>
