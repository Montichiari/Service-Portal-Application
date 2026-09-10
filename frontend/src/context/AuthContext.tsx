import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  getMe,
  login as loginRequest,
  logout as logoutRequest,
  type LoginInput,
  type SessionUser,
} from '@/lib/api'

/**
 * The real session (T-AUTH-5), replacing the prototype's cosmetic `role`
 * useState.
 *
 * The session itself lives in two httpOnly cookies the page can never read
 * (design.md §1), so this context holds no credential and no token — only a
 * cache of what `GET /auth/me` last returned. That is what fixes "signed-in
 * state is lost on reload" structurally: a fresh page has the cookies whether
 * or not React remembers anything, and AUTH-14 is how it finds out.
 *
 * The cache is refreshed on mount and after login/logout — the three moments
 * it can change without a navigation. It is never the authority on access:
 * every real check is server-side (XC-5, XC-6), so a stale `user` here can
 * make the UI wrong, never permissive.
 *
 * Context, provider and hook are colocated on purpose — they are one public
 * surface. That trips react/only-export-components (a fast-refresh hint),
 * suppressed on the hook below; editing this file forces a full reload, which
 * is fine for an auth boundary.
 */
interface AuthContextValue {
  /** `null` once bootstrapped and signed out; also `null` while loading. */
  user: SessionUser | null
  /** True until the bootstrap `GET /auth/me` settles, either way. */
  isLoading: boolean
  /** Throws the `ApiError` from `POST /auth/login` — AUTH-7 is the caller's to render. */
  signIn: (input: LoginInput) => Promise<SessionUser>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    async function bootstrap() {
      try {
        const me = await getMe(controller.signal)
        if (active) setUser(me)
      } catch {
        // A `401` is the expected answer for a visitor who isn't signed in
        // (AUTH-15), and every other failure leaves us just as sessionless.
        // Nothing here distinguishes them because nothing here would act on
        // the difference — an abort is covered by `active` instead.
        if (active) setUser(null)
      } finally {
        if (active) setIsLoading(false)
      }
    }

    void bootstrap()
    return () => {
      active = false
      controller.abort()
    }
  }, [])

  const signIn = useCallback(async (input: LoginInput) => {
    // Login returns the same shape as `/auth/me` (design.md §2), so there is
    // no confirming round trip to make — the response *is* the bootstrap.
    const me = await loginRequest(input)
    setUser(me)
    return me
  }, [])

  const signOut = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      // Cleared even if the call failed. AUTH-13 makes logout idempotent, so
      // the only failure left is "the request never arrived" — and refusing to
      // sign out locally would strand the user on a page they asked to leave.
      // Their next load asks `/auth/me` again and tells the truth either way.
      setUser(null)
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, signIn, signOut }),
    [user, isLoading, signIn, signOut],
  )

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
