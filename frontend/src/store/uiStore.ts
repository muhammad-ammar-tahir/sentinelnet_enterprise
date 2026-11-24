/**
 * store/uiStore.ts — Global UI State (Zustand)
 *
 * Manages lightweight, ephemeral UI state that:
 * - Does not belong in React Query (it's not server state)
 * - Needs to be shared across components that aren't parent-child related
 *
 * State managed here:
 * - sidebarOpen: mobile sidebar toggle
 * - selectedDeviceId: which device node is focused in the topology map
 * - selectedIncidentId: which incident is highlighted in the incident list
 * - globalFilter: shared status/type filter across incident views
 *
 * Usage:
 *   const { sidebarOpen, setSidebarOpen } = useUiStore()
 */
import { create } from 'zustand'

interface GlobalFilter {
  status: string
  failureType: string
}

interface UiState {
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void

  selectedDeviceId: string | null
  setSelectedDeviceId: (id: string | null) => void

  selectedIncidentId: string | null
  setSelectedIncidentId: (id: string | null) => void

  globalFilter: GlobalFilter
  setGlobalFilter: (filter: Partial<GlobalFilter>) => void
  resetGlobalFilter: () => void
}

const DEFAULT_FILTER: GlobalFilter = { status: '', failureType: '' }

export const useUiStore = create<UiState>(set => ({
  sidebarOpen: false,
  setSidebarOpen: open => set({ sidebarOpen: open }),
  toggleSidebar: () => set(s => ({ sidebarOpen: !s.sidebarOpen })),

  selectedDeviceId: null,
  setSelectedDeviceId: id => set({ selectedDeviceId: id }),

  selectedIncidentId: null,
  setSelectedIncidentId: id => set({ selectedIncidentId: id }),

  globalFilter: DEFAULT_FILTER,
  setGlobalFilter: filter => set(s => ({ globalFilter: { ...s.globalFilter, ...filter } })),
  resetGlobalFilter: () => set({ globalFilter: DEFAULT_FILTER }),
}))
