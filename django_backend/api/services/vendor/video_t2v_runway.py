from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Any
import logging
import traceback

import cv2  # opencv-python-headless
import numpy as np
import requests
import base64

from runwayml import RunwayML
from runwayml import TaskFailedError as RunwayTaskFailedError
from runwayml import BadRequestError as RunwayBadRequestError

from .base import register_tool

logger = logging.getLogger("django")


def _suggest_from_bad_request_text(txt: str) -> dict:
    """Parse BadRequestError text to extract suggested values for known fields.
    Returns a dict like {"duration": 8, "ratio": "1280:720"} if found.
    """
    out = {}
    if not txt:
        return out
    import re as _re
    # duration values: e.g., "'path': ['duration'] ... 'values': [8]"
    m = _re.search(r"path[^\]]*\['duration'\][\s\S]*?values[^\[]*\[\s*(\d+)\s*\]", txt)
    if m:
        try:
            out["duration"] = int(m.group(1))
        except Exception:
            pass
    # ratio values: e.g., "'path': ['ratio'] ... 'values': ['1920:1080']"
    m2 = _re.search(r"path[^\]]*\['ratio'\][\s\S]*?values[^\[]*\[\s*'([^']+)'\s*\]", txt)
    if m2:
        out["ratio"] = m2.group(1)
    return out


def _sanitize_url(u: str) -> str:
    if not isinstance(u, str):
        return u
    s = u.strip().strip("\"')")
    # strip trailing punctuation often introduced by repr/lists
    while s and s[-1] in ",]}'\")":
        s = s[:-1]
    # also strip URL-encoded right bracket at the end (e.g., %5D or %5D,)
    if s.endswith('%5D'):
        s = s[:-3]
    if s.endswith('%5D,'):
        s = s[:-4]
    return s


def _get_proxies() -> dict | None:
    # Use environment proxies if present; settings.py already mirrors ALL_PROXY
    http = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    allp = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
    proxies = {}
    if http:
        proxies["http"] = http
    if https:
        proxies["https"] = https
    if allp:
        proxies.setdefault("http", allp)
        proxies.setdefault("https", allp)
    return proxies or None


@register_tool("runway_t2v")
class RunwayT2VAgent:
    """
    Text-to-Video agent for Runway (GEN-3 or similar).

    - When params['use_mock'] is True, generates a placeholder mp4 locally for development.
    - Otherwise, outlines the Runway REST API workflow (create job + poll + download).
      The actual endpoint specifics can vary by plan/version; adjust accordingly.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg or {}
        # Expect api_key via env RUNWAYML_API_SECRET (preferred) or RUNWAY_API_KEY (fallback)
        self.api_key = (
            self.cfg.get("api_key")
            or os.getenv("RUNWAYML_API_SECRET")
            or os.getenv("RUNWAY_API_KEY")
        )
        # Ensure SDK sees the secret if only RUNWAY_API_KEY was provided
        if self.api_key and not os.getenv("RUNWAYML_API_SECRET"):
            os.environ["RUNWAYML_API_SECRET"] = self.api_key
        self.api_base = self.cfg.get("api_base", "https://api.runwayml.com/v1")
        logger.info("[RunwayT2V] init api_base=%s has_api_key=%s model_name=%s", self.api_base, bool(self.api_key), self.cfg.get("model_name"))

    def _mock_generate(self, out_path: Path, width: int, height: int, fps: int, duration: float, text: str = "Mock T2V") -> str:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, float(fps), (int(width), int(height)))
        total_frames = max(1, int(round(fps * max(0.1, float(duration)))))
        bg = np.zeros((int(height), int(width), 3), dtype=np.uint8)
        for i in range(total_frames):
            frame = bg.copy()
            # simple moving rectangle to indicate motion
            x = int((i / total_frames) * (width - 50))
            y = int(0.3 * height)
            cv2.rectangle(frame, (x, y), (x + 50, y + 50), (0, 180, 255), -1)
            # overlay text
            cv2.putText(frame, text, (20, int(0.85 * height)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            writer.write(frame)
        writer.release()
        return str(out_path)

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {"Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _create_job(self, prompt: str, width: int, height: int, fps: int, duration: float) -> str:
        """
        Create a Runway video generation job and return job_id.
        NOTE: Endpoint and payload may differ; adjust per Runway's latest API.
        """
        url = f"{self.api_base}/videos"  # placeholder endpoint
        payload = {
            "prompt": prompt,
            "width": int(width),
            "height": int(height),
            "fps": int(fps),
            "duration": float(duration),
            # other optional parameters can be added here
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"Runway create job failed: {resp.status_code} {resp.text}")
        data = resp.json()
        # Assume response contains an id
        return data.get("id") or data.get("job_id") or ""

    def _poll_job(self, job_id: str, timeout_s: float = 600.0, interval_s: float = 5.0) -> Dict[str, Any]:
        url = f"{self.api_base}/videos/{job_id}"  # placeholder endpoint
        start = time.time()
        while True:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            if resp.status_code >= 300:
                raise RuntimeError(f"Runway poll job failed: {resp.status_code} {resp.text}")
            data = resp.json()
            status = str(data.get("status") or "").lower()
            if status in ("succeeded", "completed", "finished"):
                return data
            if status in ("failed", "error"):
                raise RuntimeError(f"Runway job failed: {data}")
            if time.time() - start > timeout_s:
                raise TimeoutError("Runway job polling timeout")
            time.sleep(interval_s)

    def _download_video(self, url: str, out_path: Path) -> str:
        clean_url = _sanitize_url(url)
        proxies = _get_proxies()
        logger.info("[RunwayT2V] downloading url (sanitized)=%s proxies=%s", clean_url, bool(proxies))
        with requests.get(clean_url, stream=True, timeout=120, proxies=proxies) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return str(out_path)

    def _path_to_data_uri(self, image_path: str) -> str:
        p = Path(image_path)
        if not p.is_file():
            raise FileNotFoundError(f"prompt_image_path not found: {image_path}")
        mime = "image/png"
        suf = p.suffix.lower()
        if suf in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif suf == ".webp":
            mime = "image/webp"
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        logger.info("[RunwayT2V] read prompt image: path=%s size=%d mime=%s", str(p), len(data), mime)
        return f"data:{mime};base64,{b64}"

    def _extract_video_url(self, task_obj: Any) -> str | None:
        # Try common shapes for SDK task output
        try:
            d = task_obj if isinstance(task_obj, dict) else getattr(task_obj, "__dict__", {})
        except Exception:
            d = {}
        # direct keys
        for k in ("video", "video_url", "output_url"):
            v = d.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        # nested outputs
        for k in ("output", "outputs", "result", "results", "assets"):
            v = d.get(k)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        for kk in ("uri", "url", "video", "video_url"):
                            u = item.get(kk)
                            if isinstance(u, str) and u.startswith("http"):
                                return u
            if isinstance(v, dict):
                for kk in ("uri", "url", "video", "video_url"):
                    u = v.get(kk)
                    if isinstance(u, str) and u.startswith("http"):
                        return u
        # Some SDKs expose .output as attribute list
        out_attr = getattr(task_obj, "output", None)
        if isinstance(out_attr, list):
            for item in out_attr:
                if isinstance(item, dict):
                    u = item.get("uri") or item.get("url")
                    if isinstance(u, str) and u.startswith("http"):
                        return u
        return None

    def call(self, params: Dict[str, Any]) -> str:
        story_dir = Path(params.get("story_dir", ".")).resolve()
        story_dir.mkdir(parents=True, exist_ok=True)
        out_path = story_dir / "output.mp4"

        prompt = params.get("prompt") or params.get("text") or ""
        width = int(params.get("width", 1280))
        height = int(params.get("height", 720))
        fps = int(params.get("fps", 24))
        duration = float(params.get("duration", 4))
        use_mock = bool(params.get("use_mock", False))
        ratio = params.get("ratio")
        if not ratio and width and height:
            ratio = f"{width}:{height}"
        # model can be passed in params or from cfg.model_name
        model_name = params.get("model") or self.cfg.get("model_name") or "gen4_turbo"

        # Log sanitized parameter summary
        logger.info(
            "[RunwayT2V] call story_dir=%s out=%s model=%s ratio=%s wh=%dx%d fps=%s dur=%.2f use_mock=%s prompt_len=%d img_path=%s img_uri=%s",
            str(story_dir), str(out_path), model_name, ratio, width, height, fps, duration, use_mock,
            len(prompt or ""), bool(params.get("prompt_image_path")), bool(params.get("prompt_image_data_uri")),
        )

        if use_mock:
            logger.info("[RunwayT2V] using mock generator")
            return self._mock_generate(out_path, width, height, fps, duration, text="Mock T2V")

        if not self.api_key:
            logger.error("[RunwayT2V] missing RUNWAYML_API_SECRET (or RUNWAY_API_KEY fallback); aborting")
            raise RuntimeError("RUNWAYML_API_SECRET not configured; set use_mock=true for local testing")

        start_ts = time.time()
        # Prefer SDK client (explicit api_key for robustness)
        client = RunwayML(api_key=self.api_key)

        # Determine if image-to-video or text-to-video
        prompt_image_data_uri = params.get("prompt_image_data_uri")
        if not prompt_image_data_uri and params.get("prompt_image_path"):
            prompt_image_data_uri = self._path_to_data_uri(params["prompt_image_path"])

        try:
            if prompt_image_data_uri:
                logger.info("[RunwayT2V] SDK.image_to_video.create model=%s ratio=%s duration=%.2f", model_name, ratio, duration)
                task = client.image_to_video.create(
                    model=model_name,
                    prompt_image=prompt_image_data_uri,
                    prompt_text=prompt,
                    ratio=ratio,
                    duration=int(round(duration)),
                ).wait_for_task_output()
            else:
                logger.info("[RunwayT2V] SDK.text_to_video.create model=%s ratio=%s duration=%.2f", model_name, ratio, duration)
                task = client.text_to_video.create(
                    model=model_name,
                    prompt_text=prompt,
                    ratio=ratio,
                    duration=int(round(duration)),
                ).wait_for_task_output()
        except RunwayTaskFailedError as e:
            logger.error("[RunwayT2V] SDK TaskFailedError: %s", getattr(e, 'task_details', str(e)))
            logger.debug("[RunwayT2V] traceback:\n%s", traceback.format_exc())
            raise RuntimeError(f"Runway generation failed: {getattr(e, 'task_details', str(e))}")
        except Exception:
            logger.error("[RunwayT2V] SDK unexpected exception")
            logger.debug("[RunwayT2V] traceback:\n%s", traceback.format_exc())
            raise

        elapsed = time.time() - start_ts
        logger.info("[RunwayT2V] SDK task completed in %.2fs", elapsed)

        # Extract video URL and download
        video_url = self._extract_video_url(task)
        if video_url:
            logger.info("[RunwayT2V] extracted video url: %s", video_url)
        if not video_url:
            # Fallback: try string repr to locate URL
            s = str(task)
            import re as _re
            m = _re.search(r"https?://\S+", s)
            if m:
                video_url = m.group(0)
                logger.info("[RunwayT2V] url from repr: %s", video_url)
        if not video_url:
            logger.error("[RunwayT2V] cannot extract video URL; task=%s", str(task)[:500])
            raise RuntimeError(f"Cannot extract video URL from task output: {task}")

        # Download with progress
        try:
            path = self._download_video(video_url, out_path)
            size = Path(path).stat().st_size if Path(path).exists() else -1
            logger.info("[RunwayT2V] downloaded video to %s size=%d bytes", path, size)
            return path
        except Exception:
            logger.error("[RunwayT2V] download failed: %s", video_url)
            logger.debug("[RunwayT2V] traceback:\n%s", traceback.format_exc())
            raise
