"""
模型配置加载和管理模块
支持从 models.yaml 加载模型配置，并为各个 agent 提供统一的模型访问接口
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ModelConfig:
    """模型配置管理器"""
    
    def __init__(self, config_path: str = "configs/models.yaml"):
        """
        初始化模型配置管理器
        
        Args:
            config_path: 模型配置文件路径
        """
        self.config_path = Path(config_path)
        self.models = {}
        self._load_config()
    
    def _load_config(self):
        """加载模型配置文件"""
        if not self.config_path.exists():
            print(f"Warning: Model config file not found at {self.config_path}")
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 加载各类模型配置
            self.models['llm'] = config.get('llm_models') or {}
            self.models['image'] = config.get('image_models') or {}
            self.models['speech'] = config.get('speech_models') or {}
            self.models['music'] = config.get('music_models') or {}
            self.models['sound'] = config.get('sound_models') or {}
            
            print(f"✓ Loaded model config from {self.config_path}")
            print(f"  - LLM models: {len(self.models['llm'])}")
            print(f"  - Image models: {len(self.models['image'])}")
            print(f"  - Speech models: {len(self.models['speech'])}")
            print(f"  - Music models: {len(self.models['music'])}")
            print(f"  - Sound models: {len(self.models['sound'])}")
            
        except Exception as e:
            print(f"Error loading model config: {e}")
            raise
    
    def get_model_config(self, model_type: str, model_name: str) -> Dict[str, Any]:
        """
        获取指定模型的配置
        
        Args:
            model_type: 模型类型 ('llm', 'image', 'speech', 'music', 'sound')
            model_name: 模型名称
            
        Returns:
            模型配置字典
        """
        if model_type not in self.models:
            raise ValueError(f"Unknown model type: {model_type}")
        
        if model_name not in self.models[model_type]:
            raise ValueError(
                f"Model '{model_name}' not found in {model_type} models. "
                f"Available models: {list(self.models[model_type].keys())}"
            )
        
        config = self.models[model_type][model_name].copy()
        
        # 自动加载环境变量中的API密钥
        if 'api_key_env' in config:
            api_key = os.getenv(config['api_key_env'])
            if api_key:
                config['api_key'] = api_key
            else:
                print(f"Warning: Environment variable {config['api_key_env']} not set for model {model_name}")
        
        # 加载其他环境变量
        for key in ['api_base_env', 'access_key_id_env', 'access_key_secret_env', 'app_key_env']:
            if key in config:
                env_var = config[key]
                value = os.getenv(env_var)
                if value:
                    # 去掉 _env 后缀作为实际的配置键
                    actual_key = key.replace('_env', '')
                    config[actual_key] = value
        
        return config
    
    def get_llm_config(self, model_name: str) -> Dict[str, Any]:
        """获取LLM模型配置"""
        return self.get_model_config('llm', model_name)
    
    def get_image_config(self, model_name: str) -> Dict[str, Any]:
        """获取图像生成模型配置"""
        return self.get_model_config('image', model_name)
    
    def get_speech_config(self, model_name: str) -> Dict[str, Any]:
        """获取语音合成模型配置"""
        return self.get_model_config('speech', model_name)
    
    def get_music_config(self, model_name: str) -> Dict[str, Any]:
        """获取音乐生成模型配置"""
        return self.get_model_config('music', model_name)
    
    def get_sound_config(self, model_name: str) -> Dict[str, Any]:
        """获取音效生成模型配置"""
        return self.get_model_config('sound', model_name)
    
    def list_models(self, model_type: Optional[str] = None) -> Dict[str, list]:
        """
        列出可用的模型
        
        Args:
            model_type: 可选，指定模型类型。如果为None，返回所有类型
            
        Returns:
            模型列表字典
        """
        if model_type:
            if model_type not in self.models:
                raise ValueError(f"Unknown model type: {model_type}")
            return {model_type: list(self.models[model_type].keys())}
        else:
            return {
                mtype: list(models.keys()) 
                for mtype, models in self.models.items()
            }


# 全局模型配置实例
_global_model_config: Optional[ModelConfig] = None


def get_model_config_instance(config_path: str = "configs/models.yaml") -> ModelConfig:
    """
    获取全局模型配置实例（单例模式）
    
    Args:
        config_path: 模型配置文件路径
        
    Returns:
        ModelConfig实例
    """
    global _global_model_config
    if _global_model_config is None:
        _global_model_config = ModelConfig(config_path)
    return _global_model_config


def load_model_for_agent(agent_config: Dict[str, Any], model_type: str) -> Dict[str, Any]:
    """
    为agent加载模型配置
    
    Args:
        agent_config: agent配置字典（包含model字段）
        model_type: 模型类型
        
    Returns:
        合并后的配置字典
    """
    model_name = agent_config.get('model')
    if not model_name:
        # 如果没有指定model，返回原配置
        return agent_config.get('cfg', {})
    
    # 获取模型配置
    model_config_instance = get_model_config_instance()
    model_config = model_config_instance.get_model_config(model_type, model_name)
    
    # 合并配置：agent的cfg会覆盖模型的default_params
    merged_config = {}
    
    # 1. 先添加模型的默认参数
    if 'default_params' in model_config:
        merged_config.update(model_config['default_params'])
    
    # 2. 添加模型的其他配置（provider, model_name, api_key等）
    for key, value in model_config.items():
        if key not in ['default_params', 'api_key_env', 'api_base_env', 
                       'access_key_id_env', 'access_key_secret_env', 'app_key_env']:
            merged_config[key] = value
    
    # 3. agent的cfg覆盖模型配置
    if 'cfg' in agent_config:
        merged_config.update(agent_config['cfg'])
    
    return merged_config

