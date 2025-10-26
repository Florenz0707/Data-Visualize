"""
Django Story Platform - LLM代理
"""
import json
import logging
from typing import Dict, Any, Optional, List
import requests
from abc import ABC, abstractmethod


class LLM(ABC):
    """LLM基类"""
    
    def __init__(self, model_name: str, logger: Optional[logging.Logger] = None):
        self.model_name = model_name
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        pass
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """对话生成"""
        pass


class QwenLLM(LLM):
    """通义千问LLM"""
    
    def __init__(self, api_key: str, logger: Optional[logging.Logger] = None):
        super().__init__("qwen", logger)
        self.api_key = api_key
        self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> str:
        """生成文本"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "qwen-turbo",
                "input": {
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                "parameters": {
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if "output" in result and "text" in result["output"]:
                return result["output"]["text"]
            else:
                raise ValueError(f"Unexpected response format: {result}")
                
        except Exception as e:
            self.logger.error(f"Qwen LLM generation failed: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> str:
        """对话生成"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "qwen-turbo",
                "input": {
                    "messages": messages
                },
                "parameters": {
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if "output" in result and "text" in result["output"]:
                return result["output"]["text"]
            else:
                raise ValueError(f"Unexpected response format: {result}")
                
        except Exception as e:
            self.logger.error(f"Qwen LLM chat failed: {e}")
            raise


class OpenAILLM(LLM):
    """OpenAI LLM"""
    
    def __init__(self, api_key: str, logger: Optional[logging.Logger] = None):
        super().__init__("gpt", logger)
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> str:
        """生成文本"""
        return self.chat([{"role": "user", "content": prompt}], temperature, max_tokens)
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> str:
        """对话生成"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-3.5-turbo",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                raise ValueError(f"Unexpected response format: {result}")
                
        except Exception as e:
            self.logger.error(f"OpenAI LLM chat failed: {e}")
            raise


class LocalLLM(LLM):
    """本地LLM"""
    
    def __init__(self, model_path: str, logger: Optional[logging.Logger] = None):
        super().__init__("local", logger)
        self.model_path = model_path
        self._model = None
        self._tokenizer = None
    
    def _load_model(self):
        """加载模型"""
        if self._model is None:
            try:
                from transformers import AutoTokenizer, AutoModelForCausalLM
                import torch
                
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,
                    device_map="auto"
                )
                self.logger.info(f"Local model loaded from {self.model_path}")
            except Exception as e:
                self.logger.error(f"Failed to load local model: {e}")
                raise
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> str:
        """生成文本"""
        self._load_model()
        
        try:
            inputs = self._tokenizer.encode(prompt, return_tensors="pt")
            
            with torch.no_grad():
                outputs = self._model.generate(
                    inputs,
                    max_length=inputs.shape[1] + max_tokens,
                    temperature=temperature,
                    do_sample=True,
                    pad_token_id=self._tokenizer.eos_token_id
                )
            
            generated_text = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
            return generated_text[len(prompt):].strip()
            
        except Exception as e:
            self.logger.error(f"Local LLM generation failed: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> str:
        """对话生成"""
        # 将消息转换为提示词
        prompt = ""
        for message in messages:
            role = message["role"]
            content = message["content"]
            if role == "user":
                prompt += f"User: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"
        
        prompt += "Assistant: "
        return self.generate(prompt, temperature, max_tokens)


def create_llm(llm_type: str, **kwargs) -> LLM:
    """创建LLM实例"""
    if llm_type == "qwen":
        return QwenLLM(**kwargs)
    elif llm_type == "gpt":
        return OpenAILLM(**kwargs)
    elif llm_type == "local":
        return LocalLLM(**kwargs)
    else:
        raise ValueError(f"Unsupported LLM type: {llm_type}")
