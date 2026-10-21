/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        // ── Core palette ───────────────────────────────────────────────────
        void:    { DEFAULT: "#04050A", 800: "#08090F", 700: "#0D0E17", 600: "#12141F" },
        navy:    { DEFAULT: "#0A0B14", 800: "#0F1020", 700: "#14162A", 600: "#1A1D35" },
        ink:     { DEFAULT: "#1C1E30", light: "#252842" },
        // ── Accent system ──────────────────────────────────────────────────
        indigo:  { DEFAULT: "#5B4FE8", bright: "#7B6FFF", dim: "#3D33B0", glow: "#5B4FE840" },
        cyan:    { DEFAULT: "#00D4FF", bright: "#40E4FF", dim: "#0099BB", glow: "#00D4FF30" },
        violet:  { DEFAULT: "#A855F7", bright: "#C084FC", dim: "#7C3AED" },
        emerald: { DEFAULT: "#10D97A", bright: "#34EF95", dim: "#059A52" },
        amber:   { DEFAULT: "#F59E0B", bright: "#FBBF24", dim: "#B45309" },
        rose:    { DEFAULT: "#F43F5E", bright: "#FB7185", dim: "#BE123C" },
        // ── Text ──────────────────────────────────────────────────────────
        star:    { DEFAULT: "#FFFFFF", 90: "#E8E9F5", 70: "#9FA3C2", 50: "#636685", 30: "#3A3D5C" },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "system-ui", "sans-serif"],
        body:    ["'Inter'", "system-ui", "sans-serif"],
        mono:    ["'JetBrains Mono'", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "1.4", letterSpacing: "0.08em" }],
        "xs":  ["12px", { lineHeight: "1.5", letterSpacing: "0.04em" }],
        "sm":  ["13px", { lineHeight: "1.6" }],
        "base":["15px", { lineHeight: "1.7" }],
        "lg":  ["17px", { lineHeight: "1.6" }],
        "xl":  ["20px", { lineHeight: "1.5" }],
        "2xl": ["24px", { lineHeight: "1.4" }],
        "3xl": ["30px", { lineHeight: "1.3" }],
        "4xl": ["38px", { lineHeight: "1.2" }],
        "5xl": ["48px", { lineHeight: "1.1" }],
        "6xl": ["60px", { lineHeight: "1.05" }],
        "7xl": ["76px", { lineHeight: "1.0" }],
      },
      backgroundImage: {
        "grid-void":    "radial-gradient(circle at 1px 1px, rgba(91,79,232,0.15) 1px, transparent 0)",
        "hero-radial":  "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(91,79,232,0.35) 0%, transparent 60%)",
        "card-shine":   "linear-gradient(135deg, rgba(255,255,255,0.06) 0%, transparent 50%, rgba(255,255,255,0.02) 100%)",
        "gradient-brand": "linear-gradient(135deg, #5B4FE8 0%, #00D4FF 100%)",
        "gradient-warm":  "linear-gradient(135deg, #A855F7 0%, #5B4FE8 50%, #00D4FF 100%)",
        "gradient-glow":  "linear-gradient(180deg, rgba(91,79,232,0.2) 0%, transparent 100%)",
      },
      backgroundSize: {
        "grid-32": "32px 32px",
      },
      boxShadow: {
        "glass":       "0 0 0 1px rgba(255,255,255,0.06), 0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)",
        "glass-hover": "0 0 0 1px rgba(91,79,232,0.4), 0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.10)",
        "glow-indigo": "0 0 40px rgba(91,79,232,0.4), 0 0 80px rgba(91,79,232,0.15)",
        "glow-cyan":   "0 0 40px rgba(0,212,255,0.3), 0 0 80px rgba(0,212,255,0.1)",
        "glow-sm":     "0 0 20px rgba(91,79,232,0.3)",
        "card":        "0 2px 8px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.6)",
        "card-hover":  "0 8px 32px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.6)",
      },
      animation: {
        "float":        "float 6s ease-in-out infinite",
        "pulse-slow":   "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "shimmer":      "shimmer 2s linear infinite",
        "scan":         "scan 3s ease-in-out infinite",
        "orbit":        "orbit 20s linear infinite",
        "glow-pulse":   "glowPulse 3s ease-in-out infinite",
        "typing":       "typing 1.2s steps(3) infinite",
      },
      keyframes: {
        float:     { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-12px)" } },
        shimmer:   { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        scan:      { "0%,100%": { opacity: "0.4", top: "0%" }, "50%": { opacity: "1", top: "100%" } },
        orbit:     { "0%": { transform: "rotate(0deg)" }, "100%": { transform: "rotate(360deg)" } },
        glowPulse: { "0%,100%": { opacity: "0.6" }, "50%": { opacity: "1" } },
        typing:    { "0%": { content: '"."' }, "33%": { content: '".."' }, "66%": { content: '"..."' } },
      },
      backdropBlur: { xs: "2px", "4xl": "72px" },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
    },
  },
  plugins: [],
}
