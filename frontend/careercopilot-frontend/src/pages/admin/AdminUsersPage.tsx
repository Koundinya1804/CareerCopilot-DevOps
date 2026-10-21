import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Loader2, ChevronLeft, ChevronRight,
  ShieldCheck, ShieldOff, UserCircle, ShieldPlus,
  ShieldMinus, Trash2, KeyRound, Activity, X,
} from 'lucide-react'
import { adminApi } from '@/api'
import { fadeUp } from '@/utils'

interface UserRow {
  user_id:    number
  email:      string
  full_name:  string
  role:       string
  status:     string
  is_active:  boolean
  created_at: string | null
}

interface UsersPayload {
  total: number; page: number; size: number; pages: number; items: UserRow[]
}

// ── Confirm dialog ─────────────────────────────────────────────────────────
function ConfirmDialog({
  message, onConfirm, onCancel, danger = false,
}: { message: string; onConfirm: () => void; onCancel: () => void; danger?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="glass rounded-2xl p-6 max-w-sm w-full mx-4 border border-white/10">
        <p className="text-white text-sm leading-relaxed mb-5">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm text-star-70 hover:text-white hover:bg-white/5 transition">Cancel</button>
          <button onClick={onConfirm}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              danger ? 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30 border border-rose-500/30'
                     : 'bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30 border border-indigo-500/30'
            }`}>
            Confirm
          </button>
        </div>
      </motion.div>
    </div>
  )
}

// ── Reset password modal ───────────────────────────────────────────────────
function ResetPasswordModal({ user, onClose, onSave }: { user: UserRow; onClose: () => void; onSave: (pw: string) => void }) {
  const [pw, setPw] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="glass rounded-2xl p-6 max-w-sm w-full mx-4 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold text-sm">Reset Password</h3>
          <button onClick={onClose} className="text-star-50 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-star-50 text-xs mb-4">{user.email}</p>
        <input
          type="password" placeholder="New password (min 8 chars)"
          value={pw} onChange={e => setPw(e.target.value)}
          className="input w-full mb-4"
          minLength={8}
        />
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-star-70 hover:text-white hover:bg-white/5 transition">Cancel</button>
          <button onClick={() => pw.length >= 8 && onSave(pw)} disabled={pw.length < 8}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 disabled:opacity-40 transition">
            Save
          </button>
        </div>
      </motion.div>
    </div>
  )
}

// ── User activity modal ─────────────────────────────────────────────────────
function ActivityModal({ user, onClose }: { user: UserRow; onClose: () => void }) {
  const [loading, setLoading] = useState(true)
  const [items,   setItems]   = useState<any[]>([])

  useEffect(() => {
    adminApi.getUserActivity(user.user_id, 20)
      .then(res => setItems((res.data?.data ?? res.data)?.activity ?? []))
      .finally(() => setLoading(false))
  }, [user.user_id])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="glass rounded-2xl border border-white/10 w-full max-w-md max-h-[70vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 flex-shrink-0">
          <div>
            <p className="text-sm font-semibold text-white">Recent Activity</p>
            <p className="text-2xs text-star-50">{user.full_name || user.email}</p>
          </div>
          <button onClick={onClose} className="text-star-50 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <div className="overflow-y-auto flex-1">
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 text-indigo-400 animate-spin" /></div>
          ) : items.length === 0 ? (
            <p className="text-sm text-star-50 text-center py-10">No AI agent activity for this user yet.</p>
          ) : (
            <div className="divide-y divide-white/5">
              {items.map(i => (
                <div key={i.log_id} className="px-5 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-white capitalize truncate">{String(i.agent_name).replace(/_/g, ' ')}</p>
                    <p className="text-2xs text-star-50">{i.created_at ? new Date(i.created_at).toLocaleString() : ''}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <span className={`text-2xs font-mono ${i.status === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {i.status}
                    </span>
                    <p className="text-2xs text-star-50">{i.latency_ms != null ? `${i.latency_ms}ms` : ''}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  )
}

export default function AdminUsersPage() {
  const [payload,     setPayload]     = useState<UsersPayload | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [page,        setPage]        = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [search,      setSearch]      = useState('')
  const [actionUser,  setActionUser]  = useState<UserRow | null>(null)
  const [actionType,  setActionType]  = useState<string>('')
  const [actioning,   setActioning]   = useState<number | null>(null)
  const [toast,       setToast]       = useState<{ msg: string; ok: boolean } | null>(null)
  const [activityUser, setActivityUser] = useState<UserRow | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    adminApi.getUsers({ page, page_size: 20, search: search || undefined })
      .then(res => setPayload(res.data?.data ?? res.data))
      .finally(() => setLoading(false))
  }, [page, search])

  useEffect(() => { load() }, [load])

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  const doAction = async () => {
    if (!actionUser) return
    setActioning(actionUser.user_id)
    try {
      switch (actionType) {
        case 'suspend':   await adminApi.updateUserStatus(actionUser.user_id, false); break
        case 'activate':  await adminApi.updateUserStatus(actionUser.user_id, true);  break
        case 'promote':   await adminApi.promoteUser(actionUser.user_id);  break
        case 'demote':    await adminApi.demoteUser(actionUser.user_id);   break
        case 'delete':    await adminApi.deleteUser(actionUser.user_id);   break
      }
      showToast(`Done — ${actionUser.email}`)
      load()
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Action failed', false)
    } finally {
      setActioning(null); setActionUser(null); setActionType('')
    }
  }

  const doResetPassword = async (newPw: string) => {
    if (!actionUser) return
    setActioning(actionUser.user_id)
    try {
      await adminApi.resetPassword(actionUser.user_id, newPw)
      showToast(`Password reset for ${actionUser.email}`)
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Reset failed', false)
    } finally {
      setActioning(null); setActionUser(null); setActionType('')
    }
  }

  const trigger = (user: UserRow, type: string) => { setActionUser(user); setActionType(type) }

  return (
    <div className="p-6 space-y-6">
      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl text-sm border shadow-xl ${
              toast.ok ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25'
                       : 'bg-rose-500/15 text-rose-300 border-rose-500/25'
            }`}>
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Confirm dialog */}
      {actionUser && actionType !== 'reset' && (
        <ConfirmDialog
          danger={actionType === 'delete'}
          message={
            actionType === 'delete' ? `Permanently delete ${actionUser.email}? This cannot be undone.`
            : actionType === 'promote' ? `Promote ${actionUser.email} to Admin?`
            : actionType === 'demote'  ? `Demote ${actionUser.email} to regular User?`
            : actionType === 'suspend' ? `Suspend ${actionUser.email}?`
            : `Reactivate ${actionUser.email}?`
          }
          onConfirm={doAction}
          onCancel={() => { setActionUser(null); setActionType('') }}
        />
      )}
      {actionUser && actionType === 'reset' && (
        <ResetPasswordModal user={actionUser} onClose={() => { setActionUser(null); setActionType('') }} onSave={doResetPassword} />
      )}
      {activityUser && (
        <ActivityModal user={activityUser} onClose={() => setActivityUser(null)} />
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Users</h1>
        <p className="text-sm text-star-70 mt-0.5">
          {payload ? `${payload.total.toLocaleString()} total accounts` : 'Manage user accounts'}
        </p>
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-star-50" />
          <input type="text" placeholder="Search by name or email…" value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && (setPage(1), setSearch(searchInput.trim()))}
            className="input w-full pl-9 text-sm" />
        </div>
        <button onClick={() => { setPage(1); setSearch(searchInput.trim()) }} className="btn-primary px-4 py-2.5 text-sm">
          Search
        </button>
      </div>

      {/* Table */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" className="glass rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-2xs text-star-50 uppercase tracking-widest">
                    <th className="px-5 py-3.5 text-left">User</th>
                    <th className="px-5 py-3.5 text-left">Role</th>
                    <th className="px-5 py-3.5 text-left">Status</th>
                    <th className="px-5 py-3.5 text-left">Joined</th>
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(payload?.items ?? []).map(user => (
                    <tr key={user.user_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <UserCircle className="w-8 h-8 text-star-30 flex-shrink-0" />
                          <div className="min-w-0">
                            <p className="text-white font-medium truncate max-w-[160px]">{user.full_name || '—'}</p>
                            <p className="text-star-50 text-xs truncate max-w-[160px]">{user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={`px-2 py-0.5 rounded text-2xs font-semibold border ${
                          user.role?.toLowerCase() === 'admin'
                            ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'
                            : 'bg-white/5 text-star-70 border-white/10'
                        }`}>
                          {user.role}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={`flex items-center gap-1.5 text-xs font-medium w-fit ${
                          user.is_active ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${user.is_active ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                          {user.is_active ? 'Active' : 'Suspended'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-star-50 text-xs">
                        {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-1 justify-end flex-wrap">
                          {/* Activity */}
                          <button onClick={() => setActivityUser(user)} title="View Activity"
                            className="p-1.5 rounded-lg border bg-white/5 text-star-70 border-white/10 hover:bg-white/10 hover:text-white transition">
                            <Activity className="w-3.5 h-3.5" />
                          </button>
                          {/* Suspend / Activate */}
                          <button onClick={() => trigger(user, user.is_active ? 'suspend' : 'activate')}
                            disabled={actioning === user.user_id}
                            title={user.is_active ? 'Suspend' : 'Activate'}
                            className={`p-1.5 rounded-lg border transition text-xs ${
                              user.is_active
                                ? 'bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20'
                                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
                            } disabled:opacity-40`}>
                            {user.is_active ? <ShieldOff className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                          </button>
                          {/* Promote / Demote */}
                          {user.role?.toLowerCase() !== 'admin' ? (
                            <button onClick={() => trigger(user, 'promote')} title="Promote to Admin"
                              disabled={actioning === user.user_id}
                              className="p-1.5 rounded-lg border bg-indigo-500/10 text-indigo-400 border-indigo-500/20 hover:bg-indigo-500/20 transition disabled:opacity-40">
                              <ShieldPlus className="w-3.5 h-3.5" />
                            </button>
                          ) : (
                            <button onClick={() => trigger(user, 'demote')} title="Demote to User"
                              disabled={actioning === user.user_id}
                              className="p-1.5 rounded-lg border bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20 transition disabled:opacity-40">
                              <ShieldMinus className="w-3.5 h-3.5" />
                            </button>
                          )}
                          {/* Reset password */}
                          <button onClick={() => trigger(user, 'reset')} title="Reset Password"
                            disabled={actioning === user.user_id}
                            className="p-1.5 rounded-lg border bg-cyan-500/10 text-cyan-400 border-cyan-500/20 hover:bg-cyan-500/20 transition disabled:opacity-40">
                            <KeyRound className="w-3.5 h-3.5" />
                          </button>
                          {/* Delete */}
                          <button onClick={() => trigger(user, 'delete')} title="Delete User"
                            disabled={actioning === user.user_id}
                            className="p-1.5 rounded-lg border bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20 transition disabled:opacity-40">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {payload?.items.length === 0 && (
                    <tr><td colSpan={5} className="px-5 py-10 text-center text-star-50 text-sm">
                      No users found{search ? ` for "${search}"` : ''}.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            {payload && payload.pages > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-white/10">
                <p className="text-xs text-star-50">Page {payload.page} of {payload.pages} · {payload.total} users</p>
                <div className="flex gap-2">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    className="p-1.5 rounded hover:bg-white/5 text-star-50 disabled:opacity-25 transition">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button onClick={() => setPage(p => Math.min(payload.pages, p + 1))} disabled={page === payload.pages}
                    className="p-1.5 rounded hover:bg-white/5 text-star-50 disabled:opacity-25 transition">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </motion.div>
    </div>
  )
}
