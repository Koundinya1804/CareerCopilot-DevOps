import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Loader2, Save, CheckCircle, AlertCircle } from 'lucide-react'
import { adminApi } from '@/api'
import { fadeUp } from '@/utils'

interface SettingsData {
  llm:    { default_provider: string; default_model: string; groq_model: string; gemini_model: string }
  rag:    { embedding_model: string; chunk_size: number; chunk_overlap: number; top_k: number; score_threshold: number; max_context_tokens: number }
  limits: { rate_limit_per_minute: number; rate_limit_agent_per_minute: number; max_resume_size_mb: number }
}

function Field({ label, value, onChange, type = 'text', step }: {
  label: string; value: string | number; onChange: (v: string) => void; type?: string; step?: string
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">{label}</label>
      <input type={type} step={step} value={value} onChange={e => onChange(e.target.value)}
        className="input w-full" />
    </div>
  )
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [saving,   setSaving]   = useState(false)
  const [banner,   setBanner]   = useState<{ ok: boolean; msg: string } | null>(null)

  // Editable fields
  const [chunkSize,    setChunkSize]    = useState('')
  const [chunkOverlap, setChunkOverlap] = useState('')
  const [topK,         setTopK]         = useState('')
  const [threshold,    setThreshold]    = useState('')
  const [rateLimit,    setRateLimit]    = useState('')
  const [agentLimit,   setAgentLimit]   = useState('')
  const [resumeLimit,  setResumeLimit]  = useState('')

  useEffect(() => {
    adminApi.getSettings()
      .then(res => {
        const d: SettingsData = res.data?.data ?? res.data
        setSettings(d)
        setChunkSize(String(d.rag.chunk_size))
        setChunkOverlap(String(d.rag.chunk_overlap))
        setTopK(String(d.rag.top_k))
        setThreshold(String(d.rag.score_threshold))
        setRateLimit(String(d.limits.rate_limit_per_minute))
        setAgentLimit(String(d.limits.rate_limit_agent_per_minute))
        setResumeLimit(String(d.limits.max_resume_size_mb))
      })
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await adminApi.updateSettings({
        chunk_size:             parseInt(chunkSize),
        chunk_overlap:          parseInt(chunkOverlap),
        rag_top_k:              parseInt(topK),
        rag_score_threshold:    parseFloat(threshold),
        rate_limit_per_minute:  parseInt(rateLimit),
        max_resume_size_mb:     parseInt(resumeLimit),
      })
      setBanner({ ok: true, msg: 'Settings saved for this process. Restart required for permanent persistence via .env.' })
    } catch (e: any) {
      setBanner({ ok: false, msg: e.response?.data?.detail ?? 'Save failed.' })
    } finally {
      setSaving(false)
      setTimeout(() => setBanner(null), 5000)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-full min-h-96">
      <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
    </div>
  )

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-display font-bold text-white">Settings</h1>
        <p className="text-sm text-star-70 mt-0.5">Runtime-configurable parameters (process-lifetime only — edit .env for persistence)</p>
      </div>

      {banner && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className={`flex items-start gap-2 px-4 py-3 rounded-xl text-sm border ${
            banner.ok ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                      : 'bg-rose-500/10 text-rose-300 border-rose-500/20'
          }`}>
          {banner.ok ? <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
          {banner.msg}
        </motion.div>
      )}

      {/* LLM info (read-only) */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" className="glass rounded-2xl p-6">
        <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-4">LLM Provider (read-only — set via .env)</h2>
        <div className="grid grid-cols-2 gap-4">
          {[
            ['Provider',    settings?.llm.default_provider],
            ['Model',       settings?.llm.default_model],
            ['Groq Model',  settings?.llm.groq_model],
            ['Gemini Model',settings?.llm.gemini_model],
          ].map(([label, val]) => (
            <div key={label as string}>
              <p className="text-2xs text-star-50 uppercase tracking-wide mb-1">{label}</p>
              <p className="text-sm font-mono text-white">{val as string}</p>
            </div>
          ))}
        </div>
      </motion.div>

      {/* RAG settings */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={1} className="glass rounded-2xl p-6 space-y-4">
        <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-2">RAG Pipeline</h2>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Chunk Size (tokens)" value={chunkSize} onChange={setChunkSize} type="number" />
          <Field label="Chunk Overlap (tokens)" value={chunkOverlap} onChange={setChunkOverlap} type="number" />
          <Field label="Top-K Retrieval" value={topK} onChange={setTopK} type="number" />
          <Field label="Score Threshold (0–1)" value={threshold} onChange={setThreshold} type="number" step="0.01" />
        </div>
        <div>
          <p className="text-2xs text-star-50 uppercase tracking-wide mb-1">Embedding Model (read-only)</p>
          <p className="text-sm font-mono text-white">{settings?.rag.embedding_model}</p>
        </div>
      </motion.div>

      {/* Limits */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={2} className="glass rounded-2xl p-6 space-y-4">
        <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-2">Rate & Upload Limits</h2>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Rate Limit (req/min)" value={rateLimit} onChange={setRateLimit} type="number" />
          <Field label="Agent Rate Limit (req/min)" value={agentLimit} onChange={setAgentLimit} type="number" />
          <Field label="Max Resume Size (MB)" value={resumeLimit} onChange={setResumeLimit} type="number" />
        </div>
      </motion.div>

      <div className="flex justify-end">
        <button onClick={save} disabled={saving}
          className="btn-primary flex items-center gap-2 px-6 py-3 disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving…' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}
