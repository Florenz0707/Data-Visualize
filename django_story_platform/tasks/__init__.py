"""
Django Story Platform - 异步任务统一导入
"""
from .story_tasks import (
    generate_story_task, resume_story_generation_task,
    send_progress_notification, send_completion_notification,
    cleanup_old_tasks, cleanup_old_notifications
)
from .media_tasks import (
    process_media_file, generate_thumbnail_task,
    compress_media_file_task, cleanup_orphaned_files,
    backup_media_library_task
)
from .notification_tasks import (
    send_email_notification, send_bulk_notifications,
    cleanup_read_notifications, send_daily_summary,
    send_weekly_report
)

__all__ = [
    # Story tasks
    'generate_story_task', 'resume_story_generation_task',
    'send_progress_notification', 'send_completion_notification',
    'cleanup_old_tasks', 'cleanup_old_notifications',
    
    # Media tasks
    'process_media_file', 'generate_thumbnail_task',
    'compress_media_file_task', 'cleanup_orphaned_files',
    'backup_media_library_task',
    
    # Notification tasks
    'send_email_notification', 'send_bulk_notifications',
    'cleanup_read_notifications', 'send_daily_summary',
    'send_weekly_report',
]
