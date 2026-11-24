/**
 * main.tsx — Application Entry Point
 *
 * Bootstraps the React application by:
 * 1. Creating the React root on the #root DOM element
 * 2. Wrapping the app in StrictMode for development-time double-invoke warnings
 * 3. Providing global context providers in the correct dependency order:
 *    - QueryClientProvider  → TanStack Query for server state management
 *    - AuthProvider         → JWT session and user role context
 *    - WebSocketProvider    → Persistent WS connection + event dispatch
 *    - Toaster             → react-hot-toast global notification renderer
 *
 * The import of `./index.css` loads Tailwind's base, components, and utilities.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Toaster } from 'react-hot-toast'

import App from './App'
import { AuthProvider } from './contexts/AuthContext'
import { WebSocketProvider } from './contexts/WebSocketContext'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,         // 10s — matches backend scrape interval
      refetchOnWindowFocus: true,
      retry: 2,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WebSocketProvider>
          <App />
          <Toaster
            position="top-right"
            toastOptions={{
              className: 'bg-surface-overlay border border-surface-border text-gray-100',
              duration: 4000,
            }}
          />
        </WebSocketProvider>
      </AuthProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </React.StrictMode>
)
