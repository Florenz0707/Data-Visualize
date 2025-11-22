from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

# Ensure project root on path and load env
from .bootstrap import *  # noqa: F401
from .vendor.base import init_tool_instance
from .vendor.model_config import get_model_config_instance, load_model_for_agent

logger = logging.getLogger(__name__)

ALLOWED_BGM_EXTENSIONS = {".mp3", ".wav", ".flac"}


class WorkflowRunner:
    def __init__(self, project_root: Path | None = None,
                 base_config_path: Path | None = None,
                 models_config_path: Path | None = None):
        # Prefer Django project base (django_backend) as root for config directory
        # This matches path like <...>/django_backend/config/models.yaml
        from django.conf import settings as dj_settings
        self.project_root = project_root or Path(dj_settings.BASE_DIR)

        cfg_dir = self.project_root / "config"
        self.base_config_path = Path(base_config_path) if base_config_path else (cfg_dir / "mm_story_agent.yaml")
        self.models_config_path = Path(models_config_path) if models_config_path else (cfg_dir / "models.yaml")
        if not self.base_config_path.exists():
            raise FileNotFoundError(f"Main config file not found: {self.base_config_path}")
        if not self.models_config_path.exists():
            raise FileNotFoundError(f"Model config file not found: {self.models_config_path}")
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

        # Build story setting string, prioritize user input over config defaults
        default_params = cfg.get("params", {}) or {}
        _topic = topic or default_params.get("story_topic", "")
        _role = main_role or default_params.get("main_role", "")
        _scene = scene or default_params.get("scene", "")

        parts = []
        if _topic:
            parts.append(f"Topic: {_topic}")
        if _role:
            parts.append(f"Main role: {_role}")
        if _scene:
            parts.append(f"Scene: {_scene}")
        story_setting = "; ".join(parts) if parts else str(default_params)

        # Pass a single consolidated setting string to story agent
        pages: List[str] = writer.call(story_setting)
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
    def run_split(self, story_dir: str | Path, pages: List[str] | None = None, max_chars: int | None = None) -> List[List[str]]:
        # Lazy import to avoid importing cv2-dependent modules at startup
        from .vendor.video_compose_agent import split_text_for_speech

        # Load default from config if not provided
        if max_chars is None:
            try:
                max_chars = int(self.base_cfg.get("text_split", {}).get("params", {}).get("max_chars", 60))
            except Exception:
                max_chars = 60

        story_dir = self._story_dir(story_dir)
        script = self._load_script(Path(story_dir))
        if pages is None:
            pages = [p.get("story", "") for p in script.get("pages", [])]
        segmented = [split_text_for_speech(page, max_chars=max_chars) for page in pages]

        # thresholds from config (with sensible defaults)
        ts_params = self.base_cfg.get("text_split", {}).get("params", {})
        min_chars_short = int(ts_params.get("min_chars_per_segment", 15))
        min_words_short = int(ts_params.get("min_words_per_segment", 3))

        # Post-process: merge too-short segments to avoid 1-2 word chunks
        def _word_count(s: str) -> int:
            # Rough word count: split on whitespace; for CJK text without spaces, count as len(s)
            if any(ch.isspace() for ch in s):
                return len([w for w in s.strip().split() if w])
            return max(1, len(s))

        def _merge_short_segments(segments: List[str], min_chars: int = 15, min_words: int = 3) -> List[str]:
            if not segments:
                return segments
            merged: List[str] = []
            for seg in segments:
                cur = seg.strip()
                if not cur:
                    continue
                too_short = (len(cur) < min_chars) or (_word_count(cur) < min_words)
                if too_short and merged:
                    # Try merge with previous
                    prev = merged.pop()
                    # If both are latin-ish with spaces, join with space; else direct concat
                    if any(c.isalpha() and c.lower() == c for c in (cur + prev)) and (" " in prev or " " in cur):
                        new = (prev.rstrip() + " " + cur.lstrip()).strip()
                    else:
                        new = (prev + cur)
                    merged.append(new)
                else:
                    merged.append(cur)
            # If first still short and there is more than one, merge forward
            if len(merged) >= 2 and ((len(merged[0]) < min_chars) or (_word_count(merged[0]) < min_words)):
                merged[1] = (merged[0].rstrip() + (" " if (" " in merged[0] or " " in merged[1]) else "") + merged[1].lstrip()).strip()
                merged = merged[1:]
            return merged

        segmented = [_merge_short_segments(segs) for segs in segmented]

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

    # ========== Segment 5: Video (slideshow compose) ==========
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

        # Resolve optional background music path
        raw_bgm = params.get("bgm_path")
        resolved_bgm = None
        if raw_bgm:
            from django.conf import settings as dj_settings

            candidate = Path(raw_bgm)
            if not candidate.is_absolute():
                candidate = (Path(dj_settings.BASE_DIR) / candidate).resolve()
            else:
                candidate = candidate.resolve()
            if candidate.is_file():
                suffix = candidate.suffix.lower()
                if suffix in ALLOWED_BGM_EXTENSIONS:
                    resolved_bgm = candidate
                else:
                    logger.warning(
                        "Configured BGM file has unsupported extension '%s'. Allowed: %s",
                        suffix,
                        sorted(ALLOWED_BGM_EXTENSIONS),
                    )
            else:
                logger.warning("Configured BGM file not found, skipping: %s", raw_bgm)
        if resolved_bgm:
            params["bgm_path"] = str(resolved_bgm)
        else:
            params.pop("bgm_path", None)

        # Always use task-specific story_dir instead of config default
        params["story_dir"] = str(Path(story_dir))
        params["pages"] = pages
        if segmented_pages:
            params["segmented_pages"] = segmented_pages
        agent.call(params)
        return str(Path(story_dir) / "output.mp4")

    # ========== T2V: Direct text-to-video via provider (Runway) ==========
    def run_video_t2v(self, story_dir: str | Path, prompt: str, overrides: Dict | None = None) -> str:
        story_dir = self._story_dir(story_dir)
        # Load t2v_generation config
        t2v_cfg = dict(self.base_cfg.get("t2v_generation") or {})
        if not t2v_cfg:
            raise RuntimeError("t2v_generation config missing in mm_story_agent.yaml")
        # Merge model config
        merged_cfg = load_model_for_agent(t2v_cfg, 'video')
        agent = init_tool_instance({"tool": t2v_cfg["tool"], "cfg": merged_cfg})
        params = dict(t2v_cfg.get("params") or {})
        params["story_dir"] = str(Path(story_dir))
        params["prompt"] = prompt or ""
        if overrides:
            params.update(overrides)
        return agent.call(params)
