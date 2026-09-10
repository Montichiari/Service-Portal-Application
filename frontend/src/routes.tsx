import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import RegisterPage from '@/pages/RegisterPage'
import RequestDetailsPage from '@/pages/RequestDetailsPage'
import RequestStatusPage from '@/pages/RequestStatusPage'
import RequestsDashboardPage from '@/pages/RequestsDashboardPage'
import SubmitRequestPage from '@/pages/SubmitRequestPage'

/**
 * The route table (T-DEBT-2), matching specs/frontend-phase/design.md's
 * routing table: `/login` and `/register` are public, the four in-app routes
 * require a session, and anything else is a not-found page.
 *
 * This file is the one frontend/CLAUDE.md has described since the prototype
 * phase but which was never built — routing lived inline in App.tsx, entirely
 * unguarded, from Task 3 through the whole of Group 1.
 */

/**
 * Redirect to `/login` when there is no session.
 *
 * **This guard is cosmetic only.** It is not an access control and must never
 * be treated as one: every real authorization check is server-side (`XC-6`,
 * `XC-13`, `SR-1`, `SC-4`, `CM-7` in specs/api-phase/requirements.md), where
 * it cannot be edited away by anyone holding devtools. What it buys is the
 * signed-out experience — a login redirect instead of a screenful of `401`s
 * once T-SR-1 makes these pages fetch real data. Nothing server-side may ever
 * be relaxed because this exists, and nothing may ever be gated on this alone.
 *
 * The session has **three** states, not two. `AuthContext` bootstraps from
 * `GET /auth/me`, so on first mount the answer is not yet known — pending is
 * not the same as signed out. Redirecting while pending would bounce a
 * signed-in user to `/login` on every reload, before their own session had
 * finished loading. So pending renders nothing and decides nothing; only a
 * settled `user === null` redirects.
 *
 * Nothing is rendered during that window rather than a spinner: the loading
 * pattern for this app is established once in T-SR-1 (frontend/CLAUDE.md,
 * Component conventions), and inventing a second one here first is exactly
 * what that rule exists to prevent.
 */
function RequireSession() {
  const { user, isLoading } = useAuth()

  if (isLoading) return null
  // `replace`, not a push: a redirect the user never asked for shouldn't sit
  // in their history, where Back would bounce them straight back to it.
  if (user === null) return <Navigate to="/login" replace />

  return <Outlet />
}

export function AppRoutes() {
  return (
    <Routes>
      {/* Public — reachable with no session, by definition. */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Guarded as a group rather than one wrapper per route: a route added
          inside this block is protected by construction, where a per-route
          wrapper is one forgotten line away from shipping unguarded. */}
      <Route element={<RequireSession />}>
        <Route path="/" element={<RequestsDashboardPage />} />
        <Route path="/requests/new" element={<SubmitRequestPage />} />
        <Route path="/requests/:id" element={<RequestDetailsPage />} />
        <Route path="/requests/:id/status" element={<RequestStatusPage />} />
      </Route>

      {/* frontend-contract.md §8.5 — public on purpose; see NotFoundPage. */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
