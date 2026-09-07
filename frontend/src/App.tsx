import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import SubmitRequestPage from '@/pages/SubmitRequestPage'
import ComponentPreview from '@/pages/_ComponentPreview'

// Task 2: /login and /register render the real auth pages, wrapped in the
// AuthProvider they read/write.
//
// Task 4: /requests/new is mounted directly so the Submit Service Request
// page is reachable. It is NOT guarded yet — the full route table and the
// (cosmetic) auth guard are still Task 3, and `/` still shows the Task 1
// design-system preview until then.
function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ComponentPreview />} />
          <Route path="/requests/new" element={<SubmitRequestPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
