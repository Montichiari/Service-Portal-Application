import { z } from 'zod'

/**
 * Submit Service Request form shape. Reconciled against
 * specs/api-phase/requirements.md (SR-6 to SR-9) in T-SR-1, which is the
 * permanent source of truth for these constraints — there is still no
 * openapi.yaml in the repo, and that forward-reference is retired.
 *
 *   - title       — non-empty, at most 100 characters
 *   - description — non-empty, at most 1000 characters
 *   - priority    — one of low / medium / high
 *
 * **Both maxima are stricter than the API's, on purpose.** SR-8's ceiling is
 * 10000 characters and design.md §4 names it an abuse backstop rather than the
 * intended limit, explicitly keeping the prototype's 1000-character UX cap.
 * SR-7's is 200 where this is 100 — the api-phase specs never retired the
 * prototype's 100 (frontend-phase requirements.md §3), so it stands until a
 * spec decision moves it. Neither is the false-guarantee hazard AUTH-16 had:
 * both limits are measured the same way on both sides, so anything this form
 * accepts the server accepts too. The server stays the authority on the
 * boundary; this is a UX limit sitting inside it.
 *
 * `request_type` is intentionally absent. It is fixed to "general", shown as a
 * disabled Select, and server-set per SR-10/XC-8 — the API has no field for
 * it, so there is nothing to validate and nothing to send.
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
