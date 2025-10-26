"""
Django Story Platform - 通知相关异步任务
"""
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import logging

from models import Notification, NotificationSettings

logger = logging.getLogger(__name__)


@shared_task
def send_email_notification(notification_id):
    """发送邮件通知的异步任务"""
    logger.info(f"Sending email notification {notification_id}")
    
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # 检查用户的通知设置
        try:
            settings_obj = notification.user.notification_settings
            if not settings_obj.email_notifications:
                logger.info(f"Email notifications disabled for user {notification.user.id}")
                return {'status': 'skipped', 'reason': 'email_disabled'}
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
        
        logger.info(f"Email notification sent for notification {notification_id}")
        return {'status': 'success', 'notification_id': notification_id}
        
    except Notification.DoesNotExist:
        error_msg = f"Notification {notification_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Email notification failed: {str(e)}"
        logger.error(f"Email notification error for {notification_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}


@shared_task
def send_bulk_notifications(notification_ids):
    """批量发送通知的异步任务"""
    logger.info(f"Sending bulk notifications for {len(notification_ids)} notifications")
    
    results = []
    for notification_id in notification_ids:
        try:
            result = send_email_notification.delay(notification_id)
            results.append({'notification_id': notification_id, 'task_id': result.id})
        except Exception as e:
            logger.error(f"Failed to queue notification {notification_id}: {e}")
            results.append({'notification_id': notification_id, 'error': str(e)})
    
    logger.info(f"Bulk notification tasks queued for {len(notification_ids)} notifications")
    return {'status': 'success', 'results': results}


@shared_task
def cleanup_read_notifications():
    """清理已读通知"""
    from datetime import timedelta
    
    try:
        # 删除30天前的已读通知
        cutoff_date = timezone.now() - timedelta(days=30)
        
        old_notifications = Notification.objects.filter(
            is_read=True,
            read_at__lt=cutoff_date
        )
        
        count = old_notifications.count()
        old_notifications.delete()
        
        logger.info(f"Cleaned up {count} old read notifications")
        return {'status': 'success', 'deleted_count': count}
        
    except Exception as e:
        error_msg = f"Notification cleanup failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}


@shared_task
def send_daily_summary(user_id):
    """发送每日摘要通知"""
    logger.info(f"Sending daily summary for user {user_id}")
    
    try:
        from models import User
        user = User.objects.get(id=user_id)
        
        # 获取用户的通知设置
        try:
            settings_obj = user.notification_settings
            if not settings_obj.email_notifications:
                logger.info(f"Email notifications disabled for user {user_id}")
                return {'status': 'skipped', 'reason': 'email_disabled'}
        except NotificationSettings.DoesNotExist:
            # 如果没有设置，默认发送
            pass
        
        # 获取用户今日的活动统计
        today = timezone.now().date()
        stories_created = user.stories.filter(created_at__date=today).count()
        stories_completed = user.stories.filter(
            status='completed',
            completed_at__date=today
        ).count()
        
        # 创建摘要通知
        notification = Notification.objects.create(
            user=user,
            notification_type='system',
            title='每日摘要',
            message=f'今日您创建了 {stories_created} 个故事，完成了 {stories_completed} 个故事。',
            data={
                'stories_created': stories_created,
                'stories_completed': stories_completed,
                'date': today.isoformat()
            }
        )
        
        # 发送邮件
        send_email_notification.delay(str(notification.id))
        
        logger.info(f"Daily summary sent for user {user_id}")
        return {'status': 'success', 'user_id': user_id}
        
    except User.DoesNotExist:
        error_msg = f"User {user_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Daily summary failed: {str(e)}"
        logger.error(f"Daily summary error for {user_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}


@shared_task
def send_weekly_report(user_id):
    """发送周报通知"""
    logger.info(f"Sending weekly report for user {user_id}")
    
    try:
        from models import User
        user = User.objects.get(id=user_id)
        
        # 获取用户本周的活动统计
        from datetime import timedelta
        week_ago = timezone.now() - timedelta(days=7)
        
        stories_created = user.stories.filter(created_at__gte=week_ago).count()
        stories_completed = user.stories.filter(
            status='completed',
            completed_at__gte=week_ago
        ).count()
        
        # 创建周报通知
        notification = Notification.objects.create(
            user=user,
            notification_type='system',
            title='周报',
            message=f'本周您创建了 {stories_created} 个故事，完成了 {stories_completed} 个故事。',
            data={
                'stories_created': stories_created,
                'stories_completed': stories_completed,
                'period': 'week'
            }
        )
        
        # 发送邮件
        send_email_notification.delay(str(notification.id))
        
        logger.info(f"Weekly report sent for user {user_id}")
        return {'status': 'success', 'user_id': user_id}
        
    except User.DoesNotExist:
        error_msg = f"User {user_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Weekly report failed: {str(e)}"
        logger.error(f"Weekly report error for {user_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}
