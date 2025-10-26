"""
Django Story Platform - 故事业务服务
"""
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from django.conf import settings
from django.utils import timezone

from models import Story, StoryProgress, GenerationTask, MediaFile
from agents.mm_story_agent import MMStoryAgent


class StoryGenerationService:
    """故事生成服务"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.output_dir = Path(settings.MEDIA_ROOT) / "stories"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_story(self, story: Story, progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """生成完整的故事"""
        self.logger.info(f"Starting story generation for story {story.id}")
        
        try:
            # 更新故事状态
            story.status = 'generating'
            story.save()
            
            # 创建进度记录
            progress, created = StoryProgress.objects.get_or_create(story=story)
            progress.current_stage = 'pending'
            progress.total_progress = 0
            progress.save()
            
            # 创建MM-StoryAgent实例
            agent_config = {
                'output_dir': str(self.output_dir),
                'modalities': ['image', 'speech'],
                'parallel_mode': story.config.get('execution', {}).get('mode', 'parallel') == 'parallel'
            }
            
            mm_agent = MMStoryAgent(agent_config, self.logger)
            
            # 设置进度回调
            if progress_callback:
                mm_agent.set_progress_callback(progress_callback)
            else:
                mm_agent.set_progress_callback(self._default_progress_callback)
            
            # 生成故事
            result = mm_agent.generate_story(story.config)
            
            # 更新故事数据
            story.pages = result['story']['pages']
            story.status = 'completed'
            story.save()
            
            # 更新进度
            progress.current_stage = 'completed'
            progress.total_progress = 100
            progress.save()
            
            self.logger.info(f"Story generation completed for story {story.id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Story generation failed for story {story.id}: {e}")
            
            # 更新故事状态为失败
            story.status = 'failed'
            story.save()
            
            # 更新进度
            if hasattr(story, 'progress'):
                story.progress.current_stage = 'error'
                story.progress.stage_details = {'error': str(e)}
                story.progress.save()
            
            raise
    
    def resume_story_generation(self, story: Story) -> Dict[str, Any]:
        """恢复故事生成"""
        self.logger.info(f"Resuming story generation for story {story.id}")
        
        try:
            # 创建MM-StoryAgent实例
            agent_config = {
                'output_dir': str(self.output_dir),
                'modalities': ['image', 'speech'],
                'parallel_mode': story.config.get('execution', {}).get('mode', 'parallel') == 'parallel'
            }
            
            mm_agent = MMStoryAgent(agent_config, self.logger)
            mm_agent.story_id = str(story.id)
            
            # 从视频合成阶段恢复
            result = mm_agent.resume_from_video_composition(story.config)
            
            # 更新故事状态
            story.status = 'completed'
            story.save()
            
            self.logger.info(f"Story generation resumed and completed for story {story.id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Story generation resume failed for story {story.id}: {e}")
            
            story.status = 'failed'
            story.save()
            raise
    
    def _default_progress_callback(self, stage: str, details: Dict[str, Any]):
        """默认进度回调"""
        self.logger.info(f"Progress update - Stage: {stage}, Details: {details}")
    
    def validate_story_config(self, config: Dict[str, Any]) -> bool:
        """验证故事配置"""
        required_sections = ['story_writer', 'image_generation', 'speech_generation', 'video_compose']
        
        for section in required_sections:
            if section not in config:
                self.logger.error(f"Missing required config section: {section}")
                return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "story_writer": {
                "max_conv_turns": 3,
                "num_outline": 4,
                "temperature": 0.5,
                "max_pages": 3,
                "llm": "qwen"
            },
            "image_generation": {
                "api_type": "dashscope",
                "width": 1280,
                "height": 720,
                "style_name": "Japanese Anime",
                "num_turns": 3,
                "llm": "qwen"
            },
            "speech_generation": {
                "model": "kokoro",
                "sample_rate": 24000,
                "lang_code": "a",
                "voice": "af_heart"
            },
            "video_compose": {
                "fps": 24,
                "audio_sample_rate": 44100,
                "audio_codec": "aac",
                "enable_captions": True,
                "caption": {
                    "font": "resource/font/FiraCode-Regular.ttf",
                    "fontsize": 28,
                    "color": "white",
                    "max_length": 50,
                    "max_words_per_line": 10,
                    "workers": 4
                },
                "slideshow_effect": {
                    "fade_duration": 0.5,
                    "slide_duration": 0.2,
                    "zoom_speed": 0.5,
                    "move_ratio": 0.9
                }
            },
            "execution": {
                "mode": "parallel"
            }
        }


class StoryManagementService:
    """故事管理服务"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    def create_story(self, user, story_data: Dict[str, Any]) -> Story:
        """创建故事"""
        self.logger.info(f"Creating story for user {user.id}")
        
        story = Story.objects.create(
            user=user,
            title=story_data.get('title', ''),
            topic=story_data.get('topic', ''),
            main_role=story_data.get('main_role', ''),
            scene=story_data.get('scene', ''),
            config=story_data.get('config', {}),
            status='pending'
        )
        
        self.logger.info(f"Story created with ID: {story.id}")
        return story
    
    def update_story(self, story: Story, story_data: Dict[str, Any]) -> Story:
        """更新故事"""
        self.logger.info(f"Updating story {story.id}")
        
        for field, value in story_data.items():
            if hasattr(story, field):
                setattr(story, field, value)
        
        story.save()
        
        self.logger.info(f"Story {story.id} updated")
        return story
    
    def delete_story(self, story: Story) -> bool:
        """删除故事"""
        self.logger.info(f"Deleting story {story.id}")
        
        try:
            # 删除相关文件
            story_dir = Path(settings.MEDIA_ROOT) / "stories" / str(story.id)
            if story_dir.exists():
                import shutil
                shutil.rmtree(story_dir)
            
            # 删除数据库记录
            story.delete()
            
            self.logger.info(f"Story {story.id} deleted successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete story {story.id}: {e}")
            return False
    
    def get_story_status(self, story: Story) -> Dict[str, Any]:
        """获取故事状态"""
        progress = getattr(story, 'progress', None)
        
        status_data = {
            'story_id': str(story.id),
            'status': story.status,
            'created_at': story.created_at,
            'updated_at': story.updated_at,
            'completed_at': story.completed_at,
        }
        
        if progress:
            status_data.update({
                'current_stage': progress.current_stage,
                'stage_progress': progress.stage_progress,
                'total_progress': progress.total_progress,
                'stage_details': progress.stage_details,
                'last_updated': progress.last_updated
            })
        
        return status_data
    
    def get_story_preview(self, story: Story) -> Dict[str, Any]:
        """获取故事预览"""
        preview_data = {
            'story_id': str(story.id),
            'title': story.title,
            'topic': story.topic,
            'status': story.status,
            'pages_count': len(story.pages) if story.pages else 0,
            'created_at': story.created_at,
            'updated_at': story.updated_at,
        }
        
        # 添加媒体文件信息
        media_files = story.media_files.all()
        preview_data['media_files'] = {
            'images': [f.file_name for f in media_files.filter(file_type='image')],
            'audio': [f.file_name for f in media_files.filter(file_type='audio')],
            'video': [f.file_name for f in media_files.filter(file_type='video')],
        }
        
        # 添加进度信息
        if hasattr(story, 'progress'):
            preview_data['progress'] = {
                'current_stage': story.progress.current_stage,
                'total_progress': story.progress.total_progress,
                'stage_details': story.progress.stage_details
            }
        
        return preview_data
