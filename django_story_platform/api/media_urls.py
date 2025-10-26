"""
Django Story Platform - 媒体API URL路由
"""
from django.urls import path
from . import media_api

urlpatterns = [
    # 媒体文件
    path('files/', media_api.MediaFileListView.as_view(), name='media-file-list'),
    path('files/<uuid:pk>/', media_api.MediaFileDetailView.as_view(), name='media-file-detail'),
    path('files/<uuid:media_file_id>/download/', media_api.download_media_file, name='media-file-download'),
    path('files/<uuid:media_file_id>/thumbnail/', media_api.generate_thumbnail, name='media-file-thumbnail'),
    path('files/<uuid:media_file_id>/compress/', media_api.compress_media_file, name='media-file-compress'),
    
    # 媒体库
    path('libraries/', media_api.MediaLibraryListCreateView.as_view(), name='media-library-list-create'),
    path('libraries/<uuid:pk>/', media_api.MediaLibraryDetailView.as_view(), name='media-library-detail'),
    
    # 媒体资产
    path('libraries/<uuid:library_id>/assets/', media_api.MediaAssetListView.as_view(), name='media-asset-list'),
    path('libraries/<uuid:library_id>/assets/<uuid:pk>/', media_api.MediaAssetDetailView.as_view(), name='media-asset-detail'),
    path('libraries/<uuid:library_id>/assets/<uuid:asset_id>/download/', media_api.download_media_asset, name='media-asset-download'),
    
    # 上传
    path('upload/', media_api.MediaUploadView.as_view(), name='media-upload'),
    
    # 统计
    path('stats/', media_api.media_stats, name='media-stats'),
]
