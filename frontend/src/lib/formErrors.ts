import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { isApiError } from '@/lib/api'

/**
 * Route a `422`'s `error.fields` map (XC-4) onto the form's own fields, per
 * frontend/CLAUDE.md's "Error surfacing" rule.
 *
 * The backend keys `fields` by plain field name (`email`, `first_name`), which
 * is why API-shaped schemas keep the wire's snake_case — the two names line up
 * with no translation step to get wrong.
 *
 * Returns whether anything was actually applied. A `VALIDATION_ERROR` naming
 * only fields this form doesn't render would otherwise be swallowed in
 * silence, leaving a submit that visibly did nothing; the caller falls back to
 * the page-level banner on `false`.
 *
 * `fieldNames` is the allow-list of what the form renders: `setError` on a
 * name no input is bound to blocks submission with a message nothing displays.
 */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fieldNames: readonly Path<T>[],
): boolean {
  if (!isApiError(error) || error.fields === undefined) return false

  const { fields } = error
  let applied = false

  for (const name of fieldNames) {
    const messages = fields[name]
    if (messages === undefined || messages.length === 0) continue
    // XC-4 allows several messages per field; showing all of them beats
    // picking one and leaving the user to fix them one submit at a time.
    setError(name, { type: 'server', message: messages.join(' ') })
    applied = true
  }

  return applied
}

/** For a thrown value that isn't an `ApiError` at all — i.e. a bug in ours. */
export const UNEXPECTED_ERROR_MESSAGE =
  'Something went wrong. Please try again.'

/** The banner text for any failure a form can't attribute to one field. */
export function pageErrorMessage(error: unknown): string {
  return isApiError(error) ? error.message : UNEXPECTED_ERROR_MESSAGE
}
