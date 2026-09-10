import { z } from 'zod'

/**
 * Register form shape, reconciled field-for-field against requirements.md
 * AUTH-1/AUTH-3/AUTH-16 (there is still no openapi.yaml — requirements.md is
 * the permanent source of truth here, per frontend/CLAUDE.md's Form pattern).
 *
 * `first_name` / `last_name` are snake_case because this schema mirrors
 * `POST /auth/register`'s body exactly — the Naming exception, not a slip.
 * `confirmPassword` is the one field that isn't API-shaped: it has no backend
 * counterpart, stays camelCase, and must never reach the request body (see
 * RegisterPage).
 */

// AUTH-3. Length only — no composition rule. Decided deliberately during spec
// review and matched by the server's own schema: required uppercase/digit/
// symbol rules push toward predictable substitutions without improving real
// strength. Adding a regex here would reintroduce a rule that was considered
// and rejected, and would reject passwords the API accepts.
const MIN_PASSWORD_CHARS = 12

// AUTH-16's ceiling is bcrypt's hard limit and is measured in **bytes**, so a
// `.max(72)` on string length would be a false guarantee: 30 emoji are 30
// characters and 120 bytes, and the server would still answer `422`. Counting
// the encoded length is the only client-side check that agrees with the API.
const MAX_PASSWORD_BYTES = 72

const NAME_MAX_CHARS = 100

export const registerSchema = z
  .object({
    first_name: z
      .string()
      .trim()
      .min(1, 'Enter your first name')
      .max(NAME_MAX_CHARS, `First name must be at most ${NAME_MAX_CHARS} characters`),
    last_name: z
      .string()
      .trim()
      .min(1, 'Enter your last name')
      .max(NAME_MAX_CHARS, `Last name must be at most ${NAME_MAX_CHARS} characters`),
    email: z.email('Enter a valid email address'),
    password: z
      .string()
      .min(
        MIN_PASSWORD_CHARS,
        `Password must be at least ${MIN_PASSWORD_CHARS} characters`,
      )
      .refine(
        (value) => new TextEncoder().encode(value).length <= MAX_PASSWORD_BYTES,
        `Password must be at most ${MAX_PASSWORD_BYTES} bytes — accented characters and emoji each count as more than one`,
      ),
    confirmPassword: z.string().min(1, 'Re-enter your password'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

export type RegisterValues = z.infer<typeof registerSchema>
