/**
 * components/layout/TopBar.tsx — High-Tech NOC Header & Telemetry Ticker
 *
 * Implements the sovereign telemetry ticker strip and header controls
 * matching the SentinelNet NOC container design from mockups.
 */
import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useWebSocket } from '@/contexts/WebSocketContext'

interface TopBarProps {
  onToggleSidebar?: () => void
}

export default function TopBar({ onToggleSidebar }: TopBarProps) {
  const { user, logout } = useAuth()
  const { isConnected } = useWebSocket()
  const location = useLocation()

  // Live clocks
  const [utcTime, setUtcTime] = useState('')
  const [estTime, setEstTime] = useState('')
  const [autoRecovery, setAutoRecovery] = useState(true)

  useEffect(() => {
    function updateClocks() {
      const now = new Date()
      setUtcTime(now.toUTCString().slice(17, 25))
      setEstTime(now.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false }))
    }
    updateClocks()
    const timer = setInterval(updateClocks, 1000)
    return () => clearInterval(timer)
  }, [])

  // Derive breadcrumb from pathname
  const pathSegments = location.pathname.split('/').filter(Boolean)
  const currentTitle = pathSegments.length > 0
    ? pathSegments[0].charAt(0).toUpperCase() + pathSegments[0].slice(1).replace('-', ' ')
    : 'Overview'

  return (
    <>
      {/* 1. TOP 32px TELEMETRY TICKER */}
      <div className="fixed top-0 left-0 right-0 h-8 bg-surface-container-lowest border-b border-outline-variant/30 z-50 flex items-center justify-between px-4 sm:px-6 overflow-hidden select-none">
        <div className="flex items-center gap-4 whitespace-nowrap overflow-x-auto text-[11px] font-code">
          <div className="flex items-center gap-1.5 text-on-surface-variant">
            <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
            <span className="font-semibold tracking-wider">TELEMETRY STREAM:</span>
          </div>

          <div className="flex items-center gap-2 text-secondary bg-surface-container-high/60 px-2 py-0.5 rounded">
            <span className="text-primary font-bold">●</span>
            <span>Ryu SDN Controller (C0): OpenFlow 1.3 Active</span>
          </div>

          <div className="hidden md:flex items-center gap-2 text-on-surface-variant">
            <span className="text-outline">MININET NODES:</span>
            <span className="text-primary font-medium">3 Switches · 4 Hosts · 1 Server</span>
          </div>

          <div className="hidden lg:flex items-center gap-2 text-on-surface-variant">
            <span className="text-outline">INGRESS:</span>
            <span className="text-on-surface font-medium">42.8 Gbps</span>
          </div>

          <div className="hidden xl:flex items-center gap-2 text-on-surface-variant">
            <span className="text-outline">PACKET LOSS:</span>
            <span className="text-primary font-medium">0.0001%</span>
          </div>

          <div className="hidden xl:flex items-center gap-2 text-on-surface-variant">
            <span className="text-outline">AUTONOMOUS GUARD:</span>
            <span className="px-1.5 py-0.2 rounded bg-primary/10 text-primary font-semibold">SYNCHRONIZED</span>
          </div>
        </div>

        <div className="flex items-center gap-3 font-code text-[11px] text-outline shrink-0 ml-4">
          <span className="hidden sm:inline">CLUSTER: <span className="text-secondary font-medium">CAMPUS-NET-01α</span></span>
          <span className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-primary animate-pulse' : 'bg-status-down'}`} />
            <span className={isConnected ? 'text-primary' : 'text-status-down'}>
              {isConnected ? 'LIVE WS' : 'STANDBY'}
            </span>
          </span>
        </div>
      </div>

      {/* 2. MAIN HEADER (64px) */}
      <header className="fixed top-8 left-0 lg:left-64 right-0 h-16 bg-surface/90 backdrop-blur-xl border-b border-outline-variant/20 z-30 flex items-center justify-between px-4 sm:px-6 transition-all duration-200">
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            className="lg:hidden text-outline hover:text-on-surface p-1.5 rounded transition-colors"
            title="Toggle Navigation"
          >
            <span className="material-symbols-outlined text-[22px]">menu</span>
          </button>

          <div className="flex items-center gap-2 font-body text-xs sm:text-sm text-outline">
            <span className="text-on-surface-variant font-medium">SentinelNet</span>
            <span>/</span>
            <span className="text-primary font-semibold tracking-wide">{currentTitle}</span>
          </div>
        </div>

        {/* Search */}
        <div className="hidden md:flex relative w-64 lg:w-80">
          <span className="material-symbols-outlined absolute left-3 top-2 text-outline text-[18px]">search</span>
          <input
            className="w-full bg-surface-container-lowest border border-outline-variant/30 rounded pl-9 pr-12 py-1.5 text-xs font-body text-on-surface placeholder:text-outline focus:outline-none focus:border-secondary transition-colors"
            placeholder="Search topology, incidents, IPs..."
            type="text"
          />
          <div className="absolute right-2.5 top-1.5 bg-surface-container px-1.5 py-0.5 rounded font-code text-[10px] text-outline border border-outline-variant/30">
            ⌘K
          </div>
        </div>

        {/* Right Tools */}
        <div className="flex items-center gap-3 sm:gap-4">
          {/* Clocks */}
          <div className="hidden xl:flex items-center gap-3 border-r border-outline-variant/20 pr-3 font-code text-xs text-outline">
            <span>UTC: <span className="text-on-surface font-medium">{utcTime || '14:28:40'}</span></span>
            <span>EST: <span className="text-on-surface font-medium">{estTime || '09:28:40'}</span></span>
          </div>

          {/* Auto-Recovery Toggle Pill */}
          <button
            onClick={() => setAutoRecovery(!autoRecovery)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-code transition-all border ${
              autoRecovery
                ? 'bg-primary-container/15 border-primary/40 text-primary shadow-[0_0_12px_rgba(78,222,163,0.15)]'
                : 'bg-surface-container-high border-outline-variant/30 text-outline'
            }`}
            title="Click to toggle autonomous closed-loop self-healing"
          >
            <span className={`w-2 h-2 rounded-full ${autoRecovery ? 'bg-primary animate-pulse' : 'bg-outline'}`} />
            <span className="font-semibold hidden sm:inline">Auto-Recovery:</span>
            <span>{autoRecovery ? 'ENABLED' : 'MANUAL'}</span>
          </button>

          {/* Notifications */}
          <button className="relative p-1.5 text-outline hover:text-on-surface transition-colors" title="Notifications">
            <span className="material-symbols-outlined text-[20px]">notifications</span>
            <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-error animate-ping-slow" />
          </button>

          {/* User Profile dropdown */}
          <div className="flex items-center gap-2 pl-2 border-l border-outline-variant/20">
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center font-bold text-on-primary text-xs shadow-[0_0_10px_rgba(78,222,163,0.3)]">
              {user?.username?.slice(0, 2).toUpperCase() || 'SC'}
            </div>
            <div className="hidden md:flex flex-col text-left">
              <span className="text-xs font-semibold text-on-surface leading-none">{user?.username || 'Sarah Chen'}</span>
              <span className="text-[10px] font-code text-secondary">L3 OPERATOR</span>
            </div>
            <button onClick={logout} className="text-outline hover:text-error transition-colors p-1" title="Sign out">
              <span className="material-symbols-outlined text-[18px]">logout</span>
            </button>
          </div>
        </div>
      </header>
    </>
  )
}
