/**
 * components/layout/ProtectedRoute.tsx — Authentication Guard
 *
 * Wraps all dashboard routes. If the user is not authenticated
 * (no valid JWT in AuthContext), redirects to /login with a
 * `redirect` search param so the user is returned to their
 * intended page after logging in.
 *
 * Uses React Router's <Outlet /> to render child routes when authenticated.
 *
 * Example:
 *   <Route element={<ProtectedRoute />}>
 *     <Route path="/dashboard" element={<DashboardPage />} />
 *   </Route>
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-base">
        <div className="animate-spin w-8 h-8 border-2 border-sentinel-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
