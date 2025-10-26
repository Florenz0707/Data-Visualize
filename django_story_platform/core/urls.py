"""
Django Story Platform - URL路由配置
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # 管理后台
    path('admin/', admin.site.urls),
    
    # API路由
    path('api/v1/users/', include('api.user_urls')),
    path('api/v1/stories/', include('api.story_urls')),
    path('api/v1/media/', include('api.media_urls')),
    path('api/v1/notifications/', include('api.notification_urls')),
    
    # WebSocket路由
    path('ws/', include('api.notification_api')),
]

# 开发环境下的静态文件和媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
