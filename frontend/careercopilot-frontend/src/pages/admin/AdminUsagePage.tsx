/**
 * src/pages/admin/AdminUsagePage.tsx
 *
 * Route: /admin/usage
 * Data:
 *   GET /api/v1/admin/agent-usage/summary
 *   GET /api/v1/admin/agent-usage/by-agent
 *   GET /api/v1/admin/agent-usage/daily?days=30
 *   GET /api/v1/admin/agent-usage/top-users?limit=10
 *   GET /api/v1/admin/agent-usage/logs?page&page_size&agent_name&status
 */

import { useEffect, useState, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Zap,
  TrendingUp,
  TrendingDown,
  Clock,
  DollarSign,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Hash,
  FileStack,
} from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, BarChart as ReBarChart, Bar,
  PieChart, Pie, Cell, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { adminApi } from '@/api'
import { fadeUp, stagger, cn } from '@/utils'

// ── Types ──────────────────────────────────────────────────────────────────

interface Summary {
  total_calls:      number
  successful_calls: number
  failed_calls:     number
  success_rate:     number
  avg_latency_ms:   number
  total_cost_usd:   number
  total_input_tokens?:  number
  total_output_tokens?: number
  total_tokens?:        number
  avg_input_tokens?:    number
  avg_output_tokens?:   number
}

interface AgentRow {
  agent_name:       string
  total_calls:      number
  successful_calls: number
  failed_calls:     number
  success_rate:     number
  avg_latency_ms:   number
  total_cost_usd:   number
}

interface DailyRow {
  date:             string
  total_calls:      number
  successful_calls: number
  failed_calls:     number
}

type Period = 'daily' | 'weekly' | 'monthly'

// Normalized shape used by the chart regardless of period —
// `label` is date / week_start / month depending on period.
interface VolumeRow {
  label:            string
  total_calls:      number
  successful_calls: number
  failed_calls:     number
}

interface MostUploadedDoc {
  category: string
  label:    string
  document_count: number
}

interface TopUser {
  user_id:         number
  email:           string
  full_name:       string
  total_calls:     number
  total_cost_usd:  number
}

interface LogRow {
  log_id:             number
  user_id:            number
  agent_name:         string
  status:             string
  latency_ms:         number | null
  input_tokens:       number | null
  output_tokens:      number | null
  estimated_cost_usd: number | null
  error_message:      string | null
  created_at:         string | null
}

interface LogsData {
  total:       number
  page:        number
  page_size:   number
  total_pages: number
  logs:        LogRow[]
}

// ── Helpers ────────────────────────────────────────────────────────────────

const AGENT_LABELS: Record<string, string> = {
  resume_analyser:       'Resume Analyser',
  skill_gap:             'Skill Gap',
  career_recommendation: 'Career Rec.',
  interview_coach:       'Interview Coach',
  rag_chain:             'RAG Chain',
  supervisor:            'Supervisor',
  unknown:               'Unknown',
}

function agentLabel(key: string) {
  return AGENT_LABELS[key] ?? key
}

const PIE_COLORS = ['#5B4FE8', '#00D4FF', '#F59E0B', '#10B981', '#F43F5E', '#8B5CF6', '#EC4899']

function statusBadge(s: string) {
  const cls: Record<string, string> = {
    success: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
    failed:  'bg-rose-500/15    text-rose-400    border-rose-500/20',
    timeout: 'bg-amber-500/15   text-amber-400   border-amber-500/20',
  }
  return (
    <span className={cn('px-2 py-0.5 rounded text-2xs font-medium border', cls[s] ?? 'bg-white/10 text-star-70 border-white/10')}>
      {s}
    </span>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function AdminUsagePage() {
  const [summary,   setSummary]   = useState<Summary | null>(null)
  const [byAgent,   setByAgent]   = useState<AgentRow[]>([])
  const [period,    setPeriod]    = useState<Period>('daily')
  const [volume,    setVolume]    = useState<VolumeRow[]>([])
  const [volumeLoading, setVolumeLoading] = useState(false)
  const [topUsers,  setTopUsers]  = useState<TopUser[]>([])
  const [mostUploaded, setMostUploaded] = useState<MostUploadedDoc[]>([])
  const [logs,      setLogs]      = useState<LogsData | null>(null)
  const [logsPage,  setLogsPage]  = useState(1)
  const [loading,   setLoading]   = useState(true)
  const [logsLoading, setLogsLoading] = useState(false)

  // Initial data load (period-independent)
  useEffect(() => {
    Promise.all([
      adminApi.getAgentSummary(),
      adminApi.getAgentByType(),
      adminApi.getTopUsers(10),
      adminApi.getMostUploadedDocuments(),
    ]).then(([s, b, t, m]) => {
      setSummary(s.data?.data ?? s.data)
      setByAgent((b.data?.data ?? b.data)?.by_agent ?? [])
      setTopUsers((t.data?.data ?? t.data)?.top_users ?? [])
      setMostUploaded(((m.data?.data ?? m.data)?.categories ?? []).slice(0, 5))
    }).finally(() => setLoading(false))
  }, [])

  // Volume — reload whenever the period toggle changes
  useEffect(() => {
    setVolumeLoading(true)
    const fetcher = period === 'daily'   ? adminApi.getAgentDaily(30)
                   : period === 'weekly' ? adminApi.getAgentWeekly(12)
                   : adminApi.getAgentMonthly(12)

    fetcher.then(res => {
      const data = res.data?.data ?? res.data
      const rows: VolumeRow[] = period === 'daily'
        ? (data?.daily   ?? []).map((r: DailyRow) => ({ label: r.date,       total_calls: r.total_calls, successful_calls: r.successful_calls, failed_calls: r.failed_calls }))
        : period === 'weekly'
        ? (data?.weekly  ?? []).map((r: any)      => ({ label: r.week_start, total_calls: r.total_calls, successful_calls: r.successful_calls, failed_calls: r.failed_calls }))
        : (data?.monthly ?? []).map((r: any)      => ({ label: r.month,      total_calls: r.total_calls, successful_calls: r.successful_calls, failed_calls: r.failed_calls }))
      setVolume(rows)
    }).finally(() => setVolumeLoading(false))
  }, [period])

  // Trend: sum of the most recent half of the loaded window vs the previous half
  const trend = useMemo(() => {
    if (volume.length < 2) return null
    const mid = Math.floor(volume.length / 2)
    const prev = volume.slice(0, mid).reduce((s, r) => s + r.total_calls, 0)
    const curr = volume.slice(mid).reduce((s, r) => s + r.total_calls, 0)
    if (prev === 0) return null
    return Math.round(((curr - prev) / prev) * 100)
  }, [volume])

  // Pie chart data — call distribution across AI modules ("most used module")
  const pieData = useMemo(
    () => byAgent.map(a => ({ name: agentLabel(a.agent_name), value: a.total_calls })),
    [byAgent]
  )

  // Logs — reload on page change
  const loadLogs = useCallback(() => {
    setLogsLoading(true)
    adminApi.getAgentLogs({ page: logsPage, page_size: 15 })
      .then(res => setLogs(res.data?.data ?? res.data))
      .finally(() => setLogsLoading(false))
  }, [logsPage])

  useEffect(() => { loadLogs() }, [loadLogs])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-96">
        <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Agent Usage</h1>
        <p className="text-sm text-star-70 mt-0.5">Analytics across all AI agents</p>
      </div>

      {/* Summary strip */}
      {summary && (
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-2 xl:grid-cols-4 gap-4"
        >
          {[
            { label: 'Total Calls',  value: summary.total_calls.toLocaleString(),             icon: Zap,        color: 'text-indigo-400',
              trend: trend != null ? trend : undefined },
            { label: 'Success Rate', value: `${summary.success_rate}%`,                       icon: TrendingUp, color: 'text-emerald-400' },
            { label: 'Avg Latency',  value: `${Math.round(summary.avg_latency_ms)} ms`,       icon: Clock,      color: 'text-cyan-400' },
            { label: 'Est. Groq Cost', value: `$${summary.total_cost_usd.toFixed(4)}`,        icon: DollarSign, color: 'text-rose-400' },
          ].map(({ label, value, icon: Icon, color, trend: t }, i) => (
            <motion.div key={label} variants={fadeUp} custom={i} className="glass rounded-2xl p-5">
              <div className="flex items-center justify-between mb-2">
                <p className="text-2xs text-star-50 uppercase tracking-widest">{label}</p>
                <Icon className={cn('w-4 h-4', color)} />
              </div>
              <div className="flex items-end justify-between">
                <p className="text-2xl font-mono font-bold text-white">{value}</p>
                {t != null && (
                  <span className={cn('flex items-center gap-0.5 text-2xs font-mono mb-1',
                    t >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                    {t >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {Math.abs(t)}%
                  </span>
                )}
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Token stats strip */}
      {summary && (
        <motion.div variants={stagger} initial="hidden" animate="visible" className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {[
            { label: 'Total Input Tokens',  value: (summary.total_input_tokens ?? 0).toLocaleString() },
            { label: 'Total Output Tokens', value: (summary.total_output_tokens ?? 0).toLocaleString() },
            { label: 'Avg Tokens / Call',   value: Math.round((summary.avg_input_tokens ?? 0) + (summary.avg_output_tokens ?? 0)).toLocaleString() },
            { label: 'Total Tokens',        value: (summary.total_tokens ?? 0).toLocaleString() },
          ].map(({ label, value }, i) => (
            <motion.div key={label} variants={fadeUp} custom={i} className="glass rounded-xl px-4 py-3 flex items-center gap-3">
              <Hash className="w-3.5 h-3.5 text-star-30 flex-shrink-0" />
              <div>
                <p className="text-2xs text-star-50">{label}</p>
                <p className="text-sm font-mono font-semibold text-white">{value}</p>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Volume chart with period toggle + module distribution pie */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={4} className="glass rounded-2xl p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
              Call Volume
            </h2>
            <div className="flex gap-1 bg-white/5 rounded-lg p-0.5">
              {(['daily', 'weekly', 'monthly'] as Period[]).map(p => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={cn(
                    'px-3 py-1 rounded-md text-2xs font-medium capitalize transition',
                    period === p ? 'bg-indigo-500/30 text-white' : 'text-star-50 hover:text-white'
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          {volumeLoading ? (
            <div className="flex items-center justify-center h-56"><Loader2 className="w-5 h-5 text-indigo-400 animate-spin" /></div>
          ) : volume.length === 0 ? (
            <p className="text-sm text-star-50 py-16 text-center">No data for this period.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={volume}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="label" stroke="rgba(255,255,255,0.3)" fontSize={10} tickLine={false} />
                <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#0a0b14', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="total_calls" name="Total" stroke="#5B4FE8" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="successful_calls" name="Successful" stroke="#00D4FF" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="failed_calls" name="Failed" stroke="#F43F5E" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={5} className="glass rounded-2xl p-6">
          <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-2">
            Most Used Module
          </h2>
          {pieData.length === 0 ? (
            <p className="text-sm text-star-50 py-16 text-center">No agent activity yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>
                  {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#0a0b14', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 justify-center">
            {pieData.map((d, i) => (
              <span key={d.name} className="flex items-center gap-1 text-2xs text-star-50">
                <span className="w-2 h-2 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                {d.name}
              </span>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Volume bar chart (calls, successful/failed stacked) */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={4} className="glass rounded-2xl p-6">
        <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-4">
          Success / Failure Breakdown — {period}
        </h2>
        {volume.length === 0 ? (
          <p className="text-sm text-star-50 py-4 text-center">No data for this period.</p>
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <ReBarChart data={volume}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="label" stroke="rgba(255,255,255,0.3)" fontSize={10} tickLine={false} />
              <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} tickLine={false} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#0a0b14', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="successful_calls" name="Successful" stackId="a" fill="#10B981" radius={[0, 0, 0, 0]} />
              <Bar dataKey="failed_calls" name="Failed" stackId="a" fill="#F43F5E" radius={[3, 3, 0, 0]} />
            </ReBarChart>
          </ResponsiveContainer>
        )}
      </motion.div>

      {/* Most uploaded documents */}
      {mostUploaded.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={4} className="glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <FileStack className="w-4 h-4 text-cyan-400" />
            <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
              Most Uploaded Documents (by KB category)
            </h2>
          </div>
          <div className="space-y-2">
            {mostUploaded.map(d => {
              const max = Math.max(...mostUploaded.map(m => m.document_count), 1)
              return (
                <div key={d.category} className="flex items-center gap-3">
                  <span className="text-xs text-star-70 w-40 truncate flex-shrink-0">{d.label}</span>
                  <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400"
                      style={{ width: `${(d.document_count / max) * 100}%` }} />
                  </div>
                  <span className="text-xs font-mono text-star-50 w-8 text-right flex-shrink-0">{d.document_count}</span>
                </div>
              )
            })}
          </div>
        </motion.div>
      )}

      {/* Per-agent table */}
      {byAgent.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={5} className="glass rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-white/10">
            <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">By Agent Type</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-2xs text-star-50 uppercase tracking-widest border-b border-white/5">
                  <th className="px-5 py-3 text-left">Agent</th>
                  <th className="px-5 py-3 text-right">Calls</th>
                  <th className="px-5 py-3 text-right">Success %</th>
                  <th className="px-5 py-3 text-right">Avg ms</th>
                  <th className="px-5 py-3 text-right">Cost USD</th>
                </tr>
              </thead>
              <tbody>
                {byAgent.map(row => (
                  <tr key={row.agent_name} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                    <td className="px-5 py-3 text-white font-medium">{agentLabel(row.agent_name)}</td>
                    <td className="px-5 py-3 text-right font-mono text-star-70">{row.total_calls.toLocaleString()}</td>
                    <td className="px-5 py-3 text-right">
                      <span className={cn(
                        'font-mono text-sm',
                        row.success_rate >= 90 ? 'text-emerald-400'
                          : row.success_rate >= 70 ? 'text-amber-400'
                          : 'text-rose-400',
                      )}>
                        {row.success_rate}%
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right text-star-50 font-mono text-xs">
                      {row.avg_latency_ms != null ? Math.round(row.avg_latency_ms) : '—'}
                    </td>
                    <td className="px-5 py-3 text-right text-star-50 font-mono text-xs">
                      ${row.total_cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      {/* Top users */}
      {topUsers.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={6} className="glass rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-white/10">
            <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">Top Users by Usage</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-2xs text-star-50 uppercase tracking-widest border-b border-white/5">
                <th className="px-5 py-3 text-left">#</th>
                <th className="px-5 py-3 text-left">User</th>
                <th className="px-5 py-3 text-right">Calls</th>
                <th className="px-5 py-3 text-right">Cost USD</th>
              </tr>
            </thead>
            <tbody>
              {topUsers.map((u, i) => (
                <tr key={u.user_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                  <td className="px-5 py-3 text-star-30 font-mono text-xs">{i + 1}</td>
                  <td className="px-5 py-3">
                    <p className="text-white text-sm">{u.full_name || '—'}</p>
                    <p className="text-star-50 text-xs">{u.email}</p>
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-star-70">{u.total_calls.toLocaleString()}</td>
                  <td className="px-5 py-3 text-right text-star-50 font-mono text-xs">${u.total_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}

      {/* Recent logs */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={7} className="glass rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-white/10">
          <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">Recent Agent Logs</h2>
        </div>

        {logsLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-2xs text-star-50 uppercase tracking-widest border-b border-white/5">
                    <th className="px-5 py-3 text-left">Agent</th>
                    <th className="px-5 py-3 text-left">Status</th>
                    <th className="px-5 py-3 text-right">Latency</th>
                    <th className="px-5 py-3 text-right">Tokens</th>
                    <th className="px-5 py-3 text-right">Cost</th>
                    <th className="px-5 py-3 text-right">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {(logs?.logs ?? []).map(log => (
                    <tr key={log.log_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                      <td className="px-5 py-3 text-star-70 text-xs font-mono">{agentLabel(log.agent_name)}</td>
                      <td className="px-5 py-3">{statusBadge(log.status)}</td>
                      <td className="px-5 py-3 text-right text-star-50 font-mono text-xs">
                        {log.latency_ms != null ? `${Math.round(log.latency_ms)} ms` : '—'}
                      </td>
                      <td className="px-5 py-3 text-right text-star-50 font-mono text-xs">
                        {(log.input_tokens != null || log.output_tokens != null)
                          ? `${(log.input_tokens ?? 0) + (log.output_tokens ?? 0)}`
                          : '—'}
                      </td>
                      <td className="px-5 py-3 text-right text-star-50 font-mono text-xs">
                        {log.estimated_cost_usd != null ? `$${log.estimated_cost_usd.toFixed(5)}` : '—'}
                      </td>
                      <td className="px-5 py-3 text-right text-star-30 text-xs whitespace-nowrap">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}

                  {logs?.logs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center text-star-50 text-sm">
                        No agent logs yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Logs pagination */}
            {logs && logs.total_pages > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-white/10">
                <p className="text-xs text-star-50">
                  {logs.total.toLocaleString()} logs · page {logs.page} of {logs.total_pages}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setLogsPage(p => Math.max(1, p - 1))}
                    disabled={logsPage === 1}
                    className="p-1.5 rounded hover:bg-white/5 text-star-50 disabled:opacity-25 transition"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setLogsPage(p => Math.min(logs.total_pages, p + 1))}
                    disabled={logsPage === logs.total_pages}
                    className="p-1.5 rounded hover:bg-white/5 text-star-50 disabled:opacity-25 transition"
                  >
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
