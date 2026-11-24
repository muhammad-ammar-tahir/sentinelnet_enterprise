/**
 * App.tsx — Complete Route Tree for SentinelNet
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from '@/components/layout/AppShell'
import ProtectedRoute from '@/components/layout/ProtectedRoute'

import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import LiveTopologyPage from '@/pages/LiveTopologyPage'
import AIMonitoringPage from '@/pages/AIMonitoringPage'
import FaultDiagnosisPage from '@/pages/FaultDiagnosisPage'
import IncidentHistoryPage from '@/pages/IncidentHistoryPage'
import RecoveryManagementPage from '@/pages/RecoveryManagementPage'
import PoliciesPage from '@/pages/PoliciesPage'
import DevicesInventoryPage from '@/pages/DevicesInventoryPage'
import PredictiveMaintenancePage from '@/pages/PredictiveMaintenancePage'
import DigitalTwinPage from '@/pages/DigitalTwinPage'
import IntegrationsPage from '@/pages/IntegrationsPage'
import NotFoundPage from '@/pages/NotFoundPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Login Route */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected NOC Operations Routes */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/topology" element={<LiveTopologyPage />} />
            <Route path="/ai" element={<AIMonitoringPage />} />
            <Route path="/diagnosis" element={<FaultDiagnosisPage />} />
            <Route path="/incidents/:id" element={<FaultDiagnosisPage />} />
            <Route path="/incidents" element={<IncidentHistoryPage />} />
            <Route path="/recovery" element={<RecoveryManagementPage />} />
            <Route path="/policies" element={<PoliciesPage />} />
            <Route path="/devices" element={<DevicesInventoryPage />} />
            <Route path="/maintenance" element={<PredictiveMaintenancePage />} />
            <Route path="/digital-twin" element={<DigitalTwinPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
          </Route>
        </Route>

        {/* 404 Catch-All */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}
