import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ChatProvider } from '@/context/ChatContext'
import { AppRoutes } from '@/routes'

/**
 * Composition root: the session provider, the router, and the route table
 * (`routes.tsx`, built in T-DEBT-2 — routing used to be declared inline here,
 * unguarded).
 *
 * `AuthProvider` sits outside `BrowserRouter` because the session is not a
 * routing concern: it bootstraps once from `GET /auth/me` and survives every
 * navigation. The guard inside `routes.tsx` is what connects the two.
 *
 * `ChatProvider` (T-CHAT-2) sits in the same place for the same reason, and
 * for one more: the widget it feeds is mounted inside `AppShell`, which each
 * page renders itself, so the widget is destroyed and rebuilt on every
 * navigation. CHAT-15 asks the conversation to survive that, which it can only
 * do from above the router. It is inside `AuthProvider` because the
 * conversation belongs to a session and is cleared when that session changes.
 */
function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ChatProvider>
    </AuthProvider>
  )
}

export default App
