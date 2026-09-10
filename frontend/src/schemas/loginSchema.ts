import { z } from 'zod'

/**
 * Login form shape, from requirements.md AUTH-6/AUTH-7 (design.md §0 decision
 * 6: the identifier is the email address, matching register — the prototype's
 * `username` field and its hardcoded credential pair are gone).
 *
 * Only what the client can decide on its own is checked here: both fields
 * present, and the address shaped like one. There is deliberately no length or
 * composition rule on `password` — the server's own login schema omits one for
 * the same reason (AUTH-7): rejecting a too-short password client-side would
 * answer "that isn't long enough to be one of ours" where the contract wants
 * one indistinguishable failure, and it would lock out any account whose
 * password predates a policy change.
 */
export const loginSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})

export type LoginValues = z.infer<typeof loginSchema>
