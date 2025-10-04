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

        agents = {}
        params = {}
        for modality in self.modalities:
            agents[modality] = init_tool_instance(config[modality + "_generation"])
            params[modality] = config[modality + "_generation"]["params"].copy()
            params[modality].update({
                "pages": pages,
                "save_path": story_dir / modality
            })

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
                    # Speech generation results are already saved to files
                    # No additional processing needed for script_data
                    print(f"Speech generation completed for {len(pages)} pages")
            except Exception as e:
                print(f"Error occurred during generation: {e}")

        with open(story_dir / "script_data.json", "w") as writer:
            json.dump(script_data, writer, ensure_ascii=False, indent=4)

        return images

    def compose_storytelling_video(self, config, pages):
        # Skip composing if no speech assets exist
        story_dir = Path(config["story_dir"]) if not isinstance(config["story_dir"], Path) else config["story_dir"]
        speech_dir = story_dir / "speech"
        if not speech_dir.exists() or not any(speech_dir.glob("*.wav")):
            print("No speech assets found. Skipping video composition.")
            return

        video_compose_agent = init_tool_instance(config["video_compose"])
        params = config["video_compose"]["params"].copy()
        params["pages"] = pages
        video_compose_agent.call(params)

    def call(self, config):
        pages = self.write_story(config)
        images = self.generate_modality_assets(config, pages)
        self.compose_storytelling_video(config, pages)

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
        self.compose_storytelling_video(config, pages)
