"""
Django Story Platform - 媒体API接口
"""
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import logging
import os
from pathlib import Path

from models import MediaFile, MediaLibrary, MediaAsset
from api.serializers.media_serializers import (
    MediaFileSerializer, MediaLibrarySerializer, MediaLibraryCreateSerializer,
    MediaAssetSerializer, MediaAssetCreateSerializer, MediaUploadSerializer
)
from tasks.media_tasks import process_media_file, generate_thumbnail_task, compress_media_file_task

logger = logging.getLogger(__name__)


class MediaFileListView(generics.ListAPIView):
    """媒体文件列表视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MediaFileSerializer
    
    def get_queryset(self):
        return MediaFile.objects.filter(story__user=self.request.user)


class MediaFileDetailView(generics.RetrieveDestroyAPIView):
    """媒体文件详情视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MediaFileSerializer
    
    def get_queryset(self):
        return MediaFile.objects.filter(story__user=self.request.user)


class MediaLibraryListCreateView(generics.ListCreateAPIView):
    """媒体库列表和创建视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return MediaLibrary.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MediaLibraryCreateSerializer
        return MediaLibrarySerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class MediaLibraryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """媒体库详情视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MediaLibrarySerializer
    
    def get_queryset(self):
        return MediaLibrary.objects.filter(user=self.request.user)


class MediaAssetListView(generics.ListAPIView):
    """媒体资产列表视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MediaAssetSerializer
    
    def get_queryset(self):
        library_id = self.kwargs.get('library_id')
        return MediaAsset.objects.filter(library_id=library_id, library__user=self.request.user)


class MediaAssetDetailView(generics.RetrieveDestroyAPIView):
    """媒体资产详情视图"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MediaAssetSerializer
    
    def get_queryset(self):
        library_id = self.kwargs.get('library_id')
        return MediaAsset.objects.filter(library_id=library_id, library__user=self.request.user)


class MediaUploadView(APIView):
    """媒体上传视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = MediaUploadSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # 处理文件上传
            uploaded_file = serializer.validated_data['file']
            library_id = serializer.validated_data['library_id']
            asset_type = serializer.validated_data['asset_type']
            
            # 获取媒体库
            library = get_object_or_404(MediaLibrary, id=library_id, user=request.user)
            
            # 保存文件
            file_path = default_storage.save(
                f"media_library/{library_id}/{uploaded_file.name}",
                ContentFile(uploaded_file.read())
            )
            
            # 创建媒体资产记录
            asset = MediaAsset.objects.create(
                library=library,
                asset_type=asset_type,
                file_path=file_path,
                file_name=uploaded_file.name,
                file_size=uploaded_file.size,
                mime_type=uploaded_file.content_type,
                metadata=serializer.validated_data.get('metadata', {}),
                tags=serializer.validated_data.get('tags', [])
            )
            
            # 启动异步处理任务
            process_media_file.delay(str(asset.id))
            
            logger.info(f"Media file uploaded: {asset.id}")
            
            return Response({
                'message': 'File uploaded successfully',
                'asset_id': asset.id,
                'file_path': file_path
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_media_file(request, media_file_id):
    """下载媒体文件"""
    media_file = get_object_or_404(MediaFile, id=media_file_id, story__user=request.user)
    
    try:
        file_path = Path(settings.MEDIA_ROOT) / media_file.file_path
        
        if not file_path.exists():
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=media_file.mime_type or 'application/octet-stream',
            as_attachment=True,
            filename=media_file.file_name
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to download media file {media_file_id}: {e}")
        return Response({'error': 'Download failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_media_asset(request, asset_id):
    """下载媒体资产"""
    asset = get_object_or_404(MediaAsset, id=asset_id, library__user=request.user)
    
    try:
        file_path = Path(settings.MEDIA_ROOT) / asset.file_path
        
        if not file_path.exists():
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=asset.mime_type or 'application/octet-stream',
            as_attachment=True,
            filename=asset.file_name
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to download media asset {asset_id}: {e}")
        return Response({'error': 'Download failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_thumbnail(request, media_file_id):
    """生成缩略图"""
    media_file = get_object_or_404(MediaFile, id=media_file_id, story__user=request.user)
    
    try:
        # 启动异步任务
        task = generate_thumbnail_task.delay(str(media_file.id))
        
        return Response({
            'message': 'Thumbnail generation started',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Failed to start thumbnail generation: {e}")
        return Response({'error': 'Failed to start thumbnail generation'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def compress_media_file(request, media_file_id):
    """压缩媒体文件"""
    media_file = get_object_or_404(MediaFile, id=media_file_id, story__user=request.user)
    
    quality = request.data.get('quality', 80)
    
    try:
        # 启动异步任务
        task = compress_media_file_task.delay(str(media_file.id), quality)
        
        return Response({
            'message': 'Media compression started',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Failed to start media compression: {e}")
        return Response({'error': 'Failed to start media compression'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def media_stats(request):
    """获取媒体统计信息"""
    user = request.user
    
    stats = {
        'total_files': MediaFile.objects.filter(story__user=user).count(),
        'total_libraries': MediaLibrary.objects.filter(user=user).count(),
        'total_assets': MediaAsset.objects.filter(library__user=user).count(),
        'storage_used': sum(
            asset.file_size for asset in MediaAsset.objects.filter(library__user=user)
        ),
        'file_types': {
            'image': MediaFile.objects.filter(story__user=user, file_type='image').count(),
            'audio': MediaFile.objects.filter(story__user=user, file_type='audio').count(),
            'video': MediaFile.objects.filter(story__user=user, file_type='video').count(),
        }
    }
    
    return Response(stats)
