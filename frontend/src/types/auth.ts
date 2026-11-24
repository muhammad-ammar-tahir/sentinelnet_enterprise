/**
 * types/auth.ts — Authentication and user session types
 *
 * Used by AuthContext to represent the currently authenticated
 * user session and by the login form.
 *
 * UserRole determines which UI actions are available:
 *   viewer   → read-only: can see incidents and metrics
 *   operator → can trigger recovery and edit policies
 *   admin    → full access including user management
 */

export type UserRole = 'admin' | 'operator' | 'viewer'

export interface User {
  id: string
  username: string
  email: string
  role: UserRole
}

export interface AuthTokens {
  accessToken: string
  tokenType: 'bearer'
  expiresIn: number
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse extends AuthTokens {
  user: User
}

export interface AuthState {
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
}
