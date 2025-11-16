import json
from typing import List, Dict

from ..base import register_tool, init_tool_instance
from ..prompts_en import role_extract_system, role_review_system, \
    story_to_image_reviser_system, story_to_image_review_system


@register_tool("story_diffusion_t2i")
class StoryDiffusionAgent:

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.api_type = cfg.get("api_type") or cfg.get("provider", "dashscope")
        self.api_key = cfg.get("api_key", "")
        self.api_url = cfg.get("api_url", "")
        self.model_name = cfg.get("model_name", "")

    def call(self, params: Dict):
        pages: List = params["pages"]
        save_path = params["save_path"]
        role_dict = self.extract_role_from_story(pages)
        image_prompts = self.generate_image_prompt_from_story(pages)
        image_prompts_with_role_desc = []
        for image_prompt in image_prompts:
            for role, role_desc in role_dict.items():
                if role in image_prompt:
                    image_prompt = image_prompt.replace(role, role_desc)
            image_prompts_with_role_desc.append(image_prompt)

        images = self.generate_images_via_api(
            image_prompts_with_role_desc,
            style_name=params.get("style_name", "Storybook"),
            width=self.cfg.get("width", 512),
            height=self.cfg.get("height", 512),
            seed=params.get("seed", 2047)
        )

        for idx, image in enumerate(images):
            image.save(save_path / f"p{idx + 1}.png")
        return {
            "prompts": image_prompts_with_role_desc,
            "generation_results": images,
        }

    def generate_images_via_api(self, prompts: List[str], style_name: str = "Storybook",
                                width: int = 512, height: int = 512, seed: int = 2047):
        try:
            import requests
            from PIL import Image, ImageDraw, ImageFont
            import io
            import base64
            import time
        except ImportError as e:
            print(f"Warning: Required packages not available: {e}")
            return self._create_placeholder_images(len(prompts), width, height)

        styles = {
            '(No style)': '{prompt}',
            'Japanese Anime': 'anime artwork illustrating {prompt}. created by japanese anime studio.',
            'Storybook': "Cartoon style, cute illustration of {prompt}."
        }
        style_template = styles.get(style_name, styles["Storybook"])
        styled_prompts = [style_template.format(prompt=prompt) for prompt in prompts]

        images = []
        api_type = self.api_type
        api_key = self.api_key
        api_url = self.api_url

        if api_type in ("dashscope", "aliyun"):
            images = self._generate_with_dashscope_api(styled_prompts, width, height, api_key)
        elif api_type == "openai":
            images = self._create_placeholder_images(len(prompts), width, height)
        elif api_type == "custom":
            images = self._generate_with_custom_api(styled_prompts, width, height, api_url, api_key)
        else:
            print(f"Warning: Unknown API type '{api_type}', creating placeholder images")
            images = self._create_placeholder_images(len(prompts), width, height)

        return images

    def _generate_with_dashscope_api(self, prompts: List[str], width: int, height: int, api_key: str):
        import os
        if not api_key:
            api_key = os.getenv('DASHSCOPE_API_KEY') or os.getenv('ALIYUN_APP_KEY')
        if not api_key:
            print("Warning: No DashScope API key provided, creating placeholder images")
            return self._create_placeholder_images(len(prompts), width, height)
        try:
            import dashscope
            from dashscope import ImageSynthesis
            from PIL import Image
            import requests
            import io
            import time
            dashscope.api_key = api_key
            images = []
            for idx, prompt in enumerate(prompts):
                try:
                    rsp = ImageSynthesis.call(
                        model=ImageSynthesis.Models.wanx_v1,
                        prompt=prompt,
                        n=1,
                        size=f'{width}*{height}' if width == height else '1024*1024'
                    )
                    if rsp.status_code == 200 and rsp.output and rsp.output.results:
                        image_url = rsp.output.results[0].url
                        image_response = requests.get(image_url)
                        image = Image.open(io.BytesIO(image_response.content))
                        if image.size != (width, height):
                            image = image.resize((width, height), Image.Resampling.LANCZOS)
                        images.append(image)
                    else:
                        images.append(self._create_placeholder_image(width, height))
                    time.sleep(2)
                except Exception as e:
                    print(f"DashScope error: {e}")
                    images.append(self._create_placeholder_image(width, height))
                    time.sleep(2)
            return images
        except ImportError:
            print("dashscope not installed; using placeholders")
            return self._create_placeholder_images(len(prompts), width, height)

    def _generate_with_custom_api(self, prompts: List[str], width: int, height: int, api_url: str, api_key: str):
        import requests
        from PIL import Image
        import io, base64
        if not api_url:
            print("No custom API URL; using placeholders")
            return self._create_placeholder_images(len(prompts), width, height)
        images = []
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        for prompt in prompts:
            try:
                data = {"prompt": prompt, "width": width, "height": height}
                response = requests.post(api_url, headers=headers, json=data, timeout=60)
                if response.status_code == 200:
                    ct = response.headers.get('content-type', '')
                    if 'image' in ct:
                        image = Image.open(io.BytesIO(response.content))
                    else:
                        result = response.json()
                        if 'url' in result:
                            img_resp = requests.get(result['url'])
                            image = Image.open(io.BytesIO(img_resp.content))
                        elif 'image' in result:
                            img_data = base64.b64decode(result['image'])
                            image = Image.open(io.BytesIO(img_data))
                        else:
                            image = self._create_placeholder_image(width, height)
                    images.append(image)
                else:
                    images.append(self._create_placeholder_image(width, height))
            except Exception as e:
                print(f"Custom API error: {e}")
                images.append(self._create_placeholder_image(width, height))
        return images

    def _create_placeholder_images(self, count: int, width: int, height: int):
        return [self._create_placeholder_image(width, height) for _ in range(count)]

    def _create_placeholder_image(self, width: int, height: int):
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (width, height), color=(200, 200, 200))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("arial.ttf", size=min(width, height) // 20)
        except Exception:
            font = ImageFont.load_default()
        text = "Generated Image\nPlaceholder"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, fill=(100, 100, 100), font=font, align="center")
        return image

    def extract_role_from_story(self, pages: List):
        num_turns = self.cfg.get("num_turns", 3)
        llm_tool = self.cfg.get("llm", "qwen")
        llm_cfg = {"system_prompt": role_extract_system, "track_history": False}
        if "llm_model_name" in self.cfg:
            llm_cfg["model_name"] = self.cfg["llm_model_name"]
        role_extractor = init_tool_instance({"tool": llm_tool, "cfg": llm_cfg})
        reviewer_cfg = {"system_prompt": role_review_system, "track_history": False}
        if "llm_model_name" in self.cfg:
            reviewer_cfg["model_name"] = self.cfg["llm_model_name"]
        role_reviewer = init_tool_instance({"tool": llm_tool, "cfg": reviewer_cfg})
        roles = {}
        review = ""
        for turn in range(num_turns):
            roles, success = role_extractor.call(json.dumps({
                "story_content": pages,
                "previous_result": roles,
                "improvement_suggestions": review,
            }, ensure_ascii=False))
            roles = json.loads(roles.strip("```json").strip("```"))
            review, success = role_reviewer.call(json.dumps({
                "story_content": pages,
                "role_descriptions": roles
            }, ensure_ascii=False))
            if review == "Check passed.":
                break
        return roles

    def generate_image_prompt_from_story(self, pages: List, num_turns: int = 3):
        llm_tool = self.cfg.get("llm", "qwen")
        reviewer_cfg = {"system_prompt": story_to_image_review_system, "track_history": False}
        if "llm_model_name" in self.cfg:
            reviewer_cfg["model_name"] = self.cfg["llm_model_name"]
        image_prompt_reviewer = init_tool_instance({"tool": llm_tool, "cfg": reviewer_cfg})
        reviser_cfg = {"system_prompt": story_to_image_reviser_system, "track_history": False}
        if "llm_model_name" in self.cfg:
            reviser_cfg["model_name"] = self.cfg["llm_model_name"]
        image_prompt_reviser = init_tool_instance({"tool": llm_tool, "cfg": reviser_cfg})
        image_prompts = []
        for page in pages:
            review = ""
            image_prompt = ""
            for turn in range(num_turns):
                image_prompt, success = image_prompt_reviser.call(json.dumps({
                    "all_pages": pages,
                    "current_page": page,
                    "previous_result": image_prompt,
                    "improvement_suggestions": review,
                }, ensure_ascii=False))
                if image_prompt.startswith("Image description:"):
                    image_prompt = image_prompt[len("Image description:"):]
                review, success = image_prompt_reviewer.call(json.dumps({
                    "all_pages": pages,
                    "current_page": page,
                    "image_description": image_prompt
                }, ensure_ascii=False))
                if review == "Check passed.":
                    break
            image_prompts.append(image_prompt)
        return image_prompts
