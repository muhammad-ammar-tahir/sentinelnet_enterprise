/**
 * pages/IntegrationsPage.tsx — Substrate & Observability Connectors
 *
 * Real Infrastructure Connectivity Diagnostics:
 * - Each connector has a real "Test Connection" that POSTs /api/integrations/test/{id}
 * - Real status (CONNECTED, FAILED, or NOT_IMPLEMENTED) based on socket / HTTP probe
 * - Zero simulated timeouts or fake HTTP 200 acknowledgements.
 */
import { useState } from 'react'
import {
  Database,
  Radio,
  Server,
  Activity,
  Zap,
  LayoutDashboard,
  MessageSquare,
  Webhook,
  RefreshCw
} from 'lucide-react'
import client from '@/api/client'
import toast from 'react-hot-toast'

interface IntegrationService {
  id: string
  name: string
  role: string
  endpoint: string
  protocol: string
  status: 'CONNECTED' | 'FAILED' | 'NOT_IMPLEMENTED' | 'STANDBY'
  latency: string
  lastTested?: string
  message?: string
  icon: any
  iconColor: string
}

const INITIAL_CONNECTORS: IntegrationService[] = [
  {
    id: 'postgres',
    name: 'PostgreSQL Database',
    role: 'Incidents, Metrics, Policies & Audit Logs',
    endpoint: 'postgresql://localhost:5432/sentinelnet',
    protocol: 'AsyncPG / SQLAlchemy 2.0',
    status: 'STANDBY',
    latency: '—',
    icon: Database,
    iconColor: 'text-secondary',
  },
  {
    id: 'ryu',
    name: 'Ryu SDN Controller',
    role: 'OpenFlow 1.3 Control Plane & REST API',
    endpoint: 'http://localhost:8080',
    protocol: 'OpenFlow 1.3 / TCP 6653',
    status: 'STANDBY',
    latency: '—',
    icon: Radio,
    iconColor: 'text-primary',
  },
  {
    id: 'mininet',
    name: 'Mininet Substrate',
    role: 'Virtual Linux Namespaces & OVS Bridges',
    endpoint: 'unix:///var/run/openvswitch/db.sock',
    protocol: 'Linux Kernel veth / OVS',
    status: 'STANDBY',
    latency: '—',
    icon: Server,
    iconColor: 'text-secondary',
  },
  {
    id: 'prometheus',
    name: 'Prometheus Telemetry',
    role: 'Time-Series Scraper & PromQL Exporter',
    endpoint: 'http://localhost:9090',
    protocol: 'HTTP PromQL / 10s Scrapes',
    status: 'STANDBY',
    latency: '—',
    icon: Activity,
    iconColor: 'text-amber-400',
  },
  {
    id: 'redis',
    name: 'Redis Event Bus',
    role: 'Pub/Sub & Autonomous Recovery Queue',
    endpoint: 'redis://localhost:6379/0',
    protocol: 'RESP / WebSocket Bridge',
    status: 'STANDBY',
    latency: '—',
    icon: Zap,
    iconColor: 'text-error',
  },
  {
    id: 'grafana',
    name: 'Grafana Dashboards',
    role: 'Time-Series Telemetry & SLA Panels',
    endpoint: 'http://localhost:3000',
    protocol: 'HTTP OAuth / Provisioned',
    status: 'STANDBY',
    latency: '—',
    icon: LayoutDashboard,
    iconColor: 'text-amber-500',
  },
  {
    id: 'slack',
    name: 'Slack NOC Alerts',
    role: 'Operational Incident Notification Webhook',
    endpoint: 'https://hooks.slack.com/services/...',
    protocol: 'HTTPS Webhook Payload',
    status: 'STANDBY',
    latency: '—',
    icon: MessageSquare,
    iconColor: 'text-purple-400',
  },
  {
    id: 'webhook',
    name: 'Escalation Webhook',
    role: 'External ITIL / PagerDuty Dispatcher',
    endpoint: 'https://api.pagerduty.com/v2/enqueue',
    protocol: 'REST JSON / HMAC SHA-256',
    status: 'STANDBY',
    latency: '—',
    icon: Webhook,
    iconColor: 'text-outline',
  },
]

export default function IntegrationsPage() {
  const [connectors, setConnectors] = useState<IntegrationService[]>(INITIAL_CONNECTORS)
  const [testingId, setTestingId] = useState<string | null>(null)

  // Real Test Connection -> POST /api/integrations/test/{id}
  const handleTestConnection = async (id: string, name: string) => {
    setTestingId(id)
    toast.loading(`Testing live connectivity to ${name}...`, { id: `ping-${id}` })

    try {
      const res = await client.post(`/integrations/test/${id}`)
      const data = res.data

      setConnectors(prev =>
        prev.map(c => {
          if (c.id === id) {
            return {
              ...c,
              status: data.status,
              latency: data.latency_ms > 0 ? `${data.latency_ms} ms` : '—',
              message: data.message,
              lastTested: new Date().toLocaleTimeString(),
            }
          }
          return c
        })
      )

      if (data.status === 'CONNECTED') {
        toast.success(`Connected! ${data.message}`, { id: `ping-${id}` })
      } else if (data.status === 'NOT_IMPLEMENTED') {
        toast(`${data.message}`, { id: `ping-${id}`, icon: 'ℹ️' })
      } else {
        toast.error(`Check failed: ${data.message}`, { id: `ping-${id}` })
      }
    } catch (err: any) {
      setConnectors(prev =>
        prev.map(c => {
          if (c.id === id) {
            return {
              ...c,
              status: 'FAILED',
              latency: '—',
              message: err.response?.data?.detail || err.message,
              lastTested: new Date().toLocaleTimeString(),
            }
          }
          return c
        })
      )
      toast.error(`Connection failed: ${err.response?.data?.detail || err.message}`, { id: `ping-${id}` })
    } finally {
      setTestingId(null)
    }
  }

  // Health check all in parallel
  const handleHealthCheckAll = async () => {
    toast.loading('Running parallel connection probes across all connectors...', { id: 'check-all' })
    const promises = connectors.map(c => client.post(`/integrations/test/${c.id}`).then(res => ({ id: c.id, ...res.data })).catch(err => ({ id: c.id, status: 'FAILED', message: err.message })))
    const results = await Promise.all(promises)
    setConnectors(prev =>
      prev.map(c => {
        const match = results.find(r => r.id === c.id)
        if (match) {
          return {
            ...c,
            status: match.status,
            latency: match.latency_ms > 0 ? `${match.latency_ms} ms` : '—',
            message: match.message,
            lastTested: new Date().toLocaleTimeString(),
          }
        }
        return c
      })
    )
    toast.success('Connection audits completed!', { id: 'check-all' })
  }

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-on-surface tracking-tight">
              Integrations & External Connections
            </h1>
            <span className="px-2 py-0.5 rounded bg-primary/10 text-primary font-code text-xs font-semibold border border-primary/30">
              {connectors.length} CONNECTORS
            </span>
          </div>
          <p className="font-body text-xs text-on-surface-variant">
            Service bindings connecting Mininet, the Ryu OpenFlow controller, telemetry exporters, and incident notification channels.
          </p>
        </div>

        <button
          onClick={handleHealthCheckAll}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-bright text-on-surface font-body text-xs border border-outline-variant/30 transition-all"
        >
          <RefreshCw size={14} className="text-secondary" />
          <span>Health-Check All</span>
        </button>
      </div>

      {/* Connectors Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {connectors.map(conn => {
          const isBusy = testingId === conn.id
          const IconComp = conn.icon

          return (
            <div
              key={conn.id}
              className="bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 p-4 shadow-xl flex flex-col justify-between space-y-3"
            >
              <div>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`p-1.5 rounded-lg bg-surface-container ${conn.iconColor}`}>
                      <IconComp size={20} />
                    </div>
                    <h3 className="font-display font-bold text-sm text-on-surface">{conn.name}</h3>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-code font-bold ${
                    conn.status === 'CONNECTED'
                      ? 'bg-primary/10 text-primary border border-primary/30'
                      : conn.status === 'FAILED'
                      ? 'bg-error/15 text-error border border-error/40'
                      : conn.status === 'NOT_IMPLEMENTED'
                      ? 'bg-amber-400/10 text-amber-300 border border-amber-400/30'
                      : 'bg-surface-container text-outline border border-outline-variant/30'
                  }`}>
                    {conn.status}
                  </span>
                </div>

                <p className="text-xs text-on-surface-variant mt-2 font-body">{conn.role}</p>

                <div className="mt-3 p-2 rounded bg-surface-container-lowest/80 border border-outline-variant/20 font-code text-[11px] text-outline truncate" title={conn.endpoint}>
                  {conn.endpoint}
                </div>

                {conn.message && (
                  <p className="mt-2 text-[11px] font-code text-on-surface-variant">
                    {conn.message}
                  </p>
                )}
              </div>

              <div className="space-y-2 pt-2 border-t border-outline-variant/15 text-[11px] font-code">
                <div className="flex items-center justify-between text-outline">
                  <span>Protocol:</span>
                  <span className="text-on-surface">{conn.protocol}</span>
                </div>
                <div className="flex items-center justify-between text-outline">
                  <span>Latency:</span>
                  <span className={conn.status === 'CONNECTED' ? 'text-primary font-bold' : 'text-outline'}>
                    {conn.latency}
                  </span>
                </div>

                <button
                  onClick={() => handleTestConnection(conn.id, conn.name)}
                  disabled={isBusy}
                  className="w-full mt-2 py-1.5 rounded bg-surface-container hover:bg-surface-bright text-on-surface text-xs font-code transition-colors border border-outline-variant/30 flex items-center justify-center gap-1.5 disabled:opacity-50"
                >
                  <RefreshCw size={13} className={isBusy ? 'animate-spin' : ''} />
                  <span>{isBusy ? 'Probing...' : 'Test Connection'}</span>
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
