import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import ChatPage from './pages/ChatPage'
import KnowledgeBase from './pages/KnowledgeBase'
import ProtectedRoute from './components/ProtectedRoute'

function App() {
  const token = localStorage.getItem('token')

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/knowledge"
          element={
            <ProtectedRoute adminOnly>
              <KnowledgeBase />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to={token ? "/chat" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
