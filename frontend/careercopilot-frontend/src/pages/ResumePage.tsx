import { useState, useCallback, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Zap, Award, TrendingUp, History, GitCompare, X } from 'lucide-react'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { resumeApi } from '@/api'
import { fadeUp, stagger, cn } from '@/utils'
import {
  RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis,
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'

interface ResumeHistoryItem {
  resume_id: number; filename: string; status: string; is_primary: boolean
  ats_score: number | null; page_count: number | null; created_at: string
}

// Backend response shape (from _build_report_response):
// report.scores.{ ats_score, formatting_score, content_score, keyword_score, experience_score, grade, verdict }
// report.technical_skills  → string[]   (non-soft skills by name)
// report.soft_skills       → string[]
// report.improvements      → { priority, category, suggestion }[]
// report.keywords_missing  → string[]
// report.keywords_found    → string[]
// report.summary           → string
// report.strengths         → string[]

function ScoreRing({ value, color }: { value: number; color: string }) {
  return (
    <div className="relative w-36 h-36">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          innerRadius="68%" outerRadius="100%"
          data={[{ value, fill: color }]}
          startAngle={90} endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" cornerRadius={8} background={{ fill: 'rgba(255,255,255,0.05)' }} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display font-bold text-4xl text-white">{Math.round(value)}</span>
        <span className="text-xs text-star-50 font-mono">/100</span>
      </div>
    </div>
  )
}

export default function ResumePage() {
  const [file,    setFile]    = useState<File | null>(null)
  const [role,    setRole]    = useState('')
  const [loading, setLoading] = useState(false)
  const [report,  setReport]  = useState<any>(null)
  const [error,   setError]   = useState('')

  const [history,      setHistory]      = useState<ResumeHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [compareIds,   setCompareIds]   = useState<number[]>([])
  const [compareReports, setCompareReports] = useState<Record<number, any>>({})
  const [viewingHistoryId, setViewingHistoryId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    resumeApi.list()
      .then(res => setHistory((res.data?.data ?? res.data)?.resumes ?? []))
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  const viewHistoryReport = async (resumeId: number) => {
    setViewingHistoryId(resumeId)
    setLoading(true); setError(''); setReport(null)
    try {
      const res = await resumeApi.getReport(resumeId)
      setReport(res.data?.data ?? res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not load this report.')
    } finally { setLoading(false) }
  }

  const deleteHistoryItem = async (resumeId: number) => {
    if (!confirm('Delete this resume analysis? This cannot be undone.')) return
    setDeletingId(resumeId)
    try {
      await resumeApi.delete(resumeId)
      if (viewingHistoryId === resumeId) { setReport(null); setViewingHistoryId(null) }
      setCompareIds(prev => prev.filter(id => id !== resumeId))
      loadHistory()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not delete this resume.')
    } finally {
      setDeletingId(null)
    }
  }

  const toggleCompare = (resumeId: number) => {
    setCompareIds(prev => {
      if (prev.includes(resumeId)) return prev.filter(id => id !== resumeId)
      if (prev.length >= 2) return [prev[1], resumeId]
      return [...prev, resumeId]
    })
  }

  useEffect(() => {
    compareIds.forEach(id => {
      if (!compareReports[id]) {
        resumeApi.getReport(id).then(res => {
          setCompareReports(prev => ({ ...prev, [id]: res.data?.data ?? res.data }))
        }).catch(() => {})
      }
    })
  }, [compareIds, compareReports])

  // Chronological (oldest→newest) trend data for the ATS score line chart
  const trendData = useMemo(() => {
    return [...history]
      .filter(h => h.ats_score != null)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
      .map(h => ({
        label: new Date(h.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        ats_score: Math.round(h.ats_score!),
        filename: h.filename,
      }))
  }, [history])

  const onDrop = useCallback((files: File[]) => { if (files[0]) setFile(files[0]) }, [])
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    },
    maxFiles: 1,
  })

  const analyse = async () => {
    if (!file) return
    setLoading(true); setError(''); setReport(null); setViewingHistoryId(null)
    try {
      // POST /resume/upload-and-analyse (multipart: file + optional target_role)
      const res = await resumeApi.uploadAndAnalyse(file, role || undefined)
      // response: { success, message, data: { scores, technical_skills, improvements, ... } }
      setReport(res.data?.data ?? res.data)
      loadHistory()
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
        e.response?.data?.error?.message ||
        'Analysis failed. Please try again.'
      )
    } finally { setLoading(false) }
  }

  const scoreColor = (s: number) =>
    s >= 80 ? '#10D97A' : s >= 60 ? '#00D4FF' : s >= 40 ? '#F59E0B' : '#F43F5E'

  // Safely read nested scores
  const scores       = report?.scores ?? {}
  const atsScore     = scores.ats_score        ?? 0
  const grade        = scores.grade            ?? '—'
  const verdict      = scores.verdict          ?? ''
  const techSkills   = report?.technical_skills ?? []   // string[]
  const softSkills   = report?.soft_skills      ?? []   // string[]
  const improvements = report?.improvements     ?? []   // { priority, category, suggestion }[]
  const kwMissing    = report?.keywords_missing ?? []   // string[]
  const strengths    = report?.strengths        ?? []   // string[]
  const summary      = report?.summary          ?? ''

  return (
    <DashboardLayout>
      <div className="p-6 space-y-6">
        <motion.div variants={stagger} initial="hidden" animate="visible">
          <motion.div variants={fadeUp}>
            <h1 className="font-display font-bold text-2xl text-white mb-1">Resume Analyser</h1>
            <p className="text-sm text-star-70">
              Upload your resume for ATS scoring, keyword analysis, and improvement suggestions.
            </p>
          </motion.div>

          {/* ── History + ATS Trend + Comparison ─────────────────────────── */}
          {!historyLoading && history.length > 0 && (
            <motion.div variants={fadeUp} className="grid lg:grid-cols-5 gap-5 mt-6">
              {/* History list */}
              <div className="lg:col-span-2 glass rounded-2xl overflow-hidden">
                <div className="px-5 py-4 border-b border-white/10 flex items-center gap-2">
                  <History className="w-4 h-4 text-indigo-bright" />
                  <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
                    Resume History ({history.length})
                  </h2>
                  {compareIds.length > 0 && (
                    <span className="ml-auto text-2xs text-star-50">{compareIds.length}/2 selected</span>
                  )}
                </div>
                <div className="divide-y divide-white/5 max-h-72 overflow-y-auto">
                  {history.map(h => (
                    <div key={h.resume_id}
                      className={cn('flex items-center gap-3 px-4 py-3 hover:bg-white/3 transition',
                        viewingHistoryId === h.resume_id && 'bg-indigo-500/10')}>
                      <input
                        type="checkbox"
                        checked={compareIds.includes(h.resume_id)}
                        onChange={() => toggleCompare(h.resume_id)}
                        className="w-3.5 h-3.5 flex-shrink-0"
                        title="Select for comparison"
                      />
                      <button onClick={() => viewHistoryReport(h.resume_id)} className="flex-1 min-w-0 text-left">
                        <p className="text-sm text-white truncate flex items-center gap-1.5">
                          {h.filename}
                          {h.is_primary && <span className="badge badge-cyan text-2xs flex-shrink-0">Primary</span>}
                        </p>
                        <p className="text-2xs text-star-50">{new Date(h.created_at).toLocaleDateString()}</p>
                      </button>
                      {h.ats_score != null && (
                        <span className="text-sm font-mono font-bold flex-shrink-0"
                          style={{ color: scoreColor(h.ats_score) }}>{Math.round(h.ats_score)}</span>
                      )}
                      <button
                        onClick={() => deleteHistoryItem(h.resume_id)}
                        disabled={deletingId === h.resume_id}
                        title="Delete"
                        className="p-1 rounded-lg text-star-50 hover:text-rose-400 hover:bg-rose-500/10 transition disabled:opacity-40 flex-shrink-0"
                      >
                        {deletingId === h.resume_id
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <X className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* ATS trend chart */}
              <div className="lg:col-span-3 glass rounded-2xl p-5">
                <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-emerald-400" /> ATS Score Trend
                </h2>
                {trendData.length < 2 ? (
                  <p className="text-sm text-star-50 py-14 text-center">Analyse at least 2 resumes to see a trend.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis dataKey="label" stroke="rgba(255,255,255,0.3)" fontSize={10} tickLine={false} />
                      <YAxis domain={[0, 100]} stroke="rgba(255,255,255,0.3)" fontSize={10} tickLine={false} />
                      <Tooltip contentStyle={{ background: '#0a0b14', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }} />
                      <Line type="monotone" dataKey="ats_score" stroke="#5B4FE8" strokeWidth={2} dot={{ r: 3, fill: '#5B4FE8' }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </motion.div>
          )}

          {/* Comparison strip */}
          {compareIds.length === 2 && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
              className="glass rounded-2xl p-5 mt-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider flex items-center gap-2">
                  <GitCompare className="w-4 h-4 text-cyan-400" /> Comparison
                </h2>
                <button onClick={() => setCompareIds([])} className="text-star-50 hover:text-white">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                {compareIds.map(id => {
                  const meta = history.find(h => h.resume_id === id)
                  const rep  = compareReports[id]
                  const s    = rep?.scores
                  return (
                    <div key={id} className="p-4 rounded-xl border border-white/8" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <p className="text-sm text-white font-medium truncate mb-3">{meta?.filename}</p>
                      {!s ? (
                        <div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-star-50" /></div>
                      ) : (
                        <div className="space-y-2">
                          {[
                            ['ATS Score', s.ats_score], ['Formatting', s.formatting_score],
                            ['Content', s.content_score], ['Keywords', s.keyword_score],
                            ['Experience', s.experience_score],
                          ].map(([label, val]) => (
                            <div key={label as string} className="flex items-center justify-between text-xs">
                              <span className="text-star-50">{label}</span>
                              <span className="font-mono font-semibold" style={{ color: scoreColor((val as number) ?? 0) }}>
                                {Math.round((val as number) ?? 0)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </motion.div>
          )}

          <div className="grid lg:grid-cols-5 gap-5 mt-6">
            {/* ── Upload panel ──────────────────────────────────────────── */}
            <motion.div variants={fadeUp} className="lg:col-span-2 space-y-4">
              <div
                {...getRootProps()}
                className={cn(
                  'glass rounded-2xl p-8 text-center cursor-pointer transition-all duration-300 border-2 border-dashed',
                  isDragActive ? 'border-indigo-bright bg-indigo/10' : 'border-white/10 hover:border-indigo/40 hover:bg-white/2',
                  file ? 'border-emerald/40' : '',
                )}
              >
                <input {...getInputProps()} />
                <AnimatePresence mode="wait">
                  {file ? (
                    <motion.div key="file" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
                      <CheckCircle className="w-12 h-12 mx-auto mb-3 text-emerald-400" />
                      <p className="font-semibold text-white text-sm">{file.name}</p>
                      <p className="text-xs text-star-50 mt-1">{(file.size / 1024).toFixed(1)} KB · Ready to analyse</p>
                    </motion.div>
                  ) : (
                    <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
                        style={{ background: 'rgba(91,79,232,0.15)', border: '1px solid rgba(91,79,232,0.25)' }}>
                        <Upload className="w-7 h-7 text-indigo-bright" />
                      </div>
                      <p className="font-semibold text-white text-sm mb-1">
                        {isDragActive ? 'Drop it here!' : 'Drop your resume here'}
                      </p>
                      <p className="text-xs text-star-50">PDF or DOCX · Max 10 MB</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Target Role (optional)
                </label>
                <input
                  className="input"
                  placeholder="e.g. Senior ML Engineer"
                  value={role}
                  onChange={e => setRole(e.target.value)}
                />
              </div>

              <button
                onClick={analyse}
                disabled={!file || loading}
                className="btn-primary w-full py-3.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading
                  ? <><Loader2 className="w-4 h-4 animate-spin" />Analysing…</>
                  : <><Zap className="w-4 h-4" />Analyse Resume</>
                }
              </button>

              {error && (
                <div
                  className="flex items-center gap-2 p-3 rounded-xl text-sm text-rose-400 border border-rose-400/20"
                  style={{ background: 'rgba(244,63,94,0.08)' }}
                >
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
                </div>
              )}
            </motion.div>

            {/* ── Results panel ─────────────────────────────────────────── */}
            <div className="lg:col-span-3">
              <AnimatePresence mode="wait">

                {/* Loading state */}
                {loading && (
                  <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    className="glass rounded-2xl p-12 text-center">
                    <div className="w-16 h-16 rounded-full mx-auto mb-6 flex items-center justify-center"
                      style={{ background: 'rgba(91,79,232,0.15)' }}>
                      <Loader2 className="w-8 h-8 text-indigo-bright animate-spin" />
                    </div>
                    <p className="font-display font-semibold text-white text-lg mb-2">Analysing your resume…</p>
                    <p className="text-sm text-star-70">
                      Extracting skills · Scoring ATS compatibility · Generating feedback
                    </p>
                    <div className="flex justify-center gap-3 mt-6">
                      {['Parsing PDF', 'NLP Extraction', 'ATS Scoring', 'AI Feedback'].map((s, i) => (
                        <motion.div key={s} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.4 }}
                          className="text-2xs text-star-50 font-mono">• {s}
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {/* Report */}
                {report && !loading && (
                  <motion.div key="report" variants={stagger} initial="hidden" animate="visible" className="space-y-4">

                    {/* Score hero */}
                    <motion.div variants={fadeUp} className="glass rounded-2xl p-6 flex items-center gap-8">
                      <ScoreRing value={atsScore} color={scoreColor(atsScore)} />
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="font-display font-bold text-5xl text-white">{grade}</span>
                          <div className="ml-2">
                            <p className="font-display font-semibold text-white text-lg">ATS Score</p>
                            <p className="text-sm text-star-70 mt-0.5">{verdict}</p>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3 mt-4">
                          {[
                            ['Formatting',  scores.formatting_score],
                            ['Content',     scores.content_score],
                            ['Keywords',    scores.keyword_score],
                            ['Experience',  scores.experience_score],
                          ].map(([label, val]) => (
                            <div key={label as string}>
                              <div className="flex justify-between text-2xs text-star-50 mb-1">
                                <span>{label}</span>
                                <span className="font-mono">{Math.round((val as number) ?? 0)}</span>
                              </div>
                              <div className="progress-bar">
                                <div className="progress-fill"
                                  style={{ width: `${val ?? 0}%`, background: scoreColor((val as number) ?? 0) }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </motion.div>

                    {/* AI Summary */}
                    {summary && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <p className="text-xs text-star-50 font-mono uppercase tracking-wide mb-2">AI Summary</p>
                        <p className="text-sm text-star-70 leading-relaxed">{summary}</p>
                      </motion.div>
                    )}

                    {/* Technical skills found */}
                    {techSkills.length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <Award className="w-4 h-4 text-emerald-400" />
                          Technical Skills ({techSkills.length})
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {techSkills.slice(0, 20).map((s: string) => (
                            <span key={s} className="badge badge-green text-2xs">{s}</span>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* Soft skills */}
                    {softSkills.length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <Award className="w-4 h-4 text-cyan-400" />
                          Soft Skills ({softSkills.length})
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {softSkills.slice(0, 10).map((s: string) => (
                            <span key={s} className="badge badge-cyan text-2xs">{s}</span>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* Strengths */}
                    {strengths.length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <CheckCircle className="w-4 h-4 text-emerald-400" />
                          Strengths
                        </h3>
                        <ul className="space-y-1.5">
                          {strengths.slice(0, 5).map((s: string, i: number) => (
                            <li key={i} className="flex items-start gap-2 text-sm text-star-70">
                              <span className="text-emerald-400 flex-shrink-0 mt-0.5">•</span>{s}
                            </li>
                          ))}
                        </ul>
                      </motion.div>
                    )}

                    {/* Missing keywords */}
                    {kwMissing.length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-amber-400" />
                          Missing Keywords ({kwMissing.length})
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {kwMissing.map((k: string) => (
                            <span key={k} className="badge badge-amber text-2xs">{k}</span>
                          ))}
                        </div>
                      </motion.div>
                    )}

                    {/* Improvement suggestions */}
                    {improvements.length > 0 && (
                      <motion.div variants={fadeUp} className="glass rounded-2xl p-5">
                        <h3 className="font-display font-semibold text-white text-sm mb-3 flex items-center gap-2">
                          <TrendingUp className="w-4 h-4 text-indigo-bright" />
                          Improvement Suggestions
                        </h3>
                        <div className="space-y-3">
                          {improvements.slice(0, 5).map((imp: any, i: number) => (
                            <div key={i} className="p-3 rounded-xl border border-white/5"
                              style={{ background: 'rgba(255,255,255,0.02)' }}>
                              <div className="flex items-center gap-2 mb-1">
                                <span className={`badge text-2xs ${
                                  imp.priority === 'high'   ? 'badge-rose'  :
                                  imp.priority === 'medium' ? 'badge-amber' : 'badge-green'
                                }`}>
                                  {imp.priority}
                                </span>
                                <span className="text-xs font-semibold text-white capitalize">
                                  {imp.category}
                                </span>
                              </div>
                              <p className="text-xs text-star-50 leading-relaxed">{imp.suggestion}</p>
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
                    <FileText className="w-12 h-12 mx-auto mb-4 text-star-30" />
                    <p className="font-display font-semibold text-white text-lg mb-2">No analysis yet</p>
                    <p className="text-sm text-star-70">Upload your resume and click Analyse to get started.</p>
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
