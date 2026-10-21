import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { FileText, Target, TrendingUp, Mic, ArrowRight, Zap, Brain, Loader2 } from 'lucide-react'
import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from 'recharts'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { useAuthStore } from '@/store/authStore'
import { resumeApi, skillGapApi, careerApi, interviewApi } from '@/api'
import { fadeUp, stagger } from '@/utils'

const QUICK_ACTIONS = [
  { icon:Brain,      label:'Ask AI Anything',  sub:'Chat with multi-agent system', to:'/chat',      color:'#5B4FE8' },
  { icon:FileText,   label:'Analyse Resume',    sub:'Upload & get ATS score',       to:'/resume',    color:'#00D4FF' },
  { icon:Target,     label:'Skill Gap Check',   sub:'Find missing skills',          to:'/skill-gap', color:'#10D97A' },
  { icon:Mic,        label:'Mock Interview',    sub:'Company-specific prep',        to:'/interview', color:'#F59E0B' },
]

interface StatCardData {
  label: string; value: number | null; unit: string; grade: string | null
  color: string; icon: typeof FileText; path: string; delta: string
}

interface ActivityItem {
  time: string; ts: number; event: string; sub: string; icon: string; color: string
}

function scoreGrade(score: number): string {
  if (score >= 90) return 'A'
  if (score >= 80) return 'B+'
  if (score >= 70) return 'B'
  if (score >= 60) return 'C'
  return 'D'
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function ScoreRing({ value, color, size=120 }: { value:number; color:string; size?:number }) {
  const data = [{ value, fill: color }]
  return (
    <ResponsiveContainer width={size} height={size}>
      <RadialBarChart innerRadius="70%" outerRadius="100%" data={data} startAngle={90} endAngle={-270}>
        <PolarAngleAxis type="number" domain={[0,100]} tick={false} />
        <RadialBar dataKey="value" cornerRadius={6} background={{ fill:'rgba(255,255,255,0.05)' }} />
      </RadialBarChart>
    </ResponsiveContainer>
  )
}

export default function DashboardPage() {
  const user = useAuthStore(s => s.user)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<StatCardData[]>([])
  const [activity, setActivity] = useState<ActivityItem[]>([])

  useEffect(() => {
    Promise.all([
      resumeApi.list().catch(() => null),
      skillGapApi.listReports().catch(() => null),
      careerApi.listReports().catch(() => null),
      interviewApi.listSessions().catch(() => null),
    ]).then(([resumeRes, skillRes, careerRes, interviewRes]) => {
      const resumes    = (resumeRes?.data?.data ?? resumeRes?.data)?.resumes ?? []
      const skillGaps   = (skillRes?.data?.data ?? skillRes?.data)?.reports ?? []
      const careerRecs  = (careerRes?.data?.data ?? careerRes?.data)?.reports ?? []
      const sessions    = (interviewRes?.data?.data ?? interviewRes?.data)?.sessions ?? []

      // Most recent of each (lists come back newest-first from the backend)
      const latestResume     = resumes.find((r: any) => r.ats_score != null) ?? null
      const latestSkillGap   = skillGaps[0] ?? null
      const latestCareer     = careerRecs[0] ?? null
      const latestInterview  = sessions.find((s: any) => s.overall_score != null) ?? null

      setStats([
        {
          label: 'ATS Score', unit: '/100', color: '#5B4FE8', icon: FileText, path: '/resume',
          value: latestResume ? Math.round(latestResume.ats_score) : null,
          grade: latestResume ? scoreGrade(latestResume.ats_score) : null,
          delta: latestResume ? latestResume.filename : 'No resume analysed yet',
        },
        {
          label: 'Skill Match', unit: '%', color: '#00D4FF', icon: Target, path: '/skill-gap',
          value: latestSkillGap ? Math.round(latestSkillGap.overall_match_pct) : null,
          grade: latestSkillGap ? latestSkillGap.grade : null,
          delta: latestSkillGap ? `vs ${latestSkillGap.role_title}` : 'No skill gap check yet',
        },
        {
          label: 'Interview Score', unit: '/100', color: '#10D97A', icon: Mic, path: '/interview',
          value: latestInterview ? Math.round(latestInterview.overall_score) : null,
          grade: latestInterview ? latestInterview.grade : null,
          delta: latestInterview ? (latestInterview.target_role ?? 'Last session') : 'No mock interview yet',
        },
        {
          label: 'Career Fit', unit: '%', color: '#A855F7', icon: TrendingUp, path: '/career',
          value: latestCareer ? Math.round(latestCareer.top_role_score) : null,
          grade: latestCareer ? scoreGrade(latestCareer.top_role_score) : null,
          delta: latestCareer ? latestCareer.top_recommended_role : 'No recommendation yet',
        },
      ])

      // Merge all 4 sources into one activity feed, newest first
      const merged: ActivityItem[] = [
        ...resumes.map((r: any) => ({
          ts: new Date(r.created_at).getTime(), time: timeAgo(r.created_at),
          event: 'Resume analysed', sub: r.ats_score != null ? `ATS score: ${Math.round(r.ats_score)}/100` : r.filename,
          icon: '📄', color: '#5B4FE8',
        })),
        ...skillGaps.map((r: any) => ({
          ts: new Date(r.created_at).getTime(), time: timeAgo(r.created_at),
          event: `Skill gap for ${r.role_title}`, sub: `${Math.round(r.overall_match_pct)}% match`,
          icon: '📊', color: '#00D4FF',
        })),
        ...sessions.filter((s: any) => s.status === 'completed').map((s: any) => ({
          ts: new Date(s.ended_at ?? s.started_at).getTime(), time: timeAgo(s.ended_at ?? s.started_at),
          event: 'Mock interview completed',
          sub: s.overall_score != null ? `Score ${Math.round(s.overall_score)}/100 · Grade ${s.grade}` : `${s.questions_answered}/${s.total_questions} questions`,
          icon: '🎤', color: '#10D97A',
        })),
        ...careerRecs.map((r: any) => ({
          ts: new Date(r.created_at).getTime(), time: timeAgo(r.created_at),
          event: 'Career paths recommended', sub: `Top: ${r.top_recommended_role} (${Math.round(r.top_role_score)}% fit)`,
          icon: '🚀', color: '#A855F7',
        })),
      ].sort((a, b) => b.ts - a.ts).slice(0, 6)

      setActivity(merged)
    }).finally(() => setLoading(false))
  }, [])

  const hasAnyScore = stats.some(s => s.value != null)

  return (
    <DashboardLayout>
      <div className="p-6 space-y-6 relative">
        {/* Welcome */}
        <motion.div variants={stagger} initial="hidden" animate="visible">
          <motion.div variants={fadeUp} className="flex items-center justify-between">
            <div>
              <h1 className="font-display font-bold text-2xl text-white">
                Welcome back, <span className="text-gradient">{user?.full_name?.split(' ')[0] ?? 'there'}</span> 👋
              </h1>
              <p className="text-sm text-star-70 mt-1">Here's your career readiness overview for today.</p>
            </div>
            <Link to="/chat" className="btn-primary text-sm hidden md:flex">
              <Brain className="w-4 h-4" /> Ask AI
            </Link>
          </motion.div>

          {loading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            </div>
          ) : (
          <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
            {stats.map(({ label, value, unit, grade, color, icon:Icon, path, delta }, i) => (
              <motion.div key={label} variants={fadeUp} custom={i}>
                <Link to={path} className="stat-card block group">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="text-2xs text-star-50 font-mono uppercase tracking-wide">{label}</p>
                      <div className="flex items-end gap-1 mt-1">
                        <span className="font-display font-bold text-3xl text-white">{value ?? '—'}</span>
                        {value != null && <span className="text-sm text-star-50 mb-0.5">{unit}</span>}
                      </div>
                    </div>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background:`${color}18`, border:`1px solid ${color}25` }}>
                      <Icon className="w-[18px] h-[18px]" style={{ color }} />
                    </div>
                  </div>
                  <div className="progress-bar mb-2">
                    <div className="progress-fill" style={{ width:`${value ?? 0}%`, background:`linear-gradient(90deg,${color}80,${color})` }} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-2xs text-star-50 truncate">{delta}</span>
                    {grade && <span className="text-2xs font-mono font-bold flex-shrink-0" style={{ color }}>{grade}</span>}
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>

          {/* Main grid */}
          <div className="grid lg:grid-cols-3 gap-5 mt-5">
            {/* Radar overview */}
            <motion.div variants={fadeUp} className="glass rounded-2xl p-6 col-span-1">
              <h3 className="font-display font-semibold text-white text-sm mb-5">Overall Readiness</h3>
              {hasAnyScore ? (
                <div className="grid grid-cols-2 gap-4">
                  {stats.map(({ label, value, color }) => (
                    <div key={label} className="flex flex-col items-center">
                      <div className="relative">
                        <ScoreRing value={value ?? 0} color={color} size={80} />
                        <div className="absolute inset-0 flex items-center justify-center">
                          <span className="font-display font-bold text-lg text-white">{value ?? '—'}</span>
                        </div>
                      </div>
                      <p className="text-2xs text-star-50 text-center mt-1 font-mono uppercase tracking-wide">{label.split(' ')[0]}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-star-50 py-8 text-center">Complete an analysis to see your readiness overview.</p>
              )}
            </motion.div>

            {/* Quick actions */}
            <motion.div variants={fadeUp} className="glass rounded-2xl p-6">
              <h3 className="font-display font-semibold text-white text-sm mb-4">Quick Actions</h3>
              <div className="space-y-2.5">
                {QUICK_ACTIONS.map(({ icon:Icon, label, sub, to, color }) => (
                  <Link key={to} to={to}
                    className="flex items-center gap-3 p-3 rounded-xl border border-transparent hover:border-white/8 transition-all duration-200 group"
                    style={{ background:'rgba(255,255,255,0.02)' }}>
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background:`${color}18`, border:`1px solid ${color}25` }}>
                      <Icon className="w-4 h-4" style={{ color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-white">{label}</p>
                      <p className="text-2xs text-star-50 truncate">{sub}</p>
                    </div>
                    <ArrowRight className="w-4 h-4 text-star-30 group-hover:text-white group-hover:translate-x-0.5 transition-all" />
                  </Link>
                ))}
              </div>
            </motion.div>

            {/* Activity feed */}
            <motion.div variants={fadeUp} className="glass rounded-2xl p-6">
              <h3 className="font-display font-semibold text-white text-sm mb-4">Recent Activity</h3>
              {activity.length === 0 ? (
                <p className="text-sm text-star-50 py-8 text-center">No activity yet — try one of the quick actions.</p>
              ) : (
                <div className="space-y-3">
                  {activity.map((a, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-base" style={{ background:`${a.color}15` }}>
                        {a.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white font-medium leading-tight">{a.event}</p>
                        <p className="text-2xs text-star-50 mt-0.5">{a.sub}</p>
                      </div>
                      <span className="text-2xs text-star-30 flex-shrink-0">{a.time}</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>

          {/* AI tip banner — only shown once there's a resume to reference */}
          {stats[0]?.value != null && (
            <motion.div variants={fadeUp}
              className="rounded-2xl p-5 flex items-center gap-5 mt-1"
              style={{ background:'linear-gradient(135deg,rgba(91,79,232,0.15),rgba(0,212,255,0.08))', border:'1px solid rgba(91,79,232,0.2)' }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background:'rgba(91,79,232,0.2)' }}>
                <Zap className="w-5 h-5 text-indigo-bright" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-white">Keep improving</p>
                <p className="text-xs text-star-70 mt-0.5">Your latest ATS score is {stats[0].value}/100. Re-run the analysis after each resume edit to track your progress over time.</p>
              </div>
              <Link to="/resume" className="btn-primary text-xs px-4 py-2 flex-shrink-0">View report <ArrowRight className="w-3 h-3" /></Link>
            </motion.div>
          )}
          </>
          )}
        </motion.div>
      </div>
    </DashboardLayout>
  )
}
