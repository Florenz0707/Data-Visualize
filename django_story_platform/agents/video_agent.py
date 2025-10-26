"""
Django Story Platform - 视频合成代理
"""
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import cv2
import numpy as np
from moviepy.editor import VideoFileClip, ImageSequenceClip, AudioFileClip, CompositeVideoClip, TextClip
from moviepy.video.fx import resize, fadein, fadeout
from moviepy.audio.fx import audio_fadein, audio_fadeout

from agents.base_agent import VideoAgent


class SlideshowVideoComposeAgent(VideoAgent):
    """幻灯片视频合成代理"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.fps = config.get("fps", 24)
        self.audio_sample_rate = config.get("audio_sample_rate", 44100)
        self.audio_codec = config.get("audio_codec", "aac")
        self.enable_captions = config.get("enable_captions", True)
        self.caption_config = config.get("caption", {})
        self.slideshow_effect = config.get("slideshow_effect", {})
        
        # 字幕配置
        self.font = self.caption_config.get("font", "resource/font/FiraCode-Regular.ttf")
        self.fontsize = self.caption_config.get("fontsize", 28)
        self.color = self.caption_config.get("color", "white")
        self.max_length = self.caption_config.get("max_length", 50)
        self.max_words_per_line = self.caption_config.get("max_words_per_line", 10)
        self.workers = self.caption_config.get("workers", 4)
        
        # 幻灯片效果配置
        self.fade_duration = self.slideshow_effect.get("fade_duration", 0.5)
        self.slide_duration = self.slideshow_effect.get("slide_duration", 0.2)
        self.zoom_speed = self.slideshow_effect.get("zoom_speed", 0.5)
        self.move_ratio = self.slideshow_effect.get("move_ratio", 0.9)
    
    def generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成视频"""
        self._log("Starting video composition")
        
        # 验证参数
        if not self.validate_params(params):
            raise ValueError("Invalid parameters")
        
        pages = params["pages"]
        save_path = params["save_path"]
        
        # 创建保存目录
        save_dir = Path(save_path)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 合成视频
        video_path = self._compose_video(pages, save_dir / "final_video.mp4")
        
        result = {
            "video_path": str(video_path),
            "pages_count": len(pages),
            "duration": self._get_video_duration(video_path),
            "save_path": str(save_dir)
        }
        
        self._log("Video composition completed")
        return result
    
    def _compose_video(self, pages: List[Dict[str, Any]], output_path: Path) -> Path:
        """合成视频"""
        self._log(f"Composing video with {len(pages)} pages")
        
        try:
            # 准备视频片段
            video_clips = []
            
            for i, page in enumerate(pages):
                self._progress("compose", {
                    "message": f"Processing page {i+1}/{len(pages)}",
                    "current_page": i+1,
                    "total_pages": len(pages)
                })
                
                # 创建页面视频片段
                page_clip = self._create_page_clip(page, i)
                video_clips.append(page_clip)
            
            # 合成最终视频
            final_video = CompositeVideoClip(video_clips)
            
            # 添加音频
            if self._has_audio(pages):
                audio_clip = self._create_audio_clip(pages)
                final_video = final_video.set_audio(audio_clip)
            
            # 导出视频
            final_video.write_videofile(
                str(output_path),
                fps=self.fps,
                audio_codec=self.audio_codec,
                audio_fps=self.audio_sample_rate,
                verbose=False,
                logger=None
            )
            
            # 清理资源
            final_video.close()
            for clip in video_clips:
                clip.close()
            
            self._log(f"Video saved to {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Video composition failed: {e}")
            raise
    
    def _create_page_clip(self, page: Dict[str, Any], page_index: int) -> VideoFileClip:
        """创建页面视频片段"""
        try:
            # 获取图像路径
            image_path = page.get("image_path")
            if not image_path or not Path(image_path).exists():
                # 如果没有图像，创建纯色背景
                image_clip = self._create_color_clip()
            else:
                # 加载图像
                image_clip = ImageSequenceClip([image_path], fps=self.fps)
            
            # 设置持续时间
            duration = self._calculate_page_duration(page)
            image_clip = image_clip.set_duration(duration)
            
            # 添加字幕
            if self.enable_captions:
                text_clip = self._create_text_clip(page, duration)
                if text_clip:
                    image_clip = CompositeVideoClip([image_clip, text_clip])
            
            # 添加过渡效果
            image_clip = self._add_transition_effects(image_clip, page_index)
            
            return image_clip
            
        except Exception as e:
            self.logger.error(f"Failed to create page clip: {e}")
            raise
    
    def _create_color_clip(self) -> VideoFileClip:
        """创建纯色背景片段"""
        try:
            # 创建纯色图像
            color = (100, 100, 100)  # 灰色
            image = np.full((720, 1280, 3), color, dtype=np.uint8)
            
            # 创建临时文件
            temp_path = self.output_dir / "temp_color.jpg"
            cv2.imwrite(str(temp_path), image)
            
            # 创建视频片段
            clip = ImageSequenceClip([str(temp_path)], fps=self.fps)
            
            # 删除临时文件
            temp_path.unlink()
            
            return clip
            
        except Exception as e:
            self.logger.error(f"Failed to create color clip: {e}")
            raise
    
    def _create_text_clip(self, page: Dict[str, Any], duration: float) -> Optional[TextClip]:
        """创建字幕片段"""
        try:
            text = page.get("content", "")
            if not text.strip():
                return None
            
            # 处理文本长度
            if len(text) > self.max_length:
                text = text[:self.max_length] + "..."
            
            # 分行处理
            words = text.split()
            lines = []
            current_line = []
            
            for word in words:
                current_line.append(word)
                if len(current_line) >= self.max_words_per_line:
                    lines.append(" ".join(current_line))
                    current_line = []
            
            if current_line:
                lines.append(" ".join(current_line))
            
            text = "\n".join(lines)
            
            # 创建字幕片段
            text_clip = TextClip(
                text,
                fontsize=self.fontsize,
                color=self.color,
                font=self.font,
                method='caption',
                size=(1200, None)
            ).set_duration(duration)
            
            # 设置位置（底部居中）
            text_clip = text_clip.set_position(('center', 'bottom'))
            
            return text_clip
            
        except Exception as e:
            self.logger.error(f"Failed to create text clip: {e}")
            return None
    
    def _add_transition_effects(self, clip: VideoFileClip, page_index: int) -> VideoFileClip:
        """添加过渡效果"""
        try:
            # 淡入效果
            if page_index == 0:
                clip = clip.fx(fadein, self.fade_duration)
            
            # 淡出效果
            if page_index == 0:  # 假设只有一页
                clip = clip.fx(fadeout, self.fade_duration)
            
            return clip
            
        except Exception as e:
            self.logger.error(f"Failed to add transition effects: {e}")
            return clip
    
    def _create_audio_clip(self, pages: List[Dict[str, Any]]) -> Optional[AudioFileClip]:
        """创建音频片段"""
        try:
            audio_files = []
            
            for page in pages:
                audio_path = page.get("audio_path")
                if audio_path and Path(audio_path).exists():
                    audio_clip = AudioFileClip(audio_path)
                    audio_files.append(audio_clip)
            
            if not audio_files:
                return None
            
            # 连接音频片段
            final_audio = audio_files[0]
            for audio_clip in audio_files[1:]:
                final_audio = final_audio.concatenate_audioclips(audio_clip)
            
            return final_audio
            
        except Exception as e:
            self.logger.error(f"Failed to create audio clip: {e}")
            return None
    
    def _calculate_page_duration(self, page: Dict[str, Any]) -> float:
        """计算页面持续时间"""
        # 基于文本长度计算持续时间
        text = page.get("content", "")
        word_count = len(text.split())
        
        # 每页至少3秒，每10个词增加1秒
        duration = max(3.0, word_count * 0.1)
        
        return min(duration, 10.0)  # 最长10秒
    
    def _has_audio(self, pages: List[Dict[str, Any]]) -> bool:
        """检查是否有音频"""
        for page in pages:
            if page.get("audio_path") and Path(page["audio_path"]).exists():
                return True
        return False
    
    def _get_video_duration(self, video_path: Path) -> float:
        """获取视频时长"""
        try:
            clip = VideoFileClip(str(video_path))
            duration = clip.duration
            clip.close()
            return duration
        except Exception as e:
            self.logger.error(f"Failed to get video duration: {e}")
            return 0.0
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证参数"""
        required_fields = ["pages"]
        for field in required_fields:
            if field not in params:
                self._log(f"Missing required parameter: {field}", 'error')
                return False
        
        # 验证pages格式
        pages = params["pages"]
        if not isinstance(pages, list) or len(pages) == 0:
            self._log("Pages must be a non-empty list", 'error')
            return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
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
        }
