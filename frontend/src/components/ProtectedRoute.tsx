import { createContext, useContext, useState, ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { authAPI } from '../services/authService'

interface AuthContextType {
  token: string | null
  role: string | null
  login: (token: string, role: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'))
  const [role, setRole] = useState<string | null>(localStorage.getItem('role'))

  const login = (newToken: string, newRole: string) => {
    localStorage.setItem('token', newToken)
    localStorage.setItem('role', newRole)
    setToken(newToken)
    setRole(newRole)
  }

  const logout = () => {
    // 尽力通知后端吊销当前 token；即使失败（如网络问题）也照常本地登出
    authAPI.logout().catch(() => {})
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    setToken(null)
    setRole(null)
  }

  return (
    <AuthContext.Provider value={{ token, role, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

export default function ProtectedRoute({
  children,
  adminOnly = false,
}: {
  children: ReactNode
  adminOnly?: boolean
}) {
  const token = localStorage.getItem('token')
  const role = localStorage.getItem('role')

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (adminOnly && role !== 'admin') {
    return <Navigate to="/chat" replace />
  }

  return <>{children}</>
}
