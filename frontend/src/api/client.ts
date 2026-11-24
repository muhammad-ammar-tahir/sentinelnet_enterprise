/**
 * api/client.ts — Axios HTTP Client Singleton
 *
 * Creates a pre-configured Axios instance used by all API modules.
 *
 * Configuration:
 * - baseURL: read from VITE_API_BASE_URL env variable (default: /api)
 *   The Vite dev-server proxy forwards /api/* to localhost:8000.
 * - timeout: 15 seconds (matches RYU_API_TIMEOUT in backend)
 * - Request interceptor: attaches the JWT access token from localStorage
 *   as an Authorization: Bearer header on every request.
 * - Response interceptor: on 401 Unauthorized, clears local auth state
 *   and redirects to /login so the session expires gracefully.
 *
 * Usage:
 *   import client from '@/api/client'
 *   const res = await client.get('/incidents')
 */
import axios, { AxiosError } from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor — attach JWT ───────────────────────────────────────
client.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor — handle 401 ─────────────────────────────────────
client.interceptors.response.use(
  response => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
