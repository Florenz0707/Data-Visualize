"""
Django Story Platform - 通知序列化器
"""
from rest_framework import serializers
from models import Notification, NotificationSettings


class NotificationSerializer(serializers.ModelSerializer):
    """通知序列化器"""
    user = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'notification_type', 'title', 'message',
            'data', 'is_read', 'created_at', 'read_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'read_at']


class NotificationCreateSerializer(serializers.ModelSerializer):
    """通知创建序列化器"""
    
    class Meta:
        model = Notification
        fields = ['notification_type', 'title', 'message', 'data']
    
    def validate_title(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Title must be at least 2 characters")
        return value.strip()
    
    def validate_message(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Message must be at least 5 characters")
        return value.strip()


class NotificationSettingsSerializer(serializers.ModelSerializer):
    """通知设置序列化器"""
    user = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = NotificationSettings
        fields = [
            'email_notifications', 'push_notifications',
            'story_completed_notify', 'story_failed_notify',
            'progress_notify', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class NotificationMarkReadSerializer(serializers.Serializer):
    """标记通知为已读序列化器"""
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False
    )
    
    def validate_notification_ids(self, value):
        # 验证通知是否存在且属于当前用户
        request = self.context.get('request')
        if request:
            notifications = Notification.objects.filter(
                id__in=value,
                user=request.user
            )
            if notifications.count() != len(value):
                raise serializers.ValidationError("Some notifications not found or not accessible")
        return value


class NotificationStatsSerializer(serializers.Serializer):
    """通知统计序列化器"""
    total_count = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    by_type = serializers.DictField()
    recent_notifications = NotificationSerializer(many=True)
