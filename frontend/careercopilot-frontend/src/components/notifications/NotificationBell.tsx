import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Bell, Check, Trash2, Loader2 } from 'lucide-react'
import { formatDistanceToNowStrict } from 'date-fns'
import { notificationApi } from '@/api'
import { cn } from '@/utils'
import type { NotificationItem, NotificationListResult } from '@/types/notification'
import { resolveNotificationIcon } from './notificationIcons'

const PREVIEW_PAGE_SIZE = 8

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const nav = useNavigate()
  const qc = useQueryClient()

  // Poll unread count in the background regardless of dropdown state.
  const { data: unreadData } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => notificationApi.unreadCount().then(r => r.data.data as { unread_count: number }),
    refetchInterval: 30_000,
  })
  const unreadCount = unreadData?.unread_count ?? 0

  // Fetch the preview list only while the dropdown is open.
  const { data: listData, isLoading } = useQuery({
    queryKey: ['notifications', 'preview'],
    queryFn: () =>
      notificationApi
        .list({ page: 1, page_size: PREVIEW_PAGE_SIZE })
        .then(r => r.data.data as NotificationListResult),
    enabled: open,
    refetchInterval: open ? 15_000 : false,
  })

  const markRead = useMutation({
    mutationFn: (id: number) => notificationApi.markRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const markAllRead = useMutation({
    mutationFn: () => notificationApi.markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const removeOne = useMutation({
    mutationFn: (id: number) => notificationApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  // Close on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const handleItemClick = (n: NotificationItem) => {
    if (!n.is_read) markRead.mutate(n.notification_id)
    setOpen(false)
    if (n.action_url) nav(n.action_url)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="btn-ghost p-2 relative"
        aria-label="Notifications"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span
            className="absolute top-0.5 right-0.5 min-w-[15px] h-[15px] px-[3px] rounded-full text-white text-[9px] font-bold font-mono flex items-center justify-center"
            style={{ background: '#F43F5E', boxShadow: '0 0 0 2px rgba(4,5,10,0.9)' }}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="glass absolute right-0 top-full mt-2 w-[360px] max-h-[480px] rounded-xl overflow-hidden flex flex-col z-50"
            style={{ background: 'rgba(10,11,20,0.98)' }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 flex-shrink-0">
              <span className="text-sm font-semibold text-white">Notifications</span>
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllRead.mutate()}
                  disabled={markAllRead.isPending}
                  className="text-2xs text-indigo-bright hover:text-white transition-colors flex items-center gap-1"
                >
                  {markAllRead.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                  Mark all read
                </button>
              )}
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {isLoading && (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="w-4 h-4 animate-spin text-star-50" />
                </div>
              )}

              {!isLoading && (listData?.notifications.length ?? 0) === 0 && (
                <div className="py-10 text-center text-star-50 text-sm">
                  You're all caught up.
                </div>
              )}

              {listData?.notifications.map(n => {
                const Icon = resolveNotificationIcon(n.icon)
                return (
                  <div
                    key={n.notification_id}
                    onClick={() => handleItemClick(n)}
                    className={cn(
                      'group flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors border-b border-white/[0.03] hover:bg-white/[0.04]',
                      !n.is_read && 'bg-indigo-500/[0.05]'
                    )}
                  >
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                      style={{ background: 'rgba(91,79,232,0.12)' }}
                    >
                      <Icon className="w-4 h-4" style={{ color: '#7B6FFF' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={cn('text-sm truncate', n.is_read ? 'text-star-70' : 'text-white font-medium')}>
                          {n.title}
                        </span>
                        {!n.is_read && <span className="w-1.5 h-1.5 rounded-full bg-cyan flex-shrink-0" />}
                      </div>
                      <p className="text-xs text-star-50 line-clamp-2 mt-0.5">{n.message}</p>
                      <span className="text-2xs text-star-30 mt-1 block">
                        {formatDistanceToNowStrict(new Date(n.created_at), { addSuffix: true })}
                      </span>
                    </div>
                    <button
                      onClick={e => { e.stopPropagation(); removeOne.mutate(n.notification_id) }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-star-50 hover:text-rose-400 flex-shrink-0 mt-0.5"
                      aria-label="Delete notification"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )
              })}
            </div>

            {/* Footer */}
            <button
              onClick={() => { setOpen(false); nav('/notifications') }}
              className="text-center text-xs text-star-70 hover:text-white py-3 border-t border-white/5 flex-shrink-0 transition-colors"
            >
              View all notifications
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
