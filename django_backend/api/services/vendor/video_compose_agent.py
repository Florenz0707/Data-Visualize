import platform
import re
import signal
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

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

    @classmethod
    def adjust_caption_config(cls, width, height, existing: dict | None = None):
        existing = dict(existing or {})
        area_height_default = int(height * 0.06)
        fontsize_default = int((width + height) / 2 * 0.025)
        if "area_height" not in existing:
            existing["area_height"] = area_height_default
        if "fontsize" not in existing:
            existing["fontsize"] = fontsize_default
        return existing

    @classmethod
    def _gather_assets(cls, story_dir: Path):
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

        import json

        story_dir = Path(params.get("story_dir", ".")).resolve()
        output = story_dir / "output.mp4"
        cfg_params = dict((self.cfg.get("params") or {}))
        fps = int(cfg_params.get("fps", 24))
        size = cfg_params.get("size") or [1280, 720]
        width, height = int(size[0]), int(size[1])
        default_image_duration = float(cfg_params.get("image_duration", 3.0))
        # Environment diagnostics
        try:
            import moviepy as _mp
            logger.info("[VideoCompose] moviepy.__version__=%s", getattr(_mp, "__version__", "unknown"))
        except Exception:
            logger.info("[VideoCompose] moviepy version unknown")
        try:
            import imageio_ffmpeg
            logger.info("[VideoCompose] ffmpeg_exe=%s", imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:
            logger.info("[VideoCompose] ffmpeg_exe unknown (imageio_ffmpeg not available)")
        logger.info("[VideoCompose] target=%dx%d fps=%d", width, height, fps)

        images, audios = self._gather_assets(story_dir)
        logger.info("[VideoCompose] Found %d images and %d audios", len(images), len(audios))
        if images:
            logger.info("[VideoCompose] Sample images: %s", ", ".join(str(p.name) for p in images[:5]))
        if audios:
            logger.info("[VideoCompose] Sample audios: %s", ", ".join(str(p.name) for p in audios[:5]))
        # Enforce presence of images; fail fast instead of producing black screen only
        if not images:
            raise RuntimeError("No images found for composing video.")
        # Determine per-image audio grouping strictly from segmented_pages
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
        if not isinstance(seg_pages, list) or len(seg_pages) != len(images):
            raise RuntimeError(
                "segmented_pages missing or length mismatch with images. Cannot map audio segments per page.")
        seg_counts = [len(page) for page in seg_pages]
        if sum(seg_counts) != len(audios):
            raise RuntimeError(f"Audio/page mismatch: required={sum(seg_counts)}, provided={len(audios)}.")
        logger.info("[VideoCompose] Per-image segment counts: %s", ",".join(str(x) for x in seg_counts))

        # FFmpeg-only pipeline start
        import shutil
        ffmpeg_bin = None
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = "ffmpeg"

        def run_ffmpeg(cmd, desc):
            logger.info("[VideoCompose] ffmpeg %s: %s", desc, " ".join(cmd))
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                logger.error("[VideoCompose] ffmpeg %s failed: rc=%s stderr=%s", desc, p.returncode, p.stderr[-1000:])
                raise RuntimeError(f"ffmpeg {desc} failed: rc={p.returncode}")
            else:
                logger.info("[VideoCompose] ffmpeg %s ok", desc)

        temp_dir = tempfile.mkdtemp(prefix="ffmpeg_compose_")
        logger.info("[VideoCompose] temp_dir=%s", temp_dir)
        try:
            # Build per-page videos
            audio_cursor = 0
            page_videos = []
            for idx, img_path in enumerate(images):
                k = seg_counts[idx]
                aud_list_path = Path(temp_dir) / f"aud_list_{idx + 1}.txt"
                with open(aud_list_path, "w", encoding="utf-8") as f:
                    for j in range(k):
                        apath = audios[audio_cursor + j]
                        f.write(f"file '{Path(apath).as_posix()}'\n")
                audio_cursor += k
                merged_wav = Path(temp_dir) / f"merged_audio_{idx + 1}.wav"
                run_ffmpeg(
                    [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(aud_list_path), "-c:a", "pcm_s16le",
                     str(merged_wav)],
                    f"concat_audio_page{idx + 1}")

                page_mp4 = Path(temp_dir) / f"page_{idx + 1}.mp4"
                run_ffmpeg([ffmpeg_bin, "-y",
                            "-loop", "1", "-i", str(img_path),
                            "-i", str(merged_wav),
                            "-vf",
                            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", str(fps),
                            "-c:a", "aac", "-shortest", str(page_mp4)],
                           f"make_page_video_{idx + 1}")
                page_videos.append(page_mp4)

            # Concat all pages
            concat_list = Path(temp_dir) / "list.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for p in page_videos:
                    f.write(f"file '{p.as_posix()}'\n")
            run_ffmpeg(
                [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output)],
                "concat_pages")

            logger.info("[VideoCompose] ffmpeg pipeline completed -> %s", output)
            return str(output)
        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
