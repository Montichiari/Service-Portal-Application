import { z } from 'zod'

/**
 * Submit Service Request form shape. Reconciled against
 * specs/api-phase/requirements.md (SR-6 to SR-9) in T-SR-1, which is the
 * permanent source of truth for these constraints — there is still no
 * openapi.yaml in the repo, and that forward-reference is retired.
 *
 *   - title       — non-empty, at most 200 characters
 *   - description — non-empty, at most 1000 characters
 *   - priority    — one of low / medium / high
 *
 * `title` matches SR-7's 200 exactly. It was 100 — a prototype-phase leftover
 * (frontend-phase requirements.md §3) that the api-phase specs never retired —
 * and T-DEBT-5 moved it, the spec decision the old value was standing in for.
 * Unlike `description` there was never a two-tier design behind it: design.md
 * §4 is explicit about the UX-cap-below-a-backstop split for `description` and
 * silent on `title`, so a stricter client limit here was rejecting titles the
 * API would have taken.
 *
 * `description` **is** deliberately stricter than the API's. SR-8's ceiling is
 * 10000 characters and design.md §4 names it an abuse backstop rather than the
 * intended limit, explicitly keeping the prototype's 1000-character UX cap.
 * Neither limit is the false-guarantee hazard AUTH-16 had: both are measured
 * the same way on both sides (characters, not bytes), so anything this form
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
    .max(200, 'Title must be 200 characters or fewer'),
  description: z
    .string()
    .trim()
    .min(1, 'Enter a description')
    .max(1000, 'Description must be 1000 characters or fewer'),
  priority: z.enum(['low', 'medium', 'high'], { error: 'Select a priority' }),
})

export type SubmitRequestValues = z.infer<typeof submitRequestSchema>
