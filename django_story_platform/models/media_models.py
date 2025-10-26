"""
Django Story Platform - 媒体相关数据模型
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class MediaFile(models.Model):
    """媒体文件模型"""
    FILE_TYPE_CHOICES = [
        ('image', '图像'),
        ('audio', '音频'),
        ('video', '视频'),
        ('subtitle', '字幕'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey('Story', on_delete=models.CASCADE, related_name='media_files')
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, verbose_name='文件类型')
    file_path = models.CharField(max_length=500, verbose_name='文件路径')
    file_name = models.CharField(max_length=255, verbose_name='文件名')
    file_size = models.BigIntegerField(verbose_name='文件大小(字节)')
    mime_type = models.CharField(max_length=100, blank=True, verbose_name='MIME类型')
    metadata = models.JSONField(default=dict, verbose_name='元数据')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '媒体文件'
        verbose_name_plural = '媒体文件'
    
    def __str__(self):
        return f"{self.story.title} - {self.get_file_type_display()} ({self.file_name})"
    
    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)


class MediaLibrary(models.Model):
    """媒体库模型"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='media_libraries')
    name = models.CharField(max_length=200, verbose_name='媒体库名称')
    description = models.TextField(blank=True, verbose_name='描述')
    is_public = models.BooleanField(default=False, verbose_name='是否公开')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '媒体库'
        verbose_name_plural = '媒体库'
    
    def __str__(self):
        return self.name


class MediaAsset(models.Model):
    """媒体资产模型"""
    ASSET_TYPE_CHOICES = [
        ('image', '图像'),
        ('audio', '音频'),
        ('video', '视频'),
        ('template', '模板'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(MediaLibrary, on_delete=models.CASCADE, related_name='assets')
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPE_CHOICES, verbose_name='资产类型')
    file_path = models.CharField(max_length=500, verbose_name='文件路径')
    file_name = models.CharField(max_length=255, verbose_name='文件名')
    file_size = models.BigIntegerField(verbose_name='文件大小(字节)')
    mime_type = models.CharField(max_length=100, blank=True, verbose_name='MIME类型')
    metadata = models.JSONField(default=dict, verbose_name='元数据')
    tags = models.JSONField(default=list, verbose_name='标签')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '媒体资产'
        verbose_name_plural = '媒体资产'
    
    def __str__(self):
        return f"{self.library.name} - {self.file_name}"
    
    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)
