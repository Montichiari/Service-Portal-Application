import { useEffect, useState, type DependencyList } from 'react'
import { ApiError, isApiError } from '@/lib/api'
import { UNEXPECTED_ERROR_MESSAGE } from '@/lib/formErrors'

/**
 * The one loading/error/ready shape for the whole phase (T-SR-1).
 *
 * frontend/CLAUDE.md is explicit that this gets invented **once** — here — and
 * reused by Groups 3 and 4; T-DEBT-2 deliberately rendered `null` while the
 * session was pending rather than invent a spinner first. A second shape
 * appearing on any page is the sign this was described rather than
 * established.
 *
 * A discriminated union rather than `isLoading` + nullable `data` + nullable
 * `error`: those three booleans-and-nulls describe eight states of which four
 * are nonsense (loading *and* data *and* error), and stay safe only by
 * convention about the order the branches are written in. That is the exact
 * failure T-DEBT-2 hit by collapsing a three-state session into a boolean —
 * where "pending" read as "signed out" and bounced signed-in users to /login.
 *
 * **Empty is not a fourth member.** An empty list is `ready` with an empty
 * array, and the page branches on length. A new user with no requests is a
 * legitimate answer, not a failure to load one.
 */
export type Async<T> =
  | { status: 'pending' }
  | { status: 'error'; error: ApiError }
  | { status: 'ready'; data: T }

/** Shared, since it carries no payload — every pending state is the same one. */
const PENDING: Async<never> = { status: 'pending' }

/**
 * Anything thrown out of a load, as the one error type the union carries.
 *
 * `api.ts` throws only `ApiError`, so the fallback covers a bug in our own
 * code rather than any response the server can produce — hence the reuse of
 * the form layer's "something went wrong" wording instead of inventing a
 * second phrasing for the same non-answer.
 */
function asApiError(error: unknown): ApiError {
  return isApiError(error)
    ? error
    : new ApiError('INTERNAL_ERROR', UNEXPECTED_ERROR_MESSAGE, 0, undefined, {
        cause: error,
      })
}

/** An abort is this hook's own cleanup, not a failure anyone should see. */
function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/**
 * Run `load` whenever `deps` change, as an `Async<T>`.
 *
 * **The in-flight result is invalidated on cleanup, twice over, and both halves
 * are load-bearing.** The `AbortController` stops work that is still in the
 * air; the `current` flag covers the window the controller cannot — a promise
 * that already resolved, whose `.then` is queued behind a cleanup that has
 * since run. Without the flag a late resolution still calls `setState`.
 *
 * The dashboard's filters make this reachable in normal use rather than in
 * theory: change a filter twice quickly and the earlier response can land
 * after the later one, leaving a table that contradicts its own controls.
 * Same family as T-AUTH-4's `sessionGeneration` finding — the question is "was
 * this response produced by a request I still care about?", and it is answered
 * when the response arrives, not when it is sent. It will not reproduce
 * against localhost by accident, so it is written correctly rather than left
 * to be observed.
 *
 * `load` is deliberately *not* a dependency: it is a fresh closure every
 * render, so including it would re-run on every render. The caller declares
 * what the load actually depends on, the way `useEffect` itself works.
 */
export function useAsyncData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
): Async<T> {
  const [state, setState] = useState<Async<T>>(PENDING)

  /*
   * exhaustive-deps is suppressed across this effect, and both warnings it
   * raises are the same false positive: `deps` is a real dependency list, just
   * one the rule cannot read because it arrives as a parameter rather than an
   * inline array literal. Nor is there an update loop from the `setState` below
   * — `PENDING` is a module constant, so re-setting an already-pending state
   * bails out inside React rather than re-rendering.
   */
  /* oxlint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    const controller = new AbortController()
    let current = true

    // Back to pending on every re-run: a filter change is a new question, and
    // showing the previous answer underneath a changed control is the
    // contradiction this hook exists to prevent.
    setState(PENDING)

    load(controller.signal).then(
      (data) => {
        if (current) setState({ status: 'ready', data })
      },
      (error: unknown) => {
        if (!current || isAbort(error)) return
        setState({ status: 'error', error: asApiError(error) })
      },
    )

    return () => {
      current = false
      controller.abort()
    }
  }, deps)
  /* oxlint-enable react-hooks/exhaustive-deps */

  return state
}
