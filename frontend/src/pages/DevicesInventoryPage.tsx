/**
 * pages/DevicesInventoryPage.tsx — Substrate Hardware & Port Inventory
 *
 * Implements the design from sentinelnet_devices_inventory:
 * - Switches (S1, S2, S3), Controller (C0), Hosts (H1-H4), Server (SRV1)
 * - OpenFlow DPID, IP address, MAC, Port mappings, Rx/Tx counters, and health states
 */
import { useState } from 'react'
import toast from 'react-hot-toast'

interface DeviceRecord {
  id: string
  name: string
  type: 'controller' | 'switch' | 'host' | 'server'
  zone: string
  ip: string
  mac: string
  dpid?: string
  ports: number
  status: 'UP' | 'DOWN' | 'DEGRADED'
  throughput: string
  packetLoss: string
  lastSeen: string
}

const INVENTORY: DeviceRecord[] = [
  {
    id: 'c0',
    name: 'Ryu SDN Controller (C0)',
    type: 'controller',
    zone: 'Management Plane',
    ip: '10.0.0.254',
    mac: '00:00:00:00:00:FE',
    ports: 3,
    status: 'UP',
    throughput: '320 pps',
    packetLoss: '0.00%',
    lastSeen: '1s ago',
  },
  {
    id: 's1',
    name: 'OpenFlow Switch S1 (Lab A)',
    type: 'switch',
    zone: 'Student Lab A',
    ip: '10.0.1.1 (mgmt)',
    mac: '00:00:00:00:00:01',
    dpid: '00:00:00:00:00:00:00:01',
    ports: 4,
    status: 'UP',
    throughput: '14.8 MB/s',
    packetLoss: '0.00%',
    lastSeen: '1s ago',
  },
  {
    id: 's2',
    name: 'OpenFlow Switch S2 (Core)',
    type: 'switch',
    zone: 'Core Aggregation',
    ip: '10.0.1.2 (mgmt)',
    mac: '00:00:00:00:00:02',
    dpid: '00:00:00:00:00:00:00:02',
    ports: 5,
    status: 'UP',
    throughput: '22.4 MB/s',
    packetLoss: '0.00%',
    lastSeen: '1s ago',
  },
  {
    id: 's3',
    name: 'OpenFlow Switch S3 (Server Room)',
    type: 'switch',
    zone: 'Academic Server Room',
    ip: '10.0.1.3 (mgmt)',
    mac: '00:00:00:00:00:03',
    dpid: '00:00:00:00:00:00:00:03',
    ports: 4,
    status: 'UP',
    throughput: '18.1 MB/s',
    packetLoss: '0.00%',
    lastSeen: '1s ago',
  },
  {
    id: 'h1',
    name: 'Student PC 1 (H1)',
    type: 'host',
    zone: 'Student Lab A',
    ip: '10.0.0.1/24',
    mac: '00:00:00:00:00:01',
    ports: 1,
    status: 'UP',
    throughput: '1.2 MB/s',
    packetLoss: '0.00%',
    lastSeen: '2s ago',
  },
  {
    id: 'h2',
    name: 'Student PC 2 (H2)',
    type: 'host',
    zone: 'Student Lab A',
    ip: '10.0.0.2/24',
    mac: '00:00:00:00:00:02',
    ports: 1,
    status: 'UP',
    throughput: '980 KB/s',
    packetLoss: '0.00%',
    lastSeen: '2s ago',
  },
  {
    id: 'h3',
    name: 'Student PC 3 (H3)',
    type: 'host',
    zone: 'Student Lab B',
    ip: '10.0.0.3/24',
    mac: '00:00:00:00:00:03',
    ports: 1,
    status: 'UP',
    throughput: '4.2 MB/s',
    packetLoss: '0.00%',
    lastSeen: '2s ago',
  },
  {
    id: 'h4',
    name: 'Student PC 4 (H4)',
    type: 'host',
    zone: 'Student Lab B',
    ip: '10.0.0.4/24',
    mac: '00:00:00:00:00:04',
    ports: 1,
    status: 'UP',
    throughput: '3.8 MB/s',
    packetLoss: '0.00%',
    lastSeen: '2s ago',
  },
  {
    id: 'srv1',
    name: 'Academic App Server (SRV1)',
    type: 'server',
    zone: 'Server Room',
    ip: '10.0.0.10/24',
    mac: '00:00:00:00:00:10',
    ports: 1,
    status: 'UP',
    throughput: '18.1 MB/s',
    packetLoss: '0.00%',
    lastSeen: '1s ago',
  },
]

export default function DevicesInventoryPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [filterType, setFilterType] = useState('ALL')

  const filtered = INVENTORY.filter(dev => {
    if (filterType !== 'ALL' && dev.type !== filterType) return false
    if (searchTerm && !dev.name.toLowerCase().includes(searchTerm.toLowerCase()) && !dev.ip.includes(searchTerm)) return false
    return true
  })

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-2xl font-bold text-on-surface tracking-tight">
            Device Inventory & Switch Port Matrix
          </h1>
          <p className="font-body text-xs text-on-surface-variant">
            Live OpenFlow datapath endpoints, virtual host interfaces, and Ryu controller bindings.
          </p>
        </div>

        <button
          onClick={() => toast.success('Scanned all OVS bridges & OpenFlow 1.3 datapaths.')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-bright text-on-surface font-body text-xs border border-outline-variant/30 transition-all"
        >
          <span className="material-symbols-outlined text-[16px] text-secondary">sync</span>
          <span>Rescan Topology</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 rounded-xl bg-surface-container-low/90 border border-outline-variant/30 flex flex-wrap items-center justify-between gap-3 shadow-md">
        <div className="flex items-center gap-3">
          <div className="relative w-72">
            <span className="material-symbols-outlined absolute left-2.5 top-2 text-[16px] text-outline">search</span>
            <input
              type="text"
              placeholder="Search by device ID, IP, or zone..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full bg-surface-container-lowest border border-outline-variant/30 rounded pl-8 pr-3 py-1.5 font-body text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-secondary"
            />
          </div>

          <select
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
            className="bg-surface-container-lowest border border-outline-variant/30 rounded px-3 py-1.5 font-body text-xs text-on-surface focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Device Classes</option>
            <option value="switch">Switches (OVS)</option>
            <option value="controller">Controller (Ryu)</option>
            <option value="host">Student Workstations</option>
            <option value="server">Application Server</option>
          </select>
        </div>

        <span className="font-code text-xs text-outline font-semibold">
          {filtered.length} Substrate Nodes Tracked
        </span>
      </div>

      {/* Table */}
      <div className="bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-outline-variant/30 bg-surface-container-lowest/80 text-outline font-code uppercase text-[10px]">
                <th className="px-4 py-3">Device Node</th>
                <th className="px-4 py-3">Role & Type</th>
                <th className="px-4 py-3">Campus Zone</th>
                <th className="px-4 py-3">IP Address</th>
                <th className="px-4 py-3">Hardware MAC / DPID</th>
                <th className="px-4 py-3">Active Ports</th>
                <th className="px-4 py-3">Throughput</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Ping Trace</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/15 font-body">
              {filtered.map(dev => (
                <tr key={dev.id} className="hover:bg-surface-container/60 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-display font-semibold text-on-surface block text-xs">{dev.name}</span>
                    <span className="font-code text-[11px] text-secondary font-bold">#{dev.id}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-code uppercase text-[11px] font-semibold text-outline">
                      {dev.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-code text-on-surface">{dev.zone}</td>
                  <td className="px-4 py-3 font-code text-primary font-semibold">{dev.ip}</td>
                  <td className="px-4 py-3 font-code text-outline">{dev.dpid || dev.mac}</td>
                  <td className="px-4 py-3 font-code text-on-surface">{dev.ports} Ports</td>
                  <td className="px-4 py-3 font-code text-secondary">{dev.throughput}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-code font-bold bg-primary/10 text-primary border border-primary/30">
                      {dev.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => toast.success(`ICMP Ping sent to ${dev.ip}: 0.8ms RTT`)}
                      className="px-2 py-1 rounded bg-surface-container hover:bg-surface-bright text-xs font-code text-on-surface border border-outline-variant/30"
                    >
                      Ping
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
