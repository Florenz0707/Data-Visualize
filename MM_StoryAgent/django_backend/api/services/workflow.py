from __future__ import annotations

import json
from typing import Dict, List

# Ensure project root on path and load env
from .bootstrap import *  # noqa: F401
from .vendor.base import init_tool_instance
from .vendor.model_config import get_model_config_instance, load_model_for_agent
from .vendor.video_compose_agent import split_text_for_speech


class WorkflowRunner:
    def __init__(self, project_root: Path | None = None,
                 base_config_path: Path | None = None,
                 models_config_path: Path | None = None):
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        # Resolve config paths with fallback: configs/* then config/*
        def _resolve_cfg(path: Path, alt: Path) -> Path:
            return path if path.exists() else alt
        default_main = self.project_root / "configs" / "mm_story_agent.yaml"
        alt_main = self.project_root / "config" / "mm_story_agent.yaml"
        default_models = self.project_root / "configs" / "models.yaml"
        alt_models = self.project_root / "config" / "models.yaml"
        self.base_config_path = Path(base_config_path) if base_config_path else _resolve_cfg(default_main, alt_main)
        self.models_config_path = Path(models_config_path) if models_config_path else _resolve_cfg(default_models, alt_models)
        self.model_config = get_model_config_instance(str(self.models_config_path))
        # Load base config once
        import yaml
        with open(self.base_config_path, "r", encoding="utf-8") as f:
            self.base_cfg: Dict = yaml.load(f, Loader=yaml.FullLoader)

    def _story_dir(self, story_dir: str | Path) -> Path:
        p = Path(story_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / "image").mkdir(exist_ok=True)
        (p / "speech").mkdir(exist_ok=True)
        return p

    def _save_script(self, story_dir: Path, script_data: Dict):
        with open(story_dir / "script_data.json", "w", encoding="utf-8") as w:
            json.dump(script_data, w, ensure_ascii=False, indent=4)

    def _load_script(self, story_dir: Path) -> Dict:
        p = story_dir / "script_data.json"
        if p.exists():
            with open(p, "r", encoding="utf-8") as r:
                return json.load(r)
        return {"pages": []}

    # ========== Segment 1: Story ==========
    def run_story(self, story_dir: str | Path, topic: str, main_role: str = "", scene: str = "") -> List[str]:
        story_dir = self._story_dir(story_dir)
        cfg = dict(self.base_cfg["story_writer"])  # shallow copy
        merged_cfg = load_model_for_agent(cfg, 'llm')
        writer = init_tool_instance({"tool": cfg["tool"], "cfg": merged_cfg})
        params = cfg.get("params", {}).copy()
        if topic:
            params["story_topic"] = topic
        if main_role:
            params["main_role"] = main_role
        if scene:
            params["scene"] = scene
        pages: List[str] = writer.call(params)
        script = {"pages": [{"story": p} for p in pages]}
        self._save_script(Path(story_dir), script)
        return pages

    # ========== Segment 2: Image ==========
    def run_image(self, story_dir: str | Path, pages: List[str] | None = None) -> List[str]:
        story_dir = self._story_dir(story_dir)
        script = self._load_script(Path(story_dir))
        if pages is None:
            pages = [p.get("story", "") for p in script.get("pages", [])]
        agent_config = dict(self.base_cfg["image_generation"])  # copy
        merged_cfg = load_model_for_agent(agent_config, 'image')
        # Attach LLM model info if required by image agent
        if 'llm_model' in agent_config:
            llm_config = self.model_config.get_llm_config(agent_config['llm_model'])
            merged_cfg['llm_model_name'] = llm_config.get('model_name')
            if 'llm' not in merged_cfg:
                merged_cfg['llm'] = 'qwen'
        agent = init_tool_instance({"tool": agent_config["tool"], "cfg": merged_cfg})
        params = agent_config.get("params", {}).copy()
        params.update({"pages": pages, "save_path": Path(story_dir) / "image"})
        result = agent.call(params)
        # write prompts back
        if isinstance(result, dict) and "prompts" in result:
            for idx, prompt in enumerate(result["prompts"]):
                if idx < len(script.get("pages", [])):
                    script["pages"][idx]["image_prompt"] = prompt
            self._save_script(Path(story_dir), script)
        images = sorted([str(p) for p in (Path(story_dir) / "image").glob("p*.png")])
        return images

    # ========== Segment 3: Split ==========
    def run_split(self, story_dir: str | Path, pages: List[str] | None = None, max_words: int = 20) -> List[List[str]]:
        story_dir = self._story_dir(story_dir)
        script = self._load_script(Path(story_dir))
        if pages is None:
            pages = [p.get("story", "") for p in script.get("pages", [])]
        segmented = [split_text_for_speech(page, max_words=max_words) for page in pages]
        script["segmented_pages"] = segmented
        self._save_script(Path(story_dir), script)
        return segmented

    # ========== Segment 4: Speech ==========
    def run_speech(self, story_dir: str | Path, segmented_pages: List[List[str]] | None = None,
                   pages: List[str] | None = None) -> List[str]:
        story_dir = self._story_dir(story_dir)
        script = self._load_script(Path(story_dir))
        if segmented_pages is None:
            segmented_pages = script.get("segmented_pages")
        if pages is None:
            pages = [p.get("story", "") for p in script.get("pages", [])]
        agent_config = dict(self.base_cfg["speech_generation"])  # copy
        merged_cfg = load_model_for_agent(agent_config, 'speech')
        agent = init_tool_instance({"tool": agent_config["tool"], "cfg": merged_cfg})
        params = agent_config.get("params", {}).copy()
        params.update({
            "pages": pages,
            "save_path": Path(story_dir) / "speech",
            "segmented_pages": segmented_pages,
        })
        agent.call(params)
        wavs = sorted([str(p) for p in (Path(story_dir) / "speech").glob("s*.wav")])
        return wavs

    # ========== Segment 5: Video ==========
    def run_video(self, story_dir: str | Path, pages: List[str] | None = None,
                  segmented_pages: List[List[str]] | None = None) -> str:
        story_dir = self._story_dir(story_dir)
        compose_cfg = dict(self.base_cfg["video_compose"])  # already tool + cfg + params
        agent = init_tool_instance(compose_cfg)
        script = self._load_script(Path(story_dir))
        if pages is None:
            pages = [p.get("story", "") for p in script.get("pages", [])]
        if segmented_pages is None:
            segmented_pages = script.get("segmented_pages")
        params = compose_cfg.get("params", {}).copy()
        # Always use task-specific story_dir instead of config default
        params["story_dir"] = str(Path(story_dir))
        params["pages"] = pages
        if segmented_pages:
            params["segmented_pages"] = segmented_pages
        agent.call(params)
        return str(Path(story_dir) / "output.mp4")
