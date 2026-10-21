export type NotificationType =
  | 'resume_analysis_completed'
  | 'skill_gap_report_completed'
  | 'career_recommendation_completed'
  | 'interview_evaluation_completed'
  | 'kb_indexing_completed'
  | 'document_uploaded'
  | 'chroma_indexing_finished'
  | 'system_alert'
  | 'admin_action'
  | 'login_alert'
  | 'error_notification'
  | 'weekly_progress_reminder'
  | 'learning_roadmap_reminder'

export type NotificationPriority = 'low' | 'normal' | 'high' | 'urgent'

export interface NotificationItem {
  notification_id: number
  type:             NotificationType
  priority:         NotificationPriority
  title:            string
  message:          string
  icon:             string | null
  action_url:       string | null
  is_read:          boolean
  read_at:          string | null
  created_at:       string
}

export interface NotificationListResult {
  total:         number
  unread_count:  number
  page:          number
  page_size:     number
  total_pages:   number
  notifications: NotificationItem[]
}

export const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  resume_analysis_completed:       'Resume Analysis',
  skill_gap_report_completed:      'Skill Gap',
  career_recommendation_completed: 'Career Recommendation',
  interview_evaluation_completed:  'Interview Coach',
  kb_indexing_completed:           'Knowledge Base',
  document_uploaded:               'Document Upload',
  chroma_indexing_finished:        'ChromaDB',
  system_alert:                    'System Alert',
  admin_action:                    'Admin Action',
  login_alert:                     'Login Alert',
  error_notification:              'Error',
  weekly_progress_reminder:        'Progress Reminder',
  learning_roadmap_reminder:       'Learning Roadmap',
}
