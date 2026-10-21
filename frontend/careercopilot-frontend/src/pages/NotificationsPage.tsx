import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Search, Check, Trash2, Loader2, Bell, Inbox } from 'lucide-react'
import { formatDistanceToNowStrict } from 'date-fns'
import DashboardLayout from '@/components/layout/DashboardLayout'
import { notificationApi } from '@/api'
import { cn, fadeUp } from '@/utils'
import type { NotificationItem, NotificationListResult, NotificationType } from '@/types/notification'
import { NOTIFICATION_TYPE_LABELS } from '@/types/notification'
import { resolveNotificationIcon } from '@/components/notifications/notificationIcons'

const PAGE_SIZE = 20

type TypeFilter = NotificationType | 'all'

export default function NotificationsPage() {
  const nav = useNavigate()
  const qc  = useQueryClient()

  const [search, setSearch]         = useState('')
  const [debounced, setDebounced]   = useState('')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [unreadOnly, setUnreadOnly] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 350)
    return () => clearTimeout(t)
  }, [search])

  const {
    data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading,
  } = useInfiniteQuery({
    queryKey: ['notifications', 'page', debounced, typeFilter, unreadOnly],
    queryFn: ({ pageParam }) =>
      notificationApi
        .list({
          page: pageParam,
          page_size: PAGE_SIZE,
          unread_only: unreadOnly,
          type: typeFilter === 'all' ? undefined : typeFilter,
          search: debounced || undefined,
        })
        .then(r => r.data.data as NotificationListResult),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.total_pages ? last.page + 1 : undefined),
  })

  const items = useMemo(() => data?.pages.flatMap(p => p.notifications) ?? [], [data])
  const unreadCount = data?.pages[0]?.unread_count ?? 0

  const markRead    = useMutation({ mutationFn: (id: number) => notificationApi.markRead(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  const markAllRead = useMutation({ mutationFn: () => notificationApi.markAllRead(),           onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  const removeOne   = useMutation({ mutationFn: (id: number) => notificationApi.delete(id),    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const obs = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage()
    }, { rootMargin: '200px' })
    obs.observe(el)
    return () => obs.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const handleClick = (n: NotificationItem) => {
    if (!n.is_read) markRead.mutate(n.notification_id)
    if (n.action_url) nav(n.action_url)
  }

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto px-6 py-8">
        <motion.div variants={fadeUp} initial="hidden" animate="visible" className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(91,79,232,0.12)' }}>
              <Bell className="w-5 h-5" style={{ color: '#7B6FFF' }} />
            </div>
            <div>
              <h1 className="font-display text-xl font-bold text-white">Notifications</h1>
              <p className="text-xs text-star-50">{unreadCount} unread</p>
            </div>
          </div>
          {unreadCount > 0 && (
            <button onClick={() => markAllRead.mutate()} className="btn-secondary text-xs py-2 px-4">
              <Check className="w-3.5 h-3.5" /> Mark all read
            </button>
          )}
        </motion.div>

        {/* Filters */}
        <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={1} className="flex flex-col sm:flex-row gap-3 mb-6">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-star-50" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search notifications..."
              className="input pl-10"
            />
          </div>
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value as TypeFilter)}
            className="input sm:w-56"
          >
            <option value="all">All types</option>
            {Object.entries(NOTIFICATION_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <button
            onClick={() => setUnreadOnly(u => !u)}
            className={cn('btn-secondary text-xs px-4 whitespace-nowrap', unreadOnly && 'border-indigo-bright text-white')}
          >
            {unreadOnly ? 'Unread only ✓' : 'Unread only'}
          </button>
        </motion.div>

        {/* List */}
        <div className="glass rounded-xl overflow-hidden">
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-5 h-5 animate-spin text-star-50" />
            </div>
          )}

          {!isLoading && items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Inbox className="w-8 h-8 text-star-30 mb-3" />
              <p className="text-star-50 text-sm">No notifications found.</p>
            </div>
          )}

          {items.map((n, i) => {
            const Icon = resolveNotificationIcon(n.icon)
            return (
              <motion.div
                key={n.notification_id}
                variants={fadeIn}
                initial="hidden"
                animate="visible"
                custom={Math.min(i, 8)}
                onClick={() => handleClick(n)}
                className={cn(
                  'group flex items-start gap-4 px-5 py-4 cursor-pointer border-b border-white/[0.04] last:border-b-0 transition-colors hover:bg-white/[0.03]',
                  !n.is_read && 'bg-indigo-500/[0.04]'
                )}
              >
                <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(91,79,232,0.12)' }}>
                  <Icon className="w-[18px] h-[18px]" style={{ color: '#7B6FFF' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn('text-sm', n.is_read ? 'text-star-70' : 'text-white font-semibold')}>{n.title}</span>
                    {!n.is_read && <span className="w-1.5 h-1.5 rounded-full bg-cyan flex-shrink-0" />}
                    <span className="badge ml-auto flex-shrink-0">{NOTIFICATION_TYPE_LABELS[n.type]}</span>
                  </div>
                  <p className="text-sm text-star-50 mt-1">{n.message}</p>
                  <span className="text-2xs text-star-30 mt-1.5 block">
                    {formatDistanceToNowStrict(new Date(n.created_at), { addSuffix: true })}
                  </span>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); removeOne.mutate(n.notification_id) }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-star-50 hover:text-rose-400 flex-shrink-0"
                  aria-label="Delete notification"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </motion.div>
            )
          })}

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-4" />
          {isFetchingNextPage && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-4 h-4 animate-spin text-star-50" />
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}

const fadeIn = {
  hidden:  { opacity: 0, y: 8 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.3, delay: Math.min(i, 8) * 0.03 } }),
}
