import json
from typing import List, Dict

from mm_story_agent.base import register_tool, init_tool_instance
from mm_story_agent.prompts_en import role_extract_system, role_review_system, \
    story_to_image_reviser_system, story_to_image_review_system


@register_tool("story_diffusion_t2i")
class StoryDiffusionAgent:

    def __init__(self, cfg) -> None:
        self.cfg = cfg

    def call(self, params: Dict):
        pages: List = params["pages"]
        save_path: str = params["save_path"]
        role_dict = self.extract_role_from_story(pages)
        image_prompts = self.generate_image_prompt_from_story(pages)
        image_prompts_with_role_desc = []
        for image_prompt in image_prompts:
            for role, role_desc in role_dict.items():
                if role in image_prompt:
                    image_prompt = image_prompt.replace(role, role_desc)
            image_prompts_with_role_desc.append(image_prompt)

        # Use API-based image generation
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
        """
        Generate images using API calls instead of local diffusion models.
        This method can be adapted to work with different image generation APIs.
        """
        try:
            import requests
            from PIL import Image
            import io
            import base64
            import time
        except ImportError as e:
            print(f"Warning: Required packages not available for API image generation: {e}")
            return self._create_placeholder_images(len(prompts), width, height)

        # Style templates for different art styles
        styles = {
            '(No style)': '{prompt}',
            'Japanese Anime': 'anime artwork illustrating {prompt}. created by japanese anime studio. highly emotional. best quality, high resolution, (Anime Style, Manga Style:1.3), Low detail, sketch, concept art, line art, webtoon, manhua, hand drawn, defined lines, simple shades, minimalistic, High contrast, Linear compositions, Scalable artwork, Digital art, High Contrast Shadows',
            'Digital/Oil Painting': '{prompt} . (Extremely Detailed Oil Painting:1.2), glow effects, godrays, Hand drawn, render, 8k, octane render, cinema 4d, blender, dark, atmospheric 4k ultra detailed, cinematic sensual, Sharp focus, humorous illustration, big depth of field',
            'Pixar/Disney Character': 'Create a Disney Pixar 3D style illustration on {prompt} . The scene is vibrant, motivational, filled with vivid colors and a sense of wonder.',
            'Photographic': 'cinematic photo {prompt} . Hyperrealistic, Hyperdetailed, detailed skin, matte skin, soft lighting, realistic, best quality, ultra realistic, 8k, golden ratio, Intricate, High Detail, film photography, soft focus',
            'Comic book': 'comic {prompt} . graphic illustration, comic art, graphic novel art, vibrant, highly detailed',
            'Line art': 'line art drawing {prompt} . professional, sleek, modern, minimalist, graphic, line art, vector graphics',
            'Black and White Film Noir': '{prompt} . (b&w, Monochromatic, Film Photography:1.3), film noir, analog style, soft lighting, subsurface scattering, realistic, heavy shadow, masterpiece, best quality, ultra realistic, 8k',
            'Isometric Rooms': 'Tiny cute isometric {prompt} . in a cutaway box, soft smooth lighting, soft colors, 100mm lens, 3d blender render',
            'Storybook': "Cartoon style, cute illustration of {prompt}."
        }

        # Apply style to prompts
        style_template = styles.get(style_name, styles["Storybook"])
        styled_prompts = [style_template.format(prompt=prompt) for prompt in prompts]

        images = []

        # Get API configuration
        api_type = self.cfg.get("api_type", "dashscope")  # Default to DashScope (Aliyun)
        api_key = self.cfg.get("api_key", "")
        api_url = self.cfg.get("api_url", "")

        if api_type == "dashscope" or api_type == "aliyun":
            images = self._generate_with_dashscope_api(styled_prompts, width, height, api_key)
        elif api_type == "openai":
            images = self._generate_with_openai_api(styled_prompts, width, height, api_key)
        elif api_type == "stability":
            images = self._generate_with_stability_api(styled_prompts, width, height, api_key, api_url)
        elif api_type == "replicate":
            images = self._generate_with_replicate_api(styled_prompts, width, height, api_key)
        elif api_type == "custom":
            images = self._generate_with_custom_api(styled_prompts, width, height, api_url, api_key)
        else:
            # Fallback: create placeholder images
            print(f"Warning: Unknown API type '{api_type}', creating placeholder images")
            images = self._create_placeholder_images(len(prompts), width, height)

        return images

    def _generate_with_dashscope_api(self, prompts: List[str], width: int, height: int, api_key: str):
        """Generate images using Aliyun DashScope API (通义万相)"""
        import os

        # Try to get API key from environment if not provided
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

            # Set API key
            dashscope.api_key = api_key

            # Use serial processing for image generation (API rate limit compliance)
            images = self._generate_images_serial(prompts, width, height, api_key)

            return images

        except ImportError:
            print("Warning: dashscope package not installed. Install with: pip install dashscope")
            return self._create_placeholder_images(len(prompts), width, height)

    def _generate_images_serial(self, prompts: List[str], width: int, height: int, api_key: str):
        """Generate images serially to comply with API rate limits"""
        import dashscope
        from dashscope import ImageSynthesis
        from PIL import Image
        import requests
        import io
        import time

        dashscope.api_key = api_key
        images = []

        print(f"Starting serial image generation for {len(prompts)} images...")

        for idx, prompt in enumerate(prompts):
            try:
                # Call DashScope image generation API
                rsp = ImageSynthesis.call(
                    model=ImageSynthesis.Models.wanx_v1,
                    prompt=prompt,
                    n=1,
                    size=f'{width}*{height}' if width == height else '1024*1024'
                )

                if rsp.status_code == 200 and rsp.output and rsp.output.results:
                    # Get image URL from response
                    image_url = rsp.output.results[0].url

                    # Download image
                    image_response = requests.get(image_url)
                    image = Image.open(io.BytesIO(image_response.content))

                    # Resize if needed
                    if image.size != (width, height):
                        image = image.resize((width, height), Image.Resampling.LANCZOS)

                    images.append(image)
                    print(f"Successfully generated image {idx + 1}/{len(prompts)} with DashScope API")

                else:
                    print(f"DashScope API error for image {idx + 1}: {rsp.status_code}, {rsp.message}")
                    images.append(self._create_placeholder_image(width, height))

                # Rate limiting: wait between requests to comply with API limits
                time.sleep(2)  # 2 seconds between requests (QPS limit: 0.5 per second)

            except Exception as e:
                print(f"Error generating image {idx + 1} with DashScope API: {e}")
                images.append(self._create_placeholder_image(width, height))
                time.sleep(2)  # Still wait even on error

        print(f"Completed image generation: {len(images)} images total")
        return images

    def _generate_with_openai_api(self, prompts: List[str], width: int, height: int, api_key: str):
        """Generate images using OpenAI DALL-E API"""
        import openai
        from PIL import Image
        import requests

        if not api_key:
            print("Warning: No OpenAI API key provided, creating placeholder images")
            return self._create_placeholder_images(len(prompts), width, height)

        client = openai.OpenAI(api_key=api_key)
        images = []

        for prompt in prompts:
            try:
                response = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt[:4000],  # DALL-E has prompt length limits
                    size=f"{width}x{height}" if f"{width}x{height}" in ["1024x1024", "1792x1024",
                                                                        "1024x1792"] else "1024x1024",
                    quality="standard",
                    n=1,
                )

                image_url = response.data[0].url
                image_response = requests.get(image_url)
                image = Image.open(io.BytesIO(image_response.content))

                # Resize if needed
                if image.size != (width, height):
                    image = image.resize((width, height), Image.Resampling.LANCZOS)

                images.append(image)
                time.sleep(1)  # Rate limiting

            except Exception as e:
                print(f"Error generating image with OpenAI API: {e}")
                images.append(self._create_placeholder_image(width, height))

        return images

    def _generate_with_stability_api(self, prompts: List[str], width: int, height: int, api_key: str, api_url: str):
        """Generate images using Stability AI API"""
        import requests
        from PIL import Image
        import io

        if not api_key:
            print("Warning: No Stability AI API key provided, creating placeholder images")
            return self._create_placeholder_images(len(prompts), width, height)

        if not api_url:
            api_url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"

        images = []
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        for prompt in prompts:
            try:
                data = {
                    "text_prompts": [{"text": prompt}],
                    "cfg_scale": 7,
                    "height": height,
                    "width": width,
                    "samples": 1,
                    "steps": 30,
                }

                response = requests.post(api_url, headers=headers, json=data)

                if response.status_code == 200:
                    result = response.json()
                    image_data = base64.b64decode(result["artifacts"][0]["base64"])
                    image = Image.open(io.BytesIO(image_data))
                    images.append(image)
                else:
                    print(f"Stability AI API error: {response.status_code}")
                    images.append(self._create_placeholder_image(width, height))

                time.sleep(1)  # Rate limiting

            except Exception as e:
                print(f"Error generating image with Stability AI API: {e}")
                images.append(self._create_placeholder_image(width, height))

        return images

    def _generate_with_replicate_api(self, prompts: List[str], width: int, height: int, api_key: str):
        """Generate images using Replicate API"""
        try:
            import replicate
        except ImportError:
            print("Warning: replicate package not installed, creating placeholder images")
            return self._create_placeholder_images(len(prompts), width, height)

        if not api_key:
            print("Warning: No Replicate API key provided, creating placeholder images")
            return self._create_placeholder_images(len(prompts), width, height)

        import os
        os.environ["REPLICATE_API_TOKEN"] = api_key

        images = []

        for prompt in prompts:
            try:
                output = replicate.run(
                    "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
                    input={
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "num_outputs": 1,
                        "scheduler": "K_EULER",
                        "num_inference_steps": 30,
                        "guidance_scale": 7.5,
                    }
                )

                if output and len(output) > 0:
                    image_url = output[0]
                    image_response = requests.get(image_url)
                    image = Image.open(io.BytesIO(image_response.content))
                    images.append(image)
                else:
                    images.append(self._create_placeholder_image(width, height))

                time.sleep(1)  # Rate limiting

            except Exception as e:
                print(f"Error generating image with Replicate API: {e}")
                images.append(self._create_placeholder_image(width, height))

        return images

    def _generate_with_custom_api(self, prompts: List[str], width: int, height: int, api_url: str, api_key: str):
        """Generate images using a custom API endpoint"""
        import requests
        from PIL import Image
        import io

        if not api_url:
            print("Warning: No custom API URL provided, creating placeholder images")
            return self._create_placeholder_images(len(prompts), width, height)

        images = []
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        for prompt in prompts:
            try:
                data = {
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                }

                response = requests.post(api_url, headers=headers, json=data, timeout=60)

                if response.status_code == 200:
                    # Assume the API returns image data directly or a URL
                    content_type = response.headers.get('content-type', '')
                    if 'image' in content_type:
                        image = Image.open(io.BytesIO(response.content))
                    else:
                        # Assume JSON response with image URL or base64 data
                        result = response.json()
                        if 'url' in result:
                            image_response = requests.get(result['url'])
                            image = Image.open(io.BytesIO(image_response.content))
                        elif 'image' in result:
                            image_data = base64.b64decode(result['image'])
                            image = Image.open(io.BytesIO(image_data))
                        else:
                            raise ValueError("Unknown response format")

                    images.append(image)
                else:
                    print(f"Custom API error: {response.status_code}")
                    images.append(self._create_placeholder_image(width, height))

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"Error generating image with custom API: {e}")
                images.append(self._create_placeholder_image(width, height))

        return images

    def _create_placeholder_images(self, count: int, width: int, height: int):
        """Create placeholder images when API is not available"""
        return [self._create_placeholder_image(width, height) for _ in range(count)]

    def _create_placeholder_image(self, width: int, height: int):
        """Create a single placeholder image"""
        from PIL import Image, ImageDraw, ImageFont

        # Create a simple placeholder image
        image = Image.new('RGB', (width, height), color=(200, 200, 200))
        draw = ImageDraw.Draw(image)

        # Try to use a default font, fallback to basic if not available
        try:
            font = ImageFont.truetype("arial.ttf", size=min(width, height) // 20)
        except:
            font = ImageFont.load_default()

        text = "Generated Image\nPlaceholder"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        draw.text((x, y), text, fill=(100, 100, 100), font=font, align="center")

        return image

    def extract_role_from_story(
            self,
            pages: List,
    ):
        num_turns = self.cfg.get("num_turns", 3)
        role_extractor = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": role_extract_system,
                "track_history": False
            }
        })
        role_reviewer = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": role_review_system,
                "track_history": False
            }
        })
        roles = {}
        review = ""
        for turn in range(num_turns):
            roles, success = role_extractor.call(json.dumps({
                "story_content": pages,
                "previous_result": roles,
                "improvement_suggestions": review,
            }, ensure_ascii=False
            ))
            roles = json.loads(roles.strip("```json").strip("```"))
            review, success = role_reviewer.call(json.dumps({
                "story_content": pages,
                "role_descriptions": roles
            }, ensure_ascii=False))
            if review == "Check passed.":
                break
        return roles

    def generate_image_prompt_from_story(
            self,
            pages: List,
            num_turns: int = 3
    ):
        image_prompt_reviewer = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": story_to_image_review_system,
                "track_history": False
            }
        })
        image_prompt_reviser = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": story_to_image_reviser_system,
                "track_history": False
            }
        })
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
