import json
from pathlib import Path

import torch.multiprocessing as mp

mp.set_start_method("spawn", force=True)

from .base import init_tool_instance
from .model_config import get_model_config_instance, load_model_for_agent


class MMStoryAgent:

    def __init__(self, models_config_path: str = "configs/models.yaml", resume: bool = False) -> None:
        self.modalities = ["image", "speech"]
        self.model_config = get_model_config_instance(models_config_path)
        self.resume = resume

    def call_modality_agent(self, modality, agent, params, return_dict):
        result = agent.call(params)
        return_dict[modality] = result

    def write_story(self, config):
        cfg = config["story_writer"]
        merged_cfg = load_model_for_agent(cfg, 'llm')
        story_writer = init_tool_instance({"tool": cfg["tool"], "cfg": merged_cfg})
        pages = story_writer.call(cfg["params"])
        return pages

    def generate_modality_assets(self, config, pages):
        story_dir = Path(config["story_dir"])
        script_data_path = story_dir / "script_data.json"

        if script_data_path.exists():
            with open(script_data_path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
        else:
            script_data = {"pages": [{"story": page} for page in pages]}

        if self.resume and "segmented_pages" in script_data and script_data["segmented_pages"]:
            print("🔄 Found existing text segmentation, loading...")
            segmented_pages = script_data["segmented_pages"]
        else:
            print("   - Starting text segmentation...")
            from mm_story_agent.video_compose_agent import split_text_for_speech
            segmented_pages = [split_text_for_speech(page, max_words=20) for page in pages]
            script_data["segmented_pages"] = segmented_pages
            print("     ✓ Text segmentation complete.")

        for sub_dir in self.modalities:
            (story_dir / sub_dir).mkdir(exist_ok=True, parents=True)

        processes_to_run = []
        manager = mp.Manager()
        return_dict = manager.dict()

        image_dir = story_dir / "image"
        num_images = len(list(image_dir.glob("p*.png")))
        if self.resume and image_dir.exists() and num_images >= len(pages):
            print("🔄 Found existing images, skipping generation.")
        else:
            print("   - Starting image generation...")
            agent_config = config["image_generation"]
            merged_cfg = load_model_for_agent(agent_config, 'image')
            if 'llm_model' in agent_config:
                llm_config = self.model_config.get_llm_config(agent_config['llm_model'])
                merged_cfg['llm_model_name'] = llm_config.get('model_name')
                if 'llm' not in merged_cfg:
                    merged_cfg['llm'] = 'qwen'
            agent = init_tool_instance({"tool": agent_config["tool"], "cfg": merged_cfg})
            params = agent_config["params"].copy()
            params.update({"pages": pages, "save_path": image_dir})
            processes_to_run.append(mp.Process(target=self.call_modality_agent, args=("image", agent, params, return_dict)))

        speech_dir = story_dir / "speech"
        num_speech_files = len(list(speech_dir.glob("s*.wav")))
        total_segments = sum(len(s) for s in segmented_pages)
        if self.resume and speech_dir.exists() and num_speech_files >= total_segments:
            print("🔄 Found existing speech files, skipping generation.")
        else:
            print("   - Starting speech generation...")
            agent_config = config["speech_generation"]
            merged_cfg = load_model_for_agent(agent_config, 'speech')
            agent = init_tool_instance({"tool": agent_config["tool"], "cfg": merged_cfg})
            params = agent_config["params"].copy()
            params.update({"pages": pages, "save_path": speech_dir, "segmented_pages": segmented_pages})
            processes_to_run.append(mp.Process(target=self.call_modality_agent, args=("speech", agent, params, return_dict)))

        if processes_to_run:
            for p in processes_to_run:
                p.start()
            for p in processes_to_run:
                p.join()
        else:
            print("   ✓ All modality assets already exist.")

        for modality, result in return_dict.items():
            if modality == "image" and "prompts" in result:
                for idx, prompt in enumerate(result["prompts"]):
                    if idx < len(script_data["pages"]):
                        script_data["pages"][idx]["image_prompt"] = prompt
        
        with open(script_data_path, "w", encoding="utf-8") as writer:
            json.dump(script_data, writer, ensure_ascii=False, indent=4)

        return segmented_pages

    def compose_storytelling_video(self, config, pages, segmented_pages=None):
        story_dir = Path(config["story_dir"])
        if not (story_dir / "speech").exists() or not any((story_dir / "speech").glob("*.wav")):
            print("No speech assets found. Skipping video composition.")
            return

        if segmented_pages is None:
            script_data_path = story_dir / "script_data.json"
            if script_data_path.exists():
                try:
                    with open(script_data_path, "r", encoding="utf-8") as f:
                        script_data = json.load(f)
                    segmented_pages = script_data.get("segmented_pages")
                except Exception as e:
                    print(f"Error loading script data: {e}")

        video_compose_agent = init_tool_instance(config["video_compose"])
        params = config["video_compose"]["params"].copy()
        params["pages"] = pages
        if segmented_pages:
            params["segmented_pages"] = segmented_pages
        video_compose_agent.call(params)

    def call(self, config):
        story_dir = Path(config["story_dir"])
        script_data_path = story_dir / "script_data.json"
        output_video_path = story_dir / "output.mp4"

        story_dir.mkdir(exist_ok=True, parents=True)

        if self.resume and output_video_path.exists():
            print(f"🔄 Final video already exists at {output_video_path}. Nothing to do.")
            return

        if self.resume:
            print("🔄 Resume mode enabled. Checking for existing files...")

        # Stage 1: Text Generation
        if self.resume and script_data_path.exists():
            print(f"▶️ Stage 1: Story Generation - SKIPPED")
            print(f"🔄 Found existing story data at {script_data_path}, loading...")
            with open(script_data_path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
            pages = [p.get("story", "") for p in script_data.get("pages", [])]
            print(f"   ✓ Loaded {len(pages)} pages.")
        else:
            print("▶️ Starting stage 1: Story Generation")
            pages = self.write_story(config)
            script_data = {"pages": [{"story": page} for page in pages]}
            with open(script_data_path, "w", encoding="utf-8") as f:
                json.dump(script_data, f, ensure_ascii=False, indent=4)
            print("   ✓ Story generation complete.")

        # Stage 2: Modality Asset Generation
        print("\n▶️ Starting stage 2: Modality Asset Generation")
        segmented_pages = self.generate_modality_assets(config, pages)
        print("   ✓ Modality asset generation complete.")

        # Stage 3: Video Composition
        print("\n▶️ Starting stage 3: Video Composition")
        self.compose_storytelling_video(config, pages, segmented_pages)
        print("\n✨ All stages complete. Video generated successfully!")
