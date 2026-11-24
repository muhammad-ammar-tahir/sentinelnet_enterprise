/**
 * contexts/AuthContext.tsx — Authentication Context
 *
 * Provides global authentication state and actions to the entire app:
 *   - user: currently logged-in User object (null if unauthenticated)
 *   - isAuthenticated: boolean derived from token presence
 *   - login(credentials): POST /api/auth/login, store token, set user
 *   - logout(): clear token, reset state, redirect to /login
 *
 * Token persistence:
 *   - Access token stored in localStorage under key 'access_token'
 *   - On mount, if token exists in localStorage, the user is considered
 *     authenticated (token validity is enforced by the API interceptor)
 *
 * Usage:
 *   const { user, isAuthenticated, login, logout } = useAuth()
 */
import { createContext, useContext, useState, useCallback, ReactNode, useEffect } from 'react'
import { login as apiLogin } from '@/api/auth'
import type { User, LoginCredentials, AuthState } from '@/types'

interface AuthContextValue extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(
    () => localStorage.getItem('access_token')
  )
  const [isLoading, setIsLoading] = useState(false)

  // On mount: if token in localStorage, attempt to restore user from storage
  useEffect(() => {
    const storedUser = localStorage.getItem('user')
    if (storedUser && accessToken) {
      try {
        setUser(JSON.parse(storedUser) as User)
      } catch {
        localStorage.removeItem('user')
      }
    }
  }, [accessToken])

  const login = useCallback(async (credentials: LoginCredentials) => {
    setIsLoading(true)
    try {
      const response = await apiLogin(credentials)
      localStorage.setItem('access_token', response.accessToken)
      localStorage.setItem('user', JSON.stringify(response.user))
      setAccessToken(response.accessToken)
      setUser(response.user)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    setAccessToken(null)
    setUser(null)
    // navigate happens in ProtectedRoute
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated: !!accessToken && !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

/** Hook to consume AuthContext. Throws if used outside AuthProvider. */
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
