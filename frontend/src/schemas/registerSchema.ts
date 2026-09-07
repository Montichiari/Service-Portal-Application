import { z } from 'zod'

/**
 * Register form shape, built directly from requirements.md section 2 (no
 * openapi.yaml exists in the repo yet to mirror): non-empty full name, valid
 * email format, a password of at least 8 characters, and a confirm field that
 * must match the password exactly. Nothing is persisted or sent — a valid
 * submit only shows a banner and redirects (see RegisterPage).
 */
export const registerSchema = z
  .object({
    fullName: z.string().trim().min(1, 'Enter your full name'),
    email: z.email('Enter a valid email address'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirmPassword: z.string().min(1, 'Re-enter your password'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

export type RegisterValues = z.infer<typeof registerSchema>
