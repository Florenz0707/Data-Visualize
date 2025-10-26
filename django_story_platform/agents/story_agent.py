"""
Django Story Platform - 故事生成代理
"""
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path
import json

from agents.base_agent import StoryAgent
from agents.llm import LLM


class QAOutlineStoryAgent(StoryAgent):
    """问答式大纲故事生成代理"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self.llm = LLM(self.llm_type)
        self.outline_prompt = self._load_outline_prompt()
        self.story_prompt = self._load_story_prompt()
    
    def generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成故事"""
        self._log("Starting story generation")
        
        # 验证参数
        if not self.validate_params(params):
            raise ValueError("Invalid parameters")
        
        story_topic = params["story_topic"]
        main_role = params.get("main_role", "")
        scene = params.get("scene", "")
        
        # 生成大纲
        self._progress("outline", {"message": "Generating story outline"})
        outline = self._generate_outline(story_topic, main_role, scene)
        
        # 生成故事内容
        self._progress("story", {"message": "Generating story content"})
        story_content = self._generate_story_content(outline, story_topic)
        
        # 格式化输出
        result = {
            "outline": outline,
            "story": story_content,
            "metadata": {
                "topic": story_topic,
                "main_role": main_role,
                "scene": scene,
                "num_pages": len(story_content.get("pages", [])),
                "generation_time": self._get_current_time()
            }
        }
        
        self._log("Story generation completed")
        return result
    
    def _generate_outline(self, story_topic: str, main_role: str, scene: str) -> Dict[str, Any]:
        """生成故事大纲"""
        self._log("Generating story outline")
        
        # 构建提示词
        prompt = self.outline_prompt.format(
            story_topic=story_topic,
            main_role=main_role,
            scene=scene,
            num_outline=self.num_outline
        )
        
        # 调用LLM生成大纲
        response = self.llm.generate(prompt, temperature=self.temperature)
        
        # 解析响应
        try:
            outline = json.loads(response)
        except json.JSONDecodeError:
            # 如果解析失败，尝试提取JSON部分
            outline = self._extract_json_from_response(response)
        
        return outline
    
    def _generate_story_content(self, outline: Dict[str, Any], story_topic: str) -> Dict[str, Any]:
        """生成故事内容"""
        self._log("Generating story content")
        
        pages = []
        outline_items = outline.get("outline", [])
        
        for i, item in enumerate(outline_items):
            self._progress("story", {
                "message": f"Generating page {i+1}/{len(outline_items)}",
                "current_page": i+1,
                "total_pages": len(outline_items)
            })
            
            # 构建页面提示词
            prompt = self.story_prompt.format(
                story_topic=story_topic,
                outline_item=item,
                page_number=i+1,
                total_pages=len(outline_items)
            )
            
            # 生成页面内容
            response = self.llm.generate(prompt, temperature=self.temperature)
            
            # 解析页面内容
            page_content = self._parse_page_content(response)
            pages.append(page_content)
        
        return {
            "pages": pages,
            "title": outline.get("title", f"Story: {story_topic}"),
            "summary": outline.get("summary", "")
        }
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """从响应中提取JSON"""
        import re
        
        # 尝试找到JSON部分
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # 如果无法提取JSON，返回默认结构
        return {
            "title": "Generated Story",
            "summary": response[:200] + "..." if len(response) > 200 else response,
            "outline": [
                {"title": f"Part {i+1}", "content": f"Content for part {i+1}"}
                for i in range(self.num_outline)
            ]
        }
    
    def _parse_page_content(self, response: str) -> Dict[str, Any]:
        """解析页面内容"""
        # 简单的页面内容解析
        lines = response.strip().split('\n')
        
        # 提取标题
        title = lines[0] if lines else "Page"
        
        # 提取内容
        content = '\n'.join(lines[1:]) if len(lines) > 1 else response
        
        # 提取图像描述
        image_description = self._extract_image_description(content)
        
        return {
            "title": title,
            "content": content,
            "image_description": image_description,
            "audio_text": content  # 用于语音合成
        }
    
    def _extract_image_description(self, content: str) -> str:
        """提取图像描述"""
        # 简单的图像描述提取逻辑
        # 在实际实现中，可以使用更复杂的NLP技术
        
        # 提取前两句话作为图像描述
        sentences = content.split('.')
        if len(sentences) >= 2:
            return '.'.join(sentences[:2]) + '.'
        else:
            return content[:100] + "..." if len(content) > 100 else content
    
    def _load_outline_prompt(self) -> str:
        """加载大纲生成提示词"""
        return """请为以下故事主题生成一个详细的大纲：

故事主题：{story_topic}
主角：{main_role}
场景：{scene}

请生成包含{num_outline}个部分的大纲，每个部分都应该有清晰的标题和内容描述。

请以JSON格式返回，格式如下：
{{
    "title": "故事标题",
    "summary": "故事摘要",
    "outline": [
        {{
            "title": "第一部分标题",
            "content": "第一部分内容描述"
        }},
        ...
    ]
}}"""
    
    def _load_story_prompt(self) -> str:
        """加载故事生成提示词"""
        return """请根据以下大纲项目生成详细的故事内容：

故事主题：{story_topic}
大纲项目：{outline_item}
页码：{page_number}/{total_pages}

请生成一个完整的故事页面，包含：
1. 生动的故事情节
2. 详细的场景描述
3. 人物对话和内心活动
4. 适合的图像描述

请确保内容生动有趣，适合目标读者。"""
    
    def _get_current_time(self) -> str:
        """获取当前时间"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
