"""
Django Story Platform - 通知相关数据模型
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Notification(models.Model):
    """通知模型"""
    NOTIFICATION_TYPE_CHOICES = [
        ('story_completed', '故事生成完成'),
        ('story_failed', '故事生成失败'),
        ('task_progress', '任务进度更新'),
        ('system', '系统通知'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPE_CHOICES, verbose_name='通知类型')
    title = models.CharField(max_length=200, verbose_name='标题')
    message = models.TextField(verbose_name='消息内容')
    data = models.JSONField(default=dict, verbose_name='附加数据')
    is_read = models.BooleanField(default=False, verbose_name='是否已读')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='阅读时间')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '通知'
        verbose_name_plural = '通知'
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"
    
    def mark_as_read(self):
        """标记为已读"""
        if not self.is_read:
            self.is_read = True
            from django.utils import timezone
            self.read_at = timezone.now()
            self.save()


class NotificationSettings(models.Model):
    """通知设置模型"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_settings')
    email_notifications = models.BooleanField(default=True, verbose_name='邮件通知')
    push_notifications = models.BooleanField(default=True, verbose_name='推送通知')
    story_completed_notify = models.BooleanField(default=True, verbose_name='故事完成通知')
    story_failed_notify = models.BooleanField(default=True, verbose_name='故事失败通知')
    progress_notify = models.BooleanField(default=False, verbose_name='进度通知')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '通知设置'
        verbose_name_plural = '通知设置'
    
    def __str__(self):
        return f"{self.user.username} - 通知设置"
