/** @type {import('tailwindcss').Config} */

/**
 * Tailwind CSS configuration for SentinelNet — Cyber Observability Design System
 * Matches exact tokens from cyber_observability/DESIGN.md and screen mockups
 */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Exact tokens from cyber_observability/DESIGN.md
        surface: '#0d1322',
        'surface-dim': '#0d1322',
        'surface-bright': '#33394a',
        'surface-container-lowest': '#080e1d',
        'surface-container-low': '#151b2b',
        'surface-container': '#191f2f',
        'surface-container-high': '#242a3a',
        'surface-container-highest': '#2f3445',
        'surface-variant': '#2f3445',
        'surface-tint': '#4edea3',
        background: '#0d1322',

        'on-surface': '#dde2f8',
        'on-surface-variant': '#bbcabf',
        'on-background': '#dde2f8',
        'inverse-surface': '#dde2f8',
        'inverse-on-surface': '#2a3040',

        outline: '#86948a',
        'outline-variant': '#3c4a42',

        // Primary Accent (Cyber Emerald)
        primary: '#4edea3',
        'on-primary': '#003824',
        'primary-container': '#10b981',
        'on-primary-container': '#00422b',
        'inverse-primary': '#006c49',
        'primary-fixed': '#6ffbbe',
        'primary-fixed-dim': '#4edea3',
        'on-primary-fixed': '#002113',
        'on-primary-fixed-variant': '#005236',

        // Secondary Accent (Cyber Cyan/Teal)
        secondary: '#4cd7f6',
        'on-secondary': '#003640',
        'secondary-container': '#03b5d3',
        'on-secondary-container': '#00424e',
        'secondary-fixed': '#acedff',
        'secondary-fixed-dim': '#4cd7f6',
        'on-secondary-fixed': '#001f26',
        'on-secondary-fixed-variant': '#004e5c',

        // Tertiary (Mint / Pulse)
        tertiary: '#68dba9',
        'on-tertiary': '#003825',
        'tertiary-container': '#3eb686',
        'on-tertiary-container': '#00422c',
        'tertiary-fixed': '#85f8c4',
        'tertiary-fixed-dim': '#68dba9',
        'on-tertiary-fixed': '#002114',
        'on-tertiary-fixed-variant': '#005137',

        // Semantic Alerts & Error
        error: '#ffb4ab',
        'on-error': '#690005',
        'error-container': '#93000a',
        'on-error-container': '#ffdad6',

        status: {
          up: '#4edea3',
          down: '#ef4444',
          degraded: '#f59e0b',
          unknown: '#86948a',
          suspended: '#8b5cf6',
        },
        severity: {
          low: '#4cd7f6',
          medium: '#f59e0b',
          high: '#ef4444',
          critical: '#ff5449',
        },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'Inter', 'sans-serif'],
        headline: ['"Plus Jakarta Sans"', 'Inter', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
        code: ['"JetBrains Mono"', 'monospace'],
      },
      spacing: {
        gutter: '1rem',
        'gutter-sm': '0.5rem',
        'gutter-lg': '1.5rem',
        margin: '1.5rem',
        'margin-mobile': '1rem',
        'space-xs': '0.25rem',
        'space-sm': '0.5rem',
        'space-md': '0.75rem',
        'space-lg': '1.25rem',
        'space-xl': '2rem',
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        sm: '0.125rem',
        md: '0.375rem',
        lg: '0.5rem',
        xl: '0.75rem',
        '2xl': '1rem',
        full: '9999px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ping-slow': 'ping 2s cubic-bezier(0, 0, 0.2, 1) infinite',
        'spin-slow': 'spin 8s linear infinite',
      },
    },
  },
  plugins: [],
}
