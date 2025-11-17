import platform
import re
import signal
from contextlib import contextmanager
from pathlib import Path

from moviepy import vfx

slide_in = vfx.SlideIn
slide_out = vfx.SlideOut

import logging
logger = logging.getLogger(__name__)
from .base import register_tool


# (The rest of this file is a vendored copy adapted to use local imports only.)
# For brevity, the implementation mirrors the original with no functional changes
# except imports. See original for detailed comments.

@contextmanager
def timeout_context(seconds):
    if platform.system() == 'Windows':
        import threading
        timeout_occurred = threading.Event()

        def timeout_handler():
            timeout_occurred.set()

        timer = threading.Timer(seconds, timeout_handler)
        timer.start()
        try:
            yield timeout_occurred
        finally:
            timer.cancel()
            if timeout_occurred.is_set():
                raise TimeoutError(f"Operation timed out after {seconds} seconds")
    else:
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Operation timed out after {seconds} seconds")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


# The following functions/classes are identical to the original vendor source
# except for relative imports above.
# To minimize length, we include only the public API used by services.workflow:
# - split_text_for_speech
# - SlideshowVideoComposeAgent (with .call)


def split_keep_separator(text, separator):
    pattern = f'([{re.escape(separator)}])'
    pieces = re.split(pattern, text)
    return pieces


def split_text_for_speech(text, max_chars: int = 60):
    """
    Split text into segments by character length.
    Strategy:
    1) Respect sentence boundaries first (., !, ?) while protecting common abbreviations.
    2) If a sentence still exceeds max_chars, try split by ; : , keeping separators.
    3) Still too long: perform hard character-chunking (<= max_chars), prefer to break on spaces.
    """
    import re

    if not text or not text.strip():
        return []

    common_abbreviations = [
        'Dr', 'Mr', 'Mrs', 'Ms', 'Prof', 'Sr', 'Jr', 'Ltd', 'Inc', 'Corp', 'Co',
        'St', 'Ave', 'Blvd', 'Rd', 'etc', 'vs', 'e.g', 'i.e', 'a.m', 'p.m',
        'U.S', 'U.K', 'U.N', 'Ph.D', 'M.D', 'B.A', 'M.A', 'Ph.D',
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun',
        'No', 'Nos', 'Vol', 'Vols', 'pp', 'pgs', 'ch', 'chs', 'fig', 'figs', 'ref', 'refs',
        'Gen', 'Lt', 'Col', 'Maj', 'Capt', 'Sgt', 'Cpl', 'Pvt',
        'Rev', 'Hon', 'Rt', 'Gov', 'Sen', 'Rep', 'Pres', 'Vice', 'Adm',
        'Assoc', 'Asst', 'Dir', 'Mgr', 'Exec', 'Admin',
        'Dept', 'Div', 'Sect', 'Sub', 'Subj',
        'Tech', 'Eng', 'Sci', 'Math', 'Econ', 'Psych', 'Sociol',
        'Univ', 'Coll', 'Inst', 'Acad', 'Sch',
        'Intl', 'Natl', 'Fed', 'Reg', 'Dist', 'Mun',
        'Min', 'Max', 'Avg', 'Std', 'Var', 'Dev',
        'Est', 'Aprox', 'Circa', 'ca'
    ]

    # Protect abbreviations like "Dr." to avoid sentence split on the period
    protected_text = text
    abbreviation_markers = {}
    for i, abbr in enumerate(common_abbreviations):
        pattern = re.escape(abbr) + r'\.'
        if re.search(pattern, protected_text):
            marker = f"__ABBR_{i}__"
            abbreviation_markers[marker] = abbr + '.'
            protected_text = re.sub(pattern, marker, protected_text)

    # Split into sentences (keep punctuation)
    sentences = re.split(r'([.!?]+)', protected_text)
    complete_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            sentence = (sentences[i] + sentences[i + 1]).strip()
            if sentence:
                complete_sentences.append(sentence)
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        complete_sentences.append(sentences[-1].strip())
    if not complete_sentences:
        complete_sentences = [protected_text.strip()]

    # Restore abbreviations
    for i, sentence in enumerate(complete_sentences):
        for marker, original in abbreviation_markers.items():
            sentence = sentence.replace(marker, original)
        complete_sentences[i] = sentence

    def chunk_by_chars(s: str, limit: int) -> list[str]:
        # Prefer breaking on spaces, but ensure progress even if a single token is too long
        out = []
        cur = s.strip()
        while cur:
            if len(cur) <= limit:
                out.append(cur)
                break
            # find last space within limit
            cut = cur.rfind(' ', 0, limit + 1)
            if cut == -1:
                # no space; hard cut
                out.append(cur[:limit])
                cur = cur[limit:].lstrip()
            else:
                out.append(cur[:cut])
                cur = cur[cut + 1:].lstrip()
        return out

    results = []
    for sent in complete_sentences:
        if len(sent) <= max_chars:
            results.append(sent)
            continue
        # try split by ; : , while keeping separators with the previous part
        protected_sent = sent
        sub_parts = re.split(r'([;:,])', protected_sent)
        merged = []
        for i in range(0, len(sub_parts), 2):
            part = sub_parts[i].strip()
            sep = sub_parts[i + 1] if i + 1 < len(sub_parts) else ''
            if part:
                merged.append((part + sep).strip())
        if not merged:
            merged = [sent]
        for part in merged:
            if len(part) <= max_chars:
                results.append(part)
            else:
                results.extend(chunk_by_chars(part, max_chars))

    return results


@register_tool("slideshow_video_compose")
class SlideshowVideoComposeAgent:
    def __init__(self, cfg) -> None:
        self.cfg = cfg

    def adjust_caption_config(self, width, height, existing: dict | None = None):
        existing = dict(existing or {})
        area_height_default = int(height * 0.06)
        fontsize_default = int((width + height) / 2 * 0.025)
        if "area_height" not in existing:
            existing["area_height"] = area_height_default
        if "fontsize" not in existing:
            existing["fontsize"] = fontsize_default
        return existing

    def _gather_assets(self, story_dir: Path):
        img_dir = (story_dir / "image")
        images = []
        # Gather common image extensions and naming patterns
        for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp", "p*.png", "p*.jpg", "p*.jpeg", "p*.webp"]:
            images.extend(img_dir.glob(pattern))
        # De-duplicate and sort by name
        images = sorted({p for p in images}, key=lambda p: p.name)

        aud_dir = (story_dir / "speech")
        audios = []
        for pattern in ["*.wav", "s*.wav", "*.mp3", "s*.mp3"]:
            audios.extend(aud_dir.glob(pattern))
        audios = sorted({p for p in audios}, key=lambda p: p.name)
        return images, audios

    def call(self, params):
        """Compose a simple slideshow video.
        Strategy:
        - If both images and audios exist: pair by index, duration = audio duration.
        - If only images: each image gets default duration (cfg.params.image_duration or 3s).
        - If only audios: render a blank background clip with audio (fallback), duration = audio duration.
        Output: story_dir/output.mp4
        """

        from moviepy import (ImageClip, AudioFileClip, ColorClip, CompositeVideoClip,
                             concatenate_videoclips, concatenate_audioclips)
        import json

        story_dir = Path(params.get("story_dir", ".")).resolve()
        output = story_dir / "output.mp4"
        cfg_params = dict((self.cfg.get("params") or {}))
        fps = int(cfg_params.get("fps", 24))
        size = cfg_params.get("size") or [1280, 720]
        width, height = int(size[0]), int(size[1])
        default_image_duration = float(cfg_params.get("image_duration", 3.0))

        images, audios = self._gather_assets(story_dir)
        logger.info("[VideoCompose] Found %d images and %d audios", len(images), len(audios))
        if images:
            logger.info("[VideoCompose] Sample images: %s", ", ".join(str(p.name) for p in images[:5]))
        if audios:
            logger.info("[VideoCompose] Sample audios: %s", ", ".join(str(p.name) for p in audios[:5]))
        # Enforce presence of images; fail fast instead of producing black screen only
        if not images:
            raise RuntimeError("No images found for composing video.")
        # Determine per-image audio grouping using segmented_pages if available
        seg_pages = params.get("segmented_pages")
        if not seg_pages:
            # try load from script_data.json
            script_path = story_dir / "script_data.json"
            if script_path.exists():
                try:
                    data = json.loads(script_path.read_text(encoding="utf-8"))
                    seg_pages = data.get("segmented_pages")
                except Exception:
                    seg_pages = None
        seg_counts = []
        if isinstance(seg_pages, list):
            try:
                seg_counts = [len(page) for page in seg_pages]
            except Exception:
                seg_counts = []
        if seg_counts and len(seg_counts) != len(images):
            logger.info("[VideoCompose] segmented_pages length (%d) != images (%d). Will truncate/pad with 0.", len(seg_counts), len(images))
            # Pad/truncate to images length
            if len(seg_counts) < len(images):
                seg_counts = seg_counts + [0] * (len(images) - len(seg_counts))
            else:
                seg_counts = seg_counts[:len(images)]
        elif not seg_counts:
            # Default: assume 1 audio per image if audios exist, otherwise 0
            if audios:
                seg_counts = [max(1, len(audios) // max(1, len(images)))] * len(images)
            else:
                seg_counts = [0] * len(images)
        logger.info("[VideoCompose] Per-image segment counts: %s", ",".join(str(x) for x in seg_counts))

        clips = []

        def set_duration_compat(clip, dur: float):
            try:
                return clip.set_duration(dur)
            except Exception:
                return clip.with_duration(dur)

        def set_audio_compat(clip, audio):
            try:
                return clip.set_audio(audio)
            except Exception:
                return clip.with_audio(audio)

        def resize_width_compat(img_clip, target_w: int):
            # Prefer vfx.resize if available
            return img_clip.resize(width=target_w)  # older API


        def load_image_clip(path: Path):
            """Load image robustly using PIL to avoid format/alpha issues, return ImageClip."""
            import numpy as _np
            try:
                from PIL import Image as _Image
            except Exception:
                # fall back to MoviePy loader
                return ImageClip(str(path))
            try:
                im = _Image.open(str(path))
                mode_before, size_before = im.mode, im.size
                # Convert to RGB to avoid alpha-related black frames
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                logger.info("[VideoCompose] Loaded image %s mode=%s->%s size=%s", path.name, mode_before, im.mode, size_before)
                arr = _np.array(im)
                clip = ImageClip(arr)
                return clip
            except Exception:
                logger.exception("[VideoCompose] Failed to load image via PIL, fallback to ImageClip: %s", path)
                # last resort
                return ImageClip(str(path))

        def resize_to_fit(img_clip, target_w: int, target_h: int):
            try:
                iw, ih = img_clip.size
            except Exception:
                return img_clip
            try:
                scale = min(float(target_w) / float(iw), float(target_h) / float(ih))
                new_w = max(1, int(iw * scale))
                # keep aspect ratio by width, height will be adjusted by on_color/Composite
                try:
                    from moviepy import vfx as _vfx  # type: ignore
                    return img_clip.fx(_vfx.resize, width=new_w)
                except Exception:
                    try:
                        return img_clip.resize(width=new_w)
                    except Exception:
                        return img_clip
            except Exception:
                return img_clip

        def center_on_bg(img_clip, duration: float):
            dur = max(0.1, float(duration))
            bg = ColorClip(size=(width, height), color=(0, 0, 0))
            bg = set_duration_compat(bg, dur)
            ic = resize_to_fit(img_clip, width, height)
            try:
                ic = set_duration_compat(ic, dur)
            except Exception:
                pass
            try:
                comp = CompositeVideoClip([bg, ic.set_position('center')], size=(width, height))
                comp = set_duration_compat(comp, dur)
            except Exception:
                comp = bg
            return comp

        try:
            if images or audios:
                if images and audios:
                    # Group multiple short audios (segments) under each image according to seg_counts
                    # Strict check: total audios must equal required segments
                    required = sum(int(seg_counts[i] if i < len(seg_counts) else 1) for i in range(len(images)))
                    if len(audios) != required:
                        raise RuntimeError(f"Audio/page mismatch: required={required}, provided={len(audios)}. Ensure segmented_pages matches generated audios.")
                    ai = 0  # audio index cursor
                    for idx_img, img_path in enumerate(images):
                        k = seg_counts[idx_img] if idx_img < len(seg_counts) else 1
                        group_audios = []
                        total_dur = 0.0
                        for _ in range(k):
                            apath = audios[ai]
                            try:
                                aclip = AudioFileClip(str(apath))
                                group_audios.append(aclip)
                                total_dur += float(getattr(aclip, 'duration', 0.0) or 0.0)
                            except Exception:
                                logger.exception("[VideoCompose] failed to load audio: %s", apath)
                                raise
                            ai += 1
                        # Build per-page clip with merged audio
                        img_clip = load_image_clip(Path(img_path))
                        try:
                            merged_audio = concatenate_audioclips(group_audios)
                        except Exception:
                            # Fallback: use first audio only but keep strictness by raising
                            logger.exception("[VideoCompose] concatenate_audioclips failed for IMG=%s", Path(img_path).name)
                            raise
                        dur = float(getattr(merged_audio, 'duration', 0.0) or total_dur or default_image_duration)
                        vclip = center_on_bg(img_clip, dur)
                        vclip = set_audio_compat(vclip, merged_audio)
                        try:
                            vclip = vclip.set_fps(fps)
                        except Exception:
                            pass
                        logger.info("[VideoCompose] IMG=%s segments=%d total_dur=%.3fs (audios %d..%d)", Path(img_path).name, len(group_audios), dur, max(1, ai-len(group_audios)), ai)
                        clips.append(vclip)
                elif images:
                    for img_path in images:
                        img_clip = ImageClip(str(img_path))
                        vclip = center_on_bg(img_clip, default_image_duration)
                        clips.append(vclip)
                elif audios:
                    for aud_path in audios:
                        aclip = AudioFileClip(str(aud_path))
                        bg = ColorClip(size=(width, height), color=(0, 0, 0))
                        vclip = set_duration_compat(bg, aclip.duration)
                        vclip = set_audio_compat(vclip, aclip)
                        clips.append(vclip)
            else:
                # nothing to compose; raise meaningful error
                raise RuntimeError("No images or audios found to compose video.")

            final = concatenate_videoclips(clips, method="compose")
            # Force final canvas size to avoid backend-specific black frames
            try:
                final = CompositeVideoClip([final], size=(width, height))
            except Exception:
                pass
            # write the file
            # Compatibility: older MoviePy versions may not support verbose/logger/threads/temp_audiofile
            _kwargs = dict(
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=str(story_dir / "_temp_audio.m4a"),
                remove_temp=True,
                threads=cfg_params.get("threads", 2),
            )
            # Prefer widely compatible pixel format to avoid playback black screens
            _kwargs["ffmpeg_params"] = ["-pix_fmt", "yuv420p"]
            def _try_write(**extra):
                try:
                    kw = dict(_kwargs)
                    kw.update(extra)
                    final.write_videofile(str(output), **kw)
                    return True
                except TypeError:
                    return False
            # Try with all kwargs plus quiet flags
            if not _try_write(verbose=False, logger=None):
                # Drop verbose/logger
                if not _try_write():
                    # Drop temp_audiofile/threads/ffmpeg_params for maximal compatibility
                    _kwargs.pop("temp_audiofile", None)
                    _kwargs.pop("threads", None)
                    _kwargs.pop("ffmpeg_params", None)
                    final.write_videofile(str(output), **_kwargs)
            try:
                final.close()
            except Exception:
                pass
            return str(output)
        finally:
            # best-effort close clips
            try:
                for c in clips:
                    try:
                        ac = getattr(c, 'audio', None)
                        if ac is not None:
                            ac.close()
                    except Exception:
                        pass
                    try:
                        c.close()
                    except Exception:
                        pass
            except Exception:
                pass
