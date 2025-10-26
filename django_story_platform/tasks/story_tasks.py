"""
Django Story Platform - 故事相关异步任务
"""
from celery import shared_task
from django.utils import timezone
from django.conf import settings
import logging
import traceback

from models import Story, GenerationTask, StoryProgress, Notification
from services.story_service import StoryGenerationService, StoryManagementService

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def generate_story_task(self, story_id):
    """生成故事的异步任务"""
    logger.info(f"Starting story generation task for story {story_id}")
    
    try:
        # 获取故事对象
        story = Story.objects.get(id=story_id)
        
        # 创建生成任务记录
        task_record = GenerationTask.objects.create(
            story=story,
            task_type='story',
            celery_task_id=self.request.id,
            status='running',
            started_at=timezone.now()
        )
        
        # 更新故事状态
        story.status = 'generating'
        story.save()
        
        # 创建进度记录
        progress, created = StoryProgress.objects.get_or_create(story=story)
        progress.current_stage = 'pending'
        progress.total_progress = 0
        progress.save()
        
        # 创建生成服务
        config = story.config or {}
        generation_service = StoryGenerationService(config, logger)
        
        # 设置进度回调
        def progress_callback(stage, details):
            try:
                # 更新进度记录
                progress.current_stage = stage
                progress.stage_details = details
                progress.calculate_total_progress()
                progress.save()
                
                # 更新任务进度
                task_record.progress = progress.total_progress
                task_record.save()
                
                # 发送WebSocket通知
                send_progress_notification.delay(str(story.id), stage, details)
                
                logger.info(f"Story {story_id} progress: {stage} - {progress.total_progress}%")
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
        
        # 执行故事生成
        result = generation_service.generate_story(story, progress_callback)
        
        # 更新任务状态
        task_record.status = 'completed'
        task_record.progress = 100
        task_record.result_data = result
        task_record.completed_at = timezone.now()
        task_record.save()
        
        # 更新故事状态
        story.status = 'completed'
        story.completed_at = timezone.now()
        story.save()
        
        # 发送完成通知
        send_completion_notification.delay(str(story.id), 'success')
        
        logger.info(f"Story generation completed for story {story_id}")
        return {'status': 'success', 'story_id': story_id, 'result': result}
        
    except Story.DoesNotExist:
        error_msg = f"Story {story_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Story generation failed: {str(e)}"
        logger.error(f"Story generation error for {story_id}: {error_msg}")
        logger.error(traceback.format_exc())
        
        # 更新任务状态为失败
        try:
            task_record = GenerationTask.objects.get(celery_task_id=self.request.id)
            task_record.status = 'failed'
            task_record.error_message = error_msg
            task_record.completed_at = timezone.now()
            task_record.save()
            
            # 更新故事状态
            story = Story.objects.get(id=story_id)
            story.status = 'failed'
            story.save()
            
            # 发送失败通知
            send_completion_notification.delay(str(story_id), 'failed', error_msg)
            
        except Exception as update_error:
            logger.error(f"Failed to update task status: {update_error}")
        
        return {'status': 'error', 'message': error_msg}


@shared_task
def resume_story_generation_task(story_id):
    """恢复故事生成的异步任务"""
    logger.info(f"Resuming story generation for story {story_id}")
    
    try:
        story = Story.objects.get(id=story_id)
        
        if story.status != 'generating':
            raise ValueError(f"Story {story_id} is not in generating state")
        
        # 创建生成服务
        config = story.config or {}
        generation_service = StoryGenerationService(config, logger)
        
        # 执行恢复生成
        result = generation_service.resume_story_generation(story)
        
        # 更新故事状态
        story.status = 'completed'
        story.completed_at = timezone.now()
        story.save()
        
        # 发送完成通知
        send_completion_notification.delay(str(story.id), 'success')
        
        logger.info(f"Story generation resumed and completed for story {story_id}")
        return {'status': 'success', 'story_id': story_id, 'result': result}
        
    except Exception as e:
        error_msg = f"Story generation resume failed: {str(e)}"
        logger.error(f"Story generation resume error for {story_id}: {error_msg}")
        
        # 更新故事状态为失败
        try:
            story = Story.objects.get(id=story_id)
            story.status = 'failed'
            story.save()
            
            # 发送失败通知
            send_completion_notification.delay(str(story_id), 'failed', error_msg)
            
        except Exception as update_error:
            logger.error(f"Failed to update story status: {update_error}")
        
        return {'status': 'error', 'message': error_msg}


@shared_task
def send_progress_notification(story_id, stage, details):
    """发送进度通知"""
    try:
        story = Story.objects.get(id=story_id)
        
        # 创建通知
        notification = Notification.objects.create(
            user=story.user,
            notification_type='task_progress',
            title=f'故事生成进度更新',
            message=f'您的故事 "{story.title}" 当前阶段: {stage}',
            data={
                'story_id': story_id,
                'stage': stage,
                'details': details
            }
        )
        
        # 发送WebSocket消息
        from api.notification_api import send_websocket_message
        send_websocket_message(
            story.user.id,
            {
                'type': 'progress_update',
                'story_id': story_id,
                'stage': stage,
                'details': details
            }
        )
        
        logger.info(f"Progress notification sent for story {story_id}")
        
    except Exception as e:
        logger.error(f"Failed to send progress notification: {e}")


@shared_task
def send_completion_notification(story_id, status, error_message=None):
    """发送完成通知"""
    try:
        story = Story.objects.get(id=story_id)
        
        if status == 'success':
            notification_type = 'story_completed'
            title = '故事生成完成'
            message = f'您的故事 "{story.title}" 已生成完成！'
        else:
            notification_type = 'story_failed'
            title = '故事生成失败'
            message = f'您的故事 "{story.title}" 生成失败: {error_message or "未知错误"}'
        
        # 创建通知
        notification = Notification.objects.create(
            user=story.user,
            notification_type=notification_type,
            title=title,
            message=message,
            data={
                'story_id': story_id,
                'status': status,
                'error_message': error_message
            }
        )
        
        # 发送WebSocket消息
        from api.notification_api import send_websocket_message
        send_websocket_message(
            story.user.id,
            {
                'type': 'story_completion',
                'story_id': story_id,
                'status': status,
                'error_message': error_message
            }
        )
        
        logger.info(f"Completion notification sent for story {story_id}")
        
    except Exception as e:
        logger.error(f"Failed to send completion notification: {e}")


@shared_task
def cleanup_old_tasks():
    """清理旧任务"""
    from datetime import timedelta
    
    try:
        # 删除7天前的已完成任务
        cutoff_date = timezone.now() - timedelta(days=7)
        
        old_tasks = GenerationTask.objects.filter(
            status__in=['completed', 'failed'],
            completed_at__lt=cutoff_date
        )
        
        count = old_tasks.count()
        old_tasks.delete()
        
        logger.info(f"Cleaned up {count} old tasks")
        
    except Exception as e:
        logger.error(f"Failed to cleanup old tasks: {e}")


@shared_task
def cleanup_old_notifications():
    """清理旧通知"""
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
        
        logger.info(f"Cleaned up {count} old notifications")
        
    except Exception as e:
        logger.error(f"Failed to cleanup old notifications: {e}")
