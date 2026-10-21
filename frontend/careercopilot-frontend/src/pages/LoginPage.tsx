import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Link, useNavigate } from 'react-router-dom'
import { Brain, Eye, EyeOff, ArrowRight, Loader2 } from 'lucide-react'
import { authApi } from '@/api'
import { useAuthStore } from '@/store/authStore'
import { fadeUp, stagger } from '@/utils'

export default function LoginPage() {
  const [mode,    setMode]    = useState<'login' | 'register'>('login')
  const [show,    setShow]    = useState(false)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [form,    setForm]    = useState({ full_name: '', email: '', password: '' })

  const setAuth = useAuthStore(s => s.setAuth)
  const nav     = useNavigate()

  const handle = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      if (mode === 'register') {
        await authApi.register({
          full_name: form.full_name,
          email:     form.email,
          password:  form.password,
        })
        setMode('login')
        setForm(f => ({ ...f, password: '' }))
        return
      }

      const res = await authApi.login({ email: form.email, password: form.password })

      // Backend: { success, message, data: { tokens: { access_token, refresh_token }, user } }
      const { tokens, user } = res.data.data

      setAuth(tokens.access_token, tokens.refresh_token, user)

      // ── FIX: Route based on role, not hardcoded to /dashboard ──────────
      // Normalise to lowercase so "admin", "ADMIN", "Admin" all match.
      const destination = user.role?.toLowerCase() === 'admin' ? '/admin' : '/dashboard'
      nav(destination, { replace: true })

    } catch (err: any) {
      const msg =
        err.response?.data?.error?.message  ||
        err.response?.data?.detail          ||
        err.response?.data?.message         ||
        'Something went wrong. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-void flex items-center justify-center relative overflow-hidden">
      <div className="absolute inset-0 bg-grid" />
      <div className="absolute inset-0 bg-hero-glow opacity-60" />

      <motion.div
        animate={{ scale: [1, 1.15, 1], opacity: [0.2, 0.35, 0.2] }}
        transition={{ duration: 8, repeat: Infinity }}
        className="absolute top-20 right-20 w-96 h-96 rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle,#5B4FE8,transparent)' }}
      />
      <motion.div
        animate={{ scale: [1, 1.2, 1], opacity: [0.15, 0.3, 0.15] }}
        transition={{ duration: 10, repeat: Infinity, delay: 3 }}
        className="absolute bottom-20 left-20 w-80 h-80 rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle,#00D4FF,transparent)' }}
      />

      <div className="relative z-10 w-full max-w-md px-4">
        <motion.div variants={stagger} initial="hidden" animate="visible">

          {/* Logo + heading */}
          <motion.div variants={fadeUp} className="text-center mb-8">
            <Link to="/" className="inline-flex items-center gap-2.5 mb-6">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}
              >
                <Brain className="w-5 h-5 text-white" />
              </div>
              <span className="font-display font-bold text-xl text-white">
                CareerCopilot <span className="text-gradient">AI</span>
              </span>
            </Link>

            <h1 className="font-display font-bold text-3xl text-white mb-2">
              {mode === 'login' ? 'Welcome back' : 'Create account'}
            </h1>
            <p className="text-sm text-star-70">
              {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
              <button
                onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
                className="text-indigo-bright hover:text-white transition-colors font-semibold"
              >
                {mode === 'login' ? 'Sign up free' : 'Sign in'}
              </button>
            </p>
          </motion.div>

          {/* Card */}
          <motion.div
            variants={fadeUp}
            className="glass rounded-2xl p-8"
            style={{ boxShadow: '0 0 0 1px rgba(91,79,232,0.15), 0 24px 64px rgba(0,0,0,0.5)' }}
          >
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mb-5 px-4 py-3 rounded-xl text-sm text-rose-400 border border-rose-400/20"
                  style={{ background: 'rgba(244,63,94,0.08)' }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <form onSubmit={handle} className="space-y-4">
              <AnimatePresence>
                {mode === 'register' && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                      Full Name
                    </label>
                    <input
                      className="input"
                      placeholder="Priya Sharma"
                      value={form.full_name}
                      onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                      required
                    />
                  </motion.div>
                )}
              </AnimatePresence>

              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Email
                </label>
                <input
                  type="email"
                  className="input"
                  placeholder="priya@example.com"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-star-70 mb-1.5 uppercase tracking-wide">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={show ? 'text' : 'password'}
                    className="input pr-11"
                    placeholder="Min 8 chars, 1 uppercase, 1 digit"
                    value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    required
                    minLength={8}
                  />
                  <button
                    type="button"
                    onClick={() => setShow(s => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-star-50 hover:text-white transition-colors"
                  >
                    {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full py-3.5 mt-2 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    {mode === 'login' ? 'Sign in' : 'Create account'}
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>

            <div className="mt-6 pt-5 border-t border-white/5 text-center">
              <p className="text-xs text-star-50">
                By continuing you agree to our{' '}
                <a href="#" className="text-indigo-bright hover:underline">Terms</a> and{' '}
                <a href="#" className="text-indigo-bright hover:underline">Privacy Policy</a>.
              </p>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}
