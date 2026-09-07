import { z } from 'zod'

/**
 * Login form shape. There is no openapi.yaml in the repo yet, so this is built
 * directly from requirements.md section 1: a non-empty, valid-format email and
 * a non-empty password. No credential check happens anywhere — a standard
 * submit only validates (see LoginPage).
 */
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, 'Enter your email address')
    .refine((value) => z.email().safeParse(value).success, {
      message: 'Enter a valid email address',
    }),
  password: z.string().min(1, 'Enter your password'),
})

export type LoginValues = z.infer<typeof loginSchema>
