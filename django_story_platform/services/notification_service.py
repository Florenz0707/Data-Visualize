"""
Django Story Platform - 通知业务服务
"""
import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from models import Notification, NotificationSettings


class NotificationService:
    """通知服务"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def create_notification(self, user, notification_data: Dict[str, Any]) -> Notification:
        """创建通知"""
        self.logger.info(f"Creating notification for user {user.id}")
        
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_data.get('notification_type', 'system'),
            title=notification_data.get('title', ''),
            message=notification_data.get('message', ''),
            data=notification_data.get('data', {})
        )
        
        self.logger.info(f"Notification created with ID: {notification.id}")
        return notification
    
    def send_email_notification(self, notification: Notification) -> bool:
        """发送邮件通知"""
        try:
            # 检查用户的通知设置
            try:
                settings_obj = notification.user.notification_settings
                if not settings_obj.email_notifications:
                    self.logger.info(f"Email notifications disabled for user {notification.user.id}")
                    return False
            except NotificationSettings.DoesNotExist:
                # 如果没有设置，默认发送
                pass
            
            # 发送邮件
            subject = f"[故事平台] {notification.title}"
            message = f"""
{notification.message}

详情: {notification.data}

---
此邮件由故事平台自动发送，请勿回复。
            """.strip()
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
                fail_silently=False,
            )
            
            self.logger.info(f"Email notification sent for notification {notification.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Email notification failed: {e}")
            return False
    
    def mark_notifications_read(self, user, notification_ids: List[str]) -> int:
        """标记通知为已读"""
        try:
            updated_count = Notification.objects.filter(
                id__in=notification_ids,
                user=user
            ).update(is_read=True)
            
            self.logger.info(f"Marked {updated_count} notifications as read for user {user.id}")
            return updated_count
            
        except Exception as e:
            self.logger.error(f"Failed to mark notifications as read: {e}")
            return 0
    
    def mark_all_notifications_read(self, user) -> int:
        """标记所有通知为已读"""
        try:
            updated_count = Notification.objects.filter(
                user=user,
                is_read=False
            ).update(is_read=True)
            
            self.logger.info(f"Marked all {updated_count} notifications as read for user {user.id}")
            return updated_count
            
        except Exception as e:
            self.logger.error(f"Failed to mark all notifications as read: {e}")
            return 0
    
    def delete_notification(self, user, notification_id: str) -> bool:
        """删除通知"""
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.delete()
            
            self.logger.info(f"Notification {notification_id} deleted for user {user.id}")
            return True
            
        except Notification.DoesNotExist:
            self.logger.warning(f"Notification {notification_id} not found for user {user.id}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to delete notification {notification_id}: {e}")
            return False
    
    def delete_all_read_notifications(self, user) -> int:
        """删除所有已读通知"""
        try:
            deleted_count = Notification.objects.filter(
                user=user,
                is_read=True
            ).delete()[0]
            
            self.logger.info(f"Deleted {deleted_count} read notifications for user {user.id}")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to delete read notifications: {e}")
            return 0
    
    def get_notification_stats(self, user) -> Dict[str, Any]:
        """获取通知统计信息"""
        try:
            # 获取通知统计
            total_count = Notification.objects.filter(user=user).count()
            unread_count = Notification.objects.filter(user=user, is_read=False).count()
            read_count = total_count - unread_count
            
            # 按类型统计
            by_type = {}
            for notification_type, _ in Notification.NOTIFICATION_TYPE_CHOICES:
                count = Notification.objects.filter(user=user, notification_type=notification_type).count()
                by_type[notification_type] = count
            
            stats = {
                'total_count': total_count,
                'unread_count': unread_count,
                'read_count': read_count,
                'by_type': by_type
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get notification stats: {e}")
            return {}


class NotificationSettingsService:
    """通知设置服务"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def get_or_create_settings(self, user) -> NotificationSettings:
        """获取或创建通知设置"""
        try:
            settings_obj, created = NotificationSettings.objects.get_or_create(
                user=user,
                defaults={
                    'email_notifications': True,
                    'push_notifications': True,
                    'story_completed_notify': True,
                    'story_failed_notify': True,
                    'progress_notify': False
                }
            )
            
            if created:
                self.logger.info(f"Created notification settings for user {user.id}")
            else:
                self.logger.info(f"Retrieved notification settings for user {user.id}")
            
            return settings_obj
            
        except Exception as e:
            self.logger.error(f"Failed to get or create notification settings: {e}")
            raise
    
    def update_settings(self, user, settings_data: Dict[str, Any]) -> NotificationSettings:
        """更新通知设置"""
        try:
            settings_obj = self.get_or_create_settings(user)
            
            # 更新设置
            for field, value in settings_data.items():
                if hasattr(settings_obj, field):
                    setattr(settings_obj, field, value)
            
            settings_obj.save()
            
            self.logger.info(f"Updated notification settings for user {user.id}")
            return settings_obj
            
        except Exception as e:
            self.logger.error(f"Failed to update notification settings: {e}")
            raise
