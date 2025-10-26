"""
Django Story Platform - 通知API接口
"""
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging

from models import Notification, NotificationSettings
from api.serializers.notification_serializers import (
    NotificationSerializer, NotificationCreateSerializer,
    NotificationSettingsSerializer, NotificationMarkReadSerializer,
    NotificationStatsSerializer
)
from tasks.notification_tasks import send_email_notification, send_bulk_notifications

logger = logging.getLogger(__name__)


class NotificationListView(generics.ListAPIView):
    """通知列表视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


class NotificationDetailView(generics.RetrieveAPIView):
    """通知详情视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationCreateView(generics.CreateAPIView):
    """通知创建视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationCreateSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class NotificationSettingsView(generics.RetrieveUpdateAPIView):
    """通知设置视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSettingsSerializer
    
    def get_object(self):
        settings_obj, created = NotificationSettings.objects.get_or_create(
            user=self.request.user
        )
        return settings_obj


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_notifications_read(request):
    """标记通知为已读"""
    serializer = NotificationMarkReadSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        notification_ids = serializer.validated_data['notification_ids']
        
        # 更新通知状态
        updated_count = Notification.objects.filter(
            id__in=notification_ids,
            user=request.user
        ).update(is_read=True)
        
        logger.info(f"Marked {updated_count} notifications as read for user {request.user.id}")
        
        return Response({
            'message': f'{updated_count} notifications marked as read',
            'updated_count': updated_count
        })
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_all_notifications_read(request):
    """标记所有通知为已读"""
    try:
        updated_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)
        
        logger.info(f"Marked all {updated_count} notifications as read for user {request.user.id}")
        
        return Response({
            'message': f'All {updated_count} notifications marked as read',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Failed to mark all notifications as read: {e}")
        return Response({'error': 'Failed to mark notifications as read'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def notification_stats(request):
    """获取通知统计信息"""
    user = request.user
    
    # 获取通知统计
    total_count = Notification.objects.filter(user=user).count()
    unread_count = Notification.objects.filter(user=user, is_read=False).count()
    read_count = total_count - unread_count
    
    # 按类型统计
    by_type = {}
    for notification_type, _ in Notification.NOTIFICATION_TYPE_CHOICES:
        count = Notification.objects.filter(user=user, notification_type=notification_type).count()
        by_type[notification_type] = count
    
    # 获取最近的通知
    recent_notifications = Notification.objects.filter(user=user).order_by('-created_at')[:5]
    recent_serializer = NotificationSerializer(recent_notifications, many=True)
    
    stats = {
        'total_count': total_count,
        'unread_count': unread_count,
        'read_count': read_count,
        'by_type': by_type,
        'recent_notifications': recent_serializer.data
    }
    
    return Response(stats)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def send_test_notification(request):
    """发送测试通知"""
    try:
        notification = Notification.objects.create(
            user=request.user,
            notification_type='system',
            title='测试通知',
            message='这是一个测试通知，用于验证通知系统是否正常工作。',
            data={'test': True}
        )
        
        # 发送邮件通知
        send_email_notification.delay(str(notification.id))
        
        logger.info(f"Test notification sent to user {request.user.id}")
        
        return Response({
            'message': 'Test notification sent',
            'notification_id': notification.id
        })
        
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}")
        return Response({'error': 'Failed to send test notification'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_notification(request, notification_id):
    """删除通知"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    
    try:
        notification.delete()
        logger.info(f"Notification {notification_id} deleted for user {request.user.id}")
        
        return Response({'message': 'Notification deleted successfully'})
        
    except Exception as e:
        logger.error(f"Failed to delete notification {notification_id}: {e}")
        return Response({'error': 'Failed to delete notification'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_all_read_notifications(request):
    """删除所有已读通知"""
    try:
        deleted_count = Notification.objects.filter(
            user=request.user,
            is_read=True
        ).delete()[0]
        
        logger.info(f"Deleted {deleted_count} read notifications for user {request.user.id}")
        
        return Response({
            'message': f'{deleted_count} read notifications deleted',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logger.error(f"Failed to delete read notifications: {e}")
        return Response({'error': 'Failed to delete notifications'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# WebSocket相关功能
def send_websocket_message(user_id, message):
    """发送WebSocket消息"""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "notification_message",
                "message": message
            }
        )
        
        logger.info(f"WebSocket message sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send WebSocket message: {e}")


# WebSocket URL patterns
from django.urls import path
from .consumers import StoryProgressConsumer, NotificationConsumer

websocket_urlpatterns = [
    path('ws/story-progress/', StoryProgressConsumer.as_asgi()),
    path('ws/notifications/', NotificationConsumer.as_asgi()),
]
