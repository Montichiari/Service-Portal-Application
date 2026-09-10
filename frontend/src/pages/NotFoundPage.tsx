import { Link } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'

/**
 * Catch-all for any URL the route table doesn't match, closing
 * frontend-contract.md §8.5 — six routes were declared with no `path="*"`, so
 * an unmatched URL rendered a blank page.
 *
 * Deliberately public, i.e. outside the guard in routes.tsx: a mistyped URL
 * should say so in both session states rather than silently becoming a login
 * page for a signed-out visitor. AppShell is still the frame (the convention
 * for in-app pages) and stays honest when there is no session — it fetches
 * nothing, and its account block already hides itself without one, so a
 * signed-out visitor sees chrome plus two links that the guard then bounces
 * to `/login`.
 *
 * Layout follows design-tokens.md "Content width": detail width, centered,
 * via the shared `.content-detail` class.
 */
export default function NotFoundPage() {
  return (
    <AppShell>
      <div className="content-detail flex flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-h2 font-semibold text-text-primary">
            Page not found
          </h1>
          <p className="text-dense text-text-secondary">
            The page you asked for doesn’t exist. Check the address, or head
            back to your requests.
          </p>
        </header>
        <Button asChild className="self-start">
          <Link to="/">Back to dashboard</Link>
        </Button>
      </div>
    </AppShell>
  )
}
