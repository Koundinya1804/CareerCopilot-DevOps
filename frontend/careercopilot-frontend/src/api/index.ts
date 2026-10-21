/**
 * src/api/index.ts
 * Central API client — Zustand-based auth, single source of truth.
 */

import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/authStore'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60_000,
})

// Attach JWT from Zustand on every request
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token ?? localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-refresh on 401
api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      try {
        const refreshToken =
          useAuthStore.getState().refreshToken ?? localStorage.getItem('refresh_token')
        const { data } = await axios.post(`${BASE_URL}/auth/refresh`, { refresh_token: refreshToken })
        const newToken: string = data?.data?.access_token ?? data?.access_token
        const { user, refreshToken: existingRefresh } = useAuthStore.getState()
        useAuthStore.getState().setAuth(newToken, existingRefresh ?? '', user!)
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      } catch {
        useAuthStore.getState().logout()
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  register: (data: { full_name: string; email: string; password: string }) =>
    api.post('/auth/register', data),
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data),
  refresh: (refresh_token: string) =>
    api.post('/auth/refresh', { refresh_token }),
  logout: (refresh_token: string) =>
    api.post('/auth/logout', { refresh_token }),
  me: () => api.get('/users/me'),
}

// ── Resume ────────────────────────────────────────────────────────────────────

export const resumeApi = {
  uploadAndAnalyse: (file: File, targetRole?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (targetRole) fd.append('target_role', targetRole)
    return api.post('/resume/upload-and-analyse', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list:      ()          => api.get('/resume/'),
  getOne:    (id: number) => api.get(`/resume/${id}`),
  getReport: (id: number) => api.get(`/resume/${id}/report`),
  setPrimary:(id: number) => api.put(`/resume/${id}/primary`),
  delete:    (id: number) => api.delete(`/resume/${id}`),
}

// ── Skill Gap ─────────────────────────────────────────────────────────────────

export const skillGapApi = {
  listRoles: () => api.get('/skill-gap/roles'),
  analyseFromText: (data: { resume_text: string; role_key: string; target_company?: string }) =>
    api.post('/skill-gap/analyse/text', data),
  listReports:  () =>          api.get('/skill-gap/reports'),
  getReport:    (id: number) => api.get(`/skill-gap/reports/${id}`),
  deleteReport: (id: number) => api.delete(`/skill-gap/reports/${id}`),
}

// ── Career ────────────────────────────────────────────────────────────────────

export const careerApi = {
  listRoles: () => api.get('/career/roles'),
  recommend: (data: {
    skills: string[]; interests: string[]; years_experience: number
    education_level: string; resume_text?: string
  }) => api.post('/career/recommend/profile', data),
  listReports:  () =>          api.get('/career/reports'),
  getReport:    (id: number) => api.get(`/career/reports/${id}`),
  deleteReport: (id: number) => api.delete(`/career/reports/${id}`),
}

// ── Interview ─────────────────────────────────────────────────────────────────

export const interviewApi = {
  startSession: (data: {
    mode: string; difficulty: string; target_role?: string
    target_company?: string; total_questions: number
  }) => api.post('/interview/sessions', data),
  listSessions:       ()             => api.get('/interview/sessions'),
  getSession:         (id: number)   => api.get(`/interview/sessions/${id}`),
  getCurrentQuestion: (id: number)   => api.get(`/interview/sessions/${id}/current-question`),
  submitAnswer: (id: number, data: { question_number: number; answer_text: string; time_taken_seconds?: number }) =>
    api.post(`/interview/sessions/${id}/answer`, data),
  completeSession: (id: number) => api.post(`/interview/sessions/${id}/complete`),
  getReport:       (id: number) => api.get(`/interview/sessions/${id}/report`),
}

// ── RAG ───────────────────────────────────────────────────────────────────────

export const ragApi = {
  chat: (data: { query: string; categories?: string[]; chat_history?: { role: string; content: string }[] }) =>
    api.post('/rag/chat', data),
  getCategories: () => api.get('/rag/categories'),
}

// ── Agent (supervisor) ────────────────────────────────────────────────────────

export const agentApi = {
  chat: (data: {
    query: string; session_id?: string | null
    target_role?: string; target_company?: string; include_history?: boolean
  }) => api.post('/agent/chat', data),
  classify: (query: string) => api.post('/agent/classify', { query }),
  getSession:  (id: string) => api.get(`/agent/sessions/${id}`),
  listSessions: (limit = 20) => api.get('/agent/sessions', { params: { limit } }),
  getMessages: (id: string) => api.get(`/agent/sessions/${id}/messages`),
  clearSession: (id: string) => api.delete(`/agent/sessions/${id}`),
  getMemory:   () => api.get('/agent/memory'),
  clearMemory: () => api.delete('/agent/memory'),
}

// ── Notifications ─────────────────────────────────────────────────────────────

export const notificationApi = {
  list: (params: {
    page?: number; page_size?: number; unread_only?: boolean
    type?: string; search?: string
  }) => api.get('/notifications', { params }),
  unreadCount: () => api.get('/notifications/unread-count'),
  markRead:    (id: number) => api.patch(`/notifications/${id}/read`),
  markAllRead: () => api.post('/notifications/mark-all-read'),
  delete:      (id: number) => api.delete(`/notifications/${id}`),
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export const adminApi = {
  // ── Overview (existing) ────────────────────────────────────────────────────
  getOverview: () => api.get('/admin/overview'),

  // ── Users (existing + new role/delete/reset actions) ──────────────────────
  getUsers: (params: { page?: number; page_size?: number; search?: string }) =>
    api.get('/admin/users', { params }),
  getUserDetail:    (userId: number) => api.get(`/admin/users/${userId}`),
  updateUserStatus: (userId: number, is_active: boolean) =>
    api.patch(`/admin/users/${userId}/status`, null, { params: { is_active } }),

  // Role management (from admin_extended.py)
  promoteUser:   (userId: number) => api.patch(`/admin/users/${userId}/promote`),
  demoteUser:    (userId: number) => api.patch(`/admin/users/${userId}/demote`),
  deleteUser:    (userId: number) => api.delete(`/admin/users/${userId}`),
  resetPassword: (userId: number, new_password: string) =>
    api.post(`/admin/users/${userId}/reset-password`, { new_password }),
  getUserActivity: (userId: number, limit = 20) =>
    api.get(`/admin/users/${userId}/activity`, { params: { limit } }),

  // ── Agent usage analytics (existing) ──────────────────────────────────────
  getAgentSummary: () => api.get('/admin/agent-usage/summary'),
  getAgentByType:  () => api.get('/admin/agent-usage/by-agent'),
  getAgentDaily:   (days = 30) => api.get('/admin/agent-usage/daily', { params: { days } }),
  getAgentWeekly:  (weeks = 12) => api.get('/admin/agent-usage/weekly', { params: { weeks } }),
  getAgentMonthly: (months = 12) => api.get('/admin/agent-usage/monthly', { params: { months } }),
  getTopUsers:     (limit = 10) => api.get('/admin/agent-usage/top-users', { params: { limit } }),
  getAgentLogs: (params: { page?: number; page_size?: number; agent_name?: string; status?: string }) =>
    api.get('/admin/agent-usage/logs', { params }),

  // ── KB documents (existing + new from admin_extended.py) ──────────────────
  getDocuments:       () => api.get('/admin/documents'),
  getMostUploadedDocuments: () => api.get('/admin/documents/most-uploaded'),
  getEmbeddingStatus: () => api.get('/admin/embedding-status'),
  listKbDocuments:    (category: string) => api.get(`/admin/kb/documents/${category}`),
  deleteKbDocument:   (category: string, filename: string) =>
    api.delete(`/admin/kb/documents/${category}/${filename}`),
  reindexKbCategory:  (category: string) => api.post(`/admin/kb/reindex/${category}`),
  uploadKbDocument:   (category: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/admin/kb/upload/${category}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  renameKbDocument:  (category: string, filename: string, new_filename: string) =>
    api.patch(`/admin/kb/documents/${category}/${encodeURIComponent(filename)}/rename`, { new_filename }),
  reindexKbDocument: (category: string, filename: string) =>
    api.post(`/admin/kb/documents/${category}/${encodeURIComponent(filename)}/reindex`),
  previewKbDocument: (category: string, filename: string) =>
    api.get(`/admin/kb/documents/${category}/${encodeURIComponent(filename)}/preview`),
  reindexAllCategories: (replace = false) =>
    api.post('/rag/admin/ingest/all', null, { params: { replace } }),

  // ── ChromaDB (from admin_extended.py) ─────────────────────────────────────
  getChromaCollections:     ()              => api.get('/admin/chroma/collections'),
  reindexChromaCollection:  (cat: string)   => api.post(`/admin/chroma/collections/${cat}/reindex`),
  deleteChromaCollection:   (cat: string)   => api.delete(`/admin/chroma/collections/${cat}`),
  viewChromaChunks: (cat: string, page = 1, page_size = 25) =>
    api.get(`/admin/chroma/collections/${cat}/chunks`, { params: { page, page_size } }),
  deleteOrphanEmbeddings: (cat: string) =>
    api.post(`/admin/chroma/collections/${cat}/delete-orphans`),
  getChromaDocuments: (cat: string) => api.get(`/admin/kb/chromadocs/${cat}`),

  // ── System health (from admin_extended.py) ────────────────────────────────
  getFullHealth: () => api.get('/admin/health/full'),

  // ── Settings (from admin_extended.py) ─────────────────────────────────────
  getSettings:    () => api.get('/admin/settings'),
  updateSettings: (data: Record<string, unknown>) => api.patch('/admin/settings', data),

  // ── Logs (from admin_extended.py) ─────────────────────────────────────────
  getLogs: (params: { page?: number; page_size?: number; level?: string; search?: string }) =>
    api.get('/admin/logs', { params }),
}
