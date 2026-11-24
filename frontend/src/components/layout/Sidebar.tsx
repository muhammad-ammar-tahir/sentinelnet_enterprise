/**
 * components/layout/Sidebar.tsx — SentinelNet Enterprise NOC Sidebar
 *
 * Replicates the exact sidebar from the mockups with:
 * - Brand banner with glowing hub symbol & AUTONOMOUS SDN label
 * - Sections: OPERATIONS, AUTOMATION, INFRASTRUCTURE
 * - Live incident counters, health bar, and operator clearance badge
 */
import { NavLink } from 'react-router-dom'
import { useIncidents } from '@/hooks/useIncidents'

interface SidebarProps {
  open: boolean
  onClose: () => void
}

interface NavItem {
  label: string
  to: string
  icon: string
  badge?: string | number
  badgeColor?: string
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const { data: incidents } = useIncidents({ status: 'DETECTED' })
  const activeCount = incidents?.total ?? 3

  const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
    {
      title: 'OPERATIONS',
      items: [
        { label: 'Overview', to: '/dashboard', icon: 'grid_view' },
        { label: 'Live Topology', to: '/topology', icon: 'hub', badge: 'SDN', badgeColor: 'bg-primary/10 text-primary' },
        { label: 'AI Monitoring', to: '/ai', icon: 'psychology', badge: 'LIVE', badgeColor: 'bg-secondary/15 text-secondary' },
        { label: 'Fault Diagnosis', to: '/diagnosis', icon: 'troubleshoot', badge: activeCount, badgeColor: 'bg-error/20 text-error' },
        { label: 'Incident Analytics', to: '/incidents', icon: 'analytics' },
      ],
    },
    {
      title: 'AUTOMATION',
      items: [
        { label: 'Recovery Center', to: '/recovery', icon: 'autorenew', badge: 'ACTIVE', badgeColor: 'bg-primary/15 text-primary' },
        { label: 'Policies & Rules', to: '/policies', icon: 'shield' },
      ],
    },
    {
      title: 'INFRASTRUCTURE',
      items: [
        { label: 'Device Inventory', to: '/devices', icon: 'dns' },
        { label: 'Predictive Health', to: '/maintenance', icon: 'monitoring' },
        { label: 'Digital Twin', to: '/digital-twin', icon: 'memory' },
        { label: 'Integrations', to: '/integrations', icon: 'cable' },
      ],
    },
  ]

  const linkClass = ({ isActive }: { isActive: boolean }) => `
    flex items-center justify-between px-3 py-2 rounded text-xs font-medium transition-all group
    ${isActive
      ? 'bg-surface-container-high/90 text-primary border-l-2 border-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
      : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container/60'
    }
  `

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed top-8 bottom-0 left-0 w-64 bg-surface-container-low border-r border-outline-variant/20 z-40 flex flex-col justify-between transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Logo Brand Header */}
          <div className="p-4 border-b border-outline-variant/20 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded bg-primary flex items-center justify-center text-on-primary shadow-[0_0_15px_rgba(78,222,163,0.35)]">
                <span className="material-symbols-outlined text-[22px]">shield_with_heart</span>
              </div>
              <div className="flex flex-col">
                <span className="font-display font-bold text-sm text-on-surface tracking-tight">SentinelNet</span>
                <span className="font-code text-[10px] text-primary tracking-widest uppercase font-semibold">AUTONOMOUS SDN</span>
              </div>
            </div>

            <button onClick={onClose} className="lg:hidden text-outline hover:text-on-surface p-1">
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          </div>

          {/* Nav Categories */}
          <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
            {NAV_SECTIONS.map(section => (
              <div key={section.title} className="space-y-1">
                <div className="px-3 pb-1 font-code text-[10px] text-outline tracking-wider font-semibold">
                  {section.title}
                </div>
                {section.items.map(item => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={() => { if (window.innerWidth < 1024) onClose() }}
                    className={linkClass}
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="material-symbols-outlined text-[18px] opacity-80 group-hover:opacity-100">
                        {item.icon}
                      </span>
                      <span>{item.label}</span>
                    </div>
                    {item.badge !== undefined && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-code font-bold ${item.badgeColor || 'bg-surface-container text-outline'}`}>
                        {item.badge}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        </div>

        {/* Bottom Health & Clearance Status */}
        <div className="p-3 border-t border-outline-variant/20 bg-surface-container-lowest/60">
          <div className="bg-surface-container/80 border border-outline-variant/20 rounded p-2.5 space-y-2 mb-2">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-outline font-medium">Campus SLA Health</span>
              <span className="text-primary font-code font-bold">98.2%</span>
            </div>
            <div className="w-full h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full transition-all duration-500 shadow-[0_0_8px_rgba(78,222,163,0.5)]" style={{ width: '98.2%' }} />
            </div>
          </div>

          <div className="flex items-center justify-between px-1 text-[11px] text-outline font-code">
            <span>Ryu v4.34</span>
            <span className="text-secondary">OpenFlow 1.3</span>
          </div>
        </div>
      </aside>
    </>
  )
}
