/**
 * src/pages/admin/AdminKnowledgePage.tsx
 *
 * Complete Knowledge Base management page.
 *
 * Features:
 *  - Category selector (all 9 KB categories)
 *  - Drag-and-drop + click-to-browse multi-file upload (PDF/DOCX/TXT/MD)
 *  - Per-file upload + indexing progress
 *  - ChromaDB document list (actual indexed docs with chunk counts)
 *  - Disk-file list (uploaded files awaiting or post-indexing)
 *  - Document preview (text extraction shown in modal)
 *  - Delete document (removes file + ChromaDB embeddings)
 *  - Re-index category button
 *  - Live stats: doc count, chunk count, collection status
 *
 * Backend endpoints used:
 *  POST   /api/v1/rag/admin/upload/{category}        — upload + ingest in one call
 *  GET    /api/v1/admin/kb/chromadocs/{category}     — list indexed docs with chunks
 *  GET    /api/v1/admin/kb/documents/{category}      — list disk files
 *  DELETE /api/v1/admin/kb/documents/{category}/{fn} — delete file + embeddings
 *  POST   /api/v1/admin/kb/reindex/{category}        — rebuild entire category
 *  GET    /api/v1/admin/documents                    — overall KB stats
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Upload, FileText, Trash2, RefreshCw, Eye, X,
  CheckCircle2, AlertCircle, Loader2, ChevronDown,
  Database, BookOpen, File, FileArchive, Search, Pencil,
} from 'lucide-react'
import { api, adminApi } from '@/api'
import { fadeUp, cn } from '@/utils'

// ── KB Categories ─────────────────────────────────────────────────────────────

const KB_CATEGORIES = [
  { key: 'dbms',              label: 'Database Management Systems', icon: '🗄️',  color: '#6366F1' },
  { key: 'operating_systems', label: 'Operating Systems',           icon: '💻',  color: '#8B5CF6' },
  { key: 'computer_networks', label: 'Computer Networks',           icon: '🌐',  color: '#06B6D4' },
  { key: 'oop',               label: 'Object-Oriented Programming', icon: '🏗️',  color: '#10B981' },
  { key: 'java',              label: 'Java',                        icon: '☕',   color: '#F59E0B' },
  { key: 'python',            label: 'Python',                      icon: '🐍',  color: '#3B82F6' },
  { key: 'aptitude',          label: 'Aptitude & Reasoning',        icon: '🧮',  color: '#EF4444' },
  { key: 'hr_questions',      label: 'HR Interview Questions',      icon: '👔',  color: '#EC4899' },
  { key: 'company_guides',    label: 'Company Guides',              icon: '🏢',  color: '#F97316' },
] as const

type CategoryKey = typeof KB_CATEGORIES[number]['key']

const ACCEPTED_TYPES = '.pdf,.docx,.doc,.txt,.md'
const ACCEPTED_MIME  = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
  'text/plain',
  'text/markdown',
]

// ── Types ─────────────────────────────────────────────────────────────────────

interface IndexedDoc  { source: string; chunks: number; avg_chunk_chars?: number }
interface DiskFile    { filename: string; size_bytes: number; uploaded_at: string; extension: string }

type FileStatus = 'pending' | 'uploading' | 'indexing' | 'done' | 'error'

interface UploadItem {
  id:       string
  file:     File
  status:   FileStatus
  progress: number   // 0-100
  error?:   string
  chunks?:  number
}

// ── File icon helper ──────────────────────────────────────────────────────────

function FileIcon({ ext, size = 16 }: { ext: string; size?: number }) {
  const cls = `w-${size === 16 ? 4 : 5} h-${size === 16 ? 4 : 5} flex-shrink-0`
  if (ext === '.pdf')           return <FileText    className={cls} style={{ color: '#F43F5E' }} />
  if (['.docx','.doc'].includes(ext)) return <FileArchive className={cls} style={{ color: '#3B82F6' }} />
  if (['.md'].includes(ext))    return <FileText    className={cls} style={{ color: '#10B981' }} />
  return <File className={cls} style={{ color: '#9CA3AF' }} />
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar({ value, color = '#5B4FE8' }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
      <motion.div className="h-full rounded-full"
        initial={{ width: 0 }}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        style={{ background: color }}
      />
    </div>
  )
}

// ── Preview Modal ─────────────────────────────────────────────────────────────

function PreviewModal({ doc, category, onClose }: { doc: IndexedDoc | DiskFile | null; category: string; onClose: () => void }) {
  const [text, setText]         = useState<string | null>(null)
  const [truncated, setTruncated] = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const name = doc ? ('source' in doc ? doc.source : doc.filename) : ''

  useEffect(() => {
    if (!doc) return
    setText(null); setError(null); setLoading(true)
    adminApi.previewKbDocument(category, name)
      .then(res => {
        const data = res.data?.data ?? res.data
        setText(data?.text ?? '')
        setTruncated(!!data?.truncated)
      })
      .catch(e => setError(e.response?.data?.detail ?? 'Preview unavailable — the original file may not be stored on disk.'))
      .finally(() => setLoading(false))
  }, [doc, category, name])

  if (!doc) return null
  const chunks = 'chunks' in doc ? doc.chunks : null
  const avgChunkChars = 'avg_chunk_chars' in doc ? doc.avg_chunk_chars : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="glass rounded-2xl border border-white/10 w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 flex-shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <FileIcon ext={name.slice(name.lastIndexOf('.'))} size={20} />
            <p className="text-sm font-semibold text-white truncate">{name}</p>
          </div>
          <button onClick={onClose} className="text-star-50 hover:text-white ml-2 flex-shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-5 py-5 space-y-3 overflow-y-auto">
          <div className="grid grid-cols-3 gap-3">
            {chunks != null && (
              <div className="p-3 rounded-xl bg-white/3 border border-white/8">
                <p className="text-2xs text-star-50 uppercase tracking-wide mb-1">Chunks</p>
                <p className="text-xl font-mono font-bold text-white">{chunks}</p>
              </div>
            )}
            {avgChunkChars != null && (
              <div className="p-3 rounded-xl bg-white/3 border border-white/8">
                <p className="text-2xs text-star-50 uppercase tracking-wide mb-1">Avg Chunk Size</p>
                <p className="text-xl font-mono font-bold text-white">{avgChunkChars}c</p>
              </div>
            )}
            {'size_bytes' in doc && (
              <div className="p-3 rounded-xl bg-white/3 border border-white/8">
                <p className="text-2xs text-star-50 uppercase tracking-wide mb-1">File Size</p>
                <p className="text-xl font-mono font-bold text-white">
                  {doc.size_bytes < 1024 ? `${doc.size_bytes} B`
                    : doc.size_bytes < 1048576 ? `${(doc.size_bytes / 1024).toFixed(1)} KB`
                    : `${(doc.size_bytes / 1048576).toFixed(1)} MB`}
                </p>
              </div>
            )}
          </div>
          {'uploaded_at' in doc && (
            <div className="p-3 rounded-xl bg-white/3 border border-white/8">
              <p className="text-2xs text-star-50 uppercase tracking-wide mb-1">Uploaded</p>
              <p className="text-sm text-white">{new Date(doc.uploaded_at).toLocaleString()}</p>
            </div>
          )}

          <div className="p-3 rounded-xl bg-white/3 border border-white/8">
            <p className="text-2xs text-star-50 uppercase tracking-wide mb-2">Extracted Text</p>
            {loading && (
              <div className="flex items-center gap-2 text-star-50 text-sm py-4 justify-center">
                <Loader2 className="w-4 h-4 animate-spin" /> Extracting…
              </div>
            )}
            {error && <p className="text-sm text-rose-400">{error}</p>}
            {!loading && !error && (
              <>
                <p className="text-sm text-star-70 whitespace-pre-wrap max-h-64 overflow-y-auto font-mono leading-relaxed">
                  {text || 'No extractable text found.'}
                </p>
                {truncated && <p className="text-2xs text-star-30 mt-2">Preview truncated — showing first portion only.</p>}
              </>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdminKnowledgePage() {
  const [selectedCat,   setSelectedCat]   = useState<CategoryKey>('dbms')
  const [showCatMenu,   setShowCatMenu]   = useState(false)
  const [uploads,       setUploads]       = useState<UploadItem[]>([])
  const [isDragging,    setIsDragging]    = useState(false)
  const [indexedDocs,   setIndexedDocs]   = useState<IndexedDoc[]>([])
  const [diskFiles,     setDiskFiles]     = useState<DiskFile[]>([])
  const [loadingDocs,   setLoadingDocs]   = useState(false)
  const [reindexing,    setReindexing]    = useState(false)
  const [deletingFile,  setDeletingFile]  = useState<string | null>(null)
  const [previewDoc,    setPreviewDoc]    = useState<IndexedDoc | DiskFile | null>(null)
  const [toast,         setToast]         = useState<{ msg: string; ok: boolean } | null>(null)
  const [search,        setSearch]        = useState('')
  const [renamingFile,  setRenamingFile]  = useState<string | null>(null)
  const [reindexingFile, setReindexingFile] = useState<string | null>(null)
  const [reindexingAll, setReindexingAll] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const cat = KB_CATEGORIES.find(c => c.key === selectedCat)!

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 4000)
  }

  // ── Load indexed docs + disk files ────────────────────────────────────────

  const loadDocs = useCallback(async () => {
    setLoadingDocs(true)
    try {
      const [chromaRes, diskRes] = await Promise.allSettled([
        api.get(`/admin/kb/chromadocs/${selectedCat}`),
        api.get(`/admin/kb/documents/${selectedCat}`),
      ])
      if (chromaRes.status === 'fulfilled') {
        setIndexedDocs((chromaRes.value.data?.data ?? chromaRes.value.data)?.documents ?? [])
      }
      if (diskRes.status === 'fulfilled') {
        setDiskFiles((diskRes.value.data?.data ?? diskRes.value.data)?.documents ?? [])
      }
    } finally {
      setLoadingDocs(false)
    }
  }, [selectedCat])

  useEffect(() => {
    setIndexedDocs([])
    setDiskFiles([])
    loadDocs()
  }, [loadDocs])

  // ── Upload logic ───────────────────────────────────────────────────────────

  const processFiles = (files: FileList | File[]) => {
    const arr = Array.from(files)
    const valid = arr.filter(f => {
      const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
      return ACCEPTED_MIME.includes(f.type) || ['.pdf','.docx','.doc','.txt','.md'].includes(ext)
    })
    if (valid.length === 0) {
      showToast('No valid files. Accepted: PDF, DOCX, TXT, MD', false)
      return
    }
    if (valid.length < arr.length) {
      showToast(`${arr.length - valid.length} file(s) skipped — unsupported type`, false)
    }

    const items: UploadItem[] = valid.map(f => ({
      id:       `${Date.now()}-${Math.random()}`,
      file:     f,
      status:   'pending',
      progress: 0,
    }))
    setUploads(prev => [...items, ...prev])

    // Upload each file sequentially
    items.forEach(item => uploadFile(item))
  }

  const uploadFile = async (item: UploadItem) => {
    // 1. Mark uploading
    setUploads(prev => prev.map(u => u.id === item.id
      ? { ...u, status: 'uploading', progress: 10 }
      : u))

    const fd = new FormData()
    fd.append('file', item.file)

    try {
      // Simulate upload progress (XHR progress events aren't easy with axios interceptors)
      const progressTimer = setInterval(() => {
        setUploads(prev => prev.map(u => u.id === item.id && u.status === 'uploading'
          ? { ...u, progress: Math.min(u.progress + 15, 70) }
          : u))
      }, 300)

      // POST to /rag/admin/upload/{category} — this uploads AND ingests in one call
      const res = await api.post(`/rag/admin/upload/${selectedCat}`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      clearInterval(progressTimer)

      const data  = res.data?.data ?? res.data
      const chunks = data?.chunks_indexed ?? data?.chunks_stored ?? data?.chunks ?? 0

      // Mark indexing briefly then done
      setUploads(prev => prev.map(u => u.id === item.id
        ? { ...u, status: 'indexing', progress: 90 }
        : u))

      await new Promise(r => setTimeout(r, 600))

      setUploads(prev => prev.map(u => u.id === item.id
        ? { ...u, status: 'done', progress: 100, chunks }
        : u))

      if (data?.duplicate_of) {
        showToast(`Note: "${item.file.name}" has identical content to existing "${data.duplicate_of}"`, false)
      } else if (data?.name_overwritten) {
        showToast(`"${item.file.name}" already existed and was overwritten`, false)
      }

      // Refresh doc lists
      await loadDocs()

    } catch (e: any) {
      const msg = e.response?.data?.detail ?? e.response?.data?.message ?? 'Upload failed'
      setUploads(prev => prev.map(u => u.id === item.id
        ? { ...u, status: 'error', progress: 0, error: msg }
        : u))
      showToast(`Failed: ${item.file.name} — ${msg}`, false)
    }
  }

  const clearDoneUploads = () =>
    setUploads(prev => prev.filter(u => u.status !== 'done'))

  // ── Drag and drop ─────────────────────────────────────────────────────────

  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true)  }
  const onDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false) }
  const onDrop      = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    processFiles(e.dataTransfer.files)
  }

  // ── Delete ─────────────────────────────────────────────────────────────────

  const deleteDocument = async (filename: string) => {
    if (!confirm(`Delete "${filename}" and remove its embeddings from ChromaDB?`)) return
    setDeletingFile(filename)
    try {
      const res = await adminApi.deleteKbDocument(selectedCat, filename)
      const data = res.data?.data ?? res.data
      showToast(`Deleted "${filename}" — ${data?.chunks_removed ?? 0} chunk(s) removed`)
      await loadDocs()
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Delete failed', false)
    } finally {
      setDeletingFile(null)
    }
  }

  // ── Reindex ────────────────────────────────────────────────────────────────

  const reindex = async () => {
    setReindexing(true)
    try {
      const res  = await adminApi.reindexKbCategory(selectedCat)
      const data = res.data?.data ?? res.data
      showToast(`Reindexed '${cat.label}' — ${data?.chunks_indexed ?? 0} chunks`)
      await loadDocs()
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Reindex failed', false)
    } finally {
      setReindexing(false)
    }
  }

  // ── Rename ─────────────────────────────────────────────────────────────────

  const renameDocument = async (filename: string) => {
    const newName = window.prompt(`Rename "${filename}" to:`, filename)
    if (!newName || newName === filename) return
    setRenamingFile(filename)
    try {
      const res  = await adminApi.renameKbDocument(selectedCat, filename, newName)
      const data = res.data?.data ?? res.data
      showToast(`Renamed to "${data?.new_filename ?? newName}"`)
      await loadDocs()
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Rename failed', false)
    } finally {
      setRenamingFile(null)
    }
  }

  // ── Single-document re-index ──────────────────────────────────────────────

  const reindexDocument = async (filename: string) => {
    setReindexingFile(filename)
    try {
      const res  = await adminApi.reindexKbDocument(selectedCat, filename)
      const data = res.data?.data ?? res.data
      showToast(`Re-indexed "${filename}" — ${data?.chunks_stored ?? 0} chunks`)
      await loadDocs()
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Re-index failed', false)
    } finally {
      setReindexingFile(null)
    }
  }

  // ── Re-index every category ───────────────────────────────────────────────

  const reindexAll = async () => {
    if (!confirm('Re-index ALL knowledge base categories? This may take a few minutes.')) return
    setReindexingAll(true)
    try {
      const res  = await adminApi.reindexAllCategories(false)
      const data = res.data?.data ?? res.data
      showToast(`Re-indexed all categories — ${data?.total_chunks ?? 0} total chunks`)
      await loadDocs()
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Re-index all failed', false)
    } finally {
      setReindexingAll(false)
    }
  }

  const totalChunks = indexedDocs.reduce((s, d) => s + d.chunks, 0)
  const activeUploads = uploads.filter(u => u.status === 'uploading' || u.status === 'indexing')
  const doneUploads   = uploads.filter(u => u.status === 'done')

  // ── Search filtering (client-side — full lists are already loaded) ────────
  const q = search.trim().toLowerCase()
  const filteredIndexedDocs = q ? indexedDocs.filter(d => d.source.toLowerCase().includes(q)) : indexedDocs
  const filteredDiskFiles   = q ? diskFiles.filter(f => f.filename.toLowerCase().includes(q)) : diskFiles
  const diskFilenames = new Set(diskFiles.map(f => f.filename))

  return (
    <div className="p-6 space-y-6">

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl text-sm border shadow-xl ${
              toast.ok
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25'
                : 'bg-rose-500/15 text-rose-300 border-rose-500/25'
            }`}>
            {toast.ok ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Preview modal */}
      <AnimatePresence>
        {previewDoc && <PreviewModal doc={previewDoc} category={selectedCat} onClose={() => setPreviewDoc(null)} />}
      </AnimatePresence>

      {/* Hidden file input */}
      <input ref={fileInputRef} type="file" multiple accept={ACCEPTED_TYPES} className="hidden"
        onChange={e => { if (e.target.files) processFiles(e.target.files); e.target.value = '' }} />

      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">Knowledge Base</h1>
          <p className="text-sm text-star-70 mt-0.5">Upload, manage, and index documents for RAG retrieval</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={reindexAll} disabled={reindexingAll}
            className="flex items-center gap-2 px-4 py-2.5 glass rounded-xl text-sm text-star-70 hover:text-white transition border border-white/10 hover:border-white/20 disabled:opacity-40">
            <Database className={`w-4 h-4 ${reindexingAll ? 'animate-pulse' : ''}`} />
            {reindexingAll ? 'Re-indexing all…' : 'Re-index All'}
          </button>
          <button onClick={reindex} disabled={reindexing}
            className="flex items-center gap-2 px-4 py-2.5 glass rounded-xl text-sm text-star-70 hover:text-white transition border border-white/10 hover:border-white/20 disabled:opacity-40">
            <RefreshCw className={`w-4 h-4 ${reindexing ? 'animate-spin' : ''}`} />
            {reindexing ? 'Reindexing…' : 'Re-index'}
          </button>
          <button onClick={() => fileInputRef.current?.click()}
            className="btn-primary flex items-center gap-2 px-4 py-2.5 text-sm">
            <Upload className="w-4 h-4" />
            Upload Documents
          </button>
        </div>
      </div>

      {/* Category selector */}
      <div className="relative">
        <button onClick={() => setShowCatMenu(m => !m)}
          className="flex items-center gap-3 px-4 py-3 glass rounded-xl border border-white/10 hover:border-white/20 transition w-full sm:w-auto">
          <span className="text-xl">{cat.icon}</span>
          <div className="text-left flex-1 min-w-0">
            <p className="text-sm font-semibold text-white">{cat.label}</p>
            <p className="text-2xs text-star-50 font-mono">{cat.key}</p>
          </div>
          <ChevronDown className={`w-4 h-4 text-star-50 transition-transform ${showCatMenu ? 'rotate-180' : ''}`} />
        </button>

        <AnimatePresence>
          {showCatMenu && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="absolute top-full mt-2 left-0 z-30 w-72 glass rounded-xl border border-white/10 overflow-hidden shadow-xl">
              {KB_CATEGORIES.map(c => (
                <button key={c.key} onClick={() => { setSelectedCat(c.key); setShowCatMenu(false) }}
                  className={`flex items-center gap-3 w-full px-4 py-2.5 text-left text-sm transition hover:bg-white/5 ${
                    selectedCat === c.key ? 'bg-white/8 text-white' : 'text-star-70'
                  }`}>
                  <span>{c.icon}</span>
                  <span>{c.label}</span>
                  {selectedCat === c.key && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 ml-auto" />}
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-star-50" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search documents in this category..."
          className="input pl-10"
        />
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Indexed Docs',   value: indexedDocs.length, icon: BookOpen,  color: cat.color },
          { label: 'Total Chunks',   value: totalChunks,        icon: Database,  color: '#10D97A' },
          { label: 'Files on Disk',  value: diskFiles.length,   icon: FileText,  color: '#00D4FF' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="glass rounded-2xl p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-2xs text-star-50 uppercase tracking-wide">{label}</p>
              <Icon className="w-4 h-4" style={{ color }} />
            </div>
            <p className="text-2xl font-mono font-bold text-white">
              {loadingDocs ? '—' : value.toLocaleString()}
            </p>
          </div>
        ))}
      </div>

      {/* ── Drag-and-drop Upload Zone ──────────────────────────────────────── */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible"
        onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          'rounded-2xl border-2 border-dashed p-8 text-center cursor-pointer transition-all duration-200',
          isDragging
            ? 'border-indigo-400 bg-indigo-500/10 scale-[1.01]'
            : 'border-white/10 hover:border-white/20 hover:bg-white/2',
        )}>
        <div className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center"
          style={{ background: `${cat.color}15`, border: `1px solid ${cat.color}30` }}>
          <Upload className="w-6 h-6" style={{ color: cat.color }} />
        </div>
        <p className="font-semibold text-white text-sm mb-1">
          {isDragging ? 'Drop files here' : 'Drop files or click to upload'}
        </p>
        <p className="text-xs text-star-50">PDF, DOCX, TXT, Markdown · Multiple files supported</p>
        <p className="text-2xs text-star-30 mt-2">
          Files are automatically embedded into: <span className="font-mono">{cat.key}</span>
        </p>
      </motion.div>

      {/* ── Upload Queue ──────────────────────────────────────────────────── */}
      <AnimatePresence>
        {uploads.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0 }}
            className="glass rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/10">
              <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
                Upload Queue
                {activeUploads.length > 0 && (
                  <span className="ml-2 text-indigo-400">· {activeUploads.length} in progress</span>
                )}
              </h2>
              {doneUploads.length > 0 && (
                <button onClick={clearDoneUploads}
                  className="text-2xs text-star-50 hover:text-white transition">
                  Clear completed
                </button>
              )}
            </div>

            <div className="divide-y divide-white/5 max-h-72 overflow-y-auto">
              {uploads.map(u => {
                const ext  = u.file.name.slice(u.file.name.lastIndexOf('.')).toLowerCase()
                const size = u.file.size < 1024 ? `${u.file.size} B`
                           : u.file.size < 1048576 ? `${(u.file.size / 1024).toFixed(1)} KB`
                           : `${(u.file.size / 1048576).toFixed(1)} MB`

                return (
                  <div key={u.id} className="px-5 py-3.5">
                    <div className="flex items-center gap-3 mb-2">
                      <FileIcon ext={ext} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white font-medium truncate">{u.file.name}</p>
                        <p className="text-2xs text-star-50">{size}</p>
                      </div>
                      {/* Status indicator */}
                      {u.status === 'done' && (
                        <div className="flex items-center gap-1.5 text-2xs text-emerald-400 flex-shrink-0">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          {u.chunks != null ? `${u.chunks} chunks` : 'Done'}
                        </div>
                      )}
                      {u.status === 'error' && (
                        <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                      )}
                      {(u.status === 'uploading' || u.status === 'indexing') && (
                        <Loader2 className="w-4 h-4 text-indigo-400 animate-spin flex-shrink-0" />
                      )}
                      <button onClick={() => setUploads(p => p.filter(x => x.id !== u.id))}
                        className="text-star-30 hover:text-white transition flex-shrink-0">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* Progress bar */}
                    {u.status !== 'pending' && u.status !== 'error' && (
                      <ProgressBar
                        value={u.progress}
                        color={
                          u.status === 'done'     ? '#10D97A'
                          : u.status === 'indexing' ? '#00D4FF'
                          : cat.color
                        }
                      />
                    )}
                    {u.status === 'uploading' && (
                      <p className="text-2xs text-star-50 mt-1">Uploading & embedding…</p>
                    )}
                    {u.status === 'indexing' && (
                      <p className="text-2xs text-cyan-400 mt-1">Storing in ChromaDB…</p>
                    )}
                    {u.status === 'error' && (
                      <p className="text-2xs text-rose-400 mt-1">{u.error}</p>
                    )}
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Indexed Documents (ChromaDB) ───────────────────────────────────── */}
      <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={1} className="glass rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
              Indexed in ChromaDB
            </h2>
          </div>
          <button onClick={loadDocs} disabled={loadingDocs}
            className="text-star-50 hover:text-white transition">
            <RefreshCw className={`w-3.5 h-3.5 ${loadingDocs ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loadingDocs ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
          </div>
        ) : filteredIndexedDocs.length === 0 ? (
          <div className="py-10 text-center">
            <Database className="w-8 h-8 mx-auto mb-3 text-star-30" />
            <p className="text-sm text-star-50">
              {q ? 'No documents match your search.' : 'No documents indexed for this category.'}
            </p>
            {!q && <p className="text-xs text-star-30 mt-1">Upload documents above to get started.</p>}
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {filteredIndexedDocs.map(doc => {
              const ext = doc.source.includes('.')
                ? doc.source.slice(doc.source.lastIndexOf('.')).toLowerCase()
                : ''
              const onDisk = diskFilenames.has(doc.source)
              return (
                <div key={doc.source} className="flex items-center gap-3 px-5 py-3.5 hover:bg-white/3 transition">
                  <FileIcon ext={ext} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white font-medium truncate">{doc.source}</p>
                    <p className="text-2xs text-star-50 font-mono">
                      {doc.chunks} chunks embedded{doc.avg_chunk_chars ? ` · avg ${doc.avg_chunk_chars}c/chunk` : ''}
                    </p>
                  </div>
                  {/* Chunk badge */}
                  <span className="px-2 py-0.5 rounded text-2xs font-mono border bg-emerald-500/10 text-emerald-400 border-emerald-500/20 flex-shrink-0">
                    {doc.chunks}
                  </span>
                  {onDisk && (
                    <>
                      <button onClick={() => reindexDocument(doc.source)}
                        disabled={reindexingFile === doc.source}
                        title="Re-index this document"
                        className="p-1.5 rounded-lg text-star-50 hover:text-white hover:bg-white/5 transition disabled:opacity-40 flex-shrink-0">
                        {reindexingFile === doc.source
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <RefreshCw className="w-3.5 h-3.5" />}
                      </button>
                      <button onClick={() => renameDocument(doc.source)}
                        disabled={renamingFile === doc.source}
                        title="Rename"
                        className="p-1.5 rounded-lg text-star-50 hover:text-white hover:bg-white/5 transition disabled:opacity-40 flex-shrink-0">
                        {renamingFile === doc.source
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Pencil className="w-3.5 h-3.5" />}
                      </button>
                    </>
                  )}
                  <button onClick={() => setPreviewDoc(doc)} title="Preview"
                    className="p-1.5 rounded-lg text-star-50 hover:text-white hover:bg-white/5 transition flex-shrink-0">
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => deleteDocument(doc.source)}
                    disabled={deletingFile === doc.source}
                    title="Delete document and embeddings"
                    className="p-1.5 rounded-lg text-star-50 hover:text-rose-400 hover:bg-rose-500/10 transition disabled:opacity-40 flex-shrink-0">
                    {deletingFile === doc.source
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <Trash2 className="w-3.5 h-3.5" />}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </motion.div>

      {/* ── Disk Files ─────────────────────────────────────────────────────── */}
      {filteredDiskFiles.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={2} className="glass rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-white/10">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              <h2 className="text-xs font-semibold text-star-70 uppercase tracking-wider">
                Files on Disk ({filteredDiskFiles.length})
              </h2>
            </div>
          </div>
          <div className="divide-y divide-white/5">
            {filteredDiskFiles.map(f => (
              <div key={f.filename} className="flex items-center gap-3 px-5 py-3.5 hover:bg-white/3 transition">
                <FileIcon ext={f.extension} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{f.filename}</p>
                  <p className="text-2xs text-star-50">
                    {f.size_bytes < 1024 ? `${f.size_bytes} B`
                      : f.size_bytes < 1048576 ? `${(f.size_bytes / 1024).toFixed(1)} KB`
                      : `${(f.size_bytes / 1048576).toFixed(1)} MB`}
                    {' · '}{new Date(f.uploaded_at).toLocaleDateString()}
                  </p>
                </div>
                <button onClick={() => reindexDocument(f.filename)}
                  disabled={reindexingFile === f.filename}
                  title="Re-index this document"
                  className="p-1.5 rounded-lg text-star-50 hover:text-white hover:bg-white/5 transition disabled:opacity-40 flex-shrink-0">
                  {reindexingFile === f.filename
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <RefreshCw className="w-3.5 h-3.5" />}
                </button>
                <button onClick={() => renameDocument(f.filename)}
                  disabled={renamingFile === f.filename}
                  title="Rename"
                  className="p-1.5 rounded-lg text-star-50 hover:text-white hover:bg-white/5 transition disabled:opacity-40 flex-shrink-0">
                  {renamingFile === f.filename
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Pencil className="w-3.5 h-3.5" />}
                </button>
                <button onClick={() => setPreviewDoc(f)} title="Preview"
                  className="p-1.5 rounded-lg text-star-50 hover:text-white hover:bg-white/5 transition flex-shrink-0">
                  <Eye className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => deleteDocument(f.filename)}
                  disabled={deletingFile === f.filename}
                  title="Delete"
                  className="p-1.5 rounded-lg text-star-50 hover:text-rose-400 hover:bg-rose-500/10 transition disabled:opacity-40 flex-shrink-0">
                  {deletingFile === f.filename
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Trash2 className="w-3.5 h-3.5" />}
                </button>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}
