import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from '@/components/shell/AuthShell'
import { Button } from '@/components/ui/Button'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { TextInput } from '@/components/ui/TextInput'
import { useAuth, type Role } from '@/context/AuthContext'
import { loginSchema, type LoginValues } from '@/schemas/loginSchema'

// Throwaway demo credential. requirements.md section 1 has no credential check
// at all — a standard submit is informational only. This single hardcoded pair
// stands in until real auth lands server-side in Phase 3: an exact match signs
// the user in and routes to the Submit Service Request page, anything else is
// rejected inline.
const DEMO_USERNAME = 'username'
const DEMO_PASSWORD = 'password'

export default function LoginPage() {
  const navigate = useNavigate()
  const { setRole } = useAuth()
  const [rejected, setRejected] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  const onValidSubmit = (values: LoginValues) => {
    if (values.username === DEMO_USERNAME && values.password === DEMO_PASSWORD) {
      // Matching pair = a successful sign-in: establish the cosmetic role the
      // Task 3 guard will read, then go to the request form.
      setRole('user')
      navigate('/requests/new')
      return
    }
    setRejected(true)
  }

  // Drop the rejection notice as soon as the user edits either field.
  const clearRejected = () => setRejected(false)

  function continueAs(role: Role) {
    setRole(role)
    navigate('/')
  }

  return (
    <AuthShell>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Access the IT service portal to submit and track requests.
        </CardDescription>
      </CardHeader>

      {rejected ? (
        <p
          role="alert"
          className="rounded-card border border-danger bg-card px-3 py-2 text-dense font-semibold text-danger"
        >
          Incorrect username or password
        </p>
      ) : null}

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={handleSubmit(onValidSubmit)}
      >
        <Field
          label="Username"
          htmlFor="login-username"
          error={errors.username?.message}
        >
          <TextInput
            id="login-username"
            autoComplete="username"
            aria-invalid={errors.username ? true : undefined}
            {...register('username', { onChange: clearRejected })}
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
            {...register('password', { onChange: clearRejected })}
          />
        </Field>

        <Button type="submit">Sign in</Button>
      </form>

      <div className="flex flex-col gap-2">
        <span className="text-dense text-text-secondary">
          Or continue with a demo role
        </span>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="secondary"
            className="flex-1"
            onClick={() => continueAs('user')}
          >
            Continue as User
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="flex-1"
            onClick={() => continueAs('admin')}
          >
            Continue as Admin
          </Button>
        </div>
      </div>

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

/**
 * Local label + inline-error wrapper around a Task 1 field primitive. Kept
 * private to this page on purpose — Task 2 must not add shared form primitives
 * (that gap is deferred), so this is not exported.
 */
function Field({
  label,
  htmlFor,
  error,
  children,
}: {
  label: string
  htmlFor: string
  error?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={htmlFor}
        className="text-dense font-semibold text-text-primary"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-meta text-danger">
          {error}
        </p>
      ) : null}
    </div>
  )
}
