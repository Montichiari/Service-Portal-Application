import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import RequestsDashboardPage from '@/pages/RequestsDashboardPage'
import SubmitRequestPage from '@/pages/SubmitRequestPage'

// Task 2: /login and /register render the real auth pages, wrapped in the
// AuthProvider they read/write.
//
// Task 4: /requests/new renders the Submit Service Request page.
//
// Task 5: `/` renders the real Requests Dashboard, replacing the temporary
// Task 1 design-system preview (now deleted).
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
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
