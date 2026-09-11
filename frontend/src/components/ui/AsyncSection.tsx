import type { ReactNode } from 'react'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import type { Async } from '@/lib/async'

/**
 * Renders an `Async<T>`: the loading and error halves once, the ready half by
 * whoever owns the data.
 *
 * This is the other half of the pattern lib/async.ts establishes (T-SR-1).
 * The union makes the impossible states unrepresentable; this makes the three
 * possible ones render the same way on every page, so Groups 3 and 4 inherit
 * a look rather than each inventing one.
 *
 * **Empty is not handled here**, on purpose. An empty list is `ready` with an
 * empty array and the caller branches on length — because only the caller
 * knows what empty *means*: a user with no requests yet and an admin whose
 * filter matched nothing are both legitimately empty, and they need different
 * words. Folding empty in here would force one sentence to cover both.
 */
export interface AsyncSectionProps<T> {
  state: Async<T>
  /**
   * What is being waited for, as a sentence — 'Loading requests…'. Spelled out
   * by the caller rather than defaulted, because it is read aloud by a screen
   * reader and 'Loading…' on its own says nothing useful.
   */
  loadingLabel: string
  children: (data: T) => ReactNode
}

export function AsyncSection<T>({
  state,
  loadingLabel,
  children,
}: AsyncSectionProps<T>) {
  if (state.status === 'pending') {
    return (
      // `status`, not `alert`: this is progress, not a problem, so it should
      // not interrupt a screen reader mid-sentence.
      <p role="status" className="text-dense text-text-secondary">
        {loadingLabel}
      </p>
    )
  }

  if (state.status === 'error') {
    // The server's message, per frontend/CLAUDE.md's Error surfacing rule —
    // the client does not reword what it was told.
    return <ErrorBanner message={state.error.message} />
  }

  return <>{children(state.data)}</>
}
