"""
Django Story Platform - 图像生成代理
"""
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import requests
from PIL import Image
import io

from agents.base_agent import MediaAgent
from agents.llm import create_llm


class StoryDiffusionAgent(MediaAgent):
    """故事扩散图像生成代理"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.api_type = config.get("api_type", "dashscope")
        self.width = config.get("width", 1280)
        self.height = config.get("height", 720)
        self.style_name = config.get("style_name", "Japanese Anime")
        self.num_turns = config.get("num_turns", 3)
        self.llm_type = config.get("llm", "qwen")
        
        # 初始化LLM
        self.llm = create_llm(self.llm_type, logger=self.logger)
        
        # API配置
        if self.api_type == "dashscope":
            self.api_key = config.get("api_key")
            self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        elif self.api_type == "openai":
            self.api_key = config.get("api_key")
            self.base_url = "https://api.openai.com/v1/images/generations"
        else:
            raise ValueError(f"Unsupported API type: {self.api_type}")
    
    def generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成图像"""
        self._log("Starting image generation")
        
        # 验证参数
        if not self.validate_params(params):
            raise ValueError("Invalid parameters")
        
        pages = params["pages"]
        save_path = params["save_path"]
        
        # 创建保存目录
        save_dir = Path(save_path)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        generated_images = []
        
        for i, page in enumerate(pages):
            self._progress("image", {
                "message": f"Generating image {i+1}/{len(pages)}",
                "current_page": i+1,
                "total_pages": len(pages)
            })
            
            # 生成图像描述
            image_description = self._generate_image_description(page)
            
            # 生成图像
            image_path = self._generate_single_image(
                image_description, 
                save_dir / f"page_{i+1}.jpg"
            )
            
            generated_images.append({
                "page_index": i,
                "image_path": str(image_path),
                "description": image_description
            })
        
        result = {
            "images": generated_images,
            "total_count": len(generated_images),
            "save_path": str(save_dir)
        }
        
        self._log("Image generation completed")
        return result
    
    def _generate_image_description(self, page: Dict[str, Any]) -> str:
        """生成图像描述"""
        self._log(f"Generating image description for page: {page.get('title', 'Unknown')}")
        
        # 构建提示词
        prompt = f"""
请为以下故事页面生成详细的图像描述：

页面标题：{page.get('title', '')}
页面内容：{page.get('content', '')}

请生成一个生动、详细的图像描述，包含：
1. 场景设置
2. 人物形象
3. 动作和表情
4. 环境细节
5. 色彩和氛围

风格：{self.style_name}
尺寸：{self.width}x{self.height}

请用中文描述，描述要具体生动，适合AI图像生成。
        """.strip()
        
        # 调用LLM生成描述
        description = self.llm.generate(prompt, temperature=0.7)
        
        # 清理描述
        description = description.strip()
        if description.startswith('"') and description.endswith('"'):
            description = description[1:-1]
        
        return description
    
    def _generate_single_image(self, description: str, output_path: Path) -> Path:
        """生成单张图像"""
        self._log(f"Generating image: {description[:50]}...")
        
        if self.api_type == "dashscope":
            return self._generate_with_dashscope(description, output_path)
        elif self.api_type == "openai":
            return self._generate_with_openai(description, output_path)
        else:
            raise ValueError(f"Unsupported API type: {self.api_type}")
    
    def _generate_with_dashscope(self, description: str, output_path: Path) -> Path:
        """使用DashScope生成图像"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "wanx-v1",
                "input": {
                    "prompt": description,
                    "style": self.style_name
                },
                "parameters": {
                    "size": f"{self.width}*{self.height}",
                    "n": 1,
                    "seed": 42
                }
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if "output" in result and "results" in result["output"]:
                image_url = result["output"]["results"][0]["url"]
                
                # 下载图像
                image_response = requests.get(image_url, timeout=30)
                image_response.raise_for_status()
                
                # 保存图像
                with open(output_path, 'wb') as f:
                    f.write(image_response.content)
                
                self._log(f"Image saved to {output_path}")
                return output_path
            else:
                raise ValueError(f"Unexpected response format: {result}")
                
        except Exception as e:
            self.logger.error(f"DashScope image generation failed: {e}")
            raise
    
    def _generate_with_openai(self, description: str, output_path: Path) -> Path:
        """使用OpenAI生成图像"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "prompt": description,
                "n": 1,
                "size": f"{self.width}x{self.height}",
                "response_format": "url"
            }
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if "data" in result and len(result["data"]) > 0:
                image_url = result["data"][0]["url"]
                
                # 下载图像
                image_response = requests.get(image_url, timeout=30)
                image_response.raise_for_status()
                
                # 保存图像
                with open(output_path, 'wb') as f:
                    f.write(image_response.content)
                
                self._log(f"Image saved to {output_path}")
                return output_path
            else:
                raise ValueError(f"Unexpected response format: {result}")
                
        except Exception as e:
            self.logger.error(f"OpenAI image generation failed: {e}")
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
        
        for page in pages:
            if not isinstance(page, dict) or "content" not in page:
                self._log("Each page must be a dict with 'content' field", 'error')
                return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "api_type": "dashscope",
            "width": 1280,
            "height": 720,
            "style_name": "Japanese Anime",
            "num_turns": 3,
            "llm": "qwen"
        }
