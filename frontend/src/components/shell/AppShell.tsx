import type { ReactNode } from 'react'

/**
 * Persistent dark sidebar (chrome tokens) + light content area. Wraps every
 * in-app page post-login. The sidebar is the sole wayfinding device; content
 * never uses dark chrome.
 *
 * Nav is exactly the two top-level destinations from design.md's routing
 * table. Links are plain anchors for now — active state and client-side
 * navigation are wired in the routing task.
 */
const NAV_ITEMS = [
  { label: 'Requests Dashboard', href: '/' },
  { label: 'Submit Request', href: '/requests/new' },
]

export interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-sidebar shrink-0 flex-col gap-6 bg-chrome p-4">
        <span className="px-3 text-subhead font-bold text-chrome-text-active">
          Service Portal
        </span>
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="rounded-card px-3 py-2 text-body font-semibold text-chrome-text transition-colors hover:text-chrome-text-active"
            >
              {item.label}
            </a>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 bg-surface p-6 text-text-primary">
        {children}
      </main>
    </div>
  )
}
