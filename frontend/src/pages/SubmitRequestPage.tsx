import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { AppShell } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { TextInput } from '@/components/ui/TextInput'
import { Textarea } from '@/components/ui/Textarea'
import { cn } from '@/lib/utils'
import {
  submitRequestSchema,
  type SubmitRequestValues,
} from '@/schemas/submitRequestSchema'

/**
 * Submit Service Request (`/requests/new`). Post-login page, so it uses
 * AppShell. Field list, validation, and submit behaviour come from
 * requirements.md section 3 and tasks.md Task 4.
 *
 * Request type is a fixed constant ("general") for this demo — rendered as a
 * disabled Select and deliberately left out of the form state and the zod
 * schema. Everything else (title, description, priority) is validated by
 * submitRequestSchema. A valid submit is simulated only: the form is cleared
 * and a success banner shown. Nothing is persisted, sent, or added to the
 * Requests Dashboard.
 */
export default function SubmitRequestPage() {
  const [submitted, setSubmitted] = useState(false)
  const [bannerVisible, setBannerVisible] = useState(false)
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<SubmitRequestValues>({
    resolver: zodResolver(submitRequestSchema),
    defaultValues: { title: '', description: '' },
  })

  // Fade the banner in once, matching RegisterPage / design-tokens.md's
  // "brief, purposeful transition" allowance for success states.
  useEffect(() => {
    if (!submitted) {
      return
    }
    const frame = requestAnimationFrame(() => setBannerVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [submitted])

  const onValidSubmit = () => {
    // requirements.md section 3: the submit is simulated only — nothing is
    // persisted, sent, or added to any list. reset() clears the registered
    // fields (title, description, priority); the disabled Request type Select
    // is uncontrolled and not registered, so it keeps showing "General".
    reset()
    setSubmitted(true)
  }

  return (
    <AppShell>
      <div className="flex max-w-xl flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-h2 font-semibold text-text-primary">
            Submit a service request
          </h1>
          <p className="text-dense text-text-secondary">
            Describe the issue or request and set a priority. IT triages new
            requests from the dashboard.
          </p>
        </header>

        {submitted ? (
          <p
            role="status"
            className={cn(
              'rounded-card border border-accent bg-card px-3 py-2 text-dense font-semibold text-accent transition',
              bannerVisible ? 'opacity-100' : 'opacity-0',
            )}
          >
            Request submitted
          </p>
        ) : null}

        <form
          className="flex flex-col gap-4 rounded-card border border-border bg-card p-4"
          noValidate
          onSubmit={handleSubmit(onValidSubmit)}
        >
          <Field label="Request type" htmlFor="submit-request-type">
            {/*
             * Fixed to "general" for this demo: disabled, not registered with
             * the form, excluded from validation (requirements.md section 3,
             * tasks.md Task 4). The matching SelectItem is required — Radix
             * reads the displayed label from it; a bare <SelectValue /> would
             * render blank without it. Uncontrolled defaultValue, so reset()
             * leaves this showing "General".
             */}
            <Select disabled defaultValue="general">
              <SelectTrigger id="submit-request-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">General</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field
            label="Title"
            htmlFor="submit-request-title"
            error={errors.title?.message}
          >
            <TextInput
              id="submit-request-title"
              aria-invalid={errors.title ? true : undefined}
              {...register('title')}
            />
          </Field>

          <Field
            label="Description"
            htmlFor="submit-request-description"
            error={errors.description?.message}
          >
            <Textarea
              id="submit-request-description"
              aria-invalid={errors.description ? true : undefined}
              {...register('description')}
            />
          </Field>

          <Field
            label="Priority"
            htmlFor="submit-request-priority"
            error={errors.priority?.message}
          >
            <Controller
              control={control}
              name="priority"
              render={({ field }) => (
                <Select value={field.value ?? ''} onValueChange={field.onChange}>
                  <SelectTrigger
                    id="submit-request-priority"
                    aria-invalid={errors.priority ? true : undefined}
                    onBlur={field.onBlur}
                  >
                    <SelectValue placeholder="Select a priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </Field>

          <Button type="submit" className="self-start">
            Submit request
          </Button>
        </form>
      </div>
    </AppShell>
  )
}

/**
 * Local label + inline-error wrapper around a Task 1 field primitive. Kept
 * private to this page, matching LoginPage / RegisterPage — Phase 2 doesn't
 * add a shared form-field primitive (that gap is deferred).
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
