"""
Django Story Platform - 多模态故事生成代理
"""
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
import time

from agents.base_agent import BaseAgent
from agents.story_agent import QAOutlineStoryAgent
from agents.image_agent import StoryDiffusionAgent
from agents.speech_agent import SpeechAgent
from agents.video_agent import SlideshowVideoComposeAgent


class MMStoryAgent(BaseAgent):
    """多模态故事生成代理"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.output_dir = Path(config.get("output_dir", "./output"))
        self.modalities = config.get("modalities", ["image", "speech"])
        self.parallel_mode = config.get("parallel_mode", False)
        self.story_id = config.get("story_id")
        
        # 创建子代理
        self.story_agent = QAOutlineStoryAgent(config.get("story_writer", {}), logger)
        self.image_agent = StoryDiffusionAgent(config.get("image_generation", {}), logger)
        self.speech_agent = SpeechAgent(config.get("speech_generation", {}), logger)
        self.video_agent = SlideshowVideoComposeAgent(config.get("video_compose", {}), logger)
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_story(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """生成完整的故事"""
        self._log("Starting multi-modal story generation")
        
        try:
            # 1. 生成故事内容
            self._progress("story", {"message": "Generating story content"})
            story_result = self.story_agent.generate(config)
            
            # 2. 生成图像
            if "image" in self.modalities:
                self._progress("image", {"message": "Generating images"})
                image_result = self._generate_images(story_result)
            else:
                image_result = {"images": []}
            
            # 3. 生成语音
            if "speech" in self.modalities:
                self._progress("speech", {"message": "Generating speech"})
                speech_result = self._generate_speech(story_result)
            else:
                speech_result = {"audio_files": []}
            
            # 4. 合成视频
            self._progress("compose", {"message": "Composing video"})
            video_result = self._compose_video(story_result, image_result, speech_result)
            
            # 5. 整理结果
            result = {
                "story": story_result,
                "images": image_result,
                "speech": speech_result,
                "video": video_result,
                "metadata": {
                    "story_id": self.story_id,
                    "generation_time": time.time(),
                    "modalities": self.modalities,
                    "parallel_mode": self.parallel_mode
                }
            }
            
            self._log("Multi-modal story generation completed")
            return result
            
        except Exception as e:
            self.logger.error(f"Multi-modal story generation failed: {e}")
            raise
    
    def resume_from_video_composition(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """从视频合成阶段恢复生成"""
        self._log("Resuming from video composition")
        
        try:
            # 检查是否有现有的故事数据
            story_data = self._load_existing_story_data()
            if not story_data:
                raise ValueError("No existing story data found")
            
            # 直接进行视频合成
            self._progress("compose", {"message": "Resuming video composition"})
            video_result = self._compose_video(
                story_data["story"],
                story_data["images"],
                story_data["speech"]
            )
            
            result = {
                "story": story_data["story"],
                "images": story_data["images"],
                "speech": story_data["speech"],
                "video": video_result,
                "metadata": {
                    "story_id": self.story_id,
                    "generation_time": time.time(),
                    "resumed": True
                }
            }
            
            self._log("Video composition resumed and completed")
            return result
            
        except Exception as e:
            self.logger.error(f"Video composition resume failed: {e}")
            raise
    
    def _generate_images(self, story_result: Dict[str, Any]) -> Dict[str, Any]:
        """生成图像"""
        try:
            pages = story_result["story"]["pages"]
            save_path = self.output_dir / "images"
            
            image_params = {
                "pages": pages,
                "save_path": str(save_path)
            }
            
            return self.image_agent.generate(image_params)
            
        except Exception as e:
            self.logger.error(f"Image generation failed: {e}")
            raise
    
    def _generate_speech(self, story_result: Dict[str, Any]) -> Dict[str, Any]:
        """生成语音"""
        try:
            pages = story_result["story"]["pages"]
            save_path = self.output_dir / "audio"
            
            speech_params = {
                "pages": pages,
                "save_path": str(save_path)
            }
            
            return self.speech_agent.generate(speech_params)
            
        except Exception as e:
            self.logger.error(f"Speech generation failed: {e}")
            raise
    
    def _compose_video(self, story_result: Dict[str, Any], image_result: Dict[str, Any], speech_result: Dict[str, Any]) -> Dict[str, Any]:
        """合成视频"""
        try:
            pages = story_result["story"]["pages"]
            
            # 合并图像和语音信息到页面
            enhanced_pages = []
            for i, page in enumerate(pages):
                enhanced_page = page.copy()
                
                # 添加图像路径
                if image_result["images"] and i < len(image_result["images"]):
                    enhanced_page["image_path"] = image_result["images"][i]["image_path"]
                
                # 添加语音路径
                if speech_result["audio_files"] and i < len(speech_result["audio_files"]):
                    enhanced_page["audio_path"] = speech_result["audio_files"][i]["audio_path"]
                
                enhanced_pages.append(enhanced_page)
            
            save_path = self.output_dir / "video"
            video_params = {
                "pages": enhanced_pages,
                "save_path": str(save_path)
            }
            
            return self.video_agent.generate(video_params)
            
        except Exception as e:
            self.logger.error(f"Video composition failed: {e}")
            raise
    
    def _load_existing_story_data(self) -> Optional[Dict[str, Any]]:
        """加载现有的故事数据"""
        try:
            if not self.story_id:
                return None
            
            # 从文件系统加载数据
            story_file = self.output_dir / f"{self.story_id}_story.json"
            if story_file.exists():
                with open(story_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to load existing story data: {e}")
            return None
    
    def _save_story_data(self, data: Dict[str, Any]):
        """保存故事数据"""
        try:
            if not self.story_id:
                return
            
            story_file = self.output_dir / f"{self.story_id}_story.json"
            with open(story_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            self.logger.error(f"Failed to save story data: {e}")
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证参数"""
        required_fields = ["story_topic"]
        for field in required_fields:
            if field not in params:
                self._log(f"Missing required parameter: {field}", 'error')
                return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "output_dir": "./output",
            "modalities": ["image", "speech"],
            "parallel_mode": False,
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
            }
        }
