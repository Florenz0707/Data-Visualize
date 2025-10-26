"""
Django Story Platform - 媒体相关异步任务
"""
from celery import shared_task
from django.utils import timezone
from django.core.files.storage import default_storage
from django.conf import settings
import logging
import os
from pathlib import Path

from models import MediaFile, MediaAsset, MediaLibrary
from services.media_service import MediaProcessingService

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_media_file(self, media_file_id):
    """处理媒体文件的异步任务"""
    logger.info(f"Starting media processing for file {media_file_id}")
    
    try:
        media_file = MediaFile.objects.get(id=media_file_id)
        
        # 创建处理服务
        processing_service = MediaProcessingService(logger)
        
        # 根据文件类型进行处理
        if media_file.file_type == 'image':
            result = processing_service.process_image(media_file)
        elif media_file.file_type == 'audio':
            result = processing_service.process_audio(media_file)
        elif media_file.file_type == 'video':
            result = processing_service.process_video(media_file)
        else:
            raise ValueError(f"Unsupported file type: {media_file.file_type}")
        
        # 更新媒体文件元数据
        media_file.metadata.update(result.get('metadata', {}))
        media_file.save()
        
        logger.info(f"Media processing completed for file {media_file_id}")
        return {'status': 'success', 'media_file_id': media_file_id, 'result': result}
        
    except MediaFile.DoesNotExist:
        error_msg = f"Media file {media_file_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Media processing failed: {str(e)}"
        logger.error(f"Media processing error for {media_file_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}


@shared_task
def generate_thumbnail_task(media_file_id):
    """生成缩略图的异步任务"""
    logger.info(f"Generating thumbnail for media file {media_file_id}")
    
    try:
        media_file = MediaFile.objects.get(id=media_file_id)
        
        # 创建处理服务
        processing_service = MediaProcessingService(logger)
        
        # 生成缩略图
        thumbnail_path = processing_service.generate_thumbnail(media_file)
        
        if thumbnail_path:
            # 更新元数据
            media_file.metadata['thumbnail_path'] = thumbnail_path
            media_file.save()
            
            logger.info(f"Thumbnail generated for media file {media_file_id}")
            return {'status': 'success', 'thumbnail_path': thumbnail_path}
        else:
            raise ValueError("Failed to generate thumbnail")
        
    except Exception as e:
        error_msg = f"Thumbnail generation failed: {str(e)}"
        logger.error(f"Thumbnail generation error for {media_file_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}


@shared_task
def compress_media_file_task(media_file_id, quality=80):
    """压缩媒体文件的异步任务"""
    logger.info(f"Compressing media file {media_file_id} with quality {quality}")
    
    try:
        media_file = MediaFile.objects.get(id=media_file_id)
        
        # 创建处理服务
        processing_service = MediaProcessingService(logger)
        
        # 压缩文件
        compressed_path = processing_service.compress_file(media_file, quality)
        
        if compressed_path:
            # 更新文件路径
            media_file.file_path = compressed_path
            media_file.save()
            
            logger.info(f"Media file compressed for {media_file_id}")
            return {'status': 'success', 'compressed_path': compressed_path}
        else:
            raise ValueError("Failed to compress file")
        
    except Exception as e:
        error_msg = f"Media compression failed: {str(e)}"
        logger.error(f"Media compression error for {media_file_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}


@shared_task
def cleanup_orphaned_files():
    """清理孤儿文件"""
    try:
        # 获取所有媒体文件路径
        media_files = MediaFile.objects.all()
        valid_paths = set()
        
        for media_file in media_files:
            if media_file.file_path:
                valid_paths.add(media_file.file_path)
        
        # 扫描媒体目录
        media_root = Path(settings.MEDIA_ROOT)
        orphaned_files = []
        
        for file_path in media_root.rglob('*'):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(media_root))
                if relative_path not in valid_paths:
                    orphaned_files.append(file_path)
        
        # 删除孤儿文件
        deleted_count = 0
        for file_path in orphaned_files:
            try:
                file_path.unlink()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete orphaned file {file_path}: {e}")
        
        logger.info(f"Cleaned up {deleted_count} orphaned files")
        return {'status': 'success', 'deleted_count': deleted_count}
        
    except Exception as e:
        error_msg = f"Orphaned files cleanup failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}


@shared_task
def backup_media_library_task(library_id):
    """备份媒体库的异步任务"""
    logger.info(f"Backing up media library {library_id}")
    
    try:
        library = MediaLibrary.objects.get(id=library_id)
        
        # 创建备份服务
        from services.media_service import MediaBackupService
        backup_service = MediaBackupService(logger)
        
        # 执行备份
        backup_path = backup_service.backup_library(library)
        
        logger.info(f"Media library backup completed for {library_id}")
        return {'status': 'success', 'backup_path': backup_path}
        
    except MediaLibrary.DoesNotExist:
        error_msg = f"Media library {library_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Media library backup failed: {str(e)}"
        logger.error(f"Media library backup error for {library_id}: {error_msg}")
        return {'status': 'error', 'message': error_msg}
