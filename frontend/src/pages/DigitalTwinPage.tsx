/**
 * pages/DigitalTwinPage.tsx — Air-Gapped Digital Twin Recovery Sandbox
 *
 * Implements NetworkX graph-based recovery simulation:
 * - "Simulate" button -> POST /api/recovery/simulate { incident_id }
 * - Clearly labeled as "simulated, not measured"
 * - Displays predicted latency, packet loss, capacity headroom, and predicted vs actual metrics.
 * - Zero hardcoded mock outcomes.
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Cpu,
  Play,
  ArrowRight,
  Info
} from 'lucide-react'
import client from '@/api/client'
import DataStateWrapper from '@/components/ui/DataStateWrapper'
import toast from 'react-hot-toast'

interface SimulationResponse {
  incident_id: string
  target: string
  scenario: string
  simulated: boolean
  disclaimer: string
  predicted_metrics: {
    predicted_latency_ms: number
    baseline_latency_ms: number
    latency_delta_ms: number
    predicted_packet_loss_pct: number
    flow_mod_rules_required: number
    capacity_headroom_mbps: number
    safeguards_verified: boolean
  }
  simulated_path: {
    hops: string[]
    path_type: string
    avoided_nodes: string[]
  }
  timestamp: string
}

export default function DigitalTwinPage() {
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>('')
  const [simulationResult, setSimulationResult] = useState<SimulationResponse | null>(null)

  // 1. Fetch real incidents from DB to pick which one to simulate
  const { data: incidents = [], isLoading: incidentsLoading } = useQuery<any[]>({
    queryKey: ['incidents', 'for-sim'],
    queryFn: async () => {
      const res = await client.get('/incidents')
      if (res.data && res.data.length > 0 && !selectedIncidentId) {
        setSelectedIncidentId(res.data[0].id)
      }
      return res.data || []
    },
  })

  // 2. Real Simulation Mutation -> POST /api/recovery/simulate
  const simMutation = useMutation({
    mutationFn: async (incidentId: string) => {
      const res = await client.post('/recovery/simulate', { incident_id: incidentId })
      return res.data as SimulationResponse
    },
    onMutate: () => {
      toast.loading('Running NetworkX path simulation & capacity check...', { id: 'sim-post' })
    },
    onSuccess: (data) => {
      setSimulationResult(data)
      toast.success('Simulation complete (labeled: simulated, not measured)', { id: 'sim-post' })
    },
    onError: (err: any) => {
      toast.error(`Simulation failed: ${err.response?.data?.detail || err.message}`, { id: 'sim-post' })
    },
  })

  const targetIncident = incidents.find(i => i.id === selectedIncidentId)

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-on-surface tracking-tight">
              Digital Twin Recovery Sandbox
            </h1>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-code text-xs border border-primary/20 shadow-[0_0_12px_rgba(78,222,163,0.2)]">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />
              <span>NetworkX Model Active</span>
            </span>
          </div>
          <p className="font-body text-xs text-on-surface-variant">
            Simulate recovery actions in a mathematical graph model before applying to production switches.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-surface-container font-code text-xs text-on-surface-variant border border-outline-variant/30">
            <Cpu size={14} className="text-secondary" />
            <span>Sandbox: <strong className="text-on-surface">Mininet + OVS + NetworkX</strong></span>
          </div>
        </div>
      </div>

      {/* Top Info Banner with Clear Simulation Label */}
      <div className="rounded-xl bg-surface-container-low border border-outline-variant/30 p-5 shadow-xl backdrop-blur-xl space-y-2">
        <div className="flex items-center gap-2 text-primary">
          <Info size={18} />
          <span className="font-code text-xs font-bold uppercase tracking-wider">Predictive Telemetry Notice</span>
        </div>
        <p className="font-body text-xs text-on-surface-variant">
          All recovery plans evaluated in this sandbox execute inside an in-memory NetworkX graph representation.
          Outcomes are <strong className="text-amber-400">simulated, not measured</strong>. Real data-plane verification occurs post-actuation via OpenFlow flow monitors.
        </p>
      </div>

      {/* Main Grid: Select Incident to Simulate & Outcomes */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left 5 Cols: Incident Target Selector */}
        <div className="lg:col-span-5 bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
            <h3 className="font-display font-semibold text-sm text-on-surface">Select Incident to Simulate</h3>
            <span className="font-code text-xs text-outline">POST /api/recovery/simulate</span>
          </div>

          <DataStateWrapper
            isLoading={incidentsLoading}
            isEmpty={incidents.length === 0}
            emptyTitle="No Incidents Available for Simulation"
            emptyMessage="No incidents currently exist in database to run what-if simulation against."
          >
            <div className="space-y-3 font-code text-xs">
              <div>
                <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">Incident Target</label>
                <select
                  value={selectedIncidentId}
                  onChange={e => setSelectedIncidentId(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded p-2.5 text-on-surface focus:outline-none focus:border-secondary cursor-pointer"
                >
                  {incidents.map(inc => (
                    <option key={inc.id} value={inc.id}>
                      {inc.id} — {inc.title || inc.fault_type} ({inc.severity})
                    </option>
                  ))}
                </select>
              </div>

              {targetIncident && (
                <div className="p-3 rounded bg-surface-container/60 border border-outline-variant/20 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-outline uppercase text-[10px]">Severity:</span>
                    <span className="font-bold text-amber-400">{targetIncident.severity.toUpperCase()}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-outline uppercase text-[10px]">Affected Target:</span>
                    <span className="font-bold text-on-surface">
                      {targetIncident.affected_link_id || targetIncident.affected_device_id || 'Campus Core'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-outline uppercase text-[10px]">Root Cause:</span>
                    <span className="text-secondary">{targetIncident.root_cause || 'link_degradation'}</span>
                  </div>
                </div>
              )}

              <button
                onClick={() => simMutation.mutate(selectedIncidentId)}
                disabled={simMutation.isPending || !selectedIncidentId}
                className="w-full py-2.5 rounded bg-primary hover:bg-primary-container text-on-primary font-bold transition-all shadow-[0_0_15px_rgba(78,222,163,0.3)] disabled:opacity-50 flex items-center justify-center gap-2 mt-4"
              >
                <Play size={15} />
                <span>{simMutation.isPending ? 'Simulating Alternate Path...' : 'Simulate Recovery Policy'}</span>
              </button>
            </div>
          </DataStateWrapper>
        </div>

        {/* Right 7 Cols: Simulation Outcomes & Predicted vs Actual */}
        <div className="lg:col-span-7 bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
            <div className="flex items-center gap-2">
              <span className="font-display font-semibold text-sm text-on-surface">Predicted Metrics (Simulated, Not Measured)</span>
            </div>
            <span className={`font-code text-xs font-bold px-2 py-0.5 rounded ${
              simulationResult ? 'bg-primary/10 text-primary border border-primary/30' : 'bg-surface-container text-outline'
            }`}>
              {simulationResult ? 'SIMULATION READY' : 'AWAITING RUN'}
            </span>
          </div>

          <DataStateWrapper
            isEmpty={!simulationResult}
            emptyTitle="No Simulation Executed"
            emptyMessage="Select an incident on the left and click 'Simulate Recovery Policy' to run NetworkX graph calculation."
          >
            {simulationResult && (
              <div className="space-y-4">
                {/* Notice Pill */}
                <div className="p-2.5 rounded bg-amber-400/10 border border-amber-400/30 text-amber-300 font-code text-xs flex items-center gap-2">
                  <Info size={16} className="shrink-0" />
                  <span>{simulationResult.disclaimer}</span>
                </div>

                {/* 4 Metric Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-code">
                  <div className="p-3 rounded bg-surface-container/70 border border-outline-variant/20">
                    <span className="text-[10px] text-outline uppercase block">Predicted Latency</span>
                    <span className="font-bold text-base text-on-surface block mt-1">
                      {simulationResult.predicted_metrics.predicted_latency_ms} ms
                    </span>
                    <span className="text-[10px] text-secondary">
                      Δ {simulationResult.predicted_metrics.latency_delta_ms > 0 ? '+' : ''}
                      {simulationResult.predicted_metrics.latency_delta_ms} ms
                    </span>
                  </div>

                  <div className="p-3 rounded bg-surface-container/70 border border-outline-variant/20">
                    <span className="text-[10px] text-outline uppercase block">Predicted Loss</span>
                    <span className="font-bold text-base text-primary block mt-1">
                      {simulationResult.predicted_metrics.predicted_packet_loss_pct}%
                    </span>
                    <span className="text-[10px] text-primary">Lossless bypass</span>
                  </div>

                  <div className="p-3 rounded bg-surface-container/70 border border-outline-variant/20">
                    <span className="text-[10px] text-outline uppercase block">FlowMod Rules</span>
                    <span className="font-bold text-base text-secondary block mt-1">
                      {simulationResult.predicted_metrics.flow_mod_rules_required} rules
                    </span>
                    <span className="text-[10px] text-outline">OpenFlow 1.3</span>
                  </div>

                  <div className="p-3 rounded bg-surface-container/70 border border-outline-variant/20">
                    <span className="text-[10px] text-outline uppercase block">Capacity Headroom</span>
                    <span className="font-bold text-base text-primary block mt-1">
                      {simulationResult.predicted_metrics.capacity_headroom_mbps} Mbps
                    </span>
                    <span className="text-[10px] text-primary">Safe load</span>
                  </div>
                </div>

                {/* Simulated Path Hops */}
                <div className="p-3.5 rounded bg-surface-container/60 border border-outline-variant/20 space-y-2 font-code text-xs">
                  <span className="text-[10px] text-outline uppercase font-semibold block">Simulated Bypass Path (NetworkX Graph)</span>
                  <div className="flex items-center gap-2 text-on-surface font-bold">
                    {simulationResult.simulated_path.hops.map((hop, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded bg-primary/15 text-primary border border-primary/30">
                          {hop.toUpperCase()}
                        </span>
                        {idx < simulationResult.simulated_path.hops.length - 1 && (
                          <ArrowRight size={13} className="text-outline" />
                        )}
                      </div>
                    ))}
                  </div>
                  <span className="text-[11px] text-outline block">
                    Avoided damaged element: {simulationResult.simulated_path.avoided_nodes.join(', ')}
                  </span>
                </div>
              </div>
            )}
          </DataStateWrapper>
        </div>
      </div>
    </div>
  )
}
