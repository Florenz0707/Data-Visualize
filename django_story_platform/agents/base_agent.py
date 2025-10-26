"""
Django Story Platform - AI代理基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
import logging
from pathlib import Path


class BaseAgent(ABC):
    """代理基类"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable[[str, Dict], None]):
        """设置进度回调函数"""
        self._progress_callback = callback
    
    def _log(self, message: str, level: str = 'info'):
        """记录日志"""
        getattr(self.logger, level)(message)
    
    def _progress(self, stage: str, details: Optional[Dict] = None):
        """发送进度更新"""
        if self._progress_callback:
            try:
                self._progress_callback(stage, details or {})
            except Exception as e:
                self._log(f"Progress callback error: {e}", 'error')
    
    @abstractmethod
    def generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成内容的主要方法"""
        pass
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证参数"""
        return True
    
    def cleanup(self):
        """清理资源"""
        pass


class StoryAgent(BaseAgent):
    """故事生成代理基类"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.temperature = config.get("temperature", 1.0)
        self.max_conv_turns = config.get("max_conv_turns", 3)
        self.num_outline = config.get("num_outline", 4)
        self.max_pages = config.get("max_pages", None)
        self.llm_type = config.get("llm", "qwen")
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证故事生成参数"""
        required_fields = ["story_topic"]
        for field in required_fields:
            if field not in params:
                self._log(f"Missing required parameter: {field}", 'error')
                return False
        return True


class MediaAgent(BaseAgent):
    """媒体生成代理基类"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.output_dir = Path(config.get("output_dir", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证媒体生成参数"""
        required_fields = ["pages", "save_path"]
        for field in required_fields:
            if field not in params:
                self._log(f"Missing required parameter: {field}", 'error')
                return False
        return True


class VideoAgent(BaseAgent):
    """视频合成代理基类"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.output_dir = Path(config.get("output_dir", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证视频合成参数"""
        required_fields = ["pages"]
        for field in required_fields:
            if field not in params:
                self._log(f"Missing required parameter: {field}", 'error')
                return False
        return True
