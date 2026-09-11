import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from '@/components/shell/AuthShell'
import { Button } from '@/components/ui/Button'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Field } from '@/components/ui/Field'
import { TextInput } from '@/components/ui/TextInput'
import { register as registerAccount } from '@/lib/api'
import { applyFieldErrors, pageErrorMessage } from '@/lib/formErrors'
import { cn } from '@/lib/utils'
import { registerSchema, type RegisterValues } from '@/schemas/registerSchema'

/**
 * Create an account (`/register`) — wired to `POST /auth/register` (AUTH-1
 * through AUTH-5, AUTH-16) in T-AUTH-5, replacing the prototype's
 * confirm-and-discard flow.
 *
 * Registering does not sign the new user in — no cookies are set (design.md
 * §2) — so the success path still ends at `/login`, now with a real row
 * created behind it.
 */

// Brief pause so the success banner is readable before redirecting to /login.
// This is a JS timing value, not a visual token, so it lives here rather than
// in tokens.css.
const REDIRECT_DELAY_MS = 1500

// The API-shaped fields this form renders. `confirmPassword` is absent by
// design: the server has no such field and can never report an error for it.
const REGISTER_FIELDS = ['first_name', 'last_name', 'email', 'password'] as const

export default function RegisterPage() {
  const navigate = useNavigate()
  const [submitted, setSubmitted] = useState(false)
  const [bannerVisible, setBannerVisible] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) })

  useEffect(() => {
    if (!submitted) {
      return
    }
    const frame = requestAnimationFrame(() => setBannerVisible(true))
    const timer = window.setTimeout(() => navigate('/login'), REDIRECT_DELAY_MS)
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
    }
  }, [submitted, navigate])

  const onValidSubmit = async (values: RegisterValues) => {
    setFormError(null)
    try {
      // Listed field by field rather than spread: `confirmPassword` is
      // client-only validation with no backend counterpart, and naming the
      // four fields explicitly is what makes it impossible for it to reach the
      // request body.
      await registerAccount({
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        password: values.password,
      })
      setSubmitted(true)
    } catch (error) {
      // A `422` lands on the offending fields (XC-4); a `409` for an address
      // already registered (AUTH-2) carries no `fields` map by design, so it
      // surfaces as the banner with the server's own message.
      if (!applyFieldErrors(error, setError, REGISTER_FIELDS)) {
        setFormError(pageErrorMessage(error))
      }
    }
  }

  const clearFormError = () => setFormError(null)

  return (
    <AuthShell>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>
          Register to submit and track IT service requests.
        </CardDescription>
      </CardHeader>

      {submitted ? (
        <p
          role="status"
          className={cn(
            'rounded-card border border-accent bg-card px-3 py-2 text-dense font-semibold text-accent transition',
            bannerVisible ? 'opacity-100' : 'opacity-0',
          )}
        >
          Account created — please sign in
        </p>
      ) : null}

      {formError !== null ? <ErrorBanner message={formError} /> : null}

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={handleSubmit(onValidSubmit)}
      >
        <Field
          label="First name"
          htmlFor="register-first-name"
          error={errors.first_name?.message}
        >
          <TextInput
            id="register-first-name"
            autoComplete="given-name"
            aria-invalid={errors.first_name ? true : undefined}
            {...register('first_name', { onChange: clearFormError })}
          />
        </Field>

        <Field
          label="Last name"
          htmlFor="register-last-name"
          error={errors.last_name?.message}
        >
          <TextInput
            id="register-last-name"
            autoComplete="family-name"
            aria-invalid={errors.last_name ? true : undefined}
            {...register('last_name', { onChange: clearFormError })}
          />
        </Field>

        <Field
          label="Email"
          htmlFor="register-email"
          error={errors.email?.message}
        >
          <TextInput
            id="register-email"
            type="email"
            autoComplete="email"
            aria-invalid={errors.email ? true : undefined}
            {...register('email', { onChange: clearFormError })}
          />
        </Field>

        <Field
          label="Password"
          htmlFor="register-password"
          error={errors.password?.message}
        >
          <TextInput
            id="register-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={errors.password ? true : undefined}
            {...register('password', { onChange: clearFormError })}
          />
        </Field>

        <Field
          label="Confirm password"
          htmlFor="register-confirm-password"
          error={errors.confirmPassword?.message}
        >
          <TextInput
            id="register-confirm-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={errors.confirmPassword ? true : undefined}
            {...register('confirmPassword', { onChange: clearFormError })}
          />
        </Field>

        {/* Disabled while the request is in flight as well as after it
            succeeds: `submitted` alone was harmless against a simulated
            submit, but now a second click would be a second registration
            attempt. */}
        <Button type="submit" disabled={isSubmitting || submitted}>
          {isSubmitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>

      <p className="text-dense text-text-secondary">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}
