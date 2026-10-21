import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Brain, User, Loader2, Target, FileText, Mic, TrendingUp, BookOpen,
  Sparkles, RotateCcw, ChevronRight, ChevronDown, History, X, Quote,
} from 'lucide-react'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { agentApi } from '@/api'
import { useAuthStore } from '@/store/authStore'
import { cn } from '@/utils'

// ── Types ──────────────────────────────────────────────────────────────────

interface SuggestedAction { action: string; label: string; description: string }
interface Citation {
  number: number; filename: string; category: string; category_label: string
  score: number; excerpt: string
}

interface Message {
  id:                string
  role:              'user' | 'assistant'
  content:           string
  agentChain?:       string[]
  citations?:        Citation[]
  suggestedActions?: SuggestedAction[]
  loading?:          boolean
  streaming?:        boolean
}

interface LongTermMemory {
  career_goal?: string; career_best_domain?: string
  preferred_role?: string; preferred_company?: string
  resume_improvements?: string[]; learning_roadmap?: string[]
  interview_history?: { overall_score: number; target_role?: string }[]
  last_ats_score?: number
}

interface SessionSummary {
  session_id: string; last_active: number; preview: string | null; still_live: boolean
}

const AGENT_META: Record<string, { icon: string; color: string; label: string }> = {
  resume_agent:     { icon: '📄', color: '#5B4FE8', label: 'Resume Agent' },
  skill_gap_agent:  { icon: '📊', color: '#00D4FF', label: 'Skill Gap Agent' },
  career_agent:     { icon: '🚀', color: '#A855F7', label: 'Career Agent' },
  interview_agent:  { icon: '🎤', color: '#F59E0B', label: 'Interview Agent' },
  rag_agent:        { icon: '🎯', color: '#10D97A', label: 'Knowledge Agent' },
  default:          { icon: '🧠', color: '#5B4FE8', label: 'CareerCopilot AI' },
}

const QUICK_PROMPTS = [
  { icon: FileText,   label: 'How do I improve my ATS resume score?',     color: '#10D97A' },
  { icon: Target,     label: 'What skills do I need for ML Engineer?',    color: '#00D4FF' },
  { icon: TrendingUp, label: 'Which career suits a Python developer?',    color: '#A855F7' },
  { icon: Mic,        label: 'Common Amazon interview questions',          color: '#F59E0B' },
  { icon: BookOpen,   label: 'Explain deadlock with an example',           color: '#5B4FE8' },
  { icon: Brain,      label: 'What is the salary for a Data Scientist?',  color: '#F43F5E' },
]

const WELCOME_MESSAGE: Message = {
  id:      '0',
  role:    'assistant',
  content: "👋 Hi! I'm CareerCopilot AI — a multi-agent system with persistent memory.\n\nI automatically route your question to the right specialist:\n• **Resume Agent** → ATS scoring and feedback\n• **Skill Gap Agent** → What you're missing for a target role\n• **Career Agent** → Which roles suit your background\n• **Interview Agent** → Company-specific mock interview prep\n• **Knowledge Agent** → DBMS, OS, Networks, OOP, Java, Python, HR\n\nI remember your career goals and preferences across conversations — just ask.",
}

function timeAgo(unixSeconds: number): string {
  const diffMs = Date.now() - unixSeconds * 1000
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ── SSE streaming helper ─────────────────────────────────────────────────────
// EventSource can't do POST + custom auth headers, so this reads the raw
// stream body manually. Backend event shape:
//   {"type":"routing","agent":...,"intent":...}
//   {"type":"token","text":...}                (repeated)
//   {"type":"done","session_id":...,"agent_chain":...,"citations":...,"suggested_actions":...}
//   {"type":"error","message":...}
async function streamChat(
  query: string,
  sessionId: string | null,
  token: string | null,
  onEvent: (evt: any) => void,
  signal: AbortSignal,
): Promise<void> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL ?? '/api/v1'
  const res = await fetch(`${base}/agent/chat/stream`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query, session_id: sessionId, include_history: true }),
  })
  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed (${res.status})`)
  }

  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find(l => l.startsWith('data:'))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(5).trim()))
      } catch {
        // ignore malformed frame
      }
    }
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-4 py-3">
      {[0, 1, 2].map(i => (
        <motion.div key={i} className="w-2 h-2 rounded-full bg-indigo-bright"
          animate={{ y: [0, -6, 0] }}
          transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }} />
      ))}
    </div>
  )
}

function AgentBadge({ agentChain }: { agentChain?: string[] }) {
  const key  = agentChain?.find(a => a !== 'supervisor') ?? 'default'
  const meta = AGENT_META[key] ?? AGENT_META.default
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <span className="text-xs">{meta.icon}</span>
      <span className="text-2xs font-mono uppercase tracking-wide" style={{ color: meta.color }}>
        {meta.label}
      </span>
    </div>
  )
}

function CitationCard({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-white/8 overflow-hidden" style={{ background: 'rgba(255,255,255,0.02)' }}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/3 transition"
      >
        <span className="text-2xs font-mono font-bold text-indigo-bright flex-shrink-0">[{citation.number}]</span>
        <Quote className="w-3 h-3 text-star-30 flex-shrink-0" />
        <span className="text-2xs text-star-70 truncate flex-1">{citation.category_label || citation.filename}</span>
        <ChevronDown className={cn('w-3 h-3 text-star-30 flex-shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
            <div className="px-3 pb-3 pt-1 space-y-1.5">
              {citation.excerpt && (
                <p className="text-2xs text-star-50 italic leading-relaxed border-l-2 border-white/10 pl-2">
                  "{citation.excerpt}"
                </p>
              )}
              <div className="flex items-center gap-2 text-2xs text-star-30">
                <span>{citation.filename}</span>
                {citation.score != null && <span>· relevance {(citation.score * 100).toFixed(0)}%</span>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function MessageBubble({ msg, onAction }: { msg: Message; onAction: (label: string) => void }) {
  const isUser = msg.role === 'user'
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      <div
        className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${isUser ? 'bg-indigo-bright/20' : ''}`}
        style={!isUser ? { background: 'linear-gradient(135deg,#5B4FE8,#00D4FF)' } : {}}
      >
        {isUser ? <User className="w-4 h-4 text-indigo-bright" /> : <Brain className="w-4 h-4 text-white" />}
      </div>

      <div className={`flex-1 max-w-[80%] ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        {!isUser && (msg.agentChain?.length || msg.streaming) && <AgentBadge agentChain={msg.agentChain} />}

        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser ? 'chat-user rounded-tr-sm' : 'chat-assist rounded-tl-sm'
        }`}>
          {msg.loading && !msg.streaming
            ? <TypingIndicator />
            : (
              <div className="whitespace-pre-wrap text-star-70">
                {msg.content}
                {msg.streaming && <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-indigo-bright/70 animate-pulse align-middle" />}
              </div>
            )
          }
        </div>

        {msg.citations && msg.citations.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5 w-full">
            {msg.citations.slice(0, 4).map(c => <CitationCard key={c.number} citation={c} />)}
          </div>
        )}

        {msg.suggestedActions && msg.suggestedActions.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5 w-full">
            {msg.suggestedActions.map((a, i) => (
              <button
                key={i}
                onClick={() => onAction(a.description || a.label)}
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl border border-white/8 text-left text-xs text-star-70 hover:text-white hover:border-white/20 transition-all"
                style={{ background: 'rgba(255,255,255,0.02)' }}
              >
                <span>{a.label}</span>
                <ChevronRight className="w-3 h-3 flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE])
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [memory,  setMemory]  = useState<LongTermMemory>({})
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)
  const abortRef  = useRef<AbortController | null>(null)
  const token     = useAuthStore(s => s.token)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadMemory = useCallback(() => {
    agentApi.getMemory()
      .then(res => setMemory((res.data?.data ?? res.data)?.memory ?? {}))
      .catch(() => {})
  }, [])

  const loadSessions = useCallback(() => {
    agentApi.listSessions(20)
      .then(res => setSessions((res.data?.data ?? res.data)?.sessions ?? []))
      .catch(() => {})
  }, [])

  useEffect(() => { loadMemory(); loadSessions() }, [loadMemory, loadSessions])

  useEffect(() => () => abortRef.current?.abort(), [])

  const sendMessage = async (text?: string) => {
    const query = text ?? input.trim()
    if (!query || loading) return

    const userMsg: Message = { id: `${Date.now()}-u`, role: 'user', content: query }
    const aiMsgId = `${Date.now()}-ai`
    const aiMsg: Message = { id: aiMsgId, role: 'assistant', content: '', loading: true, streaming: true }

    setMessages(prev => [...prev, userMsg, aiMsg])
    setInput('')
    setLoading(true)
    setHistoryOpen(false)

    const controller = new AbortController()
    abortRef.current = controller

    const patch = (fn: (m: Message) => Message) =>
      setMessages(prev => prev.map(m => (m.id === aiMsgId ? fn(m) : m)))

    try {
      await streamChat(query, sessionId, token, (evt) => {
        if (evt.type === 'routing') {
          patch(m => ({ ...m, agentChain: [evt.agent], loading: false }))
        } else if (evt.type === 'token') {
          patch(m => ({ ...m, content: m.content + evt.text, loading: false }))
        } else if (evt.type === 'done') {
          patch(m => ({
            ...m,
            streaming: false,
            loading: false,
            agentChain: evt.agent_chain ?? m.agentChain,
            citations: evt.citations ?? [],
            suggestedActions: evt.suggested_actions ?? [],
          }))
          setSessionId(evt.session_id ?? sessionId)
          loadSessions()
        } else if (evt.type === 'error') {
          patch(m => ({ ...m, streaming: false, loading: false, content: m.content || evt.message || 'Something went wrong.' }))
        }
      }, controller.signal)

      // Long-term memory isn't in the stream payload — refresh separately
      // once the turn completes (cheap, and keeps the memory chips in sync).
      loadMemory()
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        patch(m => ({
          ...m, streaming: false, loading: false,
          content: m.content || 'Something went wrong. Please try again.',
        }))
      }
    } finally {
      setLoading(false)
    }
  }

  const newChat = () => {
    abortRef.current?.abort()
    setSessionId(null)
    setMessages([WELCOME_MESSAGE])
    setHistoryOpen(false)
  }

  const openSession = async (sid: string) => {
    setHistoryOpen(false)
    setLoading(true)
    try {
      const res  = await agentApi.getMessages(sid)
      const data = res.data?.data ?? res.data
      const loaded: Message[] = (data?.messages ?? []).map((m: any, i: number) => ({
        id:      `${sid}-${i}`,
        role:    m.role === 'user' ? 'user' : 'assistant',
        content: m.content ?? '',
        agentChain: m.agent ? [m.agent] : undefined,
      }))
      setMessages(loaded.length ? loaded : [WELCOME_MESSAGE])
      setSessionId(sid)
    } catch {
      // session may have expired past its 24h TTL — start fresh rather than
      // leaving the user stuck on a broken load
      setMessages([WELCOME_MESSAGE])
      setSessionId(null)
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const memoryChips = [
    memory.preferred_role && `Preferred role: ${memory.preferred_role}`,
    memory.preferred_company && `Preferred company: ${memory.preferred_company}`,
    memory.career_goal && `Career goal: ${memory.career_goal}`,
    memory.last_ats_score != null && `Last ATS score: ${Math.round(memory.last_ats_score)}`,
  ].filter(Boolean) as string[]

  return (
    <DashboardLayout>
      <div className="flex h-full relative">
        {/* History sidebar (overlay on mobile, inline on desktop when open) */}
        <AnimatePresence>
          {historyOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                onClick={() => setHistoryOpen(false)}
                className="fixed inset-0 bg-black/50 z-40 lg:hidden"
              />
              <motion.div
                initial={{ x: -280, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -280, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="fixed lg:absolute left-0 top-0 bottom-0 w-72 glass border-r border-white/10 z-50 flex flex-col"
              >
                <div className="flex items-center justify-between px-4 py-4 border-b border-white/10 flex-shrink-0">
                  <span className="text-sm font-semibold text-white">Conversations</span>
                  <button onClick={() => setHistoryOpen(false)} className="text-star-50 hover:text-white">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {sessions.length === 0 ? (
                    <p className="text-xs text-star-50 text-center py-8 px-4">No past conversations yet.</p>
                  ) : (
                    sessions.map(s => (
                      <button
                        key={s.session_id}
                        onClick={() => openSession(s.session_id)}
                        className={cn(
                          'w-full text-left px-4 py-3 border-b border-white/5 hover:bg-white/5 transition',
                          s.session_id === sessionId && 'bg-indigo-500/10',
                          !s.still_live && 'opacity-50'
                        )}
                      >
                        <p className="text-xs text-white truncate">{s.preview || 'New conversation'}</p>
                        <p className="text-2xs text-star-50 mt-0.5">
                          {timeAgo(s.last_active)}{!s.still_live && ' · expired'}
                        </p>
                      </button>
                    ))
                  )}
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>

        <div className="flex flex-col flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-white/5 flex-shrink-0">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <button onClick={() => setHistoryOpen(o => !o)} className="btn-ghost p-2 flex-shrink-0" aria-label="Conversation history">
                <History className="w-4 h-4" />
              </button>
              <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>
                <Brain className="w-4 h-4 text-white" />
              </div>
              <div className="min-w-0">
                <h2 className="font-display font-bold text-white text-sm truncate">CareerCopilot AI</h2>
                <p className="text-2xs text-star-50 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse inline-block flex-shrink-0" />
                  <span className="truncate">Multi-Agent System Active</span>
                </p>
              </div>
            </div>
            <button onClick={newChat} className="btn-ghost text-xs gap-1.5 border border-white/8 flex-shrink-0">
              <RotateCcw className="w-3.5 h-3.5" /> <span className="hidden sm:inline">New Chat</span>
            </button>
          </div>

          {/* Long-term memory strip */}
          {memoryChips.length > 0 && (
            <div className="px-4 sm:px-6 py-2.5 border-b border-white/5 flex items-center gap-2 flex-wrap flex-shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-indigo-bright flex-shrink-0" />
              {memoryChips.map(c => (
                <span key={c} className="badge text-2xs">{c}</span>
              ))}
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
            {messages.map(msg => <MessageBubble key={msg.id} msg={msg} onAction={sendMessage} />)}
            <div ref={bottomRef} />
          </div>

          {/* Quick prompts — only on empty chat */}
          {messages.length <= 1 && (
            <div className="px-4 sm:px-6 pb-2 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
              {QUICK_PROMPTS.map(({ icon: Icon, label, color }) => (
                <button
                  key={label}
                  onClick={() => sendMessage(label)}
                  className="flex items-center gap-2 p-3 rounded-xl border border-white/6 text-left text-xs text-star-70 hover:text-white hover:border-white/12 transition-all"
                  style={{ background: 'rgba(255,255,255,0.02)' }}
                >
                  <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color }} />
                  <span className="line-clamp-1">{label}</span>
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="px-4 sm:px-6 pb-4 sm:pb-6 pt-2 flex-shrink-0">
            <div
              className="glass rounded-2xl p-3 flex items-end gap-3"
              style={{ border: '1px solid rgba(91,79,232,0.2)' }}
            >
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Ask anything — interview questions, skill gaps, career advice, or CS concepts…"
                className="flex-1 bg-transparent text-sm text-star-90 placeholder-star-30 resize-none outline-none min-h-[44px] max-h-[160px] py-1"
                rows={1}
                disabled={loading}
                aria-label="Message CareerCopilot AI"
              />
              <div className="flex items-center gap-2 flex-shrink-0">
                {input.length > 0 && (
                  <span className="text-2xs text-star-30 font-mono hidden sm:inline">{input.length}</span>
                )}
                <button
                  onClick={() => sendMessage()}
                  disabled={!input.trim() || loading}
                  aria-label="Send message"
                  className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
                  style={{
                    background:  input.trim() && !loading ? 'linear-gradient(135deg,#5B4FE8,#4A42D4)' : 'rgba(91,79,232,0.2)',
                    boxShadow:   input.trim() && !loading ? '0 0 16px rgba(91,79,232,0.4)' : 'none',
                  }}
                >
                  {loading
                    ? <Loader2 className="w-4 h-4 text-white animate-spin" />
                    : <Send className="w-4 h-4 text-white" />
                  }
                </button>
              </div>
            </div>
            <p className="text-2xs text-star-30 text-center mt-2 hidden sm:block">
              Auto-routes to the right specialist agent · Remembers your goals across chats · Press Enter to send
            </p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  )
}
