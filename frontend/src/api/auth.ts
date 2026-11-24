/**
 * api/auth.ts — Authentication API module
 *
 * Wraps the FastAPI auth endpoints:
 *   POST /api/auth/login   → obtain JWT tokens
 *   POST /api/auth/refresh → refresh an expired access token
 *
 * Functions here are called by AuthContext, not by components directly.
 * Components should interact with auth via the useAuth() hook.
 */
import client from './client'
import type { LoginCredentials, LoginResponse, AuthTokens } from '@/types'

/**
 * Authenticate with username + password.
 * Returns access token + user profile on success.
 * Throws AxiosError on 401 (invalid credentials).
 */
export async function login(credentials: LoginCredentials): Promise<LoginResponse> {
  const { data } = await client.post<LoginResponse>('/auth/login', credentials)
  return data
}

/**
 * Exchange a refresh token for a new access token.
 * Called automatically by AuthContext before the access token expires.
 */
export async function refreshToken(refreshToken: string): Promise<AuthTokens> {
  const { data } = await client.post<AuthTokens>('/auth/refresh', { refresh_token: refreshToken })
  return data
}
