import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ModelConfig:
    """模型配置管理器（本地vendored版本）"""
    def __init__(self, config_path: str = "configs/models.yaml"):
        self.config_path = Path(config_path)
        self.models = {}
        self._load_config()

    def _load_config(self):
        if not self.config_path.exists():
            print(f"Warning: Model config file not found at {self.config_path}")
            return
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        self.models['llm'] = config.get('llm_models') or {}
        self.models['image'] = config.get('image_models') or {}
        self.models['speech'] = config.get('speech_models') or {}
        self.models['music'] = config.get('music_models') or {}
        self.models['sound'] = config.get('sound_models') or {}

    def get_model_config(self, model_type: str, model_name: str) -> Dict[str, Any]:
        if model_type not in self.models:
            raise ValueError(f"Unknown model type: {model_type}")
        if model_name not in self.models[model_type]:
            raise ValueError(f"Model '{model_name}' not found in {model_type} models")
        config = self.models[model_type][model_name].copy()
        if 'api_key_env' in config:
            api_key = os.getenv(config['api_key_env'])
            if api_key:
                config['api_key'] = api_key
        for key in ['api_base_env', 'access_key_id_env', 'access_key_secret_env', 'app_key_env']:
            if key in config:
                env_var = config[key]
                value = os.getenv(env_var)
                if value:
                    actual_key = key.replace('_env', '')
                    config[actual_key] = value
        return config

    def get_llm_config(self, model_name: str) -> Dict[str, Any]:
        return self.get_model_config('llm', model_name)


def get_model_config_instance(config_path: str = "configs/models.yaml") -> ModelConfig:
    global _global_model_config
    try:
        _global_model_config
    except NameError:
        _global_model_config = None
    if _global_model_config is None:
        _global_model_config = ModelConfig(config_path)
    return _global_model_config


def load_model_for_agent(agent_config: Dict[str, Any], model_type: str) -> Dict[str, Any]:
    model_name = agent_config.get('model')
    if not model_name:
        return agent_config.get('cfg', {})
    model_config_instance = get_model_config_instance()
    model_config = model_config_instance.get_model_config(model_type, model_name)
    merged_config = {}
    if 'default_params' in model_config:
        merged_config.update(model_config['default_params'])
    for key, value in model_config.items():
        if key not in ['default_params', 'api_key_env', 'api_base_env', 'access_key_id_env', 'access_key_secret_env', 'app_key_env']:
            merged_config[key] = value
    if 'cfg' in agent_config:
        merged_config.update(agent_config['cfg'])
    return merged_config

