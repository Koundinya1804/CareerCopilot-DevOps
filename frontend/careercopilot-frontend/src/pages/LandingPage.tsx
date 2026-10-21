import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Brain, Zap, Target, Mic, BookOpen, ChevronRight, Star, Check,
         ChevronDown, ArrowRight, Sparkles, TrendingUp, Menu, X } from 'lucide-react'
import { fadeUp, stagger } from '@/utils'

// ── Navbar ─────────────────────────────────────────────────────────────────
function Navbar() {
  const [open, setOpen] = useState(false)
  const links = ['Features', 'Agents', 'Pricing', 'FAQ']
  return (
    <nav className="fixed top-0 inset-x-0 z-50 border-b border-white/5" style={{ background: 'rgba(4,5,10,0.85)', backdropFilter: 'blur(20px)' }}>
      <div className="section-container flex items-center justify-between h-16">
        <Link to="/" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
          <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>
            <Brain className="w-4 h-4 text-white" />
          </div>
          <span className="font-display font-bold text-lg text-white">CareerCopilot <span className="text-gradient">AI</span></span>
        </Link>
        <div className="hidden md:flex items-center gap-8">
          {links.map(l => (
            <a key={l} href={`#${l.toLowerCase()}`} className="text-sm text-star-70 hover:text-white transition-colors">{l}</a>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="btn-ghost text-sm hidden md:flex">Sign in</Link>
          <Link to="/login" className="btn-primary text-sm hidden sm:flex">Get Started <ArrowRight className="w-4 h-4" /></Link>
          <button
            onClick={() => setOpen(o => !o)}
            className="btn-ghost p-2 md:hidden"
            aria-label={open ? 'Close menu' : 'Open menu'}
          >
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden border-t border-white/5 overflow-hidden"
            style={{ background: 'rgba(4,5,10,0.98)' }}
          >
            <div className="section-container flex flex-col py-4 gap-1">
              {links.map(l => (
                <a
                  key={l}
                  href={`#${l.toLowerCase()}`}
                  onClick={() => setOpen(false)}
                  className="text-sm text-star-70 hover:text-white transition-colors py-2.5"
                >
                  {l}
                </a>
              ))}
              <Link to="/login" onClick={() => setOpen(false)} className="text-sm text-star-70 hover:text-white transition-colors py-2.5 sm:hidden">
                Sign in
              </Link>
              <Link to="/login" onClick={() => setOpen(false)} className="btn-primary text-sm mt-2 justify-center">
                Get Started <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}

// ── Hero ───────────────────────────────────────────────────────────────────
function Hero() {
  const ref   = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] })
  const y     = useTransform(scrollYProgress, [0, 1], [0, 120])
  const opacity = useTransform(scrollYProgress, [0, 0.6], [1, 0])

  return (
    <section ref={ref} className="relative min-h-screen flex items-center pt-20 overflow-hidden">
      {/* Background layers */}
      <div className="absolute inset-0 bg-grid" />
      <div className="absolute inset-0 bg-hero-glow" />
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full opacity-10 blur-3xl"
           style={{ background: 'radial-gradient(circle,#5B4FE8 0%,transparent 70%)' }} />
      {/* Animated orbs */}
      <motion.div animate={{ scale:[1,1.15,1], opacity:[0.3,0.5,0.3] }} transition={{ duration:8, repeat:Infinity, ease:'easeInOut' }}
        className="absolute top-32 right-20 w-64 h-64 rounded-full blur-3xl opacity-20"
        style={{ background: 'radial-gradient(circle,#00D4FF,transparent)' }} />
      <motion.div animate={{ scale:[1,1.2,1], opacity:[0.2,0.4,0.2] }} transition={{ duration:10, repeat:Infinity, ease:'easeInOut', delay:2 }}
        className="absolute bottom-32 left-10 w-80 h-80 rounded-full blur-3xl opacity-15"
        style={{ background: 'radial-gradient(circle,#A855F7,transparent)' }} />

      <motion.div style={{ y, opacity }} className="section-container relative z-10 py-24">
        <motion.div variants={stagger} initial="hidden" animate="visible" className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <motion.div variants={fadeUp} className="inline-flex items-center gap-2 px-4 py-2 rounded-full mb-8 border border-indigo/30"
            style={{ background: 'rgba(91,79,232,0.1)' }}>
            <Sparkles className="w-3.5 h-3.5 text-indigo-bright" />
            <span className="text-xs font-mono text-indigo-bright tracking-widest uppercase">Powered by Multi-Agent AI</span>
          </motion.div>

          {/* Headline */}
          <motion.h1 variants={fadeUp} className="text-hero font-display font-bold text-white mb-6 leading-[0.98]">
            Your AI Career<br/>
            <span className="text-gradient">Co-Pilot</span> is Here
          </motion.h1>

          <motion.p variants={fadeUp} className="text-lg text-star-70 max-w-2xl mx-auto mb-10 leading-relaxed">
            Resume analysis, skill gap detection, career recommendations, and interview coaching — all powered by specialised AI agents working together in real-time.
          </motion.p>

          {/* CTA buttons */}
          <motion.div variants={fadeUp} className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/login" className="btn-primary text-base px-8 py-4">
              Start Free — No Card Required
              <ArrowRight className="w-5 h-5" />
            </Link>
            <a href="#agents" className="btn-secondary text-base px-8 py-4">
              See How It Works
            </a>
          </motion.div>

          {/* Social proof */}
          <motion.div variants={fadeUp} className="flex items-center justify-center gap-8 mt-14">
            {[['500+','Beta Users'],['92%','Interview Success'],['4.9★','Avg Rating']].map(([num,label]) => (
              <div key={label} className="text-center">
                <div className="font-display font-bold text-2xl text-gradient">{num}</div>
                <div className="text-xs text-star-50 mt-0.5">{label}</div>
              </div>
            ))}
          </motion.div>
        </motion.div>

        {/* Dashboard preview card */}
        <motion.div initial={{ opacity: 0, y: 60 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6, duration: 0.8, ease: [0.22,1,0.36,1] }}
          className="relative mt-20 max-w-5xl mx-auto">
          <div className="glass rounded-3xl overflow-hidden" style={{ boxShadow: '0 0 0 1px rgba(91,79,232,0.2), 0 40px 80px rgba(0,0,0,0.6)' }}>
            {/* Fake browser chrome */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5" style={{ background: 'rgba(255,255,255,0.02)' }}>
              <div className="flex gap-1.5">{['#F43F5E','#F59E0B','#10D97A'].map(c=><div key={c} className="w-3 h-3 rounded-full" style={{background:c}}/>)}</div>
              <div className="flex-1 mx-4 h-6 rounded-md flex items-center px-3" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <span className="text-xs text-star-50 font-mono">careercopilot.ai/dashboard</span>
              </div>
            </div>
            <DashboardPreview />
          </div>
          {/* Glow under card */}
          <div className="absolute -inset-4 -z-10 rounded-3xl blur-3xl opacity-30" style={{ background: 'linear-gradient(135deg,rgba(91,79,232,0.4),rgba(0,212,255,0.2))' }} />
        </motion.div>
      </motion.div>
    </section>
  )
}

function DashboardPreview() {
  return (
    <div className="p-6 grid grid-cols-3 gap-4" style={{ background: 'rgba(4,5,10,0.8)', minHeight: 340 }}>
      {/* Stat cards */}
      {[
        { label:'ATS Score',   value:'84',  unit:'/100',  color:'#5B4FE8', grade:'B+' },
        { label:'Skill Match', value:'72',  unit:'%',     color:'#00D4FF', grade:'↑8%' },
        { label:'Interview',   value:'78',  unit:'/100',  color:'#10D97A', grade:'B' },
      ].map(({label,value,unit,color,grade}) => (
        <div key={label} className="glass rounded-xl p-4">
          <div className="text-xs text-star-50 mb-2 font-mono uppercase tracking-wide">{label}</div>
          <div className="flex items-end gap-1 mb-2">
            <span className="font-display font-bold text-3xl text-white">{value}</span>
            <span className="text-sm text-star-50 mb-1">{unit}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="progress-bar flex-1 mr-3"><div className="progress-fill" style={{ width:`${value}%`, background:`linear-gradient(90deg,${color}80,${color})` }}/></div>
            <span className="text-xs font-mono" style={{color}}>{grade}</span>
          </div>
        </div>
      ))}
      {/* Chat preview */}
      <div className="col-span-2 glass rounded-xl p-4 flex flex-col gap-3">
        <div className="text-xs text-star-50 font-mono uppercase tracking-wide mb-1">AI Agent Chat</div>
        {[
          { role:'user',    msg:'What skills am I missing for ML Engineer at Google?' },
          { role:'agent',   msg:'Based on your resume analysis, you\'re missing: MLflow, Kubernetes, and distributed training experience. Your Python and PyTorch are strong ✓' },
        ].map(({role,msg},i) => (
          <div key={i} className={`rounded-xl px-3 py-2 text-xs ${role==='user' ? 'chat-user ml-6' : 'chat-assist mr-6'}`}>
            <span className="text-star-70">{msg}</span>
          </div>
        ))}
        <div className="chat-assist rounded-xl px-3 py-2 flex items-center gap-1.5">
          <span className="typing-dot"/><span className="typing-dot"/><span className="typing-dot"/>
        </div>
      </div>
      {/* Skills */}
      <div className="glass rounded-xl p-4">
        <div className="text-xs text-star-50 font-mono uppercase tracking-wide mb-3">Top Skills</div>
        {['Python','PyTorch','FastAPI','Docker','SQL'].map((s,i) => (
          <div key={s} className="flex items-center gap-2 mb-2">
            <div className="h-1.5 rounded-full flex-1" style={{ background:'rgba(255,255,255,0.06)' }}>
              <div className="h-full rounded-full" style={{ width:`${[92,78,71,65,60][i]}%`, background:'linear-gradient(90deg,#5B4FE8,#00D4FF)' }}/>
            </div>
            <span className="text-2xs text-star-50 w-6">{[92,78,71,65,60][i]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Features ───────────────────────────────────────────────────────────────
const FEATURES = [
  { icon: Brain,     color: '#5B4FE8', title: 'Resume Analysis',     desc: 'AI-powered ATS scoring with actionable feedback. Know exactly what recruiters see when your resume lands on their desk.' },
  { icon: Target,    color: '#00D4FF', title: 'Skill Gap Detection',  desc: 'Compare your skills against any role at any company. Get a prioritised learning plan with real course links.' },
  { icon: TrendingUp,color: '#10D97A', title: 'Career Recommendations',desc: 'Score your fit across 20 career roles. Find where your unique skills and interests create the strongest match.' },
  { icon: Mic,       color: '#A855F7', title: 'Interview Coaching',   desc: 'Company-specific mock interviews with real-time STAR evaluation, model answers, and confidence scoring.' },
  { icon: BookOpen,  color: '#F59E0B', title: 'Knowledge Q&A',        desc: 'Ask anything about CS, DBMS, OS, networking, Java, Python, aptitude — answered from a curated knowledge base.' },
  { icon: Zap,       color: '#F43F5E', title: 'Multi-Agent Routing',  desc: 'One chat interface automatically routes to the right specialist agent. No menus, no modes — just ask.' },
]

function Features() {
  return (
    <section id="features" className="py-32 relative">
      <div className="absolute inset-0 bg-grid-sm opacity-50" />
      <div className="section-container relative">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once:true, margin:'-100px' }} variants={stagger}>
          <motion.div variants={fadeUp} className="text-center mb-16">
            <div className="badge mb-4">Platform Features</div>
            <h2 className="text-section font-display font-bold text-white mb-4">
              Every tool a serious<br/><span className="text-gradient">job seeker needs</span>
            </h2>
            <p className="text-base text-star-70 max-w-xl mx-auto">Six specialised AI agents, one unified interface. No tab-switching, no context loss.</p>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map(({icon:Icon,color,title,desc}, i) => (
              <motion.div key={title} variants={fadeUp} custom={i} className="glass glass-hover rounded-2xl p-6 relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl opacity-0 group-hover:opacity-20 transition-opacity duration-500"
                     style={{ background: color, transform: 'translate(30%,-30%)' }} />
                <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-4" style={{ background:`${color}20`, border:`1px solid ${color}30` }}>
                  <Icon className="w-5 h-5" style={{ color }} />
                </div>
                <h3 className="font-display font-semibold text-lg text-white mb-2">{title}</h3>
                <p className="text-sm text-star-70 leading-relaxed">{desc}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ── Agents ─────────────────────────────────────────────────────────────────
const AGENTS = [
  { name:'Supervisor Agent', role:'Orchestrator', color:'#5B4FE8', desc:'Classifies your intent and routes to the right specialist. Handles multi-step requests across multiple agents.', tools:['Intent Classification','Agent Routing','State Management'] },
  { name:'Resume Agent',     role:'Analyst',      color:'#00D4FF', desc:'Extracts skills, scores ATS compatibility, detects gaps, and generates improvement suggestions with evidence.', tools:['NLP Extraction','ATS Scoring','Keyword Analysis'] },
  { name:'Skill Gap Agent',  role:'Strategist',   color:'#10D97A', desc:'Maps your skills against 6 target roles. Generates a prioritised learning plan with course and project recommendations.', tools:['Role Skill DB','Gap Scoring','Course Matching'] },
  { name:'Career Agent',     role:'Advisor',      color:'#A855F7', desc:'Scores your fit across 20 career paths using a multi-signal algorithm. Delivers personalised salary insights.', tools:['20 Role Catalogue','Salary Data','Market Trends'] },
  { name:'Interview Agent',  role:'Coach',        color:'#F59E0B', desc:'Generates company-specific interview questions. Evaluates answers on 5 dimensions with STAR analysis.', tools:['8 Company Profiles','STAR Evaluation','Model Answers'] },
  { name:'RAG Agent',        role:'Knowledge',    color:'#F43F5E', desc:'Answers any career or CS question from a curated knowledge base across 9 categories with cited sources.', tools:['ChromaDB','Hybrid Search','Source Citations'] },
]

function Agents() {
  const [active, setActive] = useState(0)
  return (
    <section id="agents" className="py-32 relative">
      <div className="section-container">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once:true, margin:'-80px' }} variants={stagger}>
          <motion.div variants={fadeUp} className="text-center mb-16">
            <div className="badge badge-cyan mb-4">Agent Architecture</div>
            <h2 className="text-section font-display font-bold text-white mb-4">Six agents, <span className="text-gradient">one mission</span></h2>
            <p className="text-base text-star-70 max-w-xl mx-auto">Each agent is a specialist. The supervisor orchestrates them to answer complex, multi-step career questions.</p>
          </motion.div>

          <div className="grid lg:grid-cols-5 gap-6">
            {/* Agent list */}
            <div className="lg:col-span-2 flex flex-col gap-2">
              {AGENTS.map(({ name, role, color }, i) => (
                <motion.button key={name} variants={fadeUp} custom={i} onClick={() => setActive(i)}
                  className={`flex items-center gap-4 p-4 rounded-xl text-left transition-all duration-200 border ${active===i ? 'border-white/10' : 'border-transparent'}`}
                  style={active===i ? { background:`${color}15`, borderColor:`${color}30` } : { background:'rgba(255,255,255,0.02)' }}>
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background:`${color}20`, border:`1px solid ${color}30` }}>
                    <span className="text-lg" style={{color}}>{i===0?'🎯':i===1?'📄':i===2?'📊':i===3?'🚀':i===4?'🎤':'💬'}</span>
                  </div>
                  <div>
                    <div className="font-display font-semibold text-sm text-white">{name}</div>
                    <div className="text-2xs text-star-50 font-mono uppercase tracking-wide mt-0.5">{role}</div>
                  </div>
                  {active===i && <ChevronRight className="w-4 h-4 ml-auto" style={{color}} />}
                </motion.button>
              ))}
            </div>

            {/* Agent detail */}
            <div className="lg:col-span-3">
              <AnimatePresence mode="wait">
                <motion.div key={active} initial={{ opacity:0, x:20 }} animate={{ opacity:1, x:0 }} exit={{ opacity:0, x:-20 }}
                  transition={{ duration:0.3 }} className="glass rounded-2xl p-8 h-full relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-64 h-64 rounded-full blur-3xl opacity-15"
                       style={{ background:AGENTS[active].color, transform:'translate(40%,-40%)' }} />
                  <div className="relative">
                    <div className="text-4xl mb-4">{active===0?'🎯':active===1?'📄':active===2?'📊':active===3?'🚀':active===4?'🎤':'💬'}</div>
                    <div className="badge mb-4" style={{ background:`${AGENTS[active].color}15`, borderColor:`${AGENTS[active].color}30`, color:AGENTS[active].color }}>
                      {AGENTS[active].role}
                    </div>
                    <h3 className="font-display font-bold text-2xl text-white mb-3">{AGENTS[active].name}</h3>
                    <p className="text-base text-star-70 leading-relaxed mb-6">{AGENTS[active].desc}</p>
                    <div className="flex flex-wrap gap-2">
                      {AGENTS[active].tools.map(t => (
                        <span key={t} className="px-3 py-1.5 rounded-lg text-xs font-mono" style={{ background:`${AGENTS[active].color}12`, border:`1px solid ${AGENTS[active].color}25`, color:AGENTS[active].color }}>
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ── Testimonials ──────────────────────────────────────────────────────────
const TESTIMONIALS = [
  { name:'Priya Sharma',     role:'ML Engineer @ Google',   avatar:'PS', text:'CareerCopilot helped me identify the exact skill gaps for Google. The interview coaching was incredibly accurate — I got the offer after 2 weeks of prep.' },
  { name:'Rahul Nair',       role:'SDE-2 @ Amazon',         avatar:'RN', text:'The resume analyser showed me I had a 67/100 ATS score. After following its suggestions, I went from 0 callbacks to 5 in the same week.' },
  { name:'Aisha Khan',       role:'Data Scientist @ Swiggy', avatar:'AK', text:'The career recommendation engine suggested Data Science when I was aiming for Business Analyst. Best decision I made was listening to it.' },
  { name:'Dev Patel',        role:'Cloud Eng @ Infosys',    avatar:'DP', text:'Company-specific interview prep for TCS was spot-on. The STAR evaluation feedback is brutally honest but exactly what you need.' },
  { name:'Sneha Reddy',      role:'Full Stack @ Freshworks', avatar:'SR', text:'I used the skill gap analyser for Full Stack role and it gave me a 4-month roadmap. I followed it exactly and got placed.' },
  { name:'Arjun Menon',      role:'Fresher @ TCS',          avatar:'AM', text:'The RAG Q&A for DBMS, OS, and CN helped me crack every technical round. It\'s like having a tutor available 24/7.' },
]

function Testimonials() {
  return (
    <section className="py-32 overflow-hidden">
      <div className="section-container">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once:true, margin:'-80px' }} variants={stagger}>
          <motion.div variants={fadeUp} className="text-center mb-16">
            <div className="badge badge-green mb-4">Real Results</div>
            <h2 className="text-section font-display font-bold text-white mb-4">Candidates who <span className="text-gradient">got placed</span></h2>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {TESTIMONIALS.map(({ name, role, avatar, text }, i) => (
              <motion.div key={name} variants={fadeUp} custom={i} className="glass glass-hover rounded-2xl p-6">
                <div className="flex text-amber-400 mb-4 gap-0.5">
                  {[...Array(5)].map((_,j) => <Star key={j} className="w-4 h-4 fill-current" />)}
                </div>
                <p className="text-sm text-star-70 leading-relaxed mb-6">"{text}"</p>
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white"
                       style={{ background:'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>{avatar}</div>
                  <div>
                    <div className="font-semibold text-sm text-white">{name}</div>
                    <div className="text-xs text-star-50">{role}</div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ── Pricing ────────────────────────────────────────────────────────────────
function Pricing() {
  const plans = [
    { name:'Free',    price:'0',   period:'forever', features:['5 resume analyses/month','Basic skill gap report','10 RAG Q&A queries','Community support'], cta:'Start Free',  highlight:false },
    { name:'Pro',     price:'299', period:'month',   features:['Unlimited analyses','Full skill gap + roadmap','Unlimited Q&A','All 8 company interview packs','Priority AI queue','PDF exports'], cta:'Start 7-day Trial', highlight:true },
    { name:'Campus',  price:'99',  period:'month',   features:['Everything in Pro','Campus placement focus','TCS/Infosys/Wipro packs','Aptitude Q&A bank','Batch analytics'], cta:'Get Campus Plan', highlight:false },
  ]
  return (
    <section id="pricing" className="py-32">
      <div className="section-container">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once:true, margin:'-80px' }} variants={stagger}>
          <motion.div variants={fadeUp} className="text-center mb-16">
            <div className="badge badge-violet mb-4">Pricing</div>
            <h2 className="text-section font-display font-bold text-white mb-4">Simple, <span className="text-gradient">honest pricing</span></h2>
          </motion.div>
          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {plans.map(({ name, price, period, features, cta, highlight }, i) => (
              <motion.div key={name} variants={fadeUp} custom={i}
                className={`rounded-2xl p-6 relative ${highlight ? 'border-gradient' : 'glass'}`}
                style={highlight ? { background:'rgba(91,79,232,0.08)' } : {}}>
                {highlight && <div className="absolute -top-3 left-1/2 -translate-x-1/2 badge">Most Popular</div>}
                <div className="mb-6">
                  <div className="font-display font-bold text-xl text-white mb-2">{name}</div>
                  <div className="flex items-end gap-1">
                    <span className="text-3xl font-display font-bold text-white">₹{price}</span>
                    <span className="text-star-50 text-sm mb-1">/{period}</span>
                  </div>
                </div>
                <ul className="space-y-3 mb-8">
                  {features.map(f => (
                    <li key={f} className="flex items-center gap-2.5 text-sm text-star-70">
                      <Check className="w-4 h-4 flex-shrink-0" style={{ color: highlight ? '#5B4FE8':'#10D97A' }} />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link to="/login" className={`block text-center py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${highlight ? 'btn-primary' : 'btn-secondary'}`}>
                  {cta}
                </Link>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ── FAQ ────────────────────────────────────────────────────────────────────
const FAQS = [
  { q:'How accurate is the ATS scoring?',   a:'Our ATS scorer uses a deterministic rule-based engine that replicates the logic of enterprise ATS systems. It scores on 5 dimensions: content, keywords, formatting, experience quality, and education. Accuracy is validated against real ATS outcomes from our beta users.' },
  { q:'Which companies are supported for company-specific interviews?', a:'We currently support Google, Amazon, Microsoft, TCS, Infosys, Wipro, Flipkart, and Swiggy — with company-specific question banks, interview style guidance, and values-aligned behavioural questions.' },
  { q:'Is my resume data secure?', a:'All resume files are stored encrypted in AWS S3 (AES-256) and your data is never shared with third parties or used to train our models. PII is anonymised before being processed by any LLM.' },
  { q:'What AI models power CareerCopilot?', a:'We use Google Gemini for narrative generation (summaries, feedback, model answers) and our own deterministic engines for scoring (ATS, skill matching, answer evaluation). This combination ensures scores are stable and reproducible.' },
  { q:'Can I use it for campus placements?', a:'Yes — the Campus plan is specifically designed for students. It includes aptitude Q&A, DBMS/OS/CN/OOP topic coverage, company-specific prep for mass recruiters (TCS, Infosys, Wipro), and HR question coaching.' },
]

function FAQ() {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <section id="faq" className="py-32">
      <div className="section-container max-w-3xl">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once:true, margin:'-80px' }} variants={stagger}>
          <motion.div variants={fadeUp} className="text-center mb-16">
            <div className="badge mb-4">FAQ</div>
            <h2 className="text-section font-display font-bold text-white mb-4">Common <span className="text-gradient">questions</span></h2>
          </motion.div>
          <div className="space-y-3">
            {FAQS.map(({ q, a }, i) => (
              <motion.div key={i} variants={fadeUp} custom={i} className="glass rounded-xl overflow-hidden">
                <button onClick={() => setOpen(open===i ? null : i)} className="w-full flex items-center justify-between p-5 text-left">
                  <span className="font-display font-semibold text-white text-sm pr-4">{q}</span>
                  <ChevronDown className={`w-5 h-5 text-star-50 flex-shrink-0 transition-transform duration-300 ${open===i ? 'rotate-180' : ''}`} />
                </button>
                <AnimatePresence>
                  {open===i && (
                    <motion.div initial={{ height:0, opacity:0 }} animate={{ height:'auto', opacity:1 }} exit={{ height:0, opacity:0 }} transition={{ duration:0.25 }}>
                      <p className="text-sm text-star-70 leading-relaxed px-5 pb-5">{a}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ── CTA Banner ─────────────────────────────────────────────────────────────
function CTABanner() {
  return (
    <section className="py-24">
      <div className="section-container">
        <motion.div initial={{ opacity:0, y:40 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ duration:0.6 }}
          className="relative rounded-3xl overflow-hidden p-12 text-center"
          style={{ background:'linear-gradient(135deg,rgba(91,79,232,0.25) 0%,rgba(0,212,255,0.1) 100%)', border:'1px solid rgba(91,79,232,0.3)' }}>
          <div className="absolute inset-0 bg-grid opacity-30" />
          <div className="relative">
            <h2 className="font-display font-bold text-4xl text-white mb-4">Ready to land your <span className="text-gradient">dream role?</span></h2>
            <p className="text-star-70 text-base mb-8 max-w-xl mx-auto">Join 500+ candidates who used CareerCopilot AI to sharpen their resume, close skill gaps, and ace their interviews.</p>
            <Link to="/login" className="btn-primary text-base px-10 py-4 inline-flex">
              Start for free — it takes 30 seconds
              <ArrowRight className="w-5 h-5" />
            </Link>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ── Footer ─────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="border-t border-white/5 py-12">
      <div className="section-container flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background:'linear-gradient(135deg,#5B4FE8,#00D4FF)' }}>
            <Brain className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-display font-bold text-white">CareerCopilot <span className="text-gradient">AI</span></span>
        </div>
        <p className="text-xs text-star-50">© 2025 CareerCopilot AI. Built with ❤️ for placement aspirants.</p>
        <div className="flex gap-6">
          {['Privacy','Terms','Contact'].map(l => <a key={l} href="#" className="text-xs text-star-50 hover:text-white transition-colors">{l}</a>)}
        </div>
      </div>
    </footer>
  )
}

// ── Main Export ────────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <div className="bg-void min-h-screen">
      <Navbar />
      <Hero />
      <Features />
      <Agents />
      <Testimonials />
      <Pricing />
      <FAQ />
      <CTABanner />
      <Footer />
    </div>
  )
}
