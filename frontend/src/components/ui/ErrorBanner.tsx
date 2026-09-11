import { cn } from '@/lib/utils'

/**
 * The page-level failure banner — one component, not one copy per page.
 *
 * frontend/CLAUDE.md's Error surfacing section says a `401`/`403`/`404`/`409`/
 * `500` that isn't a field-level validation error surfaces as a page-level
 * banner reusing the pattern RegisterPage established, and explicitly forbids
 * inventing a second banner. T-SR-1 needs that banner in three more places
 * (every `AsyncSection` error state), so the markup moves here and the two
 * auth pages import it — the same extract-when-you-touch-it reasoning that
 * produced Field.tsx, applied before a third and fourth copy exist rather than
 * after, which is how SubmitRequestPage ended up with its own Field for a
 * whole phase.
 *
 * `role="alert"` rather than `status`: this is always the answer to something
 * the user just did, or to a page that failed to load what they asked for.
 */
export interface ErrorBannerProps {
  /**
   * The server's own `error.message`, not a local constant. Callers branch on
   * `error.code` and render `error.message` — messages can be reworded without
   * that being a breaking change, codes are the contract.
   */
  message: string
  className?: string
}

export function ErrorBanner({ message, className }: ErrorBannerProps) {
  return (
    <p
      role="alert"
      className={cn(
        'rounded-card border border-danger bg-card px-3 py-2 text-dense font-semibold text-danger',
        className,
      )}
    >
      {message}
    </p>
  )
}
