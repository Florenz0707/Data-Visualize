"""
Django Story Platform - 故事相关数据模型
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Story(models.Model):
    """故事模型"""
    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('generating', '生成中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stories')
    title = models.CharField(max_length=200, verbose_name='故事标题')
    topic = models.TextField(verbose_name='故事主题')
    main_role = models.CharField(max_length=100, blank=True, verbose_name='主角')
    scene = models.CharField(max_length=200, blank=True, verbose_name='场景')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    config = models.JSONField(default=dict, verbose_name='生成配置')
    pages = models.JSONField(default=list, blank=True, verbose_name='故事页面')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '故事'
        verbose_name_plural = '故事'
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_generating(self):
        return self.status == 'generating'


class GenerationTask(models.Model):
    """生成任务模型"""
    TASK_TYPE_CHOICES = [
        ('story', '故事生成'),
        ('image', '图像生成'),
        ('speech', '语音生成'),
        ('video', '视频合成'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('running', '运行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='tasks')
    task_type = models.CharField(max_length=50, choices=TASK_TYPE_CHOICES, verbose_name='任务类型')
    celery_task_id = models.CharField(max_length=255, unique=True, verbose_name='Celery任务ID')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    progress = models.IntegerField(default=0, verbose_name='进度百分比')
    result_data = models.JSONField(default=dict, verbose_name='结果数据')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '生成任务'
        verbose_name_plural = '生成任务'
    
    def __str__(self):
        return f"{self.story.title} - {self.get_task_type_display()} ({self.get_status_display()})"


class StoryProgress(models.Model):
    """故事生成进度模型"""
    story = models.OneToOneField(Story, on_delete=models.CASCADE, related_name='progress')
    current_stage = models.CharField(max_length=50, default='pending', verbose_name='当前阶段')
    stage_progress = models.IntegerField(default=0, verbose_name='阶段进度')
    total_progress = models.IntegerField(default=0, verbose_name='总进度')
    stage_details = models.JSONField(default=dict, verbose_name='阶段详情')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='最后更新时间')
    
    class Meta:
        verbose_name = '故事进度'
        verbose_name_plural = '故事进度'
    
    def __str__(self):
        return f"{self.story.title} - {self.current_stage} ({self.total_progress}%)"
    
    def update_progress(self, stage, progress, details=None):
        """更新进度"""
        self.current_stage = stage
        self.stage_progress = progress
        self.stage_details = details or {}
        self.save()
    
    def calculate_total_progress(self):
        """计算总进度"""
        stage_weights = {
            'story': 20,
            'segment': 10,
            'image': 30,
            'speech': 30,
            'compose': 10,
        }
        
        total = 0
        for stage, weight in stage_weights.items():
            if stage == self.current_stage:
                total += (self.stage_progress * weight) // 100
            elif self.stage_progress == 100:
                total += weight
        
        self.total_progress = min(total, 100)
        self.save()
        return self.total_progress
