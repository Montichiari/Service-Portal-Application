import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from '@/components/shell/AuthShell'
import { Button } from '@/components/ui/Button'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { TextInput } from '@/components/ui/TextInput'
import { cn } from '@/lib/utils'
import { registerSchema, type RegisterValues } from '@/schemas/registerSchema'

// Brief pause so the success banner is readable before redirecting to /login.
// This is a JS timing value, not a visual token, so it lives here rather than
// in tokens.css.
const REDIRECT_DELAY_MS = 1500

export default function RegisterPage() {
  const navigate = useNavigate()
  const [submitted, setSubmitted] = useState(false)
  const [bannerVisible, setBannerVisible] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
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

  const onValidSubmit = () => {
    // No account is created or stored anywhere (requirements.md section 2):
    // just confirm, then hand off to the login page.
    setSubmitted(true)
  }

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

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={handleSubmit(onValidSubmit)}
      >
        <Field
          label="Full name"
          htmlFor="register-full-name"
          error={errors.fullName?.message}
        >
          <TextInput
            id="register-full-name"
            autoComplete="name"
            aria-invalid={errors.fullName ? true : undefined}
            {...register('fullName')}
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
            {...register('email')}
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
            {...register('password')}
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
            {...register('confirmPassword')}
          />
        </Field>

        <Button type="submit" disabled={submitted}>
          Create account
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
