/**
 * components/topology/DeviceDetailPanel.tsx — Device Side-Panel
 *
 * Slide-in panel shown when a node is clicked in TopologyMap.
 * Displays full device information and its latest metric snapshot.
 *
 * Sections:
 *   1. Device metadata (type, zone, IP, status)
 *   2. Latest metrics (RTT, utilization, error rate)
 *   3. Active incident links (if any incidents affect this device)
 *
 * Props:
 *   device: Device | null — null collapses the panel
 *   onClose: () => void
 */
import { X, Server, Network, Monitor } from 'lucide-react'
import { useMetrics } from '@/hooks/useMetrics'
import StatusBadge from '@/components/ui/StatusBadge'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { Device } from '@/types'

interface DeviceDetailPanelProps {
  device: Device | null
  onClose: () => void
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  controller: <Network size={16} />,
  switch: <Network size={16} />,
  host: <Monitor size={16} />,
  server: <Server size={16} />,
}

export default function DeviceDetailPanel({ device, onClose }: DeviceDetailPanelProps) {
  const { data: metricsData, isLoading } = useMetrics(
    device ? { deviceId: device.id, limit: 1 } : {}
  )

  if (!device) return null

  const latest = metricsData?.snapshots[0]

  return (
    <div className="card flex flex-col gap-4 w-72 animate-slide-in-right">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-gray-300">
          {TYPE_ICONS[device.type]}
          <span className="text-sm font-semibold">{device.name}</span>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white">
          <X size={14} />
        </button>
      </div>

      {/* Metadata */}
      <div className="space-y-2 text-xs">
        <Row label="ID" value={device.id} />
        <Row label="Type" value={device.type} />
        <Row label="Zone" value={device.zone ?? '—'} />
        <Row label="IP" value={device.ipAddress ?? '—'} />
        <Row label="Status" value={<StatusBadge status={device.status} size="sm" />} />
      </div>

      {/* Metrics */}
      <div>
        <p className="section-title mb-2">Latest Metrics</p>
        {isLoading ? (
          <LoadingSpinner size="sm" />
        ) : latest ? (
          <div className="space-y-2 text-xs">
            <Row label="RTT" value={`${latest.metrics.rttMs.toFixed(1)} ms`} />
            <Row label="Link Util." value={`${latest.metrics.linkUtilization.toFixed(1)}%`} />
            <Row label="RX Errors" value={`${latest.metrics.rxErrorRate.toFixed(1)}/s`} />
            <Row label="TX Drops" value={`${latest.metrics.txDropRate.toFixed(1)}/s`} />
            <Row label="CPU" value={`${latest.metrics.hostCpuPct.toFixed(1)}%`} />
          </div>
        ) : (
          <p className="text-xs text-gray-500">No metrics available</p>
        )}
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-200 font-mono">{value}</span>
    </div>
  )
}
