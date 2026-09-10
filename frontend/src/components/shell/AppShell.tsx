import { useState } from 'react'
import type { ReactNode } from 'react'
import { LogOutIcon, MenuIcon, XIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/lib/utils'

/**
 * App frame for every in-app (post-login) page: dark chrome nav + light
 * content area. The nav is the sole wayfinding device; content never uses
 * dark chrome.
 *
 * Responsive behaviour per design-tokens.md "Breakpoints" (--bp-mobile, wired
 * to Tailwind's `md` variant in index.css):
 * - `md` and up: nav is a persistent 240px left sidebar; content padding 32px.
 * - below `md`: nav is a full-width top bar (brand + hamburger toggle); the
 *   links collapse into a drawer opened by the toggle; content padding 16px.
 *
 * The breakpoint itself is pure CSS (Tailwind variants), so no resize/
 * matchMedia listener is involved. `menuOpen` only drives the sub-`md` drawer;
 * at/above `md` the nav shows via `md:flex` and the toggle is `md:hidden`, so
 * a stale value there is harmless.
 *
 * Nav is exactly the two top-level destinations from design.md's routing
 * table. Links are plain anchors for now — active state and client-side
 * navigation are wired in the routing task.
 *
 * The account block below the nav is T-AUTH-5's: the app had no way to sign
 * out at all before it. It renders only for a session `GET /auth/me` actually
 * confirmed, so it doubles as the visible proof that a reload kept the
 * session. Routes themselves stay unguarded — that gap is Task 3's and is
 * explicitly out of this task's scope (frontend/CLAUDE.md, "Auth guard
 * pattern").
 */
const NAV_ITEMS = [
  { label: 'Requests Dashboard', href: '/' },
  { label: 'Submit Request', href: '/requests/new' },
]

export interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const [signingOut, setSigningOut] = useState(false)

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await signOut()
      navigate('/login')
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="shrink-0 bg-chrome p-4 md:flex md:w-sidebar md:flex-col md:gap-6">
        <div className="flex items-center justify-between md:block">
          <span className="px-3 text-subhead font-bold text-chrome-text-active">
            Service Portal
          </span>
          <button
            type="button"
            aria-label="Toggle navigation menu"
            aria-expanded={menuOpen}
            aria-controls="app-shell-nav"
            onClick={() => setMenuOpen((open) => !open)}
            className="rounded-card p-2 text-chrome-text transition-colors hover:text-chrome-text-active md:hidden"
          >
            {menuOpen ? (
              <XIcon className="size-5" />
            ) : (
              <MenuIcon className="size-5" />
            )}
          </button>
        </div>
        <nav
          id="app-shell-nav"
          className={cn(
            'mt-4 flex-col gap-1 md:mt-0 md:flex',
            menuOpen ? 'flex' : 'hidden',
          )}
        >
          {NAV_ITEMS.map((item) => (
            <a
              key={item.href}
              href={item.href}
              onClick={() => setMenuOpen(false)}
              className="rounded-card px-3 py-2 text-body font-semibold text-chrome-text transition-colors hover:text-chrome-text-active"
            >
              {item.label}
            </a>
          ))}
        </nav>
        {user !== null ? (
          // Collapses with the nav below the breakpoint (same menuOpen gate),
          // and sits at the foot of the sidebar above it.
          <div
            className={cn(
              'mt-4 flex-col gap-1 md:mt-auto md:flex',
              menuOpen ? 'flex' : 'hidden',
            )}
          >
            <span className="px-3 text-meta text-chrome-text">
              Signed in as {user.first_name} {user.last_name}
            </span>
            <button
              type="button"
              onClick={handleSignOut}
              disabled={signingOut}
              className="flex items-center gap-2 rounded-card px-3 py-2 text-body font-semibold text-chrome-text transition-colors hover:text-chrome-text-active disabled:opacity-50"
            >
              <LogOutIcon className="size-4" />
              {signingOut ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        ) : null}
      </aside>
      <main className="min-w-0 flex-1 bg-surface p-4 text-text-primary md:p-8">
        {children}
      </main>
    </div>
  )
}
