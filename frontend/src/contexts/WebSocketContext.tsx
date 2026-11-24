/**
 * contexts/WebSocketContext.tsx — WebSocket Connection Context
 *
 * Maintains a single persistent WebSocket connection to the FastAPI backend
 * (ws://localhost:8000/ws) and dispatches incoming events to the rest of
 * the app via a subscription model.
 *
 * Architecture:
 * - On mount (after auth), opens a WS connection and sends an AUTH frame
 * - Implements exponential back-off reconnection on disconnect
 * - Exposes `subscribe(eventType, handler)` so individual hooks can listen
 *   to specific event types (e.g. TOPOLOGY_CHANGED, ANOMALY_DETECTED)
 * - On unmount, closes the WS cleanly
 *
 * Usage:
 *   const { subscribe, isConnected } = useWebSocket()
 *   useEffect(() => {
 *     const unsub = subscribe('TOPOLOGY_CHANGED', (data) => { ... })
 *     return unsub
 *   }, [subscribe])
 */
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  ReactNode,
} from 'react'
import { useAuth } from './AuthContext'
import type { WebSocketEventType, WebSocketMessage } from '@/types'

type Handler = (data: unknown) => void

interface WebSocketContextValue {
  isConnected: boolean
  subscribe: (event: WebSocketEventType, handler: Handler) => () => void
}

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'

const WebSocketContext = createContext<WebSocketContextValue | null>(null)

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const { accessToken, isAuthenticated } = useAuth()
  const wsRef = useRef<WebSocket | null>(null)
  const handlersRef = useRef<Map<WebSocketEventType, Set<Handler>>>(new Map())
  const [isConnected, setIsConnected] = useState(false)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectDelay = useRef(1000)

  const connect = useCallback(() => {
    if (!isAuthenticated || !accessToken) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      reconnectDelay.current = 1000
      // Send auth frame
      ws.send(JSON.stringify({ type: 'AUTH', token: `Bearer ${accessToken}` }))
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(event.data) as WebSocketMessage
        const handlers = handlersRef.current.get(msg.event)
        handlers?.forEach(h => h(msg.data))
      } catch {
        // ignore malformed frames
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      // Exponential back-off: 1s, 2s, 4s, … max 30s
      reconnectTimeout.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30_000)
        connect()
      }, reconnectDelay.current)
    }

    ws.onerror = () => ws.close()
  }, [isAuthenticated, accessToken])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      wsRef.current?.close()
    }
  }, [connect])

  const subscribe = useCallback((event: WebSocketEventType, handler: Handler) => {
    if (!handlersRef.current.has(event)) {
      handlersRef.current.set(event, new Set())
    }
    handlersRef.current.get(event)!.add(handler)
    return () => {
      handlersRef.current.get(event)?.delete(handler)
    }
  }, [])

  return (
    <WebSocketContext.Provider value={{ isConnected, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWebSocket(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext)
  if (!ctx) throw new Error('useWebSocket must be used within <WebSocketProvider>')
  return ctx
}
