/**
 * pages/PoliciesPage.tsx — Recovery Policies & Governance Rules
 *
 * Implements the design from sentinelnet_recovery_policies_rules:
 * - Policy prioritization matrix (Priority 1–10)
 * - Automation gate toggles (AUTOMATED vs MANUAL_APPROVAL vs DISABLED)
 * - Zone matchers, failure conditions, schedule filters
 * - Interactive New Policy Modal with form validation
 */
import { useState } from 'react'
import toast from 'react-hot-toast'

interface PolicyRule {
  id: string
  priority: number
  name: string
  description: string
  failureType: string
  severity: 'ANY' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  zone: string
  action: string
  automation: 'AUTOMATED' | 'MANUAL_APPROVAL' | 'DISABLED'
  enabled: boolean
}

const INITIAL_POLICIES: PolicyRule[] = [
  {
    id: 'pol-01',
    priority: 1,
    name: 'Link Failure Immediate Failover',
    description: 'When primary link L1 or L2 suffers loss >50%, immediately install OpenFlow flow redirect to Backup Link BL1/BL2.',
    failureType: 'LINK_FAILURE',
    severity: 'ANY',
    zone: 'ALL_CAMPUS',
    action: 'REROUTE_TO_BACKUP',
    automation: 'AUTOMATED',
    enabled: true,
  },
  {
    id: 'pol-02',
    priority: 2,
    name: 'Lab Congestion Metering Guard',
    description: 'When link utilization exceeds 85% for 3 consecutive cycles, install OpenFlow 50Mbps drop meter on bulk flow.',
    failureType: 'CONGESTION',
    severity: 'HIGH',
    zone: 'Student Lab B',
    action: 'RATE_LIMIT',
    automation: 'AUTOMATED',
    enabled: true,
  },
  {
    id: 'pol-03',
    priority: 3,
    name: 'Core Switch Bypass & Isolation',
    description: 'If Switch S2 disconnects from Ryu controller, reroute Student Lab A flows via BL1; isolate Lab B for safety.',
    failureType: 'DEVICE_FAILURE',
    severity: 'CRITICAL',
    zone: 'Core Backbone',
    action: 'REROUTE_AROUND_DEVICE',
    automation: 'AUTOMATED',
    enabled: true,
  },
  {
    id: 'pol-04',
    priority: 4,
    name: 'Flapping Link Permanent Suppression',
    description: 'If same link fails >3 times in 60 minutes, lock backup route permanently and suspend flapping interface.',
    failureType: 'REPEATED_FAILURE',
    severity: 'HIGH',
    zone: 'ALL_CAMPUS',
    action: 'PERMANENT_REROUTE',
    automation: 'AUTOMATED',
    enabled: true,
  },
  {
    id: 'pol-05',
    priority: 5,
    name: 'Exam Period No Rate Limiting Guarantee',
    description: 'During scheduled exams, never throttle LMS student PC traffic. Require manual approval for any rate limiting.',
    failureType: 'CONGESTION',
    severity: 'LOW',
    zone: 'Student Lab A',
    action: 'ESCALATE_TO_MANUAL',
    automation: 'MANUAL_APPROVAL',
    enabled: false,
  },
]

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyRule[]>(INITIAL_POLICIES)
  const [isModalOpen, setIsModalOpen] = useState(false)

  // New policy form state
  const [formName, setFormName] = useState('')
  const [formFailureType, setFormFailureType] = useState('LINK_FAILURE')
  const [formAction, setFormAction] = useState('REROUTE_TO_BACKUP')
  const [formZone, setFormZone] = useState('ALL_CAMPUS')
  const [formAutomation, setFormAutomation] = useState<'AUTOMATED' | 'MANUAL_APPROVAL'>('AUTOMATED')
  const [formPriority, setFormPriority] = useState(6)

  const handleToggle = (id: string) => {
    setPolicies(prev =>
      prev.map(p => {
        if (p.id === id) {
          const next = !p.enabled
          toast.success(`Policy "${p.name}" ${next ? 'ENABLED' : 'DISABLED'}`)
          return { ...p, enabled: next }
        }
        return p
      })
    )
  }

  const handleDelete = (id: string) => {
    if (confirm('Delete this policy rule?')) {
      setPolicies(prev => prev.filter(p => p.id !== id))
      toast.success('Policy removed from ruleset.')
    }
  }

  const handleCreatePolicy = (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) return

    const newRule: PolicyRule = {
      id: `pol-${Date.now()}`,
      priority: formPriority,
      name: formName,
      description: `User-defined rule for ${formFailureType} targeting ${formZone}.`,
      failureType: formFailureType,
      severity: 'ANY',
      zone: formZone,
      action: formAction,
      automation: formAutomation,
      enabled: true,
    }

    setPolicies(prev => [...prev, newRule].sort((a, b) => a.priority - b.priority))
    setIsModalOpen(false)
    setFormName('')
    toast.success(`Created policy "${formName}" successfully!`)
  }

  return (
    <div className="flex flex-col gap-5 w-full">
      {/* Top Header */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[11px] font-code uppercase bg-primary/10 text-primary border-l-2 border-primary font-bold">
              Governance v4.12
            </span>
            <span className="text-outline font-code text-xs">:: RULESET_HASH: e9f2..d83a</span>
          </div>
          <h1 className="font-display text-2xl font-bold text-on-surface tracking-tight">
            Recovery Policies & Automation Rules
          </h1>
          <p className="font-body text-xs text-on-surface-variant mt-0.5">
            Define what the system is allowed to do automatically — University Campus Network Core SDN
          </p>
        </div>

        {/* Global Actions */}
        <div className="flex items-center flex-wrap gap-2">
          <button
            onClick={() => toast.success('Policy Audit Log exported to JSON.')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-bright text-on-surface text-xs font-body transition-colors border border-outline-variant/30"
          >
            <span className="material-symbols-outlined text-[16px] text-secondary">file_download</span>
            <span>Audit Log</span>
          </button>

          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary text-on-primary text-xs font-code font-bold hover:bg-primary-container transition-all shadow-[0_0_15px_rgba(78,222,163,0.3)]"
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            <span>New Policy Rule</span>
          </button>
        </div>
      </div>

      {/* Policies Rules Table */}
      <div className="bg-surface-container-low/90 backdrop-blur-md rounded-xl border border-outline-variant/30 overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-outline-variant/30 bg-surface-container-lowest/80 text-outline font-code uppercase text-[10px]">
                <th className="px-4 py-3">Pri</th>
                <th className="px-4 py-3">Rule Name & Scope</th>
                <th className="px-4 py-3">Failure Trigger</th>
                <th className="px-4 py-3">Campus Zone</th>
                <th className="px-4 py-3">SDN Action</th>
                <th className="px-4 py-3">Automation Gate</th>
                <th className="px-4 py-3">State</th>
                <th className="px-4 py-3 text-right">Delete</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/15 font-body">
              {policies.map(p => (
                <tr key={p.id} className="hover:bg-surface-container/60 transition-colors">
                  <td className="px-4 py-3 font-code font-bold text-primary">#{p.priority}</td>
                  <td className="px-4 py-3">
                    <span className="font-display font-semibold text-on-surface block text-xs">{p.name}</span>
                    <span className="text-[11px] text-outline font-body line-clamp-1">{p.description}</span>
                  </td>
                  <td className="px-4 py-3 font-code font-semibold text-secondary">{p.failureType}</td>
                  <td className="px-4 py-3 font-code text-outline">{p.zone}</td>
                  <td className="px-4 py-3 font-code font-bold text-on-surface">{p.action}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-code font-bold ${
                      p.automation === 'AUTOMATED'
                        ? 'bg-primary/10 text-primary border border-primary/30'
                        : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                    }`}>
                      {p.automation}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggle(p.id)}
                      className={`w-10 h-5 rounded-full transition-colors relative flex items-center px-0.5 ${
                        p.enabled ? 'bg-primary' : 'bg-surface-container-highest'
                      }`}
                    >
                      <span
                        className={`w-4 h-4 rounded-full bg-surface-lowest shadow transform transition-transform ${
                          p.enabled ? 'translate-x-5 bg-on-primary' : 'translate-x-0 bg-outline'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="text-outline hover:text-error transition-colors p-1"
                      title="Delete rule"
                    >
                      <span className="material-symbols-outlined text-[16px]">delete</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: New Policy Rule Creator */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="bg-surface-container-low border border-outline-variant/40 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-outline-variant/20">
              <h3 className="font-display font-bold text-lg text-on-surface">Create New Recovery Policy Rule</h3>
              <button onClick={() => setIsModalOpen(false)} className="text-outline hover:text-on-surface">
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            <form onSubmit={handleCreatePolicy} className="space-y-3 font-code text-xs">
              <div>
                <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">Rule Name</label>
                <input
                  type="text"
                  placeholder="e.g. Student Lab High Latency Auto-Reroute"
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded p-2 text-on-surface focus:outline-none focus:border-secondary font-body text-xs"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">Failure Trigger</label>
                  <select
                    value={formFailureType}
                    onChange={e => setFormFailureType(e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded p-2 text-on-surface focus:outline-none cursor-pointer"
                  >
                    <option value="LINK_FAILURE">LINK_FAILURE</option>
                    <option value="CONGESTION">CONGESTION</option>
                    <option value="HIGH_LATENCY">HIGH_LATENCY</option>
                    <option value="DEVICE_FAILURE">DEVICE_FAILURE</option>
                    <option value="REPEATED_FAILURE">REPEATED_FAILURE</option>
                  </select>
                </div>

                <div>
                  <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">SDN Action</label>
                  <select
                    value={formAction}
                    onChange={e => setFormAction(e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded p-2 text-on-surface focus:outline-none cursor-pointer"
                  >
                    <option value="REROUTE_TO_BACKUP">REROUTE_TO_BACKUP</option>
                    <option value="RATE_LIMIT">RATE_LIMIT</option>
                    <option value="REROUTE_AROUND_DEVICE">REROUTE_AROUND_DEVICE</option>
                    <option value="RESET_FLOW_TABLE">RESET_FLOW_TABLE</option>
                    <option value="PERMANENT_REROUTE">PERMANENT_REROUTE</option>
                    <option value="ESCALATE_TO_MANUAL">ESCALATE_TO_MANUAL</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">Zone Matcher</label>
                  <select
                    value={formZone}
                    onChange={e => setFormZone(e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded p-2 text-on-surface focus:outline-none cursor-pointer"
                  >
                    <option value="ALL_CAMPUS">ALL_CAMPUS (Any zone)</option>
                    <option value="Student Lab A">Student Lab A (S1)</option>
                    <option value="Student Lab B">Student Lab B (S2)</option>
                    <option value="Server Room">Server Room (S3)</option>
                    <option value="Core Backbone">Core Backbone</option>
                  </select>
                </div>

                <div>
                  <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">Automation Mode</label>
                  <select
                    value={formAutomation}
                    onChange={e => setFormAutomation(e.target.value as 'AUTOMATED' | 'MANUAL_APPROVAL')}
                    className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded p-2 text-on-surface focus:outline-none cursor-pointer"
                  >
                    <option value="AUTOMATED">AUTOMATED (Zero-touch)</option>
                    <option value="MANUAL_APPROVAL">MANUAL_APPROVAL (Require operator)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-outline uppercase text-[10px] mb-1 font-semibold">Rule Priority (1-10)</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={formPriority}
                  onChange={e => setFormPriority(Number(e.target.value))}
                  className="w-24 bg-surface-container-lowest border border-outline-variant/40 rounded p-2 text-on-surface focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-outline-variant/20">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-3 py-1.5 rounded bg-surface-container text-outline hover:text-on-surface"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 rounded bg-primary text-on-primary font-bold hover:bg-primary-container"
                >
                  Save Policy
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
