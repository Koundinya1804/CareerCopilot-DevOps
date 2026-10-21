import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw, Loader2, Database, Cpu, HardDrive, Zap, Server, Activity } from 'lucide-react'
import { adminApi } from '@/api'
import { fadeUp, stagger } from '@/utils'

interface HealthCheck {
  status: 'green' | 'yellow' | 'red'
  message: string
  free_gb?: number
  total_gb?: number
}

interface HealthData {
  overall_status: 'green' | 'yellow' | 'red'
  checks: {
    database:  HealthCheck
    redis:     HealthCheck
    chromadb:  HealthCheck
    groq_api:  HealthCheck
    disk:      HealthCheck
  }
}

const STATUS_STYLES = {
  green:  { dot: 'bg-emerald-400', badge: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', label: 'Healthy' },
  yellow: { dot: 'bg-amber-400',   badge: 'bg-amber-500/10 text-amber-300 border-amber-500/20',       label: 'Degraded' },
  red:    { dot: 'bg-rose-400',    badge: 'bg-rose-500/10 text-rose-300 border-rose-500/20',           label: 'Down' },
}

const SERVICE_META: Record<string, { icon: React.ElementType; label: string }> = {
  database:  { icon: Database, label: 'MySQL Database' },
  redis:     { icon: Server,   label: 'Redis Cache' },
  chromadb:  { icon: HardDrive, label: 'ChromaDB' },
  groq_api:  { icon: Zap,      label: 'Groq API' },
  disk:      { icon: Cpu,      label: 'Disk Storage' },
}

export default function AdminHealthPage() {
  const [data,       setData]       = useState<HealthData | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true)
    try {
      const res = await adminApi.getFullHealth()
      setData(res.data?.data ?? res.data)
      setLastChecked(new Date())
    } finally {
      setLoading(false); setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => load(true), 30_000)
    return () => clearInterval(interval)
  }, [load])

  if (loading) return (
    <div className="flex items-center justify-center h-full min-h-96">
      <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
    </div>
  )

  const overall = data?.overall_status ?? 'red'
  const styles  = STATUS_STYLES[overall]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">System Health</h1>
          {lastChecked && (
            <p className="text-xs text-star-50 mt-0.5">
              Last checked: {lastChecked.toLocaleTimeString()} · auto-refreshes every 30s
            </p>
          )}
        </div>
        <button onClick={() => load(true)} disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2.5 glass rounded-xl text-sm text-star-70 hover:text-white transition border border-white/10 hover:border-white/20 disabled:opacity-40">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Overall status banner */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible"
        className={`flex items-center gap-3 px-5 py-4 rounded-2xl border ${styles.badge}`}>
        <div className={`w-3 h-3 rounded-full ${styles.dot} ${overall === 'green' ? 'animate-pulse' : ''}`} />
        <div>
          <p className="font-semibold text-sm">
            System {overall === 'green' ? 'Operational' : overall === 'yellow' ? 'Partially Degraded' : 'Critical Issues Detected'}
          </p>
          <p className="text-xs opacity-70 mt-0.5">
            {Object.values(data?.checks ?? {}).filter((c: any) => c.status === 'green').length} of {Object.keys(data?.checks ?? {}).length} services healthy
          </p>
        </div>
      </motion.div>

      {/* Service cards */}
      <motion.div variants={stagger} initial="hidden" animate="visible"
        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {Object.entries(data?.checks ?? {}).map(([key, check], i) => {
          const meta     = SERVICE_META[key] ?? { icon: Activity, label: key }
          const Icon     = meta.icon
          const st       = STATUS_STYLES[check.status as keyof typeof STATUS_STYLES] ?? STATUS_STYLES.red
          return (
            <motion.div key={key} variants={fadeUp} custom={i} className="glass rounded-2xl p-5">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-4 h-4 text-star-70" />
                  </div>
                  <p className="text-sm font-semibold text-white">{meta.label}</p>
                </div>
                <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-2xs font-medium border ${st.badge}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                  {st.label}
                </span>
              </div>
              <p className="text-xs text-star-50 leading-relaxed">{check.message}</p>
              {check.free_gb != null && (
                <div className="mt-3">
                  <div className="flex justify-between text-2xs text-star-50 mb-1">
                    <span>Storage used</span>
                    <span className="font-mono">{check.free_gb} GB free of {check.total_gb} GB</span>
                  </div>
                  <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.round(((check.total_gb! - check.free_gb) / check.total_gb!) * 100)}%`,
                        background: check.status === 'green' ? '#10D97A' : check.status === 'yellow' ? '#F59E0B' : '#F43F5E',
                      }} />
                  </div>
                </div>
              )}
            </motion.div>
          )
        })}
      </motion.div>
    </div>
  )
}
