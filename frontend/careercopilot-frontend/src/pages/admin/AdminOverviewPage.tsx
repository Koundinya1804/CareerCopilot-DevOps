/**
 * src/pages/admin/AdminOverviewPage.tsx
 *
 * Route: /admin  (index)
 * Data:  GET /api/v1/admin/overview
 *
 * Shows a system-wide snapshot: user counts, agent call health,
 * KB document totals, and estimated LLM cost.
 */

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Users, Activity, BookOpen, DollarSign, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { adminApi } from '@/api'
import { fadeUp, stagger } from '@/utils'

// ── Types ──────────────────────────────────────────────────────────────────

interface OverviewData {
  users: {
    total:     number
    active:    number
    suspended: number
  }
  agent_calls: {
    total:        number
    successful:   number
    failed:       number
    success_rate: number
  }
  knowledge_base: {
    total_documents:  number
    total_categories: number
  }
  cost: {
    total_estimated_usd: number
  }
}

// ── Stat card ──────────────────────────────────────────────────────────────

type AccentColor = 'indigo' | 'cyan' | 'emerald' | 'rose'

const ACCENT: Record<AccentColor, string> = {
  indigo:  'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
  cyan:    'text-cyan-400   bg-cyan-500/10   border-cyan-500/20',
  emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  rose:    'text-rose-400   bg-rose-500/10   border-rose-500/20',
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent,
  index = 0,
}: {
  label:  string
  value:  string | number
  sub?:   string
  icon:   React.ElementType
  accent: AccentColor
  index?: number
}) {
  return (
    <motion.div variants={fadeUp} custom={index} className="glass rounded-2xl p-5">
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs text-star-70 uppercase tracking-wider">{label}</p>
        <span className={`p-2 rounded-lg border ${ACCENT[accent]}`}>
          <Icon className="w-4 h-4" />
        </span>
      </div>
      <p className="text-3xl font-mono font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-star-50 mt-1">{sub}</p>}
    </motion.div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function AdminOverviewPage() {
  const [data,    setData]    = useState<OverviewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    adminApi.getOverview()
      .then(res => setData(res.data?.data ?? res.data))
      .catch(() => setError('Failed to load overview. Check your connection.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-96">
        <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full min-h-96">
        <p className="text-rose-400 text-sm">{error ?? 'No data available.'}</p>
      </div>
    )
  }

  const successPct = data.agent_calls.success_rate

  return (
    <div className="p-6 space-y-6 relative">

      {/* Background glow */}
      <div className="absolute inset-0 bg-hero-radial opacity-30 pointer-events-none" />

      {/* Page header */}
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Overview</h1>
        <p className="text-sm text-star-70 mt-0.5">System health and usage at a glance</p>
      </div>

      {/* Stat grid */}
      <motion.div
        variants={stagger}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 xl:grid-cols-4 gap-4"
      >
        <StatCard
          label="Total Users"
          value={data.users.total.toLocaleString()}
          sub={`${data.users.active} active · ${data.users.suspended} suspended`}
          icon={Users}
          accent="indigo"
          index={0}
        />
        <StatCard
          label="Agent Calls"
          value={data.agent_calls.total.toLocaleString()}
          sub={`${successPct}% success rate`}
          icon={Activity}
          accent="cyan"
          index={1}
        />
        <StatCard
          label="KB Documents"
          value={data.knowledge_base.total_documents.toLocaleString()}
          sub={`Across ${data.knowledge_base.total_categories} categories`}
          icon={BookOpen}
          accent="emerald"
          index={2}
        />
        <StatCard
          label="Est. LLM Cost"
          value={`$${data.cost.total_estimated_usd.toFixed(4)}`}
          sub="Gemini 2.0 Flash"
          icon={DollarSign}
          accent="rose"
          index={3}
        />
      </motion.div>

      {/* Agent call health bar */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={4} className="glass rounded-2xl p-6">
        <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-4">Agent Call Health</h2>
        <div className="flex gap-8 mb-4">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span className="font-mono font-bold text-white">{data.agent_calls.successful.toLocaleString()}</span>
            <span className="text-star-50 text-sm">Successful</span>
          </div>
          <div className="flex items-center gap-2">
            <XCircle className="w-4 h-4 text-rose-400" />
            <span className="font-mono font-bold text-white">{data.agent_calls.failed.toLocaleString()}</span>
            <span className="text-star-50 text-sm">Failed</span>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-2 bg-white/10 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${successPct}%` }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          />
        </div>
        <p className="text-xs text-star-50 mt-1.5">{successPct}% success rate</p>
      </motion.div>
    </div>
  )
}
