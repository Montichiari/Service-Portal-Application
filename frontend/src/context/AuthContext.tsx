import { createContext, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

/**
 * Cosmetic auth state for the demo: a single `role` value plus its setter and
 * nothing else — no credentials, no token, no persistence. Reloading the page
 * clears the role. The route guard that will read this (Task 3) is likewise
 * cosmetic; real enforcement is server-side in Phase 3. See frontend/CLAUDE.md,
 * "Auth guard pattern".
 *
 * Context, provider and hook are colocated here on purpose — they are one
 * public surface. That trips react/only-export-components (a fast-refresh
 * hint), which is suppressed on the hook below; editing this file triggers a
 * full reload, which is fine for an auth boundary.
 */
export type Role = 'user' | 'admin' | null

interface AuthContextValue {
  role: Role
  setRole: (role: Role) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>(null)
  const value = useMemo<AuthContextValue>(() => ({ role, setRole }), [role])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// oxlint-disable-next-line react/only-export-components -- hook belongs with its context; see file header
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
