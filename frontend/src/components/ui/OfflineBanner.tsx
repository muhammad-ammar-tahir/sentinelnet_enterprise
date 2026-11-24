/**
 * components/ui/OfflineBanner.tsx — Global Backend Connectivity Watchdog
 *
 * Polls GET /api/health periodically. If 3 consecutive probes fail,
 * displays a global warning banner at the top of the viewport.
 */
import { useState, useEffect } from 'react'
import { WifiOff, RefreshCw, AlertTriangle } from 'lucide-react'
import client from '@/api/client'

export default function OfflineBanner() {
  const [consecutiveFailures, setConsecutiveFailures] = useState<number>(0)
  const [isChecking, setIsChecking] = useState<boolean>(false)

  const checkHealth = async () => {
    setIsChecking(true)
    try {
      await client.get('/health', { timeout: 3000 })
      setConsecutiveFailures(0)
    } catch {
      setConsecutiveFailures(prev => prev + 1)
    } finally {
      setIsChecking(false)
    }
  }

  useEffect(() => {
    // Initial check
    checkHealth()

    // Poll health every 8 seconds
    const interval = setInterval(() => {
      checkHealth()
    }, 8000)

    return () => clearInterval(interval)
  }, [])

  const isOffline = consecutiveFailures >= 3

  if (!isOffline) return null

  return (
    <aside aria-label="Backend offline notification" className="w-full bg-error text-on-error px-4 py-2.5 shadow-lg border-b border-error-container flex items-center justify-between z-50 animate-bounce-subtle">
      <div className="flex items-center gap-3">
        <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center shrink-0">
          <WifiOff size={16} className="text-white" />
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 text-xs">
          <span className="font-display font-bold uppercase tracking-wider flex items-center gap-1">
            <AlertTriangle size={14} /> Backend System Offline:
          </span>
          <span className="font-body opacity-95">
            Unable to reach /api/health ({consecutiveFailures} consecutive failed probes). Telemetry feeds and automated SDN actuation are currently unavailable.
          </span>
        </div>
      </div>

      <button
        onClick={checkHealth}
        disabled={isChecking}
        className="flex items-center gap-1.5 px-3 py-1 rounded bg-white/20 hover:bg-white/30 text-white font-code text-xs font-bold transition-all shrink-0 ml-3"
      >
        <RefreshCw size={13} className={isChecking ? 'animate-spin' : ''} />
        <span>{isChecking ? 'Rechecking...' : 'Retry Connection'}</span>
      </button>
    </aside>
  )
}
