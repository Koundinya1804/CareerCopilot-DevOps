import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import { Brain, LayoutDashboard, FileText, Target, Mic, TrendingUp,
         MessageSquare, ChevronRight, LogOut, Menu, X } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { authApi } from '@/api'
import NotificationBell from '@/components/notifications/NotificationBell'

const NAV = [
  { to:'/dashboard', icon:LayoutDashboard, label:'Dashboard',       color:'#5B4FE8' },
  { to:'/chat',      icon:MessageSquare,   label:'AI Chat',          color:'#00D4FF' },
  { to:'/resume',    icon:FileText,        label:'Resume Analyser',  color:'#10D97A' },
  { to:'/skill-gap', icon:Target,          label:'Skill Gap',        color:'#F59E0B' },
  { to:'/career',    icon:TrendingUp,      label:'Career Paths',     color:'#A855F7' },
  { to:'/interview', icon:Mic,             label:'Interview Coach',  color:'#F43F5E' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const loc    = useLocation()
  const nav    = useNavigate()
  const user   = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const [mob, setMob] = useState(false)

  const doLogout = () => {
    const refreshToken = useAuthStore.getState().refreshToken
    // Best-effort server-side revocation — logout must still succeed locally
    // even if this call fails (network down, token already expired, etc.).
    if (refreshToken) {
      authApi.logout(refreshToken).catch(() => {})
    }
    logout()
    nav('/')
  }

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-white/5">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background:'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>
          <Brain className="w-4 h-4 text-white" />
        </div>
        <span className="font-display font-bold text-base text-white">CareerCopilot <span className="text-gradient">AI</span></span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ to, icon: Icon, label, color }) => {
          const active = loc.pathname === to
          return (
            <Link key={to} to={to} onClick={() => setMob(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 border
                ${active ? 'nav-active' : 'border-transparent text-star-70 hover:text-white hover:bg-white/4'}`}>
              <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                   style={active ? { background:`${color}20`, border:`1px solid ${color}30` } : { background:'rgba(255,255,255,0.04)' }}>
                <Icon className="w-4 h-4" style={active ? { color } : { color:'#636685' }} />
              </div>
              <span className="flex-1">{label}</span>
              {active && <ChevronRight className="w-3.5 h-3.5" style={{ color }} />}
            </Link>
          )
        })}
      </nav>

      {/* User */}
      <div className="px-3 py-4 border-t border-white/5 space-y-1">
        <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl glass mb-2">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
               style={{ background:'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>
            {user?.full_name?.[0] ?? 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-white truncate">{user?.full_name ?? 'User'}</div>
            <div className="text-2xs text-star-50 truncate">{user?.email ?? ''}</div>
          </div>
        </div>
        <button onClick={doLogout} className="btn-ghost w-full justify-start gap-3 text-star-50 hover:text-rose-400">
          <LogOut className="w-4 h-4" /> Sign out
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-void overflow-hidden">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-60 flex-shrink-0 border-r border-white/5"
             style={{ background:'rgba(8,9,15,0.9)', backdropFilter:'blur(20px)' }}>
        <SidebarContent />
      </aside>

      {/* Mobile sidebar */}
      <AnimatePresence>
        {mob && (
          <>
            <motion.div initial={{ opacity:0 }} animate={{ opacity:1 }} exit={{ opacity:0 }}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
              onClick={() => setMob(false)} />
            <motion.aside initial={{ x:-280 }} animate={{ x:0 }} exit={{ x:-280 }} transition={{ type:'spring', damping:25, stiffness:300 }}
              className="fixed left-0 top-0 bottom-0 w-64 z-50 flex flex-col border-r border-white/5 lg:hidden"
              style={{ background:'rgba(8,9,15,0.98)', backdropFilter:'blur(20px)' }}>
              <button onClick={() => setMob(false)} className="absolute top-4 right-4 text-star-50 hover:text-white">
                <X className="w-5 h-5" />
              </button>
              <SidebarContent />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 h-14 border-b border-white/5 flex-shrink-0"
                style={{ background:'rgba(4,5,10,0.8)', backdropFilter:'blur(12px)' }}>
          <button onClick={() => setMob(true)} className="lg:hidden text-star-50 hover:text-white">
            <Menu className="w-5 h-5" />
          </button>
          <div className="hidden lg:block">
            <span className="text-sm text-star-50">
              {NAV.find(n => n.to === loc.pathname)?.label ?? 'Dashboard'}
            </span>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <NotificationBell />
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white cursor-pointer"
                 style={{ background:'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>
              {user?.full_name?.[0] ?? 'U'}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="absolute inset-0 bg-grid-sm pointer-events-none opacity-30" />
          {children}
        </main>
      </div>
    </div>
  )
}
