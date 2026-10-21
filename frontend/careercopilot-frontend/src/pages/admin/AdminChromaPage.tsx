import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Loader2, RefreshCw, Trash2, RotateCcw, CheckCircle2, AlertCircle,
  Database, Clock, HardDrive, Eye, Layers, X, ShieldAlert,
} from 'lucide-react'
import { adminApi } from '@/api'
import { fadeUp, stagger } from '@/utils'

interface Collection {
  category: string; collection: string; label: string
  count: number; status: string; health: string
  embedding_model: string; embedding_dims: number
  estimated_storage_bytes: number; last_indexed_at: string | null
}

interface ChromaDoc { source: string; chunks: number; avg_chunk_chars?: number }
interface ChromaChunk { chunk_id: string; source: string; text_preview: string; chunk_index: number | null }

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`
  return `${(bytes / 1073741824).toFixed(2)} GB`
}

function formatRelative(iso: string | null): string {
  if (!iso) return 'Never'
  const then = new Date(iso).getTime()
  const diffMs = Date.now() - then
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

const STATUS_STYLES: Record<string, string> = {
  ready:   'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  empty:   'text-amber-400 bg-amber-500/10 border-amber-500/20',
  error:   'text-rose-400 bg-rose-500/10 border-rose-500/20',
  unknown: 'text-star-50 bg-white/5 border-white/10',
}

const HEALTH_DOT: Record<string, string> = {
  green:  'bg-emerald-400',
  yellow: 'bg-amber-400',
  red:    'bg-rose-400',
}

type ModalState = { type: 'documents' | 'chunks'; category: string; label: string } | null

export default function AdminChromaPage() {
  const [collections, setCollections] = useState<Collection[]>([])
  const [loading,     setLoading]     = useState(true)
  const [refreshing,  setRefreshing]  = useState(false)
  const [acting,      setActing]      = useState<string | null>(null)
  const [toast,       setToast]       = useState<{ msg: string; ok: boolean } | null>(null)
  const [modal,       setModal]       = useState<ModalState>(null)

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true); else setLoading(true)
    try {
      const res = await adminApi.getChromaCollections()
      setCollections((res.data?.data ?? res.data)?.collections ?? [])
    } finally {
      setLoading(false); setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok }); setTimeout(() => setToast(null), 3500)
  }

  const reindex = async (category: string) => {
    setActing(`reindex-${category}`)
    try {
      const res = await adminApi.reindexChromaCollection(category)
      const chunks = (res.data?.data ?? res.data)?.chunks_indexed ?? 0
      showToast(`Reindexed '${category}' — ${chunks} chunks`)
      load(true)
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Reindex failed', false)
    } finally { setActing(null) }
  }

  const deleteCol = async (category: string) => {
    if (!confirm(`Delete collection '${category}'? This cannot be undone.`)) return
    setActing(`delete-${category}`)
    try {
      await adminApi.deleteChromaCollection(category)
      showToast(`Deleted collection '${category}'`)
      load(true)
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Delete failed', false)
    } finally { setActing(null) }
  }

  const deleteOrphans = async (category: string) => {
    if (!confirm(`Delete orphaned embeddings for '${category}' — chunks whose source file no longer exists?`)) return
    setActing(`orphans-${category}`)
    try {
      const res = await adminApi.deleteOrphanEmbeddings(category)
      const removed = (res.data?.data ?? res.data)?.orphans_removed ?? 0
      showToast(`Removed ${removed} orphaned chunk(s) from '${category}'`)
      load(true)
    } catch (e: any) {
      showToast(e.response?.data?.detail ?? 'Delete orphans failed', false)
    } finally { setActing(null) }
  }

  const total = collections.reduce((s, c) => s + c.count, 0)

  return (
    <div className="p-6 space-y-6">
      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl text-sm border shadow-xl ${
              toast.ok ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25'
                       : 'bg-rose-500/15 text-rose-300 border-rose-500/25'
            }`}>
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">ChromaDB</h1>
          <p className="text-sm text-star-70 mt-0.5">
            {collections.length} collections · {total.toLocaleString()} total chunks
          </p>
        </div>
        <button onClick={() => load(true)} disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2.5 glass rounded-xl text-sm text-star-70 hover:text-white transition border border-white/10 disabled:opacity-40">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Summary card */}
      <div className="glass rounded-2xl px-5 py-4 flex items-center gap-4 flex-wrap">
        <Database className="w-5 h-5 text-indigo-400 flex-shrink-0" />
        <div>
          <p className="text-2xl font-mono font-bold text-white">{total.toLocaleString()}</p>
          <p className="text-xs text-star-50">total embedded chunks across {collections.length} collections</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-star-50 ml-4">
          <HardDrive className="w-3.5 h-3.5" />
          {formatBytes(collections.reduce((s, c) => s + (c.estimated_storage_bytes || 0), 0))}
          <span className="text-star-30">(estimated)</span>
        </div>
        {collections.length > 0 && (
          <p className="ml-auto text-xs text-star-50 font-mono">{collections[0]?.embedding_model} · {collections[0]?.embedding_dims}d</p>
        )}
      </div>

      {/* Collections grid */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
        </div>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="visible"
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {collections.map((col, i) => {
            const isReady = col.status === 'ready'
            const stStyle = STATUS_STYLES[col.status] ?? STATUS_STYLES.unknown

            return (
              <motion.div key={col.category} variants={fadeUp} custom={i} className="glass rounded-2xl p-5 flex flex-col gap-3">
                {/* Title row */}
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${HEALTH_DOT[col.health] ?? HEALTH_DOT.red}`} title={`Health: ${col.health}`} />
                    <p className="text-sm font-semibold text-white truncate">{col.label}</p>
                  </div>
                  {isReady
                    ? <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                    : <AlertCircle  className="w-4 h-4 text-amber-400   flex-shrink-0" />}
                </div>

                {/* Stats */}
                <div className="flex items-center gap-3">
                  <span className={`px-2 py-0.5 rounded text-2xs border ${stStyle}`}>
                    {col.status}
                  </span>
                  <span className="text-2xs text-star-50 font-mono">{col.category}</span>
                </div>

                {/* Count */}
                <div className="pt-2 border-t border-white/8">
                  <p className="text-2xl font-mono font-bold text-white">{col.count.toLocaleString()}</p>
                  <p className="text-2xs text-star-50 mt-0.5">chunks embedded</p>
                </div>

                {/* Storage + Last indexed */}
                <div className="flex items-center justify-between text-2xs text-star-50">
                  <span className="flex items-center gap-1"><HardDrive className="w-3 h-3" /> {formatBytes(col.estimated_storage_bytes)}</span>
                  <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {formatRelative(col.last_indexed_at)}</span>
                </div>

                {/* View actions */}
                <div className="flex gap-2">
                  <button
                    onClick={() => setModal({ type: 'documents', category: col.category, label: col.label })}
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-2xs font-medium border bg-white/3 text-star-70 border-white/10 hover:bg-white/6 hover:text-white transition"
                  >
                    <Eye className="w-3 h-3" /> Documents
                  </button>
                  <button
                    onClick={() => setModal({ type: 'chunks', category: col.category, label: col.label })}
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-2xs font-medium border bg-white/3 text-star-70 border-white/10 hover:bg-white/6 hover:text-white transition"
                  >
                    <Layers className="w-3 h-3" /> Chunks
                  </button>
                </div>

                {/* Actions */}
                <div className="flex gap-2 mt-auto pt-2 border-t border-white/5">
                  <button
                    onClick={() => reindex(col.category)}
                    disabled={acting === `reindex-${col.category}`}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium border bg-indigo-500/10 text-indigo-300 border-indigo-500/20 hover:bg-indigo-500/20 transition disabled:opacity-40"
                  >
                    {acting === `reindex-${col.category}`
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <RotateCcw className="w-3.5 h-3.5" />}
                    Re-index
                  </button>
                  <button
                    onClick={() => deleteOrphans(col.category)}
                    disabled={acting === `orphans-${col.category}`}
                    title="Delete orphaned embeddings"
                    className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20 transition disabled:opacity-40"
                  >
                    {acting === `orphans-${col.category}`
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <ShieldAlert className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={() => deleteCol(col.category)}
                    disabled={!!acting}
                    title="Delete collection"
                    className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/20 transition disabled:opacity-40"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </motion.div>
            )
          })}
        </motion.div>
      )}

      <AnimatePresence>
        {modal && <DocsChunksModal state={modal} onClose={() => setModal(null)} />}
      </AnimatePresence>
    </div>
  )
}

// ── View Documents / View Chunks modal ─────────────────────────────────────

function DocsChunksModal({ state, onClose }: { state: NonNullable<ModalState>; onClose: () => void }) {
  const [loading, setLoading] = useState(true)
  const [docs,    setDocs]    = useState<ChromaDoc[]>([])
  const [chunks,  setChunks]  = useState<ChromaChunk[]>([])
  const [page,    setPage]    = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  useEffect(() => {
    setLoading(true)
    if (state.type === 'documents') {
      adminApi.getChromaDocuments(state.category)
        .then(res => setDocs((res.data?.data ?? res.data)?.documents ?? []))
        .finally(() => setLoading(false))
    } else {
      adminApi.viewChromaChunks(state.category, page, 25)
        .then(res => {
          const data = res.data?.data ?? res.data
          setChunks(data?.chunks ?? [])
          setTotalPages(data?.total_pages ?? 1)
        })
        .finally(() => setLoading(false))
    }
  }, [state, page])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="glass rounded-2xl border border-white/10 w-full max-w-xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 flex-shrink-0">
          <p className="text-sm font-semibold text-white">
            {state.type === 'documents' ? 'Documents' : 'Raw Chunks'} — {state.label}
          </p>
          <button onClick={onClose} className="text-star-50 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <div className="overflow-y-auto flex-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />
            </div>
          ) : state.type === 'documents' ? (
            docs.length === 0 ? (
              <p className="text-sm text-star-50 text-center py-10">No documents indexed.</p>
            ) : (
              <div className="divide-y divide-white/5">
                {docs.map(d => (
                  <div key={d.source} className="px-5 py-3 flex items-center justify-between gap-3">
                    <p className="text-sm text-white truncate">{d.source}</p>
                    <span className="text-2xs text-star-50 font-mono flex-shrink-0">
                      {d.chunks} chunks{d.avg_chunk_chars ? ` · ~${d.avg_chunk_chars}c` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )
          ) : chunks.length === 0 ? (
            <p className="text-sm text-star-50 text-center py-10">No chunks found.</p>
          ) : (
            <div className="divide-y divide-white/5">
              {chunks.map(c => (
                <div key={c.chunk_id} className="px-5 py-3">
                  <p className="text-2xs text-star-50 font-mono mb-1">{c.source} {c.chunk_index != null ? `· chunk ${c.chunk_index}` : ''}</p>
                  <p className="text-xs text-star-70 line-clamp-3">{c.text_preview}</p>
                </div>
              ))}
            </div>
          )}
        </div>
        {state.type === 'chunks' && totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-white/10 flex-shrink-0">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
              className="text-2xs text-star-50 hover:text-white disabled:opacity-30">Previous</button>
            <span className="text-2xs text-star-50">Page {page} of {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
              className="text-2xs text-star-50 hover:text-white disabled:opacity-30">Next</button>
          </div>
        )}
      </motion.div>
    </div>
  )
}
