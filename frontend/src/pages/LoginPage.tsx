/**
 * pages/LoginPage.tsx — Enterprise NOC Sovereign Access Gateway
 *
 * Replicates the split-screen design from sentinelnet_enterprise_login:
 * - Left Pane (60%): Neural topology & sovereign telemetry with WebGL/Canvas animation
 * - Right Pane (40%): Enterprise Zero-Trust credentials card with quick demo login
 */
import { useState, useEffect, useRef, FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

export default function LoginPage() {
  const { login, isLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard'

  // Gate demo shortcuts and default credentials behind VITE_DEMO_MODE
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'

  const [email, setEmail] = useState(isDemoMode ? 'admin@sentinelnet.edu' : '')
  const [password, setPassword] = useState(isDemoMode ? 'sentinelpass' : '')
  const [role, setRole] = useState('NOC Commander')
  const [showPassword, setShowPassword] = useState(false)
  const [mfaEnabled, setMfaEnabled] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // Subtle interactive neural network canvas animation for left pane
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationFrameId: number
    let width = (canvas.width = canvas.parentElement?.clientWidth || 800)
    let height = (canvas.height = canvas.parentElement?.clientHeight || 600)

    const handleResize = () => {
      if (!canvas.parentElement) return
      width = canvas.width = canvas.parentElement.clientWidth
      height = canvas.height = canvas.parentElement.clientHeight
    }
    window.addEventListener('resize', handleResize)

    // Nodes for simulated SDN mesh
    const nodes = Array.from({ length: 28 }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.8,
      vy: (Math.random() - 0.5) * 0.8,
      radius: Math.random() * 2.5 + 1.5,
      isCore: Math.random() > 0.8,
    }))

    const render = () => {
      ctx.clearRect(0, 0, width, height)

      // Draw links
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 140) {
            ctx.beginPath()
            ctx.moveTo(nodes[i].x, nodes[i].y)
            ctx.lineTo(nodes[j].x, nodes[j].y)
            ctx.strokeStyle = `rgba(78, 222, 163, ${0.25 * (1 - dist / 140)})`
            ctx.lineWidth = 1
            ctx.stroke()
          }
        }
      }

      // Draw nodes
      nodes.forEach(node => {
        node.x += node.vx
        node.y += node.vy
        if (node.x < 0 || node.x > width) node.vx *= -1
        if (node.y < 0 || node.y > height) node.vy *= -1

        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx.fillStyle = node.isCore ? '#4cd7f6' : '#4edea3'
        ctx.shadowBlur = 8
        ctx.shadowColor = node.isCore ? 'rgba(76, 215, 246, 0.6)' : 'rgba(78, 222, 163, 0.6)'
        ctx.fill()
        ctx.shadowBlur = 0
      })

      animationFrameId = requestAnimationFrame(render)
    }

    render()

    return () => {
      cancelAnimationFrame(animationFrameId)
      window.removeEventListener('resize', handleResize)
    }
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await login({ username: email.includes('@') ? email.split('@')[0] : email, password })
      navigate(from, { replace: true })
    } catch (err: unknown) {
      if (isDemoMode) {
        // Fallback only if VITE_DEMO_MODE is explicitly enabled
        localStorage.setItem('access_token', 'demo-jwt-token')
        localStorage.setItem('user', JSON.stringify({ id: '1', username: email.split('@')[0] || 'admin', role }))
        navigate(from, { replace: true })
        return
      }
      const responseData = (err as { response?: { data?: { detail?: string } } })?.response?.data
      const msg = responseData?.detail || 'Authentication failed. Please verify credentials.'
      setError(msg)
    }
  }

  function handleDemoFill(demoUser: string, demoRole: string) {
    setEmail(`${demoUser}@sentinelnet.edu`)
    setPassword('sentinelpass')
    setRole(demoRole)
  }

  return (
    <div className="relative w-full min-h-screen overflow-x-hidden flex flex-col lg:flex-row bg-surface">
      {/* LEFT PANE: Sovereign Telemetry & Neural Topology (60% Desktop) */}
      <div className="relative w-full lg:w-[60%] flex flex-col justify-between p-6 sm:p-10 lg:p-12 overflow-hidden bg-gradient-to-br from-surface-container-lowest via-surface to-surface-container-low border-b lg:border-b-0 lg:border-r border-outline-variant/30">
        {/* Interactive Neural Canvas Layer */}
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none opacity-60" />

        {/* Top Header */}
        <div className="relative z-10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded bg-primary flex items-center justify-center text-on-primary shadow-[0_0_20px_rgba(78,222,163,0.4)]">
              <span className="material-symbols-outlined text-[24px]">shield_with_heart</span>
            </div>
            <div>
              <span className="font-display font-bold text-lg text-on-surface tracking-tight block">SentinelNet</span>
              <span className="font-code text-[11px] text-primary tracking-widest uppercase font-semibold">SOVEREIGN AUTONOMOUS SDN</span>
            </div>
          </div>

          <div className="flex items-center gap-2 bg-surface-container/70 border border-outline-variant/40 px-3 py-1 rounded text-xs font-code">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-on-surface">CLUSTER-01α ONLINE</span>
          </div>
        </div>

        {/* Center Telemetry & Visual Showcase */}
        <div className="relative z-10 my-10 max-w-xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded bg-primary/10 border border-primary/30 text-primary font-code text-xs font-semibold mb-4">
            <span className="material-symbols-outlined text-[16px]">bolt</span>
            CLOSED-LOOP SELF-HEALING ARCHITECTURE
          </div>

          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-on-surface tracking-tight leading-tight">
            Autonomous network remediation at wire speed.
          </h1>

          <p className="font-body text-sm text-on-surface-variant mt-4 leading-relaxed">
            SentinelNet merges Ryu OpenFlow SDN programmability, real-time Prometheus telemetry, and Scikit-learn
            Isolation Forest models to detect anomalies, isolate link cuts, and actuate zero-touch reroutes in sub-second SLA.
          </p>

          {/* Quick Metrics Ticker */}
          <div className="grid grid-cols-3 gap-3 mt-8">
            <div className="bg-surface-container-high/60 backdrop-blur-md border border-outline-variant/30 rounded p-3">
              <span className="font-code text-[10px] text-outline uppercase block">Mean TTDR</span>
              <span className="font-display font-bold text-xl text-primary font-code">740 ms</span>
            </div>
            <div className="bg-surface-container-high/60 backdrop-blur-md border border-outline-variant/30 rounded p-3">
              <span className="font-code text-[10px] text-outline uppercase block">Model Accuracy</span>
              <span className="font-display font-bold text-xl text-secondary font-code">94.2%</span>
            </div>
            <div className="bg-surface-container-high/60 backdrop-blur-md border border-outline-variant/30 rounded p-3">
              <span className="font-code text-[10px] text-outline uppercase block">Uptime Guarantee</span>
              <span className="font-display font-bold text-xl text-on-surface font-code">99.99%</span>
            </div>
          </div>
        </div>

        {/* Bottom Disclaimer & Compliance */}
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-3 text-xs text-outline font-code pt-4 border-t border-outline-variant/20">
          <span>MININET + RYU OPENFLOW 1.3 PLATFORM</span>
          <div className="flex items-center gap-4">
            <span className="text-secondary">AES-256 TLS 1.3</span>
            <span className="text-primary">ZERO-TRUST COMPLIANT</span>
          </div>
        </div>
      </div>

      {/* RIGHT PANE: Enterprise Secure Access Dock (40% Desktop) */}
      <div className="relative w-full lg:w-[40%] flex flex-col justify-center items-center p-6 sm:p-10 lg:p-12 bg-surface-container-lowest">
        {/* Ambient Glows */}
        <div className="absolute top-1/4 right-0 w-72 h-72 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-10 left-0 w-60 h-60 bg-secondary/5 rounded-full blur-3xl pointer-events-none" />

        {/* Login Card Container */}
        <div className="relative z-10 w-full max-w-md p-6 sm:p-8 rounded-2xl bg-surface-container/80 backdrop-blur-2xl border border-outline-variant/40 shadow-2xl">
          <div className="flex items-center justify-between pb-4 border-b border-outline-variant/30">
            <div>
              <h2 className="font-display font-bold text-xl text-on-surface">Sign in to NOC</h2>
              <p className="text-xs text-on-surface-variant mt-0.5">Sovereign Operator Access Gateway</p>
            </div>
            <span className="px-2 py-0.5 rounded bg-primary/10 text-primary font-code text-[11px] font-bold border border-primary/30">
              L3 GATEWAY
            </span>
          </div>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            {/* Work Email */}
            <div>
              <label className="block font-code text-[11px] text-outline uppercase mb-1">Operator ID / Email</label>
              <div className="relative rounded bg-surface-container-lowest border border-outline-variant/50 focus-within:border-secondary transition-colors">
                <span className="material-symbols-outlined absolute left-3 top-2.5 text-[18px] text-outline">
                  badge
                </span>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-transparent text-xs font-code text-on-surface placeholder:text-outline/40 focus:outline-none"
                  placeholder="operator@sentinelnet.edu"
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-code text-[11px] text-outline uppercase">Passkey / Credential</label>
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-[11px] text-secondary hover:underline font-code"
                >
                  {showPassword ? 'Hide' : 'Reveal'}
                </button>
              </div>
              <div className="relative rounded bg-surface-container-lowest border border-outline-variant/50 focus-within:border-secondary transition-colors">
                <span className="material-symbols-outlined absolute left-3 top-2.5 text-[18px] text-outline">
                  lock
                </span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-transparent text-xs font-code text-on-surface placeholder:text-outline/40 focus:outline-none"
                  required
                />
              </div>
            </div>

            {/* Role Clearance Selection */}
            <div>
              <label className="block font-code text-[11px] text-outline uppercase mb-1">Clearance Tier</label>
              <select
                value={role}
                onChange={e => setRole(e.target.value)}
                className="w-full px-3 py-2 rounded bg-surface-container-lowest border border-outline-variant/50 text-xs font-code text-on-surface focus:outline-none focus:border-secondary cursor-pointer"
              >
                <option value="NOC Commander">L1: NOC Commander (Full Actuation)</option>
                <option value="Network Operator">L2: Network Operations Engineer</option>
                <option value="Security Auditor">L3: Observability & Audit Viewer</option>
              </select>
            </div>

            {/* MFA Checkbox */}
            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-on-surface-variant">
                <input
                  type="checkbox"
                  checked={mfaEnabled}
                  onChange={e => setMfaEnabled(e.target.checked)}
                  className="rounded border-outline-variant bg-surface-container-lowest text-primary focus:ring-primary"
                />
                <span>Hardware Token MFA (FIDO2)</span>
              </label>
              <span className="font-code text-[11px] text-primary">ENFORCED</span>
            </div>

            {error && (
              <div className="p-2.5 rounded bg-error/10 border border-error/30 text-xs text-error font-body">
                {error}
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 px-4 rounded bg-primary hover:bg-primary-container text-on-primary font-display font-bold text-sm tracking-wide transition-all shadow-[0_0_15px_rgba(78,222,163,0.3)] flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isLoading ? (
                <span>Authenticating with Gateway...</span>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[18px]">vpn_key</span>
                  <span>Authorize & Enter Console</span>
                </>
              )}
            </button>
          </form>

          {/* Quick Demo Credentials Fill (Visible only when VITE_DEMO_MODE=true) */}
          {isDemoMode && (
            <div className="mt-5 pt-4 border-t border-outline-variant/20">
              <span className="font-code text-[10px] text-outline uppercase block mb-2 font-semibold">1-Click Quick Demo Profiles</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleDemoFill('admin', 'NOC Commander')}
                  className="px-2.5 py-1.5 rounded bg-surface-container-high/80 hover:bg-surface-bright border border-outline-variant/30 text-left text-xs font-code text-on-surface transition-colors flex items-center justify-between"
                >
                  <span>admin / L3</span>
                  <span className="text-primary font-bold">→</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleDemoFill('operator', 'Network Operator')}
                  className="px-2.5 py-1.5 rounded bg-surface-container-high/80 hover:bg-surface-bright border border-outline-variant/30 text-left text-xs font-code text-on-surface transition-colors flex items-center justify-between"
                >
                  <span>operator / L2</span>
                  <span className="text-secondary font-bold">→</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Security watermark footer */}
        <div className="mt-6 text-center text-[11px] text-outline font-code">
          <span>Authorized University Academic & Infrastructure Personnel Only</span>
        </div>
      </div>
    </div>
  )
}
