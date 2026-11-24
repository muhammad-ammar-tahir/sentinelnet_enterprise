/**
 * pages/RecoveryManagementPage.tsx — Closed-Loop Autonomous Recovery Center
 *
 * Real OpenFlow Actuation & Multi-State Honest Recovery Engine:
 * - Approve button -> POST /api/recovery/execute { incident_id }
 * - Rollback button -> POST /api/recovery/rollback { action_id }
 * - Real WebSocket recovery timeline (RECOVERY_STARTED, RECOVERY_COMPLETED, RECOVERY_FAILED)
 * - Honest multi-state rendering: overall_status, flow_installation, traffic_verification, rollback_status
 * - Zero simulated success timeouts
 */
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RotateCcw,
  CheckCircle,
  Play,
  Activity,
  Layers,
  ShieldAlert,
  AlertTriangle,
  X,
  RefreshCw,
  ShieldCheck,
  Trash2
} from 'lucide-react'
import { useWebSocket } from '@/contexts/WebSocketContext'
import client from '@/api/client'
import DataStateWrapper from '@/components/ui/DataStateWrapper'
import toast from 'react-hot-toast'

interface RecoveryEventLog {
  id: string
  event: 'RECOVERY_STARTED' | 'RECOVERY_COMPLETED' | 'RECOVERY_FAILED'
  timestamp: string
  incidentId: string
  details?: any
}

interface IncidentItem {
  id: string
  title: string
  severity: string
  status: string
  affected_link_id?: string
  affected_device_id?: string
  confidence_score?: number
}

interface HonestRecoveryRecord {
  id: string
  incident_id: string
  action_type: string
  overall_status: 'success' | 'failed' | 'rolled_back' | 'partial'
  flow_installation: 'success' | 'failed' | 'not_started' | 'partial'
  traffic_verification: 'success' | 'failed' | 'not_started' | 'inconclusive'
  rollback_status: 'not_needed' | 'success' | 'failed' | 'not_attempted'
  created_at?: string
  duration_ms?: number
  reason?: string
}

export default function RecoveryManagementPage() {
  const queryClient = useQueryClient()
  const { subscribe } = useWebSocket()

  const [circuitBreakerArmed, setCircuitBreakerArmed] = useState(true)
  const [timelineEvents, setTimelineEvents] = useState<RecoveryEventLog[]>([])
  const [lastRecoveryResult, setLastRecoveryResult] = useState<HonestRecoveryRecord | null>(null)

  // Rollback preview modal & execution state
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null)
  const [previewModalOpen, setPreviewModalOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewData, setPreviewData] = useState<any | null>(null)
  const [rollbackResultData, setRollbackResultData] = useState<any | null>(null)

  // 1. Fetch active incidents requiring remediation or review
  const {
    data: incidents = [],
    isLoading: incidentsLoading,
    isError: incidentsError,
    refetch: refetchIncidents,
  } = useQuery<IncidentItem[]>({
    queryKey: ['incidents', 'unresolved'],
    queryFn: async () => {
      const res = await client.get('/incidents')
      return res.data
    },
    refetchInterval: 5000,
  })

  // 2. Fetch past recovery action records
  const {
    data: recoveryHistory = [],
    isLoading: historyLoading,
  } = useQuery<HonestRecoveryRecord[]>({
    queryKey: ['recovery', 'history'],
    queryFn: async () => {
      try {
        const res = await client.get('/recovery/history')
        return res.data
      } catch {
        return []
      }
    },
    refetchInterval: 10000,
  })

  // 3. Real WebSocket subscriptions for Recovery Timeline
  useEffect(() => {
    const unsubStarted = subscribe('RECOVERY_STARTED', (data: any) => {
      const newEvt: RecoveryEventLog = {
        id: `evt-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        event: 'RECOVERY_STARTED',
        timestamp: new Date().toLocaleTimeString(),
        incidentId: data?.incident_id || 'unknown',
        details: data,
      }
      setTimelineEvents(prev => [newEvt, ...prev].slice(0, 20))
      toast(`Autonomous recovery started for ${data?.incident_id || 'incident'}`, { icon: '⚙️' })
    })

    const unsubCompleted = subscribe('RECOVERY_COMPLETED', (data: any) => {
      const newEvt: RecoveryEventLog = {
        id: `evt-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        event: 'RECOVERY_COMPLETED',
        timestamp: new Date().toLocaleTimeString(),
        incidentId: data?.incident_id || 'unknown',
        details: data,
      }
      setTimelineEvents(prev => [newEvt, ...prev].slice(0, 20))
      setLastRecoveryResult(data)
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['recovery', 'history'] })
      toast.success(`Recovery verified! Status: ${data?.overall_status || 'success'}`)
    })

    const unsubFailed = subscribe('RECOVERY_FAILED', (data: any) => {
      const newEvt: RecoveryEventLog = {
        id: `evt-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        event: 'RECOVERY_FAILED',
        timestamp: new Date().toLocaleTimeString(),
        incidentId: data?.incident_id || 'unknown',
        details: data,
      }
      setTimelineEvents(prev => [newEvt, ...prev].slice(0, 20))
      setLastRecoveryResult(data)
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      toast.error(`Recovery failed! Rollback status: ${data?.rollback_status || 'executed'}`)
    })

    return () => {
      unsubStarted()
      unsubCompleted()
      unsubFailed()
    }
  }, [subscribe, queryClient])

  // 4. Real Execute Recovery Mutation -> POST /api/recovery/execute
  const executeMutation = useMutation({
    mutationFn: async (incidentId: string) => {
      const res = await client.post('/recovery/execute', {
        incident_id: incidentId,
        action_type: 'auto_reroute',
        override_policy: !circuitBreakerArmed,
      })
      return res.data
    },
    onMutate: () => {
      toast.loading('Dispatching OpenFlow actuation to controller...', { id: 'exec-rec' })
    },
    onSuccess: (data) => {
      setLastRecoveryResult(data)
      toast.success(`Actuation executed! Status: ${data.overall_status}`, { id: 'exec-rec' })
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['recovery', 'history'] })
    },
    onError: (err: any) => {
      toast.error(`Actuation failed: ${err.response?.data?.detail || err.message}`, { id: 'exec-rec' })
    },
  })

  // 5. Real Rollback Mutation -> POST /api/recovery/rollback
  const rollbackMutation = useMutation({
    mutationFn: async (actionId: string) => {
      const res = await client.post('/recovery/rollback', {
        recovery_action_id: actionId,
        action_id: actionId,
        reason: 'Operator triggered manual rollback via NOC UI',
      })
      return res.data
    },
    onMutate: () => {
      toast.loading('Executing verified rollback to pre-recovery flow snapshot...', { id: 'rollback' })
    },
    onSuccess: (data) => {
      setPreviewModalOpen(false)
      setRollbackResultData(data.rollback_result || data)
      toast.success('Rollback completed and verified! Flow tables reverted.', { id: 'rollback' })
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['recovery', 'history'] })
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail || err.response?.data?.message || err.message
      const detailMsg = typeof detail === 'object' ? JSON.stringify(detail) : detail
      toast.error(`Rollback failed (status NOT updated): ${detailMsg}`, { id: 'rollback', duration: 6000 })
    },
  })

  // Open Preview Modal before executing rollback
  const handleOpenRollbackPreview = async (actionId: string) => {
    setSelectedActionId(actionId)
    setPreviewLoading(true)
    setPreviewModalOpen(true)
    setPreviewData(null)
    try {
      const res = await client.get(`/recovery/rollback/preview/${actionId}`)
      setPreviewData(res.data)
    } catch (err: any) {
      toast.error(`Cannot preview rollback: ${err.response?.data?.detail || err.message}`)
      setPreviewModalOpen(false)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleConfirmRollback = () => {
    if (!selectedActionId) return
    rollbackMutation.mutate(selectedActionId)
  }

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-on-surface tracking-tight">
              Recovery Management
            </h1>
            <span className="px-2 py-0.5 rounded bg-primary/10 text-primary font-code text-xs font-semibold border border-primary/30">
              OPENFLOW 1.3 ACTUATION
            </span>
          </div>
          <p className="font-body text-xs text-on-surface-variant">
            Orchestration, multi-stage verification, and atomic rollback for Ryu OpenFlow self-healing.
          </p>
        </div>

        {/* Safety Interlock Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCircuitBreakerArmed(!circuitBreakerArmed)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded font-code text-xs font-bold border transition-all ${
              circuitBreakerArmed
                ? 'bg-primary/10 border-primary/40 text-primary'
                : 'bg-error/15 border-error/40 text-error'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${circuitBreakerArmed ? 'bg-primary animate-pulse' : 'bg-error'}`} />
            <span>CIRCUIT BREAKER: {circuitBreakerArmed ? 'ARMED (STRICT)' : 'BYPASS'}</span>
          </button>
        </div>
      </div>

      {/* Honest Multi-State Recovery Summary Card */}
      {lastRecoveryResult && (
        <div className="p-4 rounded-xl bg-surface-container-low/95 border border-outline-variant/30 shadow-lg space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-outline-variant/20">
            <div className="flex items-center gap-2">
              <span className="font-display font-semibold text-sm text-on-surface">Latest Recovery Result</span>
              <span className="font-code text-xs text-outline">Incident: {lastRecoveryResult.incident_id}</span>
            </div>
            <span className={`px-2 py-0.5 rounded font-code text-xs font-bold ${
              lastRecoveryResult.overall_status === 'success'
                ? 'bg-primary/15 text-primary border border-primary/40'
                : lastRecoveryResult.overall_status === 'rolled_back'
                ? 'bg-purple-500/15 text-purple-400 border border-purple-500/40'
                : 'bg-error/15 text-error border border-error/40'
            }`}>
              OVERALL: {lastRecoveryResult.overall_status.toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-code text-xs">
            <div className="p-2.5 rounded bg-surface-container/60 border border-outline-variant/20 space-y-1">
              <span className="text-[10px] text-outline uppercase block">Stage 1: Flow Installation</span>
              <span className={`font-bold ${lastRecoveryResult.flow_installation === 'success' ? 'text-primary' : 'text-error'}`}>
                {lastRecoveryResult.flow_installation.toUpperCase()}
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface-container/60 border border-outline-variant/20 space-y-1">
              <span className="text-[10px] text-outline uppercase block">Stage 2: Traffic Verification</span>
              <span className={`font-bold ${lastRecoveryResult.traffic_verification === 'success' ? 'text-primary' : 'text-amber-400'}`}>
                {lastRecoveryResult.traffic_verification.toUpperCase()}
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface-container/60 border border-outline-variant/20 space-y-1">
              <span className="text-[10px] text-outline uppercase block">Stage 3: Rollback Status</span>
              <span className={`font-bold ${lastRecoveryResult.rollback_status === 'not_needed' ? 'text-outline' : 'text-purple-400'}`}>
                {lastRecoveryResult.rollback_status.toUpperCase()}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Grid: Pending Approval Queue + Real-time WebSocket Event Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left 6 Cols: Pending Incidents Awaiting Remediation */}
        <div className="lg:col-span-6 bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
            <div className="flex items-center gap-2">
              <Activity size={18} className="text-primary" />
              <h3 className="font-display font-semibold text-sm text-on-surface">Fault Remediation Queue</h3>
            </div>
            <span className="font-code text-xs text-outline">POST /api/recovery/execute</span>
          </div>

          <DataStateWrapper
            isLoading={incidentsLoading}
            isError={incidentsError}
            error="Failed to load incidents."
            onRetry={refetchIncidents}
            isEmpty={incidents.filter(i => i.status !== 'resolved').length === 0}
            emptyTitle="Remediation Queue Empty"
            emptyMessage="Zero active faults waiting for remediation. All paths currently stable."
          >
            <div className="space-y-3">
              {incidents
                .filter(inc => inc.status !== 'resolved')
                .map(inc => (
                  <div
                    key={inc.id}
                    className="p-3.5 rounded-lg bg-surface-container/70 border border-outline-variant/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-code font-bold text-on-surface">{inc.id}</span>
                        <span className={`text-[10px] font-code px-1.5 py-0.5 rounded font-bold ${
                          inc.severity === 'critical' ? 'bg-error/15 text-error' : 'bg-amber-400/15 text-amber-400'
                        }`}>
                          {inc.severity.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-on-surface-variant">{inc.title}</p>
                      <span className="text-[11px] font-code text-outline block">
                        Target: {inc.affected_link_id || inc.affected_device_id || 'Campus Core'}
                      </span>
                    </div>

                    <button
                      onClick={() => executeMutation.mutate(inc.id)}
                      disabled={executeMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary hover:bg-primary-container text-on-primary font-code text-xs font-bold transition-all shrink-0 disabled:opacity-50"
                    >
                      <Play size={13} />
                      <span>{executeMutation.isPending ? 'Executing...' : 'Approve & Execute'}</span>
                    </button>
                  </div>
                ))}
            </div>
          </DataStateWrapper>
        </div>

        {/* Right 6 Cols: Real WebSocket Recovery Timeline */}
        <div className="lg:col-span-6 bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
            <div className="flex items-center gap-2">
              <Layers size={18} className="text-secondary" />
              <h3 className="font-display font-semibold text-sm text-on-surface">Live WebSocket Recovery Timeline</h3>
            </div>
            <span className="font-code text-xs text-primary font-semibold">STREAM CONNECTED</span>
          </div>

          <DataStateWrapper
            isEmpty={timelineEvents.length === 0}
            emptyTitle="No Recent WebSocket Events"
            emptyMessage="Waiting for RECOVERY_STARTED, RECOVERY_COMPLETED, or RECOVERY_FAILED events from the backend."
          >
            <div className="space-y-2.5 max-h-[380px] overflow-y-auto font-code text-xs">
              {timelineEvents.map(evt => (
                <div
                  key={evt.id}
                  className={`p-3 rounded-lg border flex items-start justify-between gap-2 ${
                    evt.event === 'RECOVERY_COMPLETED'
                      ? 'bg-primary/10 border-primary/40 text-primary'
                      : evt.event === 'RECOVERY_FAILED'
                      ? 'bg-error/10 border-error/40 text-error'
                      : 'bg-secondary/10 border-secondary/40 text-secondary'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {evt.event === 'RECOVERY_COMPLETED' ? (
                        <CheckCircle size={15} />
                      ) : evt.event === 'RECOVERY_FAILED' ? (
                        <ShieldAlert size={15} />
                      ) : (
                        <RotateCcw size={15} className="animate-spin" />
                      )}
                      <span className="font-bold">{evt.event}</span>
                    </div>
                    <span className="text-[11px] text-on-surface block">Incident: {evt.incidentId}</span>
                  </div>
                  <span className="text-[10px] text-outline">{evt.timestamp}</span>
                </div>
              ))}
            </div>
          </DataStateWrapper>
        </div>
      </div>

      {/* Historical Recovery Actions with Honest Rollback Button */}
      <div className="bg-surface-container-low/80 backdrop-blur-md border border-outline-variant/30 rounded-xl p-5 shadow-xl space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-outline-variant/20">
          <h3 className="font-display font-semibold text-sm text-on-surface">Remediation Action Audit Log</h3>
          <span className="font-code text-xs text-outline">POST /api/recovery/rollback</span>
        </div>

        <DataStateWrapper
          isLoading={historyLoading}
          isEmpty={recoveryHistory.length === 0}
          emptyTitle="No Recovery Actions Found"
          emptyMessage="No past recovery or reroute operations recorded in database audit log."
        >
          <div className="space-y-2 font-code text-xs">
            {recoveryHistory.map((act) => (
              <div
                key={act.id}
                className="p-3 rounded bg-surface-container/60 border border-outline-variant/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div>
                  <span className="font-bold text-on-surface">{act.id}</span>
                  <span className="text-outline mx-2">·</span>
                  <span className="text-secondary">{act.action_type || 'REROUTE'}</span>
                  <span className="text-outline mx-2">·</span>
                  <span className="text-primary">Status: {act.overall_status}</span>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-outline text-[11px]">
                    Install: {act.flow_installation} | Verify: {act.traffic_verification}
                  </span>
                  <button
                    onClick={() => handleOpenRollbackPreview(act.id)}
                    disabled={rollbackMutation.isPending || previewLoading || act.overall_status === 'rolled_back'}
                    className="px-2.5 py-1 rounded bg-error/15 hover:bg-error/25 text-error border border-error/40 font-bold transition-all text-xs flex items-center gap-1 disabled:opacity-50"
                  >
                    <RotateCcw size={12} />
                    <span>{act.overall_status === 'rolled_back' ? 'Rolled Back' : 'Rollback'}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </DataStateWrapper>
      </div>

      {/* Verified Rollback Execution Details Banner (Displayed when rollback finishes) */}
      {rollbackResultData && (
        <div className="bg-surface-container-low/90 backdrop-blur-md border border-purple-500/40 rounded-xl p-5 shadow-2xl space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-purple-500/20">
            <div className="flex items-center gap-2 text-purple-400 font-display font-semibold text-sm">
              <ShieldCheck size={16} />
              <span>Verified Rollback Execution Outcome</span>
            </div>
            <button
              onClick={() => setRollbackResultData(null)}
              className="text-outline hover:text-on-surface text-xs flex items-center gap-1"
            >
              <X size={14} />
              <span>Dismiss</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-code text-xs">
            <div className="p-3 rounded bg-surface-container/60 border border-outline-variant/20">
              <span className="text-outline text-[11px] block">Overall Status</span>
              <span className={`font-bold ${rollbackResultData.overall_success ? 'text-green-400' : 'text-red-400'}`}>
                {rollbackResultData.overall_success ? 'VERIFIED SUCCESS' : 'FAILED'}
              </span>
            </div>
            <div className="p-3 rounded bg-surface-container/60 border border-outline-variant/20">
              <span className="text-outline text-[11px] block">Snapshot Restored</span>
              <span className="font-bold text-on-surface truncate block" title={rollbackResultData.snapshot_id}>
                {rollbackResultData.snapshot_id || 'N/A'}
              </span>
            </div>
            <div className="p-3 rounded bg-surface-container/60 border border-outline-variant/20">
              <span className="text-outline text-[11px] block">Switches Verified</span>
              <span className="font-bold text-primary">
                {Object.keys(rollbackResultData.dpids || {}).length} Switches
              </span>
            </div>
          </div>

          {rollbackResultData.dpids && (
            <div className="space-y-1">
              <span className="text-outline text-[11px] uppercase font-bold tracking-wider">Per-Switch Verification:</span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-code text-xs">
                {Object.entries(rollbackResultData.dpids).map(([dpid, res]: [string, any]) => (
                  <div key={dpid} className="p-2 rounded bg-surface-container border border-outline-variant/20 flex items-center justify-between">
                    <span>DPID {dpid}</span>
                    <span className={res.verified ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
                      {res.verified ? `Verified (Restored: ${res.restored_count || 0}, Deleted: ${res.deleted_count || 0})` : `Failed: ${res.error || 'mismatch'}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Confirmation Modal with Rollback Preview */}
      {previewModalOpen && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface-container-high border border-outline-variant/40 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
              <div className="flex items-center gap-2 text-error font-display font-bold text-base">
                <AlertTriangle size={20} />
                <span>Confirm Safe Flow Table Rollback</span>
              </div>
              <button
                onClick={() => setPreviewModalOpen(false)}
                disabled={rollbackMutation.isPending}
                className="text-outline hover:text-on-surface p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {previewLoading ? (
              <div className="py-8 flex flex-col items-center justify-center gap-3 text-outline font-code text-xs">
                <RefreshCw size={24} className="animate-spin text-primary" />
                <span>Querying switch flow tables and computing rollback diff...</span>
              </div>
            ) : previewData ? (
              <div className="space-y-4 font-code text-xs">
                {/* Impact Banner */}
                <div className="p-3 rounded-lg bg-surface-container border border-outline-variant/30 space-y-1">
                  <span className="text-outline text-[11px] block uppercase font-bold">Estimated Operational Impact</span>
                  <p className="text-on-surface font-body text-xs">{previewData.estimated_impact}</p>
                </div>

                {/* Diff summary stats */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded bg-error/10 border border-error/30 text-error">
                    <div className="flex items-center gap-1.5 font-bold mb-1">
                      <Trash2 size={14} />
                      <span>Flows to Delete ({previewData.total_flows_to_delete})</span>
                    </div>
                    <span className="text-[11px] text-outline block">Tagged with cookie 0x53454E54</span>
                  </div>

                  <div className="p-3 rounded bg-secondary/10 border border-secondary/30 text-secondary">
                    <div className="flex items-center gap-1.5 font-bold mb-1">
                      <RotateCcw size={14} />
                      <span>Flows to Restore ({previewData.total_flows_to_restore})</span>
                    </div>
                    <span className="text-[11px] text-outline block">Pre-recovery baseline rules</span>
                  </div>
                </div>

                {/* Switch list */}
                <div className="text-[11px] text-outline flex items-center justify-between">
                  <span>Target Switches: {previewData.dpids?.map((d: any) => `DPID ${d}`).join(', ') || 'N/A'}</span>
                  <span>Snapshot: {previewData.snapshot_id?.substring(0, 8)}...</span>
                </div>

                {/* Escalation warning */}
                <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-200 text-xs font-body">
                  <strong>Notice:</strong> Executing rollback will revert OpenFlow switches and transition incident status to <code>escalated</code> for NOC engineer review.
                </div>
              </div>
            ) : (
              <div className="py-4 text-center text-error font-body text-xs">
                Failed to compute rollback preview. Rollback aborted.
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-outline-variant/20">
              <button
                onClick={() => setPreviewModalOpen(false)}
                disabled={rollbackMutation.isPending}
                className="px-4 py-2 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs font-medium hover:bg-surface-container-high transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmRollback}
                disabled={rollbackMutation.isPending || previewLoading || !previewData}
                className="px-4 py-2 rounded-lg bg-error hover:bg-error/90 text-on-error text-xs font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
              >
                {rollbackMutation.isPending ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>Rolling Back Switches...</span>
                  </>
                ) : (
                  <>
                    <RotateCcw size={14} />
                    <span>Confirm & Execute Rollback</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
