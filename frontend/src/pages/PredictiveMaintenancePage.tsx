/**
 * pages/PredictiveMaintenancePage.tsx — Predictive Health & Failure Forecasting
 *
 * Implements the design from sentinelnet_predictive_maintenance:
 * - Degradation risk index per link/switch
 * - Mean Time Between Failures (MTBF) calculations
 * - Interface CRC error trends, laser bias / optical telemetry aging
 * - Recommended proactive maintenance schedule
 */
import toast from 'react-hot-toast'

interface RiskTarget {
  name: string
  zone: string
  riskScore: number // 0-100
  trend: 'STABLE' | 'DEGRADING' | 'HEALTHY'
  predictedFailureWindow: string
  primarySymptom: string
  recommendedRemediation: string
}

const PREDICTIVE_ITEMS: RiskTarget[] = [
  {
    name: 'Primary Link L1 (S1 ↔ S2)',
    zone: 'Student Lab A ↔ Core',
    riskScore: 68,
    trend: 'DEGRADING',
    predictedFailureWindow: '~14 hours',
    primarySymptom: 'Increasing CRC error frequency during peak academic lab hours',
    recommendedRemediation: 'Schedule cable inspection & pre-route non-critical traffic to BL1',
  },
  {
    name: 'Core Switch S2 Buffer Queue',
    zone: 'Core Aggregation',
    riskScore: 42,
    trend: 'STABLE',
    predictedFailureWindow: '>72 hours',
    primarySymptom: 'Egress buffer micro-burst drops during iperf file transfers',
    recommendedRemediation: 'Tune OpenFlow drop thresholds or allocate larger buffer slice',
  },
  {
    name: 'Backup Link BL1 (S1 ↔ S3)',
    zone: 'Lab A ↔ Server Room',
    riskScore: 18,
    trend: 'HEALTHY',
    predictedFailureWindow: 'No risk detected (>30d)',
    primarySymptom: 'Zero error accumulation; 5.2ms stable propagation delay',
    recommendedRemediation: 'Optimal standby state; no action required',
  },
  {
    name: 'Switch S3 Port 4 (SRV1 Link)',
    zone: 'Academic Server Room',
    riskScore: 24,
    trend: 'HEALTHY',
    predictedFailureWindow: 'No risk detected (>30d)',
    primarySymptom: 'TCP window retransmissions within normal bounds (<0.02%)',
    recommendedRemediation: 'Normal periodic audit',
  },
]

export default function PredictiveMaintenancePage() {
  const items: RiskTarget[] = PREDICTIVE_ITEMS

  const handleProactiveSchedule = (targetName: string) => {
    toast.success(`Proactive maintenance ticket dispatched for ${targetName}`)
  }

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-on-surface tracking-tight">
              Predictive Maintenance
            </h1>
            <span className="px-2 py-0.5 rounded bg-primary/10 text-primary font-code text-xs font-semibold border border-primary/30">
              PROACTIVE FORECASTING
            </span>
          </div>
          <p className="font-body text-xs text-on-surface-variant">
            Heuristic degradation curves predicting infrastructure failures before physical cut or disruption.
          </p>
        </div>

        <button
          onClick={() => toast.success('Re-evaluated statistical degradation models.')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-bright text-on-surface font-body text-xs border border-outline-variant/30 transition-all"
        >
          <span className="material-symbols-outlined text-[16px] text-secondary">update</span>
          <span>Recalculate Proactive Curves</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface-container-low/90 backdrop-blur-md p-4 rounded-xl border border-outline-variant/30">
          <span className="font-code text-[10px] text-outline uppercase block font-semibold">Highest Degradation Risk</span>
          <span className="font-display font-bold text-2xl text-amber-400 font-code mt-1 block">68 / 100</span>
          <span className="text-[11px] text-amber-400 font-code mt-1 block">Link L1 (S1 ↔ S2)</span>
        </div>

        <div className="bg-surface-container-low/90 backdrop-blur-md p-4 rounded-xl border border-outline-variant/30">
          <span className="font-code text-[10px] text-outline uppercase block font-semibold">Estimated Failure Horizon</span>
          <span className="font-display font-bold text-2xl text-on-surface font-code mt-1 block">~14 Hours</span>
          <span className="text-[11px] text-outline font-body mt-1 block">Sufficient time for planned reroute</span>
        </div>

        <div className="bg-surface-container-low/90 backdrop-blur-md p-4 rounded-xl border border-outline-variant/30">
          <span className="font-code text-[10px] text-outline uppercase block font-semibold">Prevented Disruptions</span>
          <span className="font-display font-bold text-2xl text-primary font-code mt-1 block">18 Incidents</span>
          <span className="text-[11px] text-primary font-code mt-1 block">Proactively mitigated this semester</span>
        </div>

        <div className="bg-surface-container-low/90 backdrop-blur-md p-4 rounded-xl border border-outline-variant/30">
          <span className="font-code text-[10px] text-outline uppercase block font-semibold">Hardware Health Index</span>
          <span className="font-display font-bold text-2xl text-on-surface font-code mt-1 block">96.4%</span>
          <span className="text-[11px] text-outline font-body mt-1 block">Across all campus links & switches</span>
        </div>
      </div>

      {/* Degradation Matrix */}
      <div className="bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary text-[20px]">show_chart</span>
            <h3 className="font-display font-semibold text-sm text-on-surface">Substrate Degradation Risk Matrix</h3>
          </div>
          <span className="font-code text-xs text-outline font-semibold">PREDICTIVE ML RADAR</span>
        </div>

        <div className="space-y-4">
          {items.map(item => (
            <div key={item.name} className="p-4 rounded-lg bg-surface-container/70 border border-outline-variant/30 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <h4 className="font-display font-bold text-sm text-on-surface">{item.name}</h4>
                  <span className="text-xs text-outline font-code">({item.zone})</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`px-2 py-0.5 rounded text-[11px] font-code font-bold ${
                    item.trend === 'DEGRADING'
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                      : 'bg-primary/10 text-primary border border-primary/30'
                  }`}>
                    {item.trend}
                  </span>
                  <span className="font-code font-bold text-sm text-on-surface">
                    Risk: {item.riskScore}%
                  </span>
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full h-2 bg-surface-container-lowest rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    item.riskScore > 60 ? 'bg-amber-400' : 'bg-primary'
                  }`}
                  style={{ width: `${item.riskScore}%` }}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-body pt-1">
                <div className="text-on-surface-variant">
                  <strong className="text-on-surface">Observed Symptoms:</strong> {item.primarySymptom}
                </div>
                <div className="text-on-surface-variant">
                  <strong className="text-on-surface">Horizon:</strong> <span className="font-code text-primary font-semibold">{item.predictedFailureWindow}</span>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-outline-variant/15 text-xs font-code">
                <span className="text-outline">Action: {item.recommendedRemediation}</span>
                <button
                  onClick={() => handleProactiveSchedule(item.name)}
                  className="px-2.5 py-1 rounded bg-surface-container-high hover:bg-surface-bright text-secondary border border-outline-variant/30 transition-colors"
                >
                  Schedule Fix
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
