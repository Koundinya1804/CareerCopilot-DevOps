import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, Loader2, Send, ChevronRight, Award, AlertCircle, CheckCircle, RotateCcw, History } from 'lucide-react'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { interviewApi } from '@/api'
import { fadeUp, stagger, gradeColor } from '@/utils'

// Backend schemas:
// StartSessionRequest: { mode, difficulty, target_role?, target_company?, total_questions, resume_id? }
// Response data.session_id → number (integer PK)
// Response data.current_question → { question_number, question_text, question_type, difficulty, follow_up_hint? }
// Response data.total_questions → number
//
// SubmitAnswerRequest: { question_number, answer_text, time_taken_seconds? }
// Response data → { evaluation: { scores: { overall, confidence, technical, communication, relevance, completeness },
//                                 star_breakdown, strengths, weaknesses },
//                   model_answer, improved_answer, session_complete,
//                   progress: { answered, total } }
//
// CompleteSession response → { scores: { overall, grade, technical, confidence, communication, relevance },
//                              verdict, executive_summary, improvement_tips: [{ area, action, timeline }] }

const MODES = [
  { key: 'hr',               label: 'HR Interview',     icon: '👔', color: '#5B4FE8', desc: 'Behavioural + motivation' },
  { key: 'technical',        label: 'Technical',         icon: '💻', color: '#00D4FF', desc: 'DS&A, system design, CS' },
  { key: 'company_specific', label: 'Company-Specific',  icon: '🏢', color: '#10D97A', desc: 'Tailored to company style' },
]
const DIFFICULTIES = [
  { key: 'easy',   label: 'Easy',   color: '#10D97A' },
  { key: 'medium', label: 'Medium', color: '#F59E0B' },
  { key: 'hard',   label: 'Hard',   color: '#F43F5E' },
]
const COMPANIES = ['google', 'amazon', 'microsoft', 'tcs', 'infosys', 'wipro', 'flipkart', 'swiggy']

export default function InterviewPage() {
  const [step,       setStep]       = useState<'setup' | 'session' | 'report'>('setup')
  const [mode,       setMode]       = useState('hr')
  const [diff,       setDiff]       = useState('medium')
  const [role,       setRole]       = useState('')
  const [company,    setCompany]    = useState('')
  const [qCount,     setQCount]     = useState(5)
  const [loading,    setLoading]    = useState(false)

  // session_id is number (int PK from backend)
  const [sessionId,  setSessionId]  = useState<number | null>(null)
  const [totalQ,     setTotalQ]     = useState(5)
  const [curQ,       setCurQ]       = useState<any>(null)
  const [answer,     setAnswer]     = useState('')
  const [evaluation, setEvaluation] = useState<any>(null)
  const [answered,   setAnswered]   = useState(0)
  const [report,     setReport]     = useState<any>(null)
  const [error,      setError]      = useState('')

  const [history,        setHistory]        = useState<any[]>([])
  const [historyLoading, setHistoryLoading]  = useState(true)
  const [viewingId,      setViewingId]       = useState<number | null>(null)

  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    interviewApi.listSessions()
      .then(res => setHistory((res.data?.data ?? res.data)?.sessions ?? []))
      .finally(() => setHistoryLoading(false))
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  const viewPastReport = async (sessionId: number) => {
    setViewingId(sessionId)
    setLoading(true); setError('')
    try {
      const res = await interviewApi.getReport(sessionId)
      setReport(res.data?.data ?? res.data)
      setStep('report')
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Could not load this report.')
    } finally { setLoading(false) }
  }

  // ── Start ────────────────────────────────────────────────────────────────

  const startSession = async () => {
    setLoading(true); setError('')
    try {
      const res  = await interviewApi.startSession({
        mode,
        difficulty:      diff,
        target_role:     role    || undefined,
        target_company:  company || undefined,
        total_questions: qCount,
      })
      const data = res.data?.data ?? res.data
      // data.session_id is an integer
      setSessionId(data.session_id)
      setTotalQ(data.total_questions ?? qCount)
      setCurQ(data.current_question)
      setAnswered(0)
      setStep('session')
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
        e.response?.data?.error?.message ||
        'Failed to start session. Please try again.'
      )
    } finally { setLoading(false) }
  }

  // ── Submit answer ─────────────────────────────────────────────────────────

  const submitAnswer = async () => {
    if (!answer.trim() || !curQ || sessionId === null) return
    setLoading(true); setError('')
    try {
      const res  = await interviewApi.submitAnswer(sessionId, {
        question_number:    curQ.question_number,
        answer_text:        answer,
        time_taken_seconds: 60,
      })
      const data = res.data?.data ?? res.data

      setEvaluation(data)
      setAnswered(data.progress?.answered ?? answered + 1)

      // If this was the last question, complete the session immediately
      if (data.session_complete) {
        await completeSession()
      }
      // Otherwise wait for user to click "Next Question"
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
        e.response?.data?.error?.message ||
        'Failed to evaluate answer. Please try again.'
      )
    } finally { setLoading(false) }
  }

  // ── Next question ─────────────────────────────────────────────────────────
  // Called when user clicks "Next Question" after seeing evaluation.
  // Clears evaluation first, then fetches next question.

  const goToNextQuestion = async () => {
    if (sessionId === null) return
    setLoading(true); setEvaluation(null); setAnswer('')
    try {
      const res  = await interviewApi.getCurrentQuestion(sessionId)
      const data = res.data?.data ?? res.data
      setCurQ(data.current_question ?? data)
    } catch (e: any) {
      setError('Failed to load next question.')
    } finally { setLoading(false) }
  }

  // ── Complete session ──────────────────────────────────────────────────────

  const completeSession = async () => {
    if (sessionId === null) return
    try {
      const res  = await interviewApi.completeSession(sessionId)
      const data = res.data?.data ?? res.data
      setReport(data)
      setStep('report')
      loadHistory()
    } catch (e: any) {
      setError('Failed to generate report.')
    }
  }

  // ── Reset ─────────────────────────────────────────────────────────────────

  const reset = () => {
    setStep('setup'); setSessionId(null); setCurQ(null)
    setEvaluation(null); setReport(null); setAnswered(0); setAnswer(''); setViewingId(null)
  }

  const scoreColor = (s: number) =>
    s >= 80 ? '#10D97A' : s >= 60 ? '#00D4FF' : s >= 40 ? '#F59E0B' : '#F43F5E'

  const progressPct = totalQ > 0 ? (answered / totalQ) * 100 : 0

  return (
    <DashboardLayout>
      <div className="p-6">
        <motion.div variants={stagger} initial="hidden" animate="visible">
          <motion.div variants={fadeUp} className="mb-6">
            <h1 className="font-display font-bold text-2xl text-white mb-1">Interview Coach</h1>
            <p className="text-sm text-star-70">AI-powered mock interviews with real-time evaluation and model answers.</p>
          </motion.div>

          <AnimatePresence mode="wait">

            {/* ── SETUP ─────────────────────────────────────────────────── */}
            {step === 'setup' && (
              <motion.div key="setup" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }} className="max-w-2xl space-y-5">
                <div className="glass rounded-2xl p-6 space-y-5">

                  {/* Mode */}
                  <div>
                    <label className="block text-xs font-semibold text-star-70 mb-2 uppercase tracking-wide">
                      Interview Mode
                    </label>
                    <div className="grid grid-cols-3 gap-3">
                      {MODES.map(({ key, label, icon, color, desc }) => (
                        <button key={key} onClick={() => setMode(key)}
                          className="p-3 rounded-xl text-left border transition-all duration-200"
                          style={mode === key
                            ? { background: `${color}15`, borderColor: `${color}30` }
                            : { background: 'rgba(255,255,255,0.02)', borderColor: 'rgba(255,255,255,0.06)' }}>
                          <div className="text-xl mb-1">{icon}</div>
                          <div className="text-xs font-semibold" style={mode === key ? { color } : { color: '#E8E9F5' }}>
                            {label}
                          </div>
                          <div className="text-2xs text-star-50 mt-0.5">{desc}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Difficulty */}
                  <div>
                    <label className="block text-xs font-semibold text-star-70 mb-2 uppercase tracking-wide">
                      Difficulty
                    </label>
                    <div className="flex gap-3">
                      {DIFFICULTIES.map(({ key, label, color }) => (
                        <button key={key} onClick={() => setDiff(key)}
                          className="flex-1 py-2.5 rounded-xl text-sm font-semibold border transition-all duration-200"
                          style={diff === key
                            ? { background: `${color}15`, borderColor: `${color}30`, color }
                            : { background: 'rgba(255,255,255,0.02)', borderColor: 'rgba(255,255,255,0.06)', color: '#9FA3C2' }}>
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Role + Question count */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                        Target Role
                      </label>
                      <input className="input" placeholder="e.g. ML Engineer"
                        value={role} onChange={e => setRole(e.target.value)} />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                        Questions
                      </label>
                      <select className="input" value={qCount} onChange={e => setQCount(Number(e.target.value))}>
                        {[3, 5, 7, 10].map(n => <option key={n} value={n}>{n} questions</option>)}
                      </select>
                    </div>
                  </div>

                  {/* Company (company_specific mode only) */}
                  {mode === 'company_specific' && (
                    <div>
                      <label className="block text-xs font-semibold text-star-70 mb-2 uppercase tracking-wide">
                        Company
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {COMPANIES.map(c => (
                          <button key={c} onClick={() => setCompany(c === company ? '' : c)}
                            className="px-3 py-1.5 rounded-lg text-xs font-medium capitalize border transition-all"
                            style={company === c
                              ? { background: 'rgba(16,217,122,0.1)', borderColor: 'rgba(16,217,122,0.4)', color: '#10D97A' }
                              : { background: 'rgba(255,255,255,0.02)', borderColor: 'rgba(255,255,255,0.08)', color: '#9FA3C2' }}>
                            {c}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {error && (
                    <div className="flex items-center gap-2 p-3 rounded-xl text-sm text-rose-400 border border-rose-400/20"
                      style={{ background: 'rgba(244,63,94,0.08)' }}>
                      <AlertCircle className="w-4 h-4" />{error}
                    </div>
                  )}

                  <button onClick={startSession} disabled={loading}
                    className="btn-primary w-full py-3.5 disabled:opacity-50">
                    {loading
                      ? <><Loader2 className="w-4 h-4 animate-spin" />Starting…</>
                      : <><Mic className="w-4 h-4" />Start Interview</>
                    }
                  </button>
                </div>

                {/* Interview History */}
                {!historyLoading && history.length > 0 && (
                  <div className="glass rounded-2xl overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/10 flex items-center gap-2">
                      <History className="w-4 h-4 text-indigo-bright" />
                      <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
                        Interview History ({history.length})
                      </h2>
                    </div>
                    <div className="divide-y divide-white/5 max-h-72 overflow-y-auto">
                      {history.map((s: any) => (
                        <button
                          key={s.session_id}
                          onClick={() => s.overall_score != null && viewPastReport(s.session_id)}
                          disabled={s.overall_score == null || (loading && viewingId === s.session_id)}
                          className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/3 transition text-left disabled:cursor-default"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-white truncate capitalize">
                              {s.mode?.replace('_', ' ')} · {s.target_role || 'General'}
                            </p>
                            <p className="text-2xs text-star-50">
                              {s.questions_answered}/{s.total_questions} answered ·{' '}
                              {s.started_at ? new Date(s.started_at).toLocaleDateString() : ''}
                              {s.status !== 'completed' && ` · ${s.status}`}
                            </p>
                          </div>
                          {s.overall_score != null ? (
                            <span className="text-sm font-mono font-bold flex-shrink-0" style={{ color: gradeColor(s.grade?.[0]) }}>
                              {Math.round(s.overall_score)}
                            </span>
                          ) : (
                            <span className="text-2xs text-star-30 flex-shrink-0">In progress</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </motion.div>
            )}

            {/* ── SESSION ───────────────────────────────────────────────── */}
            {step === 'session' && (
              <motion.div key="session" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}>

                {/* Progress bar */}
                <div className="glass rounded-xl p-4 mb-5 flex items-center gap-4">
                  <div className="flex-1">
                    <div className="flex justify-between text-xs text-star-50 mb-1.5">
                      <span>Progress</span>
                      <span className="font-mono">{answered}/{totalQ}</span>
                    </div>
                    <div className="progress-bar">
                      <motion.div className="progress-fill" initial={{ width: 0 }}
                        animate={{ width: `${progressPct}%` }} transition={{ duration: 0.5 }} />
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xs text-star-50 font-mono uppercase">{mode.replace('_', ' ')}</div>
                    <div className="text-xs text-white font-semibold capitalize">{diff}</div>
                  </div>
                </div>

                <div className="grid lg:grid-cols-5 gap-5">
                  <div className="lg:col-span-3 space-y-4">

                    {/* Current question — shown when no pending evaluation */}
                    {curQ && !evaluation && (
                      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                        className="glass rounded-2xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                          <span className="badge">Q{curQ.question_number}</span>
                          <span className="badge badge-cyan capitalize">
                            {(curQ.question_type ?? '').replace('_', ' ')}
                          </span>
                          {curQ.difficulty && (
                            <span className="badge badge-amber capitalize">{curQ.difficulty}</span>
                          )}
                        </div>
                        <p className="font-display font-semibold text-white text-lg leading-snug mb-6">
                          {curQ.question_text}
                        </p>
                        {curQ.follow_up_hint && (
                          <div className="p-3 rounded-xl text-xs text-star-50 mb-5"
                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                            💡 Interviewer may follow up: {curQ.follow_up_hint}
                          </div>
                        )}
                        <textarea
                          className="input min-h-[160px] resize-none mb-4"
                          placeholder="Type your answer here… Use the STAR method for behavioural questions."
                          value={answer}
                          onChange={e => setAnswer(e.target.value)}
                        />
                        {error && (
                          <div className="flex items-center gap-2 p-3 mb-3 rounded-xl text-sm text-rose-400
                            border border-rose-400/20" style={{ background: 'rgba(244,63,94,0.08)' }}>
                            <AlertCircle className="w-4 h-4" />{error}
                          </div>
                        )}
                        <button onClick={submitAnswer} disabled={!answer.trim() || loading}
                          className="btn-primary w-full py-3.5 disabled:opacity-50">
                          {loading
                            ? <><Loader2 className="w-4 h-4 animate-spin" />Evaluating…</>
                            : <><Send className="w-4 h-4" />Submit Answer</>
                          }
                        </button>
                      </motion.div>
                    )}

                    {/* Evaluation result — shown after submitting, before next question */}
                    {evaluation && !report && (
                      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                        className="space-y-4">
                        <div className="glass rounded-2xl p-6">
                          <div className="flex items-center gap-3 mb-4">
                            <CheckCircle className="w-5 h-5 text-emerald-400" />
                            <h3 className="font-display font-semibold text-white">Answer Evaluated</h3>
                          </div>

                          {/* Score grid */}
                          <div className="grid grid-cols-2 gap-3 mb-5">
                            {([
                              ['Overall',        evaluation.evaluation?.scores?.overall],
                              ['Confidence',     evaluation.evaluation?.scores?.confidence],
                              ['Technical',      evaluation.evaluation?.scores?.technical],
                              ['Communication',  evaluation.evaluation?.scores?.communication],
                            ] as [string, number][]).map(([l, v]) => (
                              <div key={l} className="p-3 rounded-xl text-center"
                                style={{ background: 'rgba(255,255,255,0.03)' }}>
                                <div className="font-display font-bold text-2xl"
                                  style={{ color: scoreColor(Number(v ?? 0)) }}>
                                  {Math.round(Number(v ?? 0))}
                                </div>
                                <div className="text-2xs text-star-50 font-mono mt-0.5">{l}</div>
                              </div>
                            ))}
                          </div>

                          {/* Strengths */}
                          {(evaluation.evaluation?.strengths ?? []).length > 0 && (
                            <div className="mb-3">
                              <p className="text-xs font-semibold text-emerald-400 mb-1">Strengths</p>
                              <ul className="space-y-1">
                                {evaluation.evaluation.strengths.slice(0, 3).map((s: string, i: number) => (
                                  <li key={i} className="text-xs text-star-70 flex gap-1.5">
                                    <span className="text-emerald-400 flex-shrink-0">•</span>{s}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Weaknesses */}
                          {(evaluation.evaluation?.weaknesses ?? []).length > 0 && (
                            <div className="mb-4">
                              <p className="text-xs font-semibold text-amber-400 mb-1">Areas to Improve</p>
                              <ul className="space-y-1">
                                {evaluation.evaluation.weaknesses.slice(0, 3).map((w: string, i: number) => (
                                  <li key={i} className="text-xs text-star-70 flex gap-1.5">
                                    <span className="text-amber-400 flex-shrink-0">•</span>{w}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Model answer */}
                          {evaluation.model_answer && (
                            <div className="p-4 rounded-xl mb-4"
                              style={{ background: 'rgba(91,79,232,0.08)', border: '1px solid rgba(91,79,232,0.2)' }}>
                              <p className="text-xs font-semibold text-indigo-bright mb-2">Model Answer</p>
                              <p className="text-sm text-star-70 leading-relaxed">{evaluation.model_answer}</p>
                            </div>
                          )}

                          {/* Next question button */}
                          {!evaluation.session_complete && (
                            <button
                              onClick={goToNextQuestion}
                              disabled={loading}
                              className="btn-secondary w-full py-3 disabled:opacity-50"
                            >
                              {loading
                                ? <><Loader2 className="w-4 h-4 animate-spin" />Loading…</>
                                : <>Next Question <ChevronRight className="w-4 h-4" /></>
                              }
                            </button>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </div>

                  {/* Tips panel */}
                  <div className="lg:col-span-2">
                    <div className="glass rounded-2xl p-5">
                      <h3 className="font-display font-semibold text-white text-sm mb-4">Interview Tips</h3>
                      <div className="space-y-3 text-xs text-star-70">
                        {[
                          'Use the STAR method for behavioural answers (Situation, Task, Action, Result)',
                          'Quantify your impact with numbers and percentages whenever possible',
                          'Think aloud — show your reasoning process, not just the final answer',
                          'Ask clarifying questions before attempting system design problems',
                          "End every answer by connecting it back to the role you're interviewing for",
                        ].map((tip, i) => (
                          <div key={i} className="flex gap-2">
                            <span className="text-indigo-bright flex-shrink-0">•</span>{tip}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* ── REPORT ────────────────────────────────────────────────── */}
            {step === 'report' && report && (
              <motion.div key="report" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                className="max-w-3xl space-y-5">

                {/* Grade hero */}
                <div className="glass rounded-2xl p-8 text-center">
                  <Award className="w-16 h-16 mx-auto mb-4" style={{ color: gradeColor(report.scores?.grade) }} />
                  <div className="font-display font-bold text-7xl mb-2"
                    style={{ color: gradeColor(report.scores?.grade) }}>
                    {report.scores?.grade}
                  </div>
                  <p className="text-xl font-display font-semibold text-white mb-1">
                    Overall Score: {Math.round(report.scores?.overall ?? 0)}/100
                  </p>
                  <p className="text-sm text-star-70 mb-6">{report.verdict}</p>

                  <div className="grid grid-cols-4 gap-4">
                    {([
                      ['Technical',     report.scores?.technical,     '#00D4FF'],
                      ['Confidence',    report.scores?.confidence,    '#5B4FE8'],
                      ['Communication', report.scores?.communication, '#10D97A'],
                      ['Relevance',     report.scores?.relevance,     '#A855F7'],
                    ] as [string, number, string][]).map(([l, v, c]) => (
                      <div key={l} className="p-3 rounded-xl" style={{ background: `${c}10` }}>
                        <div className="font-display font-bold text-2xl" style={{ color: c }}>
                          {Math.round(v ?? 0)}
                        </div>
                        <div className="text-2xs text-star-50 mt-0.5">{l}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Coach's assessment */}
                {report.executive_summary && (
                  <div className="glass rounded-2xl p-6">
                    <h3 className="font-display font-semibold text-white text-sm mb-3">Coach's Assessment</h3>
                    <p className="text-sm text-star-70 leading-relaxed">{report.executive_summary}</p>
                  </div>
                )}

                {/* Improvement plan */}
                {(report.improvement_tips ?? []).length > 0 && (
                  <div className="glass rounded-2xl p-6">
                    <h3 className="font-display font-semibold text-white text-sm mb-4">Improvement Plan</h3>
                    <div className="space-y-3">
                      {report.improvement_tips.slice(0, 5).map((t: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl border border-white/5"
                          style={{ background: 'rgba(255,255,255,0.02)' }}>
                          <p className="text-xs font-semibold text-indigo-bright mb-0.5">{t.area}</p>
                          <p className="text-xs text-star-70">
                            {t.action}
                            {t.timeline && <span className="text-star-50"> · {t.timeline}</span>}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <button onClick={reset} className="btn-primary w-full py-3.5">
                  <RotateCcw className="w-4 h-4" /> Start New Interview
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </DashboardLayout>
  )
}
