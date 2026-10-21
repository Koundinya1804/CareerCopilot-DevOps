/**
 * src/pages/ProfilePage.tsx
 *
 * Displays and allows editing of the authenticated user's career profile
 * and skill list.
 *
 * Data:
 *   GET  /api/v1/users/me              → MeResponse (user + profile + skills)
 *   PUT  /api/v1/users/me/profile      → UserProfileRequest
 *   POST /api/v1/users/me/skills       → SkillAddRequest
 *   DEL  /api/v1/users/me/skills/{id} → removes skill
 *
 * Uses the existing `api` axios instance from @/api (Zustand-based auth).
 * Matches the glassmorphism design language of ResumePage / CareerPage.
 */

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  User,
  Briefcase,
  MapPin,
  Linkedin,
  Github,
  Save,
  Plus,
  X,
  Loader2,
  CheckCircle,
  AlertCircle,
  Zap,
} from 'lucide-react'
import { api } from '@/api'
import { fadeUp, stagger, cn } from '@/utils'

// ── Types ──────────────────────────────────────────────────────────────────

interface Profile {
  profile_id:           number
  target_role:          string | null
  current_role:         string | null
  years_experience:     number
  location:             string | null
  linkedin_url:         string | null
  github_url:           string | null
  bio:                  string | null
  preferred_industries: string[] | null
}

interface Skill {
  skill_id:    number
  skill_name:  string
  proficiency: string
  years_used:  number
}

interface MeData {
  user_id:    number
  email:      string
  full_name:  string
  role:       string
  avatar_url: string | null
  profile:    Profile | null
  skills:     Skill[]
}

// ── Constants ─────────────────────────────────────────────────────────────

const PROFICIENCY_LEVELS = ['beginner', 'intermediate', 'advanced', 'expert'] as const
type ProfLevel = typeof PROFICIENCY_LEVELS[number]

const PROFICIENCY_COLOR: Record<ProfLevel, string> = {
  beginner:     'bg-star-50/10 text-star-70 border-white/10',
  intermediate: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
  advanced:     'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  expert:       'bg-violet-500/10 text-violet-400 border-violet-500/20',
}

const INDUSTRY_SUGGESTIONS = [
  'Fintech', 'EdTech', 'HealthTech', 'SaaS', 'E-commerce',
  'AI/ML', 'Cybersecurity', 'Cloud', 'Gaming', 'Logistics',
]

// ── Sub-components ─────────────────────────────────────────────────────────

function StatusBanner({ type, msg }: { type: 'success' | 'error'; msg: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className={cn(
        'flex items-center gap-2 px-4 py-3 rounded-xl text-sm border',
        type === 'success'
          ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
          : 'bg-rose-500/10 border-rose-500/20 text-rose-400',
      )}
    >
      {type === 'success' ? <CheckCircle className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
      {msg}
    </motion.div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const [me,           setMe]           = useState<MeData | null>(null)
  const [loading,      setLoading]      = useState(true)
  const [saving,       setSaving]       = useState(false)
  const [banner,       setBanner]       = useState<{ type: 'success' | 'error'; msg: string } | null>(null)

  // Profile form state
  const [targetRole,    setTargetRole]    = useState('')
  const [currentRole,   setCurrentRole]   = useState('')
  const [yearsExp,      setYearsExp]      = useState(0)
  const [location,      setLocation]      = useState('')
  const [linkedin,      setLinkedin]      = useState('')
  const [github,        setGithub]        = useState('')
  const [bio,           setBio]           = useState('')
  const [industries,    setIndustries]    = useState<string[]>([])

  // Skill form state
  const [skillName,     setSkillName]     = useState('')
  const [proficiency,   setProficiency]   = useState<ProfLevel>('intermediate')
  const [yearsUsed,     setYearsUsed]     = useState(1)
  const [addingSkill,   setAddingSkill]   = useState(false)

  // ── Load ──────────────────────────────────────────────────────────────────

  const load = async () => {
    try {
      const res = await api.get('/users/me')
      // Response is { success, message, data: MeResponse }
      const data: MeData = res.data?.data ?? res.data
      setMe(data)
      const p = data.profile
      if (p) {
        setTargetRole(p.target_role    ?? '')
        setCurrentRole(p.current_role  ?? '')
        setYearsExp(p.years_experience ?? 0)
        setLocation(p.location         ?? '')
        setLinkedin(p.linkedin_url     ?? '')
        setGithub(p.github_url         ?? '')
        setBio(p.bio                   ?? '')
        setIndustries(p.preferred_industries ?? [])
      }
    } catch {
      showBanner('error', 'Failed to load profile.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const showBanner = (type: 'success' | 'error', msg: string) => {
    setBanner({ type, msg })
    setTimeout(() => setBanner(null), 4000)
  }

  // ── Save profile ──────────────────────────────────────────────────────────

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      await api.put('/users/me/profile', {
        target_role:          targetRole   || null,
        current_role:         currentRole  || null,
        years_experience:     yearsExp,
        location:             location     || null,
        linkedin_url:         linkedin     || null,
        github_url:           github       || null,
        bio:                  bio          || null,
        preferred_industries: industries,
      })
      showBanner('success', 'Profile updated successfully.')
    } catch {
      showBanner('error', 'Failed to save profile.')
    } finally {
      setSaving(false)
    }
  }

  // ── Skills ────────────────────────────────────────────────────────────────

  const handleAddSkill = async () => {
    if (!skillName.trim()) return
    setAddingSkill(true)
    try {
      await api.post('/users/me/skills', {
        skill_name:  skillName.trim(),
        proficiency,
        years_used:  yearsUsed,
      })
      setSkillName('')
      setYearsUsed(1)
      await load()
      showBanner('success', `Skill "${skillName.trim()}" added.`)
    } catch {
      showBanner('error', 'Failed to add skill.')
    } finally {
      setAddingSkill(false)
    }
  }

  const handleDeleteSkill = async (skillId: number, name: string) => {
    try {
      await api.delete(`/users/me/skills/${skillId}`)
      setMe(prev => prev ? { ...prev, skills: prev.skills.filter(s => s.skill_id !== skillId) } : prev)
      showBanner('success', `"${name}" removed.`)
    } catch {
      showBanner('error', 'Failed to remove skill.')
    }
  }

  // ── Toggle industry ───────────────────────────────────────────────────────

  const toggleIndustry = (ind: string) => {
    setIndustries(prev =>
      prev.includes(ind) ? prev.filter(i => i !== ind) : [...prev, ind]
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-96">
        <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 relative max-w-4xl mx-auto">

      {/* Background glow */}
      <div className="absolute inset-0 bg-hero-radial opacity-40 pointer-events-none" />

      {/* Header */}
      <motion.div variants={stagger} initial="hidden" animate="visible">
        <motion.div variants={fadeUp} className="flex items-center gap-3 mb-1">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center flex-shrink-0">
            <User className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-display font-bold text-white">
              {me?.full_name ?? 'Profile'}
            </h1>
            <p className="text-sm text-star-70">{me?.email}</p>
          </div>
        </motion.div>
      </motion.div>

      {/* Status banner */}
      <AnimatePresence>
        {banner && <StatusBanner type={banner.type} msg={banner.msg} />}
      </AnimatePresence>

      {/* ── Career Profile Form ────────────────────────────────────────────── */}
      <motion.section
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="glass rounded-2xl p-6 space-y-5"
      >
        <div className="flex items-center gap-2 mb-1">
          <Briefcase className="w-4 h-4 text-indigo-400" />
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Career Profile</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Target role */}
          <div>
            <label className="block text-xs text-star-70 mb-1.5">Target Role</label>
            <input
              value={targetRole}
              onChange={e => setTargetRole(e.target.value)}
              placeholder="e.g. Senior Backend Engineer"
              className="input w-full"
            />
          </div>

          {/* Current role */}
          <div>
            <label className="block text-xs text-star-70 mb-1.5">Current Role</label>
            <input
              value={currentRole}
              onChange={e => setCurrentRole(e.target.value)}
              placeholder="e.g. Junior Developer"
              className="input w-full"
            />
          </div>

          {/* Years experience */}
          <div>
            <label className="block text-xs text-star-70 mb-1.5">Years of Experience</label>
            <input
              type="number"
              min={0}
              max={50}
              value={yearsExp}
              onChange={e => setYearsExp(Number(e.target.value))}
              className="input w-full"
            />
          </div>

          {/* Location */}
          <div>
            <label className="block text-xs text-star-70 mb-1.5 flex items-center gap-1">
              <MapPin className="w-3 h-3" /> Location
            </label>
            <input
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder="e.g. Hyderabad, India"
              className="input w-full"
            />
          </div>

          {/* LinkedIn */}
          <div>
            <label className="block text-xs text-star-70 mb-1.5 flex items-center gap-1">
              <Linkedin className="w-3 h-3" /> LinkedIn URL
            </label>
            <input
              value={linkedin}
              onChange={e => setLinkedin(e.target.value)}
              placeholder="https://linkedin.com/in/..."
              className="input w-full"
            />
          </div>

          {/* GitHub */}
          <div>
            <label className="block text-xs text-star-70 mb-1.5 flex items-center gap-1">
              <Github className="w-3 h-3" /> GitHub URL
            </label>
            <input
              value={github}
              onChange={e => setGithub(e.target.value)}
              placeholder="https://github.com/..."
              className="input w-full"
            />
          </div>
        </div>

        {/* Bio */}
        <div>
          <label className="block text-xs text-star-70 mb-1.5">Bio</label>
          <textarea
            rows={3}
            value={bio}
            onChange={e => setBio(e.target.value)}
            placeholder="A short description about your background and goals..."
            className="input w-full resize-none"
          />
        </div>

        {/* Preferred industries */}
        <div>
          <label className="block text-xs text-star-70 mb-2">Preferred Industries</label>
          <div className="flex flex-wrap gap-2">
            {INDUSTRY_SUGGESTIONS.map(ind => (
              <button
                key={ind}
                onClick={() => toggleIndustry(ind)}
                className={cn(
                  'px-3 py-1 rounded-full text-xs border transition-all',
                  industries.includes(ind)
                    ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                    : 'bg-white/5 text-star-70 border-white/10 hover:border-white/20',
                )}
              >
                {ind}
              </button>
            ))}
          </div>
        </div>

        {/* Save button */}
        <div className="flex justify-end pt-1">
          <button
            onClick={handleSaveProfile}
            disabled={saving}
            className="btn-primary flex items-center gap-2 px-5 py-2.5 text-sm"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {saving ? 'Saving…' : 'Save Profile'}
          </button>
        </div>
      </motion.section>

      {/* ── Skills ────────────────────────────────────────────────────────── */}
      <motion.section
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        custom={1}
        className="glass rounded-2xl p-6 space-y-5"
      >
        <div className="flex items-center gap-2 mb-1">
          <Zap className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Skills</h2>
          <span className="ml-auto text-xs text-star-50">{me?.skills.length ?? 0} skills</span>
        </div>

        {/* Add skill row */}
        <div className="flex flex-wrap gap-3 items-end p-4 rounded-xl bg-white/3 border border-white/8">
          <div className="flex-1 min-w-[140px]">
            <label className="block text-2xs text-star-50 mb-1">Skill Name</label>
            <input
              value={skillName}
              onChange={e => setSkillName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddSkill()}
              placeholder="e.g. Python"
              className="input w-full text-sm"
            />
          </div>

          <div>
            <label className="block text-2xs text-star-50 mb-1">Proficiency</label>
            <select
              value={proficiency}
              onChange={e => setProficiency(e.target.value as ProfLevel)}
              className="input text-sm pr-8"
            >
              {PROFICIENCY_LEVELS.map(l => (
                <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>
              ))}
            </select>
          </div>

          <div className="w-20">
            <label className="block text-2xs text-star-50 mb-1">Yrs Used</label>
            <input
              type="number"
              min={0}
              max={30}
              value={yearsUsed}
              onChange={e => setYearsUsed(Number(e.target.value))}
              className="input w-full text-sm"
            />
          </div>

          <button
            onClick={handleAddSkill}
            disabled={addingSkill || !skillName.trim()}
            className="btn-primary flex items-center gap-2 px-4 py-2.5 text-sm self-end disabled:opacity-50"
          >
            {addingSkill ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Add
          </button>
        </div>

        {/* Skill chips */}
        {me && me.skills.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            <AnimatePresence>
              {me.skills.map(skill => (
                <motion.div
                  key={skill.skill_id}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className={cn(
                    'flex items-center gap-1.5 pl-3 pr-1.5 py-1.5 rounded-full text-xs border',
                    PROFICIENCY_COLOR[skill.proficiency as ProfLevel] ?? 'bg-white/5 text-star-70 border-white/10',
                  )}
                >
                  <span className="font-medium">{skill.skill_name}</span>
                  <span className="opacity-50">·</span>
                  <span className="opacity-60">{skill.proficiency}</span>
                  {skill.years_used > 0 && (
                    <>
                      <span className="opacity-50">·</span>
                      <span className="opacity-60">{skill.years_used}y</span>
                    </>
                  )}
                  <button
                    onClick={() => handleDeleteSkill(skill.skill_id, skill.skill_name)}
                    className="ml-1 p-0.5 rounded-full hover:bg-white/15 transition-colors"
                    aria-label={`Remove ${skill.skill_name}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        ) : (
          <p className="text-sm text-star-50 text-center py-4">
            No skills added yet. Add your first skill above.
          </p>
        )}
      </motion.section>
    </div>
  )
}
