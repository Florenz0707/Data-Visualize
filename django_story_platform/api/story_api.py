"""
Django Story Platform - 故事API接口
"""
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404
from django.conf import settings
import logging

from models import Story, GenerationTask, MediaFile, StoryProgress
from api.serializers.story_serializers import (
    StorySerializer, StoryCreateSerializer, StoryUpdateSerializer,
    GenerationTaskSerializer, MediaFileSerializer, StoryProgressSerializer,
    StoryStatusSerializer, StoryDownloadSerializer, StoryGenerationRequestSerializer
)
from tasks.story_tasks import generate_story_task

logger = logging.getLogger(__name__)


class StoryListCreateView(generics.ListCreateAPIView):
    """故事列表和创建视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Story.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return StoryCreateSerializer
        return StorySerializer
    
    def perform_create(self, serializer):
        story = serializer.save(user=self.request.user)
        # 启动生成任务
        generate_story_task.delay(str(story.id))
        logger.info(f"Story generation task started for story {story.id}")


class StoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """故事详情视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Story.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return StoryUpdateSerializer
        return StorySerializer


class StoryGenerationView(APIView):
    """故事生成视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """创建新的故事生成任务"""
        serializer = StoryGenerationRequestSerializer(data=request.data)
        if serializer.is_valid():
            # 创建故事记录
            story_data = {
                'title': f"Story: {serializer.validated_data['story_topic'][:50]}...",
                'topic': serializer.validated_data['story_topic'],
                'main_role': serializer.validated_data.get('main_role', ''),
                'scene': serializer.validated_data.get('scene', ''),
                'config': serializer.validated_data.get('config', {}),
                'status': 'pending'
            }
            
            story_serializer = StoryCreateSerializer(data=story_data)
            if story_serializer.is_valid():
                story = story_serializer.save(user=request.user)
                
                # 启动生成任务
                generate_story_task.delay(str(story.id))
                
                logger.info(f"Story generation task started for story {story.id}")
                
                return Response({
                    'message': 'Story generation started',
                    'story_id': story.id,
                    'status': story.status
                }, status=status.HTTP_201_CREATED)
            else:
                return Response(story_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def story_status(request, story_id):
    """获取故事生成状态"""
    story = get_object_or_404(Story, id=story_id, user=request.user)
    
    # 获取最新的任务状态
    latest_task = story.tasks.order_by('-created_at').first()
    
    # 获取进度信息
    progress = story.progress if hasattr(story, 'progress') else None
    
    response_data = {
        'story_id': str(story.id),
        'status': story.status,
        'progress': latest_task.progress if latest_task else 0,
        'created_at': story.created_at,
        'updated_at': story.updated_at,
    }
    
    if progress:
        response_data.update({
            'current_stage': progress.current_stage,
            'stage_progress': progress.stage_progress,
            'total_progress': progress.total_progress,
            'stage_details': progress.stage_details,
            'last_updated': progress.last_updated
        })
    
    return Response(response_data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_video(request, story_id):
    """下载生成的视频"""
    story = get_object_or_404(Story, id=story_id, user=request.user)
    
    if story.status != 'completed':
        return Response({'error': 'Story not completed'}, status=status.HTTP_400_BAD_REQUEST)
    
    # 查找视频文件
    video_file = story.media_files.filter(file_type='video').first()
    if not video_file:
        return Response({'error': 'Video not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # 构建文件路径
    file_path = settings.MEDIA_ROOT / video_file.file_path
    
    if not file_path.exists():
        return Response({'error': 'Video file not found on disk'}, status=status.HTTP_404_NOT_FOUND)
    
    # 返回文件下载响应
    response = FileResponse(
        open(file_path, 'rb'),
        content_type=video_file.mime_type or 'video/mp4',
        as_attachment=True,
        filename=video_file.file_name
    )
    
    return response


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def regenerate_story(request, story_id):
    """重新生成故事"""
    story = get_object_or_404(Story, id=story_id, user=request.user)
    
    # 检查是否可以重新生成
    if story.status == 'generating':
        return Response({'error': 'Story is currently being generated'}, status=status.HTTP_400_BAD_REQUEST)
    
    # 重置状态
    story.status = 'pending'
    story.completed_at = None
    story.save()
    
    # 取消现有任务
    for task in story.tasks.filter(status__in=['pending', 'running']):
        task.status = 'cancelled'
        task.save()
    
    # 启动新的生成任务
    generate_story_task.delay(str(story.id))
    
    logger.info(f"Story regeneration started for story {story.id}")
    
    return Response({
        'message': 'Story regeneration started',
        'story_id': story.id,
        'status': story.status
    })
