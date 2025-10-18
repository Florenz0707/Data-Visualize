import json
from pathlib import Path

import torch.multiprocessing as mp

mp.set_start_method("spawn", force=True)

from .base import init_tool_instance


class MMStoryAgent:

    def __init__(self) -> None:
        self.modalities = [
            "image",
            "speech"
        ]

    def call_modality_agent(self, modality, agent, params, return_dict):
        result = agent.call(params)
        return_dict[modality] = result

    def write_story(self, config):
        cfg = config["story_writer"]
        story_writer = init_tool_instance(cfg)
        pages = story_writer.call(cfg["params"])
        return pages

    def generate_modality_assets(self, config, pages):
        script_data = {"pages": [{"story": page} for page in pages]}
        story_dir = Path(config["story_dir"])

        for sub_dir in self.modalities:
            (story_dir / sub_dir).mkdir(exist_ok=True, parents=True)

        # 预先进行文本切分
        print("开始文本切分...")
        from mm_story_agent.video_compose_agent import split_text_for_speech
        segmented_pages = []
        for idx, page in enumerate(pages):
            print(f"切分页面 {idx + 1}: {page[:100]}{'...' if len(page) > 100 else ''}")
            text_segments = split_text_for_speech(page, max_words=20)
            segmented_pages.append(text_segments)
            print(f"  切分为 {len(text_segments)} 段")
            for i, segment in enumerate(text_segments):
                word_count = len(segment.split())
                print(f"    段 {i + 1}: {segment[:50]}{'...' if len(segment) > 50 else ''} ({word_count} 单词)")

        # 将切分结果保存到脚本数据中
        script_data["segmented_pages"] = segmented_pages
        print(f"文本切分完成，共 {len(segmented_pages)} 个页面")

        agents = {}
        params = {}
        for modality in self.modalities:
            agents[modality] = init_tool_instance(config[modality + "_generation"])
            params[modality] = config[modality + "_generation"]["params"].copy()
            params[modality].update({
                "pages": pages,
                "save_path": story_dir / modality
            })

            # 为语音生成提供切分后的页面
            if modality == "speech":
                params[modality]["segmented_pages"] = segmented_pages

        processes = []
        return_dict = mp.Manager().dict()

        for modality in self.modalities:
            p = mp.Process(
                target=self.call_modality_agent,
                args=(
                    modality,
                    agents[modality],
                    params[modality],
                    return_dict)
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        for modality, result in return_dict.items():
            try:
                if modality == "image":
                    images = result["generation_results"]
                    for idx in range(len(pages)):
                        script_data["pages"][idx]["image_prompt"] = result["prompts"][idx]
                elif modality == "speech":
                    print(f"Speech generation completed for {len(pages)} pages using pre-segmented text")
            except Exception as e:
                print(f"Error occurred during generation: {e}")

        with open(story_dir / "script_data.json", "w") as writer:
            json.dump(script_data, writer, ensure_ascii=False, indent=4)

        return images, segmented_pages

    def compose_storytelling_video(self, config, pages, segmented_pages=None):
        # Skip composing if no speech assets exist
        story_dir = Path(config["story_dir"]) if not isinstance(config["story_dir"], Path) else config["story_dir"]
        speech_dir = story_dir / "speech"
        if not speech_dir.exists() or not any(speech_dir.glob("*.wav")):
            print("No speech assets found. Skipping video composition.")
            return

        # 如果没有提供切分后的页面信息，尝试从脚本数据中读取
        if segmented_pages is None:
            script_data_path = story_dir / "script_data.json"
            if script_data_path.exists():
                try:
                    with open(script_data_path, "r", encoding="utf-8") as f:
                        script_data = json.load(f)
                    segmented_pages = script_data.get("segmented_pages", None)
                    if segmented_pages:
                        print(f"Loaded segmented pages from script data: {len(segmented_pages)} pages")
                except Exception as e:
                    print(f"Error loading script data: {e}")

        video_compose_agent = init_tool_instance(config["video_compose"])
        params = config["video_compose"]["params"].copy()
        params["pages"] = pages
        if segmented_pages:
            params["segmented_pages"] = segmented_pages
        video_compose_agent.call(params)

    def call(self, config):
        pages = self.write_story(config)
        images, segmented_pages = self.generate_modality_assets(config, pages)
        self.compose_storytelling_video(config, pages, segmented_pages)

    def resume_from_video_composition(self, config):
        """Resume from video composition stage, skipping story/speech/image generation"""
        story_dir = Path(config["story_dir"])

        # Check if required assets exist
        script_data_path = story_dir / "script_data.json"
        if not script_data_path.exists():
            raise FileNotFoundError(f"Script data not found at {script_data_path}. Cannot resume without story data.")

        # Load existing story data
        with open(script_data_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)

        pages = [page["story"] for page in script_data["pages"]]

        print(f"Found existing story data with {len(pages)} pages")

        # Check if speech and image assets exist
        speech_dir = story_dir / "speech"
        image_dir = story_dir / "image"

        if speech_dir.exists() and any(speech_dir.glob("*.wav")):
            print(f"Found {len(list(speech_dir.glob('*.wav')))} speech files")
        else:
            print("Warning: No speech files found")

        if image_dir.exists() and any(image_dir.glob("*.png")):
            print(f"Found {len(list(image_dir.glob('*.png')))} image files")
        else:
            print("Warning: No image files found")

        print("Starting video composition...")
        # 从脚本数据中获取切分后的页面信息
        segmented_pages = script_data.get("segmented_pages", None)
        self.compose_storytelling_video(config, pages, segmented_pages)
