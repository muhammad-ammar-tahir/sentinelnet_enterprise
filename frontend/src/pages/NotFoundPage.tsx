/**
 * pages/NotFoundPage.tsx — 404 Not Found
 *
 * Rendered by the catch-all route (* path) in App.tsx.
 * Shows a friendly 404 message with a link back to the dashboard.
 */
import { Link } from 'react-router-dom'
import { Network } from 'lucide-react'

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-base text-center">
      <div className="space-y-4">
        <Network size={48} className="text-gray-600 mx-auto" strokeWidth={1} />
        <h1 className="text-4xl font-bold text-white">404</h1>
        <p className="text-gray-400">Page not found.</p>
        <Link to="/dashboard" className="btn-primary inline-block mt-4">
          Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
