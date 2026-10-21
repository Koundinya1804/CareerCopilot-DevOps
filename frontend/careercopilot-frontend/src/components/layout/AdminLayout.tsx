import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  BookOpen,
  BarChart3,
  Shield,
  ChevronLeft,
  Sparkles,
  Settings,
  Database,
  ScrollText,
  Heart,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

const NAV_ITEMS = [
  { to: '/admin',           label: 'Overview',       icon: LayoutDashboard, end: true },
  { to: '/admin/users',     label: 'Users',          icon: Users,           end: false },
  { to: '/admin/knowledge', label: 'Knowledge Base', icon: BookOpen,        end: false },
  { to: '/admin/usage',     label: 'Agent Usage',    icon: BarChart3,       end: false },
  { to: '/admin/logs',      label: 'Logs',           icon: ScrollText,      end: false },
  { to: '/admin/health',    label: 'System Health',  icon: Heart,           end: false },
  { to: '/admin/chromadb',  label: 'ChromaDB',       icon: Database,        end: false },
  { to: '/admin/settings',  label: 'Settings',       icon: Settings,        end: false },
] as const

export default function AdminLayout() {
  const user     = useAuthStore(s => s.user)
  const navigate = useNavigate()

  return (
    <div className="flex h-screen bg-[#0a0a1a] text-white overflow-hidden">

      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 border-r border-white/10 bg-[#0d0d20] flex flex-col">

        {/* Logo + Admin Badge */}
        <div className="px-5 py-5 border-b border-white/10">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm text-white leading-tight">CareerCopilot</p>
              <p className="text-2xs text-white/40 leading-tight">AI Platform</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 mt-3 px-2.5 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
            <Shield className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
            <span className="text-xs font-medium text-indigo-300 tracking-wide">Admin Panel</span>
          </div>
        </div>

        {/* Nav links */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 border',
                  isActive
                    ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'
                    : 'text-white/50 hover:text-white/80 hover:bg-white/5 border-transparent',
                ].join(' ')
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-3 py-4 border-t border-white/10 space-y-1">
          {user && (
            <div className="px-3 py-2 mb-1">
              <p className="text-xs font-medium text-white/70 truncate">{user.full_name}</p>
              <p className="text-2xs text-white/30 truncate">{user.email}</p>
            </div>
          )}
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2.5 px-3 py-2.5 w-full rounded-lg text-sm text-white/40 hover:text-white/70 hover:bg-white/5 transition-all"
          >
            <ChevronLeft className="w-4 h-4 flex-shrink-0" />
            Back to App
          </button>
        </div>
      </aside>

      {/* Page content rendered by child routes */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
