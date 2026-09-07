import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ComponentPreview from '@/pages/_ComponentPreview'

// Task 2: /login and /register render the real auth pages, wrapped in the
// AuthProvider they read/write. The full route table and the (cosmetic) auth
// guard are Task 3 — until then `/` still shows the Task 1 design-system
// preview.
function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ComponentPreview />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
