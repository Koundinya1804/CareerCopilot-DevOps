import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { TrendingUp, Loader2, AlertCircle, Plus, X, ArrowRight, History } from 'lucide-react'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { careerApi } from '@/api'
import { fadeUp, stagger } from '@/utils'
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from 'recharts'

// Backend RecommendFromProfileRequest:
//   { skills: string[], interests: string[], years_experience: number,
//     education_level: string, resume_text?: string }
//
// Backend response data (from CareerRecommendationService):
//   career_narrative      → string
//   domain_fit            → { [domain: string]: number }
//   recommended_roles[]   → { rank, role_key, role_title, role_icon, domain,
//                              suitability_score, suitability_label, why_suited,
//                              skill_match_pct, gap_count, salary_journey }
//   action_plan           → { immediate_wins, week_1_2, month_1, month_3 }
//   total_roles_scored    → number

const EDU_LEVELS = ['Bachelors', 'Masters', 'PhD', 'Diploma']

const INTEREST_SUGGESTIONS = [
  'machine learning', 'web development', 'cloud infrastructure', 'data analysis',
  'product management', 'cybersecurity', 'mobile apps', 'open source',
  'startups', 'fintech', 'ai research', 'devops',
]

export default function CareerPage() {
  const [skills,      setSkills]      = useState<string[]>([])
  const [interests,   setInterests]   = useState<string[]>([])
  const [years,       setYears]       = useState(2)
  const [edu,         setEdu]         = useState('Bachelors')
  const [resumeText,  setResumeText]  = useState('')
  const [skillInput,  setSkillInput]  = useState('')
  const [loading,     setLoading]     = useState(false)
  const [report,      setReport]      = useState<any>(null)
  const [error,       setError]       = useState('')

  const [history,        setHistory]        = useState<any[]>([])
  const [historyLoading, setHistoryLoading]  = useState(true)
  const [viewingId,      setViewingId]       = useState<number | null>(null)
  const [deletingId,     setDeletingId]      = useState<number | null>(null)

  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    careerApi.listReports()
      .then(res => setHistory((res.data?.data ?? res.data)?.reports ?? []))
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  const viewHistoryReport = async (id: number) => {
    setViewingId(id)
    setLoading(true); setError(''); setReport(null)
    try {
      const res = await careerApi.getReport(id)
      setReport(res.data?.data ?? res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not load this report.')
    } finally { setLoading(false) }
  }

  const deleteHistoryItem = async (id: number) => {
    if (!confirm('Delete this career recommendation? This cannot be undone.')) return
    setDeletingId(id)
    try {
      await careerApi.deleteReport(id)
      if (viewingId === id) { setReport(null); setViewingId(null) }
      loadHistory()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not delete this report.')
    } finally { setDeletingId(null) }
  }

  const addSkill = () => {
    const s = skillInput.trim()
    if (s && !skills.includes(s)) { setSkills([...skills, s]); setSkillInput('') }
  }
  const removeSkill    = (s: string) => setSkills(skills.filter(x => x !== s))
  const toggleInterest = (i: string) =>
    setInterests(interests.includes(i) ? interests.filter(x => x !== i) : [...interests, i])

  const recommend = async () => {
    if (skills.length === 0) { setError('Add at least one skill.'); return }
    setLoading(true); setError(''); setReport(null); setViewingId(null)
    try {
      // POST /career/recommend/profile
      // Body: { skills, interests, years_experience, education_level, resume_text? }
      const res = await careerApi.recommend({
        skills,
        interests,
        years_experience: years,
        education_level:  edu,
        resume_text:      resumeText || undefined,
      })
      setReport(res.data?.data ?? res.data)
      loadHistory()
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
        e.response?.data?.error?.message ||
        'Recommendation failed. Please try again.'
      )
    } finally { setLoading(false) }
  }

  const domainData = report
    ? Object.entries(report.domain_fit ?? {}).map(([d, v]) => ({
        domain: d.replace('/', '/\n'),
        score:  Math.round(Number(v)),
      }))
    : []

  const scoreColor = (s: number) =>
    s >= 75 ? '#10D97A' : s >= 55 ? '#00D4FF' : s >= 40 ? '#F59E0B' : '#F43F5E'

  return (
    <DashboardLayout>
      <div className="p-6 space-y-6">
        <motion.div variants={stagger} initial="hidden" animate="visible">
          <motion.div variants={fadeUp}>
            <h1 className="font-display font-bold text-2xl text-white mb-1">Career Recommendations</h1>
            <p className="text-sm text-star-70">
              Discover which of 20 career roles best match your skills and interests.
            </p>
          </motion.div>

          {/* History */}
          {!historyLoading && history.length > 0 && (
            <motion.div variants={fadeUp} className="glass rounded-2xl overflow-hidden mt-6">
              <div className="px-5 py-4 border-b border-white/10 flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-bright" />
                <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
                  Past Recommendations ({history.length})
                </h2>
              </div>
              <div className="divide-y divide-white/5 max-h-56 overflow-y-auto">
                {history.map((r: any) => (
                  <div key={r.report_id}
                    className={`flex items-center gap-3 px-4 py-3 hover:bg-white/3 transition ${viewingId === r.report_id ? 'bg-indigo-500/10' : ''}`}>
                    <button onClick={() => viewHistoryReport(r.report_id)} className="flex-1 min-w-0 text-left">
                      <p className="text-sm text-white truncate">{r.top_recommended_role}</p>
                      <p className="text-2xs text-star-50">
                        {r.best_domain ? `${r.best_domain} · ` : ''}{new Date(r.created_at).toLocaleDateString()}
                      </p>
                    </button>
                    <span className="text-sm font-mono font-bold flex-shrink-0" style={{ color: scoreColor(r.top_role_score) }}>
                      {Math.round(r.top_role_score)}%
                    </span>
                    <button
                      onClick={() => deleteHistoryItem(r.report_id)}
                      disabled={deletingId === r.report_id}
                      title="Delete"
                      className="p-1 rounded-lg text-star-50 hover:text-rose-400 hover:bg-rose-500/10 transition disabled:opacity-40 flex-shrink-0"
                    >
                      {deletingId === r.report_id
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

              {/* Skills */}
              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Your Skills
                </label>
                <div className="flex gap-2 mb-2">
                  <input
                    className="input flex-1"
                    placeholder="e.g. Python"
                    value={skillInput}
                    onChange={e => setSkillInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addSkill()}
                  />
                  <button onClick={addSkill} className="btn-primary px-3 py-2">
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5 min-h-[36px]">
                  {skills.map(s => (
                    <span key={s} className="badge gap-1">
                      {s}
                      <button onClick={() => removeSkill(s)} className="hover:text-white transition-colors">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                  {skills.length === 0 && (
                    <span className="text-xs text-star-30">Add skills above…</span>
                  )}
                </div>
              </div>

              {/* Interests */}
              <div>
                <label className="block text-xs font-semibold text-star-70 mb-2 uppercase tracking-wide">
                  Interests
                </label>
                <div className="flex flex-wrap gap-2">
                  {INTEREST_SUGGESTIONS.map(i => (
                    <button
                      key={i}
                      onClick={() => toggleInterest(i)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                        interests.includes(i)
                          ? 'border-indigo/40 text-indigo-bright'
                          : 'border-white/8 text-star-70 hover:border-white/20'
                      }`}
                      style={interests.includes(i)
                        ? { background: 'rgba(91,79,232,0.12)' }
                        : { background: 'rgba(255,255,255,0.02)' }}
                    >
                      {i}
                    </button>
                  ))}
                </div>
              </div>

              {/* Years + Education */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                    Experience (yrs)
                  </label>
                  <input
                    type="number"
                    className="input"
                    min={0} max={30}
                    value={years}
                    onChange={e => setYears(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                    Education
                  </label>
                  <select className="input" value={edu} onChange={e => setEdu(e.target.value)}>
                    {EDU_LEVELS.map(l => <option key={l}>{l}</option>)}
                  </select>
                </div>
              </div>

              {/* Optional resume text */}
              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Resume Text (optional)
                </label>
                <textarea
                  className="input min-h-[80px] resize-none text-xs"
                  placeholder="Paste resume for richer analysis…"
                  value={resumeText}
                  onChange={e => setResumeText(e.target.value)}
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 p-3 rounded-xl text-sm text-rose-400 border border-rose-400/20"
                  style={{ background: 'rgba(244,63,94,0.08)' }}>
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
                </div>
              )}

              <button
                onClick={recommend}
                disabled={loading || skills.length === 0}
                className="btn-primary w-full py-3.5 disabled:opacity-50"
              >
                {loading
                  ? <><Loader2 className="w-4 h-4 animate-spin" />Analysing…</>
                  : <><TrendingUp className="w-4 h-4" />Get Recommendations</>
                }
              </button>
            </motion.div>

            {/* ── Results ───────────────────────────────────────────────── */}
            <div className="lg:col-span-3">
              <AnimatePresence mode="wait">

                {/* Loading */}
                {loading && (
                  <motion.div key="load" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    className="glass rounded-2xl p-12 text-center">
                    <Loader2 className="w-10 h-10 animate-spin mx-auto mb-4 text-indigo-bright" />
                    <p className="font-display font-semibold text-white">Scoring 20 career roles…</p>
                    <p className="text-sm text-star-70 mt-2">Multi-signal algorithm · Gemini AI narrative</p>
                  </motion.div>
                )}

                {/* Report */}
                {report && !loading && (
                  <motion.div key="result" variants={stagger} initial="hidden" animate="visible" className="space-y-4">

                    {/* Career narrative */}
                    {report.career_narrative && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5"
                        style={{ border: '1px solid rgba(91,79,232,0.2)', background: 'rgba(91,79,232,0.06)' }}>
                        <p className="text-xs text-indigo-bright font-mono uppercase tracking-wide mb-2">
                          AI Career Narrative
                        </p>
                        <p className="text-sm text-star-70 leading-relaxed">{report.career_narrative}</p>
                      </motion.div>
                    )}

                    {/* Domain radar */}
                    {domainData.length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-4">
                          Domain Fit Overview
                        </h3>
                        <ResponsiveContainer width="100%" height={200}>
                          <RadarChart data={domainData}>
                            <PolarGrid stroke="rgba(255,255,255,0.08)" />
                            <PolarAngleAxis dataKey="domain" tick={{ fill: '#636685', fontSize: 10 }} />
                            <Radar name="Score" dataKey="score" stroke="#5B4FE8" fill="#5B4FE8"
                              fillOpacity={0.25} strokeWidth={2} />
                          </RadarChart>
                        </ResponsiveContainer>
                      </motion.div>
                    )}

                    {/* Top recommended roles */}
                    {(report.recommended_roles ?? []).length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-4">
                          Top Recommended Roles
                        </h3>
                        <div className="space-y-3">
                          {report.recommended_roles.map((r: any) => (
                            <div key={r.role_key}
                              className="p-4 rounded-xl border border-white/5 hover:border-white/10 transition-all"
                              style={{ background: 'rgba(255,255,255,0.02)' }}>
                              <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-3">
                                  <span className="text-2xl">{r.role_icon ?? '🎯'}</span>
                                  <div>
                                    <p className="font-display font-semibold text-white text-sm">
                                      #{r.rank} {r.role_title}
                                    </p>
                                    <p className="text-2xs text-star-50">{r.domain}</p>
                                  </div>
                                </div>
                                <div className="text-right">
                                  <div className="font-display font-bold text-2xl"
                                    style={{ color: scoreColor(r.suitability_score) }}>
                                    {Math.round(r.suitability_score)}%
                                  </div>
                                  <div className="text-2xs font-mono"
                                    style={{ color: scoreColor(r.suitability_score) }}>
                                    {r.suitability_label}
                                  </div>
                                </div>
                              </div>
                              <div className="progress-bar mb-2">
                                <motion.div className="progress-fill"
                                  initial={{ width: 0 }}
                                  animate={{ width: `${r.suitability_score}%` }}
                                  transition={{ duration: 0.6, delay: 0.1 }}
                                  style={{ background: `linear-gradient(90deg,${scoreColor(r.suitability_score)}60,${scoreColor(r.suitability_score)})` }}
                                />
                              </div>
                              {r.why_suited && (
                                <p className="text-xs text-star-70 mt-2 leading-relaxed line-clamp-2">
                                  {r.why_suited}
                                </p>
                              )}
                              {r.salary_journey && (
                                <div className="flex gap-3 mt-3 text-2xs text-star-50">
                                  <span>
                                    Fresher: <span className="text-white">{r.salary_journey.fresher_inr}</span>
                                  </span>
                                  <span>•</span>
                                  <span>
                                    Senior: <span className="text-white">{r.salary_journey.senior_inr}</span>
                                  </span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* 90-day action plan */}
                    {report.action_plan?.week_1_2 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-4">
                          90-Day Action Plan
                        </h3>
                        <div className="space-y-3">
                          {([
                            ['This Week',  report.action_plan.immediate_wins ?? [], '#10D97A'],
                            ['Weeks 1–2',  report.action_plan.week_1_2       ?? [], '#00D4FF'],
                            ['Month 1',    report.action_plan.month_1        ?? [], '#5B4FE8'],
                            ['Month 3',    report.action_plan.month_3        ?? [], '#A855F7'],
                          ] as [string, string[], string][]).map(([period, actions, color]) => (
                            <div key={period} className="flex gap-3">
                              <div className="w-20 flex-shrink-0">
                                <span className="text-2xs font-mono" style={{ color }}>{period}</span>
                              </div>
                              <ul className="flex-1 space-y-1">
                                {actions.map((a, i) => (
                                  <li key={i} className="text-xs text-star-70 flex items-start gap-1.5">
                                    <ArrowRight className="w-3 h-3 flex-shrink-0 mt-0.5" style={{ color }} />
                                    {a}
                                  </li>
                                ))}
                              </ul>
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
                    <TrendingUp className="w-12 h-12 mx-auto mb-4 text-star-30" />
                    <p className="font-display font-semibold text-white text-lg mb-2">
                      No recommendations yet
                    </p>
                    <p className="text-sm text-star-70">
                      Add your skills, select interests, and click Get Recommendations.
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
