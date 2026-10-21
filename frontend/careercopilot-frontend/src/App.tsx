import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense, lazy } from 'react'
import { useAuthStore } from '@/store/authStore'

import LandingPage from '@/pages/LandingPage'
import LoginPage   from '@/pages/LoginPage'

// Pages self-wrap with <DashboardLayout> — do NOT wrap them again here
import DashboardPage  from '@/pages/DashboardPage'
import ResumePage     from '@/pages/ResumePage'
import SkillGapPage   from '@/pages/SkillGapPage'
import InterviewPage  from '@/pages/InterviewPage'
import CareerPage     from '@/pages/CareerPage'
import ChatPage       from '@/pages/ChatPage'

// Admin pages use AdminLayout via <Outlet>
import AdminLayout from '@/components/layout/AdminLayout'

const ProfilePage           = lazy(() => import('@/pages/ProfilePage'))
const NotificationsPage     = lazy(() => import('@/pages/NotificationsPage'))
const AdminOverviewPage     = lazy(() => import('@/pages/admin/AdminOverviewPage'))
const AdminUsersPage        = lazy(() => import('@/pages/admin/AdminUsersPage'))
const AdminKnowledgePage    = lazy(() => import('@/pages/admin/AdminKnowledgePage'))
const AdminUsagePage        = lazy(() => import('@/pages/admin/AdminUsagePage'))
const AdminLogsPage         = lazy(() => import('@/pages/admin/AdminLogsPage'))
const AdminHealthPage       = lazy(() => import('@/pages/admin/AdminHealthPage'))
const AdminSettingsPage     = lazy(() => import('@/pages/admin/AdminSettingsPage'))
const AdminChromaPage       = lazy(() => import('@/pages/admin/AdminChromaPage'))

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000 * 60 * 5, retry: 1 } },
})

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-void">
      <div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

// ── Route guards ──────────────────────────────────────────────────────────────

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore(s => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore(s => s.user)
  const token = useAuthStore(s => s.token)

  // Not logged in at all
  if (!token || !user) return <Navigate to="/login" replace />

  // Logged in but not admin — normalise role to lowercase for comparison
  if (user.role?.toLowerCase() !== 'admin') return <Navigate to="/dashboard" replace />

  return <>{children}</>
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>

            {/* ── Public ────────────────────────────────────────────────── */}
            <Route path="/"      element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />

            {/* ── Authenticated app ─────────────────────────────────────── */}
            <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
            <Route path="/resume"    element={<ProtectedRoute><ResumePage /></ProtectedRoute>} />
            <Route path="/skill-gap" element={<ProtectedRoute><SkillGapPage /></ProtectedRoute>} />
            <Route path="/career"    element={<ProtectedRoute><CareerPage /></ProtectedRoute>} />
            <Route path="/interview" element={<ProtectedRoute><InterviewPage /></ProtectedRoute>} />
            <Route path="/chat"      element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
            <Route path="/profile"   element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
            <Route path="/notifications" element={<ProtectedRoute><NotificationsPage /></ProtectedRoute>} />

            {/* ── Admin (admin role only) ───────────────────────────────── */}
            <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
              <Route index              element={<AdminOverviewPage />} />
              <Route path="users"       element={<AdminUsersPage />} />
              <Route path="knowledge"   element={<AdminKnowledgePage />} />
              <Route path="usage"       element={<AdminUsagePage />} />
              <Route path="logs"        element={<AdminLogsPage />} />
              <Route path="health"      element={<AdminHealthPage />} />
              <Route path="settings"    element={<AdminSettingsPage />} />
              <Route path="chromadb"    element={<AdminChromaPage />} />
            </Route>

            {/* ── Fallback ──────────────────────────────────────────────── */}
            <Route path="*" element={<Navigate to="/" replace />} />

          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
