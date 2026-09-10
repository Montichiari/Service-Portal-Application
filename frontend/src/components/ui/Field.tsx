import type { ReactNode } from 'react'

/**
 * Label + inline-error wrapper around a field primitive (TextInput, Textarea,
 * Select).
 *
 * One shared component rather than a copy per page: this markup was duplicated
 * byte-for-byte across LoginPage and RegisterPage while nothing was allowed to
 * add shared form primitives, and T-AUTH-5 edits both — which is exactly the
 * condition frontend/CLAUDE.md ("Error surfacing") names as the trigger to
 * extract it here instead of scheduling it separately.
 *
 * `error` is whatever react-hook-form reports for the field, so a client-side
 * zod failure and a server `422`'s `error.fields` entry (XC-4, routed through
 * `setError` by lib/formErrors.ts) render identically — the user has no reason
 * to care which side rejected the value.
 */
export interface FieldProps {
  label: string
  /** Must match the `id` of the control passed as `children`. */
  htmlFor: string
  error?: string
  children: ReactNode
}

export function Field({ label, htmlFor, error, children }: FieldProps) {
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
