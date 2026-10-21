import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Loader2, ChevronLeft, ChevronRight, Search, RefreshCw } from 'lucide-react'
import { adminApi } from '@/api'
import { fadeUp } from '@/utils'

interface LogRow {
  log_id: number; level: string; source: string
  message: string; user_id: number; latency_ms: number | null; created_at: string | null
}
interface LogsData {
  total: number; page: number; page_size: number; total_pages: number; logs: LogRow[]
}

const LEVEL_STYLE: Record<string, string> = {
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  failed:  'bg-rose-500/10 text-rose-400 border-rose-500/20',
  timeout: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
}

const AGENT_LABELS: Record<string, string> = {
  resume_analyser: 'Resume', skill_gap: 'Skill Gap',
  career_recommendation: 'Career', interview_coach: 'Interview',
  rag_chain: 'RAG', supervisor: 'Supervisor',
}

export default function AdminLogsPage() {
  const [data,        setData]        = useState<LogsData | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [page,        setPage]        = useState(1)
  const [levelFilter, setLevelFilter] = useState('')
  const [search,      setSearch]      = useState('')
  const [searchInput, setSearchInput] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    adminApi.getLogs({ page, page_size: 25, level: levelFilter || undefined, search: search || undefined })
      .then(res => setData(res.data?.data ?? res.data))
      .finally(() => setLoading(false))
  }, [page, levelFilter, search])

  useEffect(() => { load() }, [load])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">Agent Logs</h1>
          <p className="text-sm text-star-70 mt-0.5">
            {data ? `${data.total.toLocaleString()} total entries` : 'All agent invocation records'}
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2.5 glass rounded-xl text-sm text-star-70 hover:text-white transition border border-white/10">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-star-50" />
          <input type="text" placeholder="Search errors…" value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && (setPage(1), setSearch(searchInput.trim()))}
            className="input pl-8 text-sm w-52" />
        </div>
        <select value={levelFilter} onChange={e => { setPage(1); setLevelFilter(e.target.value) }}
          className="input text-sm pr-8">
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="timeout">Timeout</option>
        </select>
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
                    <th className="px-4 py-3 text-left">Agent</th>
                    <th className="px-4 py-3 text-left">Status</th>
                    <th className="px-4 py-3 text-left">Message</th>
                    <th className="px-4 py-3 text-right">User</th>
                    <th className="px-4 py-3 text-right">Latency</th>
                    <th className="px-4 py-3 text-right">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.logs ?? []).map(log => (
                    <tr key={log.log_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                      <td className="px-4 py-3 text-star-70 text-xs font-mono">
                        {AGENT_LABELS[log.source] ?? log.source}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-2xs font-medium border ${LEVEL_STYLE[log.level] ?? 'bg-white/5 text-star-50 border-white/10'}`}>
                          {log.level}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-star-50 text-xs max-w-xs truncate">{log.message}</td>
                      <td className="px-4 py-3 text-right text-star-50 text-xs font-mono">#{log.user_id}</td>
                      <td className="px-4 py-3 text-right text-star-50 text-xs font-mono">
                        {log.latency_ms != null ? `${Math.round(log.latency_ms)} ms` : '—'}
                      </td>
                      <td className="px-4 py-3 text-right text-star-30 text-xs whitespace-nowrap">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                  {data?.logs.length === 0 && (
                    <tr><td colSpan={6} className="px-4 py-10 text-center text-star-50 text-sm">No logs found.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {data && data.total_pages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-white/10">
                <p className="text-xs text-star-50">{data.total.toLocaleString()} entries · page {data.page} of {data.total_pages}</p>
                <div className="flex gap-2">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    className="p-1.5 rounded hover:bg-white/5 text-star-50 disabled:opacity-25 transition">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button onClick={() => setPage(p => Math.min(data.total_pages, p + 1))} disabled={page === data.total_pages}
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
