import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { AppRoutes } from '@/routes'

/**
 * Composition root: the session provider, the router, and the route table
 * (`routes.tsx`, built in T-DEBT-2 — routing used to be declared inline here,
 * unguarded).
 *
 * `AuthProvider` sits outside `BrowserRouter` because the session is not a
 * routing concern: it bootstraps once from `GET /auth/me` and survives every
 * navigation. The guard inside `routes.tsx` is what connects the two.
 */
function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
