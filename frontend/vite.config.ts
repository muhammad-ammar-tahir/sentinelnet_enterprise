import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * Vite configuration for SentinelNet Frontend
 *
 * Key settings:
 * - React plugin for JSX transform and Fast Refresh (HMR)
 * - Path alias `@` mapped to `src/` for clean imports
 * - Dev server proxy: all `/api` and `/ws` calls forwarded to FastAPI backend
 *   so the frontend never has to know the backend port in development
 * - Build output goes to `dist/` for production serving
 */
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // REST API → FastAPI backend
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      // WebSocket → FastAPI backend
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor chunks for better cache performance
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
          'd3-vendor': ['d3'],
          'chart-vendor': ['recharts'],
        },
      },
    },
  },
})
