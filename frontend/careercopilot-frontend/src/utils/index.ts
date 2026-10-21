import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }

export const fadeUp = {
  hidden:  { opacity: 0, y: 24 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.5, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] } }),
}

export const fadeIn = {
  hidden:  { opacity: 0 },
  visible: (i = 0) => ({ opacity: 1, transition: { duration: 0.4, delay: i * 0.08 } }),
}

export const scaleIn = {
  hidden:  { opacity: 0, scale: 0.92 },
  visible: (i = 0) => ({ opacity: 1, scale: 1, transition: { duration: 0.4, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] } }),
}

export const stagger = { visible: { transition: { staggerChildren: 0.1 } } }

export function formatScore(n: number) { return Math.round(n) }
export function gradeColor(grade: string) {
  return { A: '#10D97A', B: '#00D4FF', C: '#F59E0B', D: '#F97316', F: '#F43F5E' }[grade] ?? '#9FA3C2'
}
export function severityColor(s: string) {
  return { none: '#10D97A', minor: '#00D4FF', moderate: '#F59E0B', major: '#F97316', critical: '#F43F5E' }[s] ?? '#9FA3C2'
}
export function truncate(str: string, n: number) { return str.length > n ? str.slice(0, n) + '…' : str }
