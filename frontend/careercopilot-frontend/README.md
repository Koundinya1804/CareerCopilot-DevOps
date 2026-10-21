# CareerCopilot AI — Frontend

Premium dark-futuristic SaaS frontend for the CareerCopilot AI multi-agent platform.

## Tech Stack
- **React 18** + TypeScript + Vite
- **Tailwind CSS** — custom dark theme (void/navy palette, indigo/cyan gradient accents)
- **Framer Motion** — page transitions, scroll-triggered animations, micro-interactions
- **Zustand** — auth state with localStorage persistence
- **React Query** — server state caching
- **Recharts** — score rings, radar charts, progress visualisations
- **react-dropzone** — resume upload
- **Lucide React** — icon system

## Setup

```bash
npm install
cp .env.example .env   # set VITE_API_URL if backend isn't on localhost:8000
npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` (see `vite.config.ts`).

## Pages

| Route         | Page                | Description |
|---------------|----------------------|--------------|
| `/`           | LandingPage          | Hero, features, agent showcase, testimonials, pricing, FAQ |
| `/login`      | LoginPage            | Combined login/register with glassmorphism card |
| `/dashboard`  | DashboardPage        | Analytics overview, score rings, quick actions, activity feed |
| `/resume`     | ResumePage           | Drag-drop upload, ATS score ring, keyword/skill breakdown |
| `/skill-gap`  | SkillGapPage         | Role selector, gap match %, learning priorities |
| `/career`     | CareerPage           | Skill/interest input, domain radar chart, top role rankings |
| `/interview`  | InterviewPage        | Mode/difficulty setup → live Q&A → final report with grade |
| `/chat`       | ChatPage             | Multi-agent chat interface with citations and suggested actions |

## Design System

Defined in `tailwind.config.js` and `src/index.css`:

- **Palette**: `void` (#04050A background) → `navy` → `ink`, accents `indigo` (#5B4FE8) + `cyan` (#00D4FF) + `violet`/`emerald`/`amber`/`rose` for status colors
- **Typography**: Space Grotesk (display/headings) + Inter (body) + JetBrains Mono (labels/code)
- **Glassmorphism**: `.glass` utility class — `backdrop-blur(20px)` + subtle border + inset highlight
- **Glow effects**: `shadow-glow-indigo`, `shadow-glow-cyan` for CTA emphasis
- **Animations**: `fadeUp`/`stagger`/`scaleIn` Framer Motion variants in `src/utils/index.ts`

## Backend Integration

All API calls go through `src/api/index.ts`, which wraps `axios` with:
- Automatic JWT injection via request interceptor
- Automatic logout on 401 via response interceptor
- Typed methods for every backend module: `authApi`, `resumeApi`, `skillGapApi`, `careerApi`, `interviewApi`, `agentApi`

Matches the CareerCopilot AI FastAPI backend's `/api/v1/*` routes exactly.

## Build for Production

```bash
npm run build   # outputs to dist/
npm run preview # preview the production build locally
```
