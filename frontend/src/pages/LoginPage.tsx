import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from '@/components/shell/AuthShell'
import { Button } from '@/components/ui/Button'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Field } from '@/components/ui/Field'
import { TextInput } from '@/components/ui/TextInput'
import { useAuth } from '@/context/AuthContext'
import { applyFieldErrors, pageErrorMessage } from '@/lib/formErrors'
import { loginSchema, type LoginValues } from '@/schemas/loginSchema'

/**
 * Sign in (`/login`) — wired to `POST /auth/login` (AUTH-6, AUTH-7) in
 * T-AUTH-5. The demo credential pair and the two "Continue as …" role buttons
 * are gone: there is exactly one way in now, and it goes through the real
 * endpoint.
 */

// The fields this form renders, so a `422` naming anything else falls through
// to the banner instead of vanishing into a control that isn't there.
const LOGIN_FIELDS = ['email', 'password'] as const

export default function LoginPage() {
  const navigate = useNavigate()
  const { signIn } = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  const onValidSubmit = async (values: LoginValues) => {
    setFormError(null)
    try {
      await signIn(values)
      // One post-login destination now that there is one sign-in path: the
      // Requests Dashboard.
      navigate('/')
    } catch (error) {
      // AUTH-7's message is rendered from the response, never from a local
      // constant — the backend owns the wording, and the whole point of it is
      // that "no such email" and "wrong password" read identically.
      if (!applyFieldErrors(error, setError, LOGIN_FIELDS)) {
        setFormError(pageErrorMessage(error))
      }
    }
  }

  // Drop the banner as soon as the user edits either field.
  const clearFormError = () => setFormError(null)

  return (
    <AuthShell>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Access the IT service portal to submit and track requests.
        </CardDescription>
      </CardHeader>

      {formError !== null ? <ErrorBanner message={formError} /> : null}

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={handleSubmit(onValidSubmit)}
      >
        <Field label="Email" htmlFor="login-email" error={errors.email?.message}>
          <TextInput
            id="login-email"
            type="email"
            autoComplete="email"
            aria-invalid={errors.email ? true : undefined}
            {...register('email', { onChange: clearFormError })}
          />
        </Field>

        <Field
          label="Password"
          htmlFor="login-password"
          error={errors.password?.message}
        >
          <TextInput
            id="login-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={errors.password ? true : undefined}
            {...register('password', { onChange: clearFormError })}
          />
        </Field>

        {/* Disabled for the duration of the request, not merely after it
            succeeds — against a real endpoint a second click is a second
            login, not a harmless no-op. */}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>

      <p className="text-dense text-text-secondary">
        Need an account?{' '}
        <Link
          to="/register"
          className="font-semibold text-accent hover:underline"
        >
          Create one
        </Link>
      </p>
    </AuthShell>
  )
}
