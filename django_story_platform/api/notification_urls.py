"""
Django Story Platform - 通知API URL路由
"""
from django.urls import path
from . import notification_api

urlpatterns = [
    # 通知
    path('', notification_api.NotificationListView.as_view(), name='notification-list'),
    path('<uuid:pk>/', notification_api.NotificationDetailView.as_view(), name='notification-detail'),
    path('create/', notification_api.NotificationCreateView.as_view(), name='notification-create'),
    path('mark-read/', notification_api.mark_notifications_read, name='notification-mark-read'),
    path('mark-all-read/', notification_api.mark_all_notifications_read, name='notification-mark-all-read'),
    path('delete/<uuid:notification_id>/', notification_api.delete_notification, name='notification-delete'),
    path('delete-all-read/', notification_api.delete_all_read_notifications, name='notification-delete-all-read'),
    
    # 通知设置
    path('settings/', notification_api.NotificationSettingsView.as_view(), name='notification-settings'),
    
    # 统计和测试
    path('stats/', notification_api.notification_stats, name='notification-stats'),
    path('test/', notification_api.send_test_notification, name='notification-test'),
]
