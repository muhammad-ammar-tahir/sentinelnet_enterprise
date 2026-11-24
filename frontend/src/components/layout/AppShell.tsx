/**
 * components/layout/AppShell.tsx — Sovereign Telemetry Container
 *
 * Provides the persistent enterprise NOC viewport:
 * - Fixed 32px top ticker strip
 * - Fixed 64px header bar
 * - Fixed 256px collapsible left sidebar
 * - Main viewport with fluid responsive margins
 */
import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import OfflineBanner from '@/components/ui/OfflineBanner'

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="min-h-screen bg-surface text-on-surface antialiased flex flex-col">
      {/* Global Connectivity Watchdog */}
      <OfflineBanner />

      {/* Top Telemetry Strip + Header */}
      <TopBar onToggleSidebar={() => setSidebarOpen(!sidebarOpen)} />

      {/* Sidebar Navigation */}
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main Content Viewport — Offset by 256px sidebar and 96px (32px ticker + 64px header) */}
      <div className="lg:pl-64 pt-24 flex-1 flex flex-col min-w-0">
        <main className="flex-1 p-4 sm:p-6 w-full max-w-[1920px] mx-auto overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
