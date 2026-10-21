import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Target, Loader2, AlertCircle, CheckCircle, BookOpen, History, X } from 'lucide-react'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { skillGapApi } from '@/api'
import { fadeUp, stagger, cn } from '@/utils'

// Backend AnalyseFromTextRequest: { resume_text, role_key, target_company?, extra_skills? }
// Backend response data shape (from SkillGapService.analyse_from_text):
//   scores.{ overall_match_pct, required_match_pct, gap_severity, estimated_prep_months }
//   missing_required[]  → { name, priority, description, category }
//   missing_optional[]  → { name, priority, description }
//   matched_skills[]    → { name, proficiency, years }
//   learning_priorities[] → { rank, skill, approach, time_weeks, resources[] }
//   executive_summary   → string
//   role_info.{ title, domain, icon }

const ROLES = [
  { key: 'ai_engineer',         label: 'AI Engineer',         icon: '🤖', color: '#5B4FE8' },
  { key: 'ml_engineer',         label: 'ML Engineer',         icon: '🧠', color: '#00D4FF' },
  { key: 'data_scientist',      label: 'Data Scientist',      icon: '📊', color: '#10D97A' },
  { key: 'java_developer',      label: 'Java Developer',      icon: '☕', color: '#F59E0B' },
  { key: 'fullstack_developer', label: 'Full Stack Dev',      icon: '🌐', color: '#A855F7' },
  { key: 'cloud_engineer',      label: 'Cloud Engineer',      icon: '☁️', color: '#F43F5E' },
  { key: 'devops_engineer',     label: 'DevOps Engineer',     icon: '⚙️', color: '#06B6D4' },
  { key: 'backend_developer',   label: 'Backend Developer',   icon: '🔧', color: '#8B5CF6' },
]

function severityColor(sev?: string) {
  if (sev === 'low')      return '#10D97A'
  if (sev === 'moderate') return '#F59E0B'
  if (sev === 'high')     return '#F97316'
  if (sev === 'critical') return '#F43F5E'
  return '#5B4FE8'
}

export default function SkillGapPage() {
  const [role,    setRole]    = useState('')
  const [text,    setText]    = useState('')
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [report,  setReport]  = useState<any>(null)
  const [error,   setError]   = useState('')

  const [history,        setHistory]        = useState<any[]>([])
  const [historyLoading, setHistoryLoading]  = useState(true)
  const [viewingId,      setViewingId]       = useState<number | null>(null)
  const [deletingId,     setDeletingId]      = useState<number | null>(null)

  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    skillGapApi.listReports()
      .then(res => setHistory((res.data?.data ?? res.data)?.reports ?? []))
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  const viewHistoryReport = async (id: number) => {
    setViewingId(id)
    setLoading(true); setError(''); setReport(null)
    try {
      const res = await skillGapApi.getReport(id)
      setReport(res.data?.data ?? res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not load this report.')
    } finally { setLoading(false) }
  }

  const deleteHistoryItem = async (id: number) => {
    if (!confirm('Delete this skill gap report? This cannot be undone.')) return
    setDeletingId(id)
    try {
      await skillGapApi.deleteReport(id)
      if (viewingId === id) { setReport(null); setViewingId(null) }
      loadHistory()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not delete this report.')
    } finally { setDeletingId(null) }
  }

  const analyse = async () => {
    if (!role || !text.trim()) return
    setLoading(true); setError(''); setReport(null); setViewingId(null)
    try {
      // POST /skill-gap/analyse/text
      // Body: { resume_text, role_key, target_company? }
      const res = await skillGapApi.analyseFromText({
        resume_text:    text,
        role_key:       role,
        target_company: company || undefined,
      })
      setReport(res.data?.data ?? res.data)
      loadHistory()
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
        e.response?.data?.error?.message ||
        'Analysis failed. Try again.'
      )
    } finally { setLoading(false) }
  }

  const scores   = report?.scores ?? {}
  const matchPct = scores.overall_match_pct ?? 0
  const sc       = severityColor(scores.gap_severity)

  return (
    <DashboardLayout>
      <div className="p-6 space-y-6">
        <motion.div variants={stagger} initial="hidden" animate="visible">

          <motion.div variants={fadeUp}>
            <h1 className="font-display font-bold text-2xl text-white mb-1">Skill Gap Analyser</h1>
            <p className="text-sm text-star-70">
              Compare your profile against a target role and get a prioritised learning plan.
            </p>
          </motion.div>

          {/* History */}
          {!historyLoading && history.length > 0 && (
            <motion.div variants={fadeUp} className="glass rounded-2xl overflow-hidden mt-6">
              <div className="px-5 py-4 border-b border-white/10 flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-bright" />
                <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
                  Past Reports ({history.length})
                </h2>
              </div>
              <div className="divide-y divide-white/5 max-h-56 overflow-y-auto">
                {history.map((r: any) => (
                  <div key={r.gap_report_id}
                    className={cn('flex items-center gap-3 px-4 py-3 hover:bg-white/3 transition',
                      viewingId === r.gap_report_id && 'bg-indigo-500/10')}>
                    <button onClick={() => viewHistoryReport(r.gap_report_id)} className="flex-1 min-w-0 text-left">
                      <p className="text-sm text-white truncate">{r.role_title}{r.target_company ? ` @ ${r.target_company}` : ''}</p>
                      <p className="text-2xs text-star-50">{new Date(r.created_at).toLocaleDateString()}</p>
                    </button>
                    <span className="text-sm font-mono font-bold flex-shrink-0"
                      style={{ color: severityColor(r.gap_severity) }}>
                      {Math.round(r.overall_match_pct)}%
                    </span>
                    <button
                      onClick={() => deleteHistoryItem(r.gap_report_id)}
                      disabled={deletingId === r.gap_report_id}
                      title="Delete"
                      className="p-1 rounded-lg text-star-50 hover:text-rose-400 hover:bg-rose-500/10 transition disabled:opacity-40 flex-shrink-0"
                    >
                      {deletingId === r.gap_report_id
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <X className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          <div className="grid lg:grid-cols-5 gap-5 mt-6">
            {/* ── Input panel ───────────────────────────────────────────── */}
            <motion.div variants={fadeUp} className="lg:col-span-2 space-y-5">

              {/* Role selector */}
              <div>
                <label className="block text-xs font-semibold text-star-70 mb-2 uppercase tracking-wide">
                  Target Role
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {ROLES.map(({ key, label, icon, color }) => (
                    <button
                      key={key}
                      onClick={() => setRole(key)}
                      className={cn(
                        'flex items-center gap-2 p-3 rounded-xl text-left text-sm transition-all duration-200 border',
                        role === key ? '' : 'border-white/5 hover:border-white/10',
                      )}
                      style={role === key
                        ? { background: `${color}15`, borderColor: `${color}30`, color }
                        : { background: 'rgba(255,255,255,0.02)' }}
                    >
                      <span>{icon}</span>
                      <span className={`text-xs font-medium ${role === key ? '' : 'text-star-70'}`}>{label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Target company */}
              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Target Company (optional)
                </label>
                <input
                  className="input"
                  placeholder="e.g. Google, Swiggy"
                  value={company}
                  onChange={e => setCompany(e.target.value)}
                />
              </div>

              {/* Resume text */}
              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Paste Your Resume
                </label>
                <textarea
                  className="input min-h-[180px] resize-none"
                  placeholder="Paste your resume text here… (minimum 50 characters)"
                  value={text}
                  onChange={e => setText(e.target.value)}
                />
                {text.length > 0 && text.length < 50 && (
                  <p className="text-2xs text-amber-400 mt-1">Need at least 50 characters ({text.length}/50)</p>
                )}
              </div>

              <button
                onClick={analyse}
                disabled={!role || text.trim().length < 50 || loading}
                className="btn-primary w-full py-3.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading
                  ? <><Loader2 className="w-4 h-4 animate-spin" />Analysing…</>
                  : <><Target className="w-4 h-4" />Analyse Skill Gap</>
                }
              </button>

              {error && (
                <div className="flex items-center gap-2 p-3 rounded-xl text-sm text-rose-400 border border-rose-400/20"
                  style={{ background: 'rgba(244,63,94,0.08)' }}>
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
                </div>
              )}
            </motion.div>

            {/* ── Results ───────────────────────────────────────────────── */}
            <div className="lg:col-span-3">
              <AnimatePresence mode="wait">

                {/* Loading */}
                {loading && (
                  <motion.div key="load" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    className="glass rounded-2xl p-12 text-center">
                    <Loader2 className="w-10 h-10 animate-spin mx-auto mb-4 text-indigo-bright" />
                    <p className="font-display font-semibold text-white">Analysing skill gap…</p>
                    <p className="text-sm text-star-70 mt-2">
                      Matching skills · Computing gap scores · Building learning plan
                    </p>
                  </motion.div>
                )}

                {/* Report */}
                {report && !loading && (
                  <motion.div key="result" variants={stagger} initial="hidden" animate="visible" className="space-y-4">

                    {/* Match overview */}
                    <motion.div variants={fadeUp} className="glass rounded-2xl p-6">
                      <div className="flex items-start justify-between mb-4">
                        <div>
                          <p className="text-xs text-star-50 font-mono uppercase tracking-wide">Overall Match</p>
                          <div className="flex items-end gap-2 mt-1">
                            <span className="font-display font-bold text-5xl text-white">
                              {Math.round(matchPct)}
                            </span>
                            <span className="text-xl text-star-50 mb-1">%</span>
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="badge" style={{
                              background: `${sc}15`, borderColor: `${sc}30`, color: sc,
                            }}>
                              {scores.gap_severity ?? 'unknown'} gap
                            </span>
                            {scores.estimated_prep_months != null && (
                              <span className="text-xs text-star-50">
                                ~{scores.estimated_prep_months} months prep
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-star-50 font-mono">Required skills</p>
                          <p className="font-display font-bold text-2xl text-white">
                            {Math.round(scores.required_match_pct ?? 0)}%
                          </p>
                        </div>
                      </div>
                      <div className="progress-bar h-3 mb-1">
                        <motion.div
                          className="progress-fill h-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${matchPct}%` }}
                          transition={{ duration: 0.8, ease: 'easeOut' }}
                          style={{ background: `linear-gradient(90deg,${sc}80,${sc})` }}
                        />
                      </div>
                      <div className="flex justify-between text-2xs text-star-50 mt-1">
                        <span>0%</span><span>50%</span><span>100%</span>
                      </div>
                    </motion.div>

                    {/* Executive summary */}
                    {report.executive_summary && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <p className="text-xs text-star-50 font-mono uppercase tracking-wide mb-2">AI Summary</p>
                        <p className="text-sm text-star-70 leading-relaxed">{report.executive_summary}</p>
                      </motion.div>
                    )}

                    {/* Missing required skills */}
                    {(report.missing_required ?? []).length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-rose-400" />
                          Missing Required Skills ({report.missing_required.length})
                        </h3>
                        <div className="space-y-2">
                          {report.missing_required.slice(0, 8).map((s: any) => (
                            <div key={s.name} className="flex items-center gap-3 p-2.5 rounded-xl"
                              style={{ background: 'rgba(255,255,255,0.02)' }}>
                              <span className={`badge text-2xs ${
                                s.priority === 'critical' ? 'badge-rose' :
                                s.priority === 'high'     ? 'badge-amber' : 'badge-cyan'
                              }`}>
                                {s.priority}
                              </span>
                              <span className="text-sm text-white font-medium">{s.name}</span>
                              {s.description && (
                                <span className="text-xs text-star-50 ml-auto line-clamp-1">{s.description}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* Missing optional skills */}
                    {(report.missing_optional ?? []).length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-amber-400" />
                          Nice-to-have Skills ({report.missing_optional.length})
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {report.missing_optional.slice(0, 10).map((s: any) => (
                            <span key={s.name} className="badge badge-amber text-2xs">{s.name}</span>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* Matched skills */}
                    {(report.matched_skills ?? []).length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <CheckCircle className="w-4 h-4 text-emerald-400" />
                          Matched Skills ({report.matched_skills.length})
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {report.matched_skills.map((s: any) => (
                            <span key={s.name ?? s} className="badge badge-green text-2xs">
                              {s.name ?? s}
                            </span>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* Learning priorities */}
                    {(report.learning_priorities ?? []).length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <BookOpen className="w-4 h-4 text-indigo-bright" />
                          Learning Priorities
                        </h3>
                        <div className="space-y-3">
                          {report.learning_priorities.slice(0, 6).map((p: any) => (
                            <div key={p.rank} className="flex gap-3">
                              <span
                                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5"
                                style={{ background: 'rgba(91,79,232,0.3)' }}
                              >
                                {p.rank}
                              </span>
                              <div>
                                <p className="text-sm font-semibold text-white">{p.skill}</p>
                                <p className="text-xs text-star-50 mt-0.5">
                                  {p.approach}
                                  {p.time_weeks != null && <> · {p.time_weeks}w</>}
                                </p>
                                {(p.resources ?? []).length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1">
                                    {p.resources.slice(0, 2).map((r: string, i: number) => (
                                      <span key={i} className="badge text-2xs opacity-70">{r}</span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </motion.div>
                )}

                {/* Empty state */}
                {!report && !loading && (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    className="glass rounded-2xl p-16 text-center">
                    <Target className="w-12 h-12 mx-auto mb-4 text-star-30" />
                    <p className="font-display font-semibold text-white text-lg mb-2">No gap analysis yet</p>
                    <p className="text-sm text-star-70">
                      Select a target role, paste your resume, and click Analyse.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>
      </div>
    </DashboardLayout>
  )
}
