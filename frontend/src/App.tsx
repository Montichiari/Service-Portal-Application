import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import RequestDetailsPage from '@/pages/RequestDetailsPage'
import RequestsDashboardPage from '@/pages/RequestsDashboardPage'
import RequestStatusPage from '@/pages/RequestStatusPage'
import SubmitRequestPage from '@/pages/SubmitRequestPage'

// Task 2: /login and /register render the real auth pages, wrapped in the
// AuthProvider they read/write.
//
// Task 4: /requests/new renders the Submit Service Request page.
//
// Task 5: `/` renders the real Requests Dashboard, replacing the temporary
// Task 1 design-system preview (now deleted).
//
// Task 6: /requests/:id and /requests/:id/status render the real View Request
// Details and Track Request Status pages. (Task 3 was never landed, so there
// were no placeholder routes here to replace — these are wired the same
// unguarded way as the others; the cosmetic auth guard is still Task 3's job.)
//
// Routing is still deliberately minimal — the full route table and the
// (cosmetic) auth guard are Task 3, so nothing here is guarded yet.
function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<RequestsDashboardPage />} />
          <Route path="/requests/new" element={<SubmitRequestPage />} />
          <Route path="/requests/:id" element={<RequestDetailsPage />} />
          <Route path="/requests/:id/status" element={<RequestStatusPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
