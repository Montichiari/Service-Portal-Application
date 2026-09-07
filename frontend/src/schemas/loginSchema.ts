import { z } from 'zod'

/**
 * Login form shape. requirements.md section 1 describes a non-empty,
 * valid-format email plus a non-empty password, and a standard submit that is
 * informational only — no credential check exists anywhere.
 *
 * That is deliberately overridden for the current demo: the first field is a
 * plain username and a valid submit is checked in LoginPage against one
 * hardcoded credential pair (username / password). An exact match routes to
 * the Submit Service Request page; anything else is rejected inline. This is a
 * throwaway stand-in until real auth lands server-side in Phase 3 — it is not
 * the behaviour in requirements.md.
 */
export const loginSchema = z.object({
  username: z.string().trim().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
})

export type LoginValues = z.infer<typeof loginSchema>
