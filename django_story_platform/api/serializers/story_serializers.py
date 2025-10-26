"""
Django Story Platform - 故事序列化器
"""
from rest_framework import serializers
from models import Story, GenerationTask, StoryProgress, MediaFile


class StorySerializer(serializers.ModelSerializer):
    """故事序列化器"""
    user = serializers.StringRelatedField(read_only=True)
    tasks_count = serializers.SerializerMethodField()
    media_files_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Story
        fields = [
            'id', 'user', 'title', 'topic', 'main_role', 'scene',
            'status', 'config', 'pages', 'created_at', 'updated_at',
            'completed_at', 'tasks_count', 'media_files_count'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'completed_at']
    
    def get_tasks_count(self, obj):
        return obj.tasks.count()
    
    def get_media_files_count(self, obj):
        return obj.media_files.count()


class StoryCreateSerializer(serializers.ModelSerializer):
    """故事创建序列化器"""
    
    class Meta:
        model = Story
        fields = ['title', 'topic', 'main_role', 'scene', 'config']
    
    def validate_topic(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Story topic must be at least 10 characters")
        return value.strip()
    
    def validate_config(self, value):
        # 验证配置格式
        required_sections = ['story_writer', 'image_generation', 'speech_generation', 'video_compose']
        for section in required_sections:
            if section not in value:
                raise serializers.ValidationError(f"Missing required config section: {section}")
        return value


class StoryUpdateSerializer(serializers.ModelSerializer):
    """故事更新序列化器"""
    
    class Meta:
        model = Story
        fields = ['title', 'topic', 'main_role', 'scene', 'config']
    
    def validate(self, attrs):
        # 如果故事正在生成中，不允许修改
        if self.instance.status == 'generating':
            raise serializers.ValidationError("Cannot update story while it's being generated")
        return attrs


class StoryStatusSerializer(serializers.ModelSerializer):
    """故事状态序列化器"""
    progress = serializers.SerializerMethodField()
    
    class Meta:
        model = Story
        fields = ['id', 'status', 'created_at', 'updated_at', 'completed_at', 'progress']
    
    def get_progress(self, obj):
        if hasattr(obj, 'progress'):
            return {
                'current_stage': obj.progress.current_stage,
                'stage_progress': obj.progress.stage_progress,
                'total_progress': obj.progress.total_progress,
                'stage_details': obj.progress.stage_details,
                'last_updated': obj.progress.last_updated
            }
        return None


class StoryDownloadSerializer(serializers.Serializer):
    """故事下载序列化器"""
    story_id = serializers.UUIDField()
    
    def validate_story_id(self, value):
        try:
            story = Story.objects.get(id=value)
            if story.status != 'completed':
                raise serializers.ValidationError("Story is not completed yet")
        except Story.DoesNotExist:
            raise serializers.ValidationError("Story not found")
        return value


class StoryGenerationRequestSerializer(serializers.Serializer):
    """故事生成请求序列化器"""
    story_topic = serializers.CharField(max_length=500)
    main_role = serializers.CharField(max_length=100, required=False, allow_blank=True)
    scene = serializers.CharField(max_length=200, required=False, allow_blank=True)
    config = serializers.JSONField(required=False, default=dict)
    
    def validate_story_topic(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Story topic must be at least 10 characters")
        return value.strip()


class GenerationTaskSerializer(serializers.ModelSerializer):
    """生成任务序列化器"""
    story = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = GenerationTask
        fields = [
            'id', 'story', 'task_type', 'status', 'progress',
            'result_data', 'error_message', 'created_at',
            'started_at', 'completed_at'
        ]
        read_only_fields = ['id', 'story', 'created_at', 'started_at', 'completed_at']


class StoryProgressSerializer(serializers.ModelSerializer):
    """故事进度序列化器"""
    
    class Meta:
        model = StoryProgress
        fields = [
            'current_stage', 'stage_progress', 'total_progress',
            'stage_details', 'last_updated'
        ]
        read_only_fields = ['last_updated']


class MediaFileSerializer(serializers.ModelSerializer):
    """媒体文件序列化器"""
    story = serializers.StringRelatedField(read_only=True)
    file_size_mb = serializers.ReadOnlyField()
    
    class Meta:
        model = MediaFile
        fields = [
            'id', 'story', 'file_type', 'file_path', 'file_name',
            'file_size', 'file_size_mb', 'mime_type', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'story', 'created_at']
