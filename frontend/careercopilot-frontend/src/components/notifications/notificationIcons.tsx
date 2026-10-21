import {
  FileText, Target, TrendingUp, Mic, Database, Upload, Layers,
  AlertTriangle, ShieldAlert, LogIn, AlertCircle, CalendarClock,
  GraduationCap, Bell,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// Maps the `icon` string stored on each notification (set server-side from
// NotificationType) to the lucide-react component that renders it.
const ICON_MAP: Record<string, LucideIcon> = {
  FileText, Target, TrendingUp, Mic, Database, Upload, Layers,
  AlertTriangle, ShieldAlert, LogIn, AlertCircle, CalendarClock, GraduationCap,
}

export function resolveNotificationIcon(icon: string | null | undefined): LucideIcon {
  if (!icon) return Bell
  return ICON_MAP[icon] ?? Bell
}

// Priority → accent color, matches the app's existing badge palette.
export function priorityColor(priority: string): string {
  return (
    { low: '#636685', normal: '#00D4FF', high: '#F59E0B', urgent: '#F43F5E' }[priority] ??
    '#00D4FF'
  )
}
