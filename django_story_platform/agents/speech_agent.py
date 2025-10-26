"""
Django Story Platform - 语音生成代理
"""
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import requests
import soundfile as sf
import numpy as np

from agents.base_agent import MediaAgent


class SpeechAgent(MediaAgent):
    """语音生成代理"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.model = config.get("model", "kokoro")
        self.sample_rate = config.get("sample_rate", 24000)
        self.lang_code = config.get("lang_code", "a")
        self.voice = config.get("voice", "af_heart")
        
        # 初始化合成器
        self.synthesizer = self._create_synthesizer()
    
    def _create_synthesizer(self):
        """创建语音合成器"""
        if self.model == "kokoro":
            return KokoroSynthesizer(self.config, self.logger)
        elif self.model == "cosyvoice":
            return CosyVoiceSynthesizer(self.config, self.logger)
        elif self.model == "neuttair":
            return NeuttAirSynthesizer(self.config, self.logger)
        elif self.model == "transformers":
            return TransformersSynthesizer(self.config, self.logger)
        else:
            raise ValueError(f"Unsupported speech model: {self.model}")
    
    def generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成语音"""
        self._log("Starting speech generation")
        
        # 验证参数
        if not self.validate_params(params):
            raise ValueError("Invalid parameters")
        
        pages = params["pages"]
        save_path = params["save_path"]
        
        # 创建保存目录
        save_dir = Path(save_path)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        generated_audio = []
        
        for i, page in enumerate(pages):
            self._progress("speech", {
                "message": f"Generating speech {i+1}/{len(pages)}",
                "current_page": i+1,
                "total_pages": len(pages)
            })
            
            # 获取要合成的文本
            text = page.get("audio_text", page.get("content", ""))
            if not text.strip():
                self._log(f"No text found for page {i+1}, skipping", 'warning')
                continue
            
            # 生成语音
            audio_path = self._generate_single_speech(
                text, 
                save_dir / f"page_{i+1}.wav"
            )
            
            generated_audio.append({
                "page_index": i,
                "audio_path": str(audio_path),
                "text": text
            })
        
        result = {
            "audio_files": generated_audio,
            "total_count": len(generated_audio),
            "save_path": str(save_dir)
        }
        
        self._log("Speech generation completed")
        return result
    
    def _generate_single_speech(self, text: str, output_path: Path) -> Path:
        """生成单段语音"""
        self._log(f"Generating speech for text: {text[:50]}...")
        
        try:
            # 使用合成器生成语音
            audio_data = self.synthesizer.synthesize(text)
            
            # 保存音频文件
            sf.write(output_path, audio_data, self.sample_rate)
            
            self._log(f"Speech saved to {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Speech generation failed: {e}")
            raise
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """验证参数"""
        required_fields = ["pages", "save_path"]
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
            "model": "kokoro",
            "sample_rate": 24000,
            "lang_code": "a",
            "voice": "af_heart"
        }


class KokoroSynthesizer:
    """Kokoro语音合成器"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.kokoro.ai/v1/synthesize")
    
    def synthesize(self, text: str) -> np.ndarray:
        """合成语音"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "text": text,
                "voice": self.config.get("voice", "af_heart"),
                "sample_rate": self.config.get("sample_rate", 24000)
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            # 假设返回的是音频数据
            audio_data = response.content
            
            # 转换为numpy数组
            import io
            audio_array, sample_rate = sf.read(io.BytesIO(audio_data))
            
            return audio_array
            
        except Exception as e:
            self.logger.error(f"Kokoro synthesis failed: {e}")
            raise


class CosyVoiceSynthesizer:
    """CosyVoice语音合成器"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.model_path = config.get("model_path")
        self._model = None
    
    def _load_model(self):
        """加载模型"""
        if self._model is None:
            try:
                # 这里应该加载CosyVoice模型
                # 由于CosyVoice的具体实现可能不同，这里提供一个框架
                self.logger.info(f"Loading CosyVoice model from {self.model_path}")
                # self._model = load_cosyvoice_model(self.model_path)
                self._model = "cosyvoice_model"  # 占位符
            except Exception as e:
                self.logger.error(f"Failed to load CosyVoice model: {e}")
                raise
    
    def synthesize(self, text: str) -> np.ndarray:
        """合成语音"""
        self._load_model()
        
        try:
            # 这里应该调用CosyVoice模型进行合成
            # 由于具体实现可能不同，这里提供一个框架
            self.logger.info(f"Synthesizing with CosyVoice: {text[:50]}...")
            
            # 生成随机音频数据作为占位符
            duration = len(text) * 0.1  # 估算时长
            sample_rate = self.config.get("sample_rate", 24000)
            audio_data = np.random.randn(int(duration * sample_rate)).astype(np.float32)
            
            return audio_data
            
        except Exception as e:
            self.logger.error(f"CosyVoice synthesis failed: {e}")
            raise


class NeuttAirSynthesizer:
    """NeuttAir语音合成器"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.neuttair.com/v1/synthesize")
    
    def synthesize(self, text: str) -> np.ndarray:
        """合成语音"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "text": text,
                "voice": self.config.get("voice", "default"),
                "sample_rate": self.config.get("sample_rate", 24000)
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            # 假设返回的是音频数据
            audio_data = response.content
            
            # 转换为numpy数组
            import io
            audio_array, sample_rate = sf.read(io.BytesIO(audio_data))
            
            return audio_array
            
        except Exception as e:
            self.logger.error(f"NeuttAir synthesis failed: {e}")
            raise


class TransformersSynthesizer:
    """Transformers语音合成器"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.model_name = config.get("model_name", "microsoft/speecht5_tts")
        self._model = None
        self._tokenizer = None
    
    def _load_model(self):
        """加载模型"""
        if self._model is None:
            try:
                from transformers import AutoTokenizer, AutoModel
                import torch
                
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModel.from_pretrained(self.model_name)
                
                if torch.cuda.is_available():
                    self._model = self._model.cuda()
                
                self.logger.info(f"Transformers model loaded: {self.model_name}")
            except Exception as e:
                self.logger.error(f"Failed to load Transformers model: {e}")
                raise
    
    def synthesize(self, text: str) -> np.ndarray:
        """合成语音"""
        self._load_model()
        
        try:
            # 这里应该调用Transformers模型进行合成
            # 由于具体实现可能不同，这里提供一个框架
            self.logger.info(f"Synthesizing with Transformers: {text[:50]}...")
            
            # 生成随机音频数据作为占位符
            duration = len(text) * 0.1  # 估算时长
            sample_rate = self.config.get("sample_rate", 24000)
            audio_data = np.random.randn(int(duration * sample_rate)).astype(np.float32)
            
            return audio_data
            
        except Exception as e:
            self.logger.error(f"Transformers synthesis failed: {e}")
            raise
