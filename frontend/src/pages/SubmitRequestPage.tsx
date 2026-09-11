import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Field } from '@/components/ui/Field'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { TextInput } from '@/components/ui/TextInput'
import { Textarea } from '@/components/ui/Textarea'
import { createServiceRequest } from '@/lib/api'
import { applyFieldErrors, pageErrorMessage } from '@/lib/formErrors'
import { cn } from '@/lib/utils'
import {
  submitRequestSchema,
  type SubmitRequestValues,
} from '@/schemas/submitRequestSchema'

/**
 * Submit Service Request (`/requests/new`) — wired to `POST /service-requests`
 * (SR-6 through SR-10) in T-SR-1, replacing the prototype's
 * simulate-and-discard submit.
 *
 * The success path now ends on the dashboard rather than on this form, which
 * closes frontend-contract.md §8.7: a submit that never touched the list left
 * the user with a banner and no way to tell whether anything had happened.
 * Landing on the dashboard puts the new request at the top of it (SR-15 orders
 * newest first), so the confirmation is the thing itself.
 *
 * Request type stays fixed to "general" — a disabled Select, deliberately
 * outside the form state and the zod schema. SR-10/XC-8 make it server-set and
 * the API has no field for it, so there is nothing to send and nothing to
 * validate.
 */

// Brief pause so the success banner is readable before the redirect, matching
// RegisterPage. A JS timing value, not a visual token, so it lives here rather
// than in tokens.css.
const REDIRECT_DELAY_MS = 1500

// The API-shaped fields this form renders, so a `422` naming anything else
// falls through to the banner instead of vanishing into a control that isn't
// there.
const REQUEST_FIELDS = ['title', 'description', 'priority'] as const

export default function SubmitRequestPage() {
  const navigate = useNavigate()
  const [submitted, setSubmitted] = useState(false)
  const [bannerVisible, setBannerVisible] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<SubmitRequestValues>({
    resolver: zodResolver(submitRequestSchema),
    // priority is listed (as undefined) so RHF has a default for the
    // Controller field — it only reliably resets what it has one for.
    defaultValues: { title: '', description: '', priority: undefined },
  })

  // Fade the banner in once, then hand off to the dashboard — same shape as
  // RegisterPage's post-submit flow, for the same reason.
  useEffect(() => {
    if (!submitted) {
      return
    }
    const frame = requestAnimationFrame(() => setBannerVisible(true))
    const timer = window.setTimeout(() => navigate('/'), REDIRECT_DELAY_MS)
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
    }
  }, [submitted, navigate])

  const onValidSubmit = async (values: SubmitRequestValues) => {
    setFormError(null)
    try {
      await createServiceRequest({
        title: values.title,
        description: values.description,
        priority: values.priority,
      })
      setSubmitted(true)
    } catch (error) {
      // A `422` lands inline on the offending field (XC-4); anything else —
      // a `401` whose refresh also failed, a `500` — is not attributable to
      // one field and surfaces as the banner with the server's own message.
      if (!applyFieldErrors(error, setError, REQUEST_FIELDS)) {
        setFormError(pageErrorMessage(error))
      }
    }
  }

  const clearFormError = () => setFormError(null)

  return (
    <AppShell>
      <div className="content-form flex flex-col gap-6">
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

        {formError !== null ? <ErrorBanner message={formError} /> : null}

        <form
          className="flex flex-col gap-4 rounded-card border border-border bg-card p-4"
          noValidate
          onSubmit={handleSubmit(onValidSubmit)}
        >
          <Field label="Request type" htmlFor="submit-request-type">
            {/*
             * Fixed to "general": disabled, not registered with the form,
             * absent from the request body. The matching SelectItem is
             * required — Radix reads the displayed label from it; a bare
             * <SelectValue /> would render blank without it.
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
              {...register('title', { onChange: clearFormError })}
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
              {...register('description', { onChange: clearFormError })}
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

          {/* Disabled for the duration of the request, not merely after it
              succeeds — against a real endpoint a second click files a second
              request, which is the same correctness fix T-AUTH-5 made to both
              auth forms. */}
          <Button
            type="submit"
            className="self-start"
            disabled={isSubmitting || submitted}
          >
            {isSubmitting ? 'Submitting…' : 'Submit request'}
          </Button>
        </form>
      </div>
    </AppShell>
  )
}
