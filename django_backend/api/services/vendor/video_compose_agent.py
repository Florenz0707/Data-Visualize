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


# ---- Text split utility (also imported by other modules) ----
def split_text_for_speech(text: str, max_chars: int = 60):
    import re as _re
    if not text or not text.strip():
        return []
    common_abbreviations = [
        'Dr', 'Mr', 'Mrs', 'Ms', 'Prof', 'Sr', 'Jr', 'Ltd', 'Inc', 'Corp', 'Co',
        'St', 'Ave', 'Blvd', 'Rd', 'etc', 'vs', 'e.g', 'i.e', 'a.m', 'p.m',
        'U.S', 'U.K', 'U.N', 'Ph.D', 'M.D', 'B.A', 'M.A', 'Ph.D',
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun',
        'No', 'Nos', 'Vol', 'Vols', 'pp', 'pgs', 'ch', 'chs', 'fig', 'figs', 'ref', 'refs',
        'Gen', 'Lt', 'Col', 'Maj', 'Capt', 'Sgt', 'Cpl', 'Pvt', 'Rev', 'Hon', 'Rt', 'Gov', 'Sen',
        'Rep', 'Pres', 'Vice', 'Adm', 'Assoc', 'Asst', 'Dir', 'Mgr', 'Exec', 'Admin',
        'Dept', 'Div', 'Sect', 'Sub', 'Subj', 'Tech', 'Eng', 'Sci', 'Math', 'Econ', 'Psych', 'Sociol',
        'Univ', 'Coll', 'Inst', 'Acad', 'Sch', 'Intl', 'Natl', 'Fed', 'Reg', 'Dist', 'Mun',
        'Min', 'Max', 'Avg', 'Std', 'Var', 'Dev', 'Est', 'Aprox', 'Circa', 'ca']
    protected_text = text
    for i, abbr in enumerate(common_abbreviations):
        pattern = _re.escape(abbr) + r'\.'
        protected_text = _re.sub(pattern, f"__ABBR_{i}__", protected_text)
    sentences = _re.split(r'([.!?]+)', protected_text)
    complete = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            s = (sentences[i] + sentences[i + 1]).strip()
            if s:
                complete.append(s)
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        complete.append(sentences[-1].strip())
    if not complete:
        complete = [protected_text.strip()]
    # restore abbreviations
    for i, s in enumerate(complete):
        s2 = s
        for j, abbr in enumerate(common_abbreviations):
            s2 = s2.replace(f"__ABBR_{j}__", abbr + ".")
        complete[i] = s2

    def chunk_by_chars(s: str, limit: int):
        out, cur = [], s.strip()
        while cur:
            if len(cur) <= limit:
                out.append(cur)
                break
            cut = cur.rfind(' ', 0, limit + 1)
            if cut == -1:
                out.append(cur[:limit]); cur = cur[limit:].lstrip()
            else:
                out.append(cur[:cut]); cur = cur[cut + 1:].lstrip()
        return out

    results = []
    for sent in complete:
        if len(sent) <= max_chars:
            results.append(sent); continue
        parts = _re.split(r'([;:,])', sent)
        merged = []
        for i in range(0, len(parts), 2):
            part = parts[i].strip()
            sep = parts[i + 1] if i + 1 < len(parts) else ''
            if part:
                merged.append((part + sep).strip())
        if not merged:
            merged = [sent]
        for part in merged:
            if len(part) <= max_chars: results.append(part)
            else: results.extend(chunk_by_chars(part, max_chars))
    return results


def _format_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _is_font_path(val: str) -> bool:
    try:
        p = Path(val)
        return p.is_file()
    except Exception:
        return False

_css_named = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "gray": (128, 128, 128),
}

def _to_ass_color(val: str, default: str = "&H00FFFFFF") -> str:
    if not val:
        return default
    s = str(val).strip()
    if s.startswith("&H") or s.startswith("&h"):
        return s.upper()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 3:
            r = int(s[0] * 2, 16); g = int(s[1] * 2, 16); b = int(s[2] * 2, 16)
        elif len(s) == 6:
            r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16)
        else:
            return default
        return f"&H00{b:02X}{g:02X}{r:02X}"
    rgb = _css_named.get(s.lower())
    if rgb is not None:
        r, g, b = rgb
        return f"&H00{b:02X}{g:02X}{r:02X}"
    return default


@register_tool("slideshow_video_compose")
class SlideshowVideoComposeAgent:
    def __init__(self, cfg) -> None:
        self.cfg = cfg

    @staticmethod
    def _numeric_key(stem: str, prefix: str) -> int:
        m = re.search(rf"{prefix}(\d+)$", stem, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 10**9
        return 10**9

    @staticmethod
    def _numeric_key_pair(stem: str, prefix: str) -> tuple:
        m = re.search(rf"{prefix}(\d+)_(\d+)$", stem, flags=re.IGNORECASE)
        if m:
            try:
                return (int(m.group(1)), int(m.group(2)))
            except Exception:
                return (10**9, 10**9)
        return (10**9, 10**9)

    def call(self, params):
        import json
        story_dir = Path(params.get("story_dir", ".")).resolve()
        output = story_dir / "output.mp4"

        # Merge base cfg params with call-time params (call overrides base)
        base_params = (self.cfg.get("params") or {})
        call_params = {}
        for k in ("fps", "size", "width", "height", "audio_sample_rate", "audio_codec", "caption"):
            v = params.get(k)
            if v is not None:
                call_params[k] = v
        cfg_params = {**base_params, **call_params}
        if not cfg_params:
            logger.warning("video_compose: cfg_params empty, using defaults")

        # Derive width/height from size or fields
        if cfg_params.get("size"):
            try:
                size = cfg_params.get("size")
                width, height = int(size[0]), int(size[1])
            except Exception:
                width = int(cfg_params.get("width", 1280))
                height = int(cfg_params.get("height", 720))
        else:
            width = int(cfg_params.get("width", 1280))
            height = int(cfg_params.get("height", 720))
        fps = int(cfg_params.get("fps", 24))

        # Caption config: base then call override
        caption_cfg = {}
        caption_cfg.update(base_params.get("caption") or {})
        caption_cfg.update((params.get("caption") or {}))

        enable_captions = bool(caption_cfg.get("enable_captions", True))
        area_height = int(caption_cfg.get("area_height", max(24, int(height * 0.06))))
        font_cfg = caption_cfg.get("font", "Arial")
        try:
            fontsize = int(caption_cfg.get("fontsize", 0) or 0)
        except Exception:
            fontsize = 0
        if fontsize <= 0:
            fontsize = int(max(18, int((width + height) * 0.025)))
        color = _to_ass_color(caption_cfg.get("color", "#FFFFFF"), "&H00FFFFFF")
        stroke_color = _to_ass_color(caption_cfg.get("stroke_color", "#000000"), "&H00000000")
        try:
            outline = float(caption_cfg.get("stroke_width", 1))
        except Exception:
            outline = 1.0
        try:
            shadow = float(caption_cfg.get("shadow", 0))
        except Exception:
            shadow = 0.0
        try:
            alignment = int(caption_cfg.get("alignment", 2))
        except Exception:
            alignment = 2
        try:
            margin_v = int(caption_cfg.get("margin_v", 10))
        except Exception:
            margin_v = 10
        try:
            max_chars_line = int(caption_cfg.get("max_chars_per_line", 0) or 0)
        except Exception:
            max_chars_line = 0

        # Resolve font path if relative
        fontsdir = None
        fontname = str(font_cfg)
        if isinstance(font_cfg, str):
            candidate = Path(font_cfg)
            if not candidate.is_file():
                try:
                    from django.conf import settings as dj_settings
                    base_dir = Path(dj_settings.BASE_DIR)
                    cand2 = (base_dir / font_cfg)
                    if cand2.is_file():
                        candidate = cand2
                except Exception:
                    pass
            if not candidate.is_file():
                cand3 = (story_dir / font_cfg)
                if cand3.is_file():
                    candidate = cand3
            if candidate.is_file():
                fontsdir = candidate.parent
                fontname = candidate.stem

        total_height = height + area_height
        logger.info("[VideoCompose] captions: enable=%s area_height=%d font=%s fontsize=%d color=%s outline=%.2f shadow=%.2f align=%d margin_v=%d fontsdir=%s",
                    enable_captions, area_height, fontname, fontsize, color, outline, shadow, alignment, margin_v, str(fontsdir) if fontsdir else "(system)")

        # Gather assets
        img_dir = story_dir / "image"
        speech_dir = story_dir / "speech"
        images = sorted([p for p in img_dir.glob("p*."+"*") if p.suffix.lower() in {".png",".jpg",".jpeg",".webp"}],
                        key=lambda p: (self._numeric_key(p.stem, 'p'), p.name.lower()))
        audios_global = sorted([p for p in speech_dir.glob("s*."+"*") if p.suffix.lower() in {".wav",".mp3"} and re.match(r"s\d+\.(wav|mp3)$", p.name, re.I)],
                               key=lambda p: (self._numeric_key(p.stem, 's'), p.name.lower()))
        if not images:
            raise RuntimeError("No images found for composing video.")

        # segmented_pages
        seg_pages = params.get("segmented_pages")
        if not seg_pages:
            try:
                data = json.loads((story_dir/"script_data.json").read_text(encoding="utf-8"))
            except Exception:
                data = {}
            seg_pages = data.get("segmented_pages")
            if not isinstance(seg_pages, list):
                pages = data.get("pages")
                if isinstance(pages, list):
                    tmp=[(pg.get("segments") or []) for pg in pages]
                    if any(len(x)>0 for x in tmp):
                        seg_pages = tmp
        if not isinstance(seg_pages, list) or len(seg_pages) != len(images):
            raise RuntimeError("segmented_pages missing or length mismatch with images.")
        seg_counts = [len(x) for x in seg_pages]

        # Tools
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe(); ffprobe_bin = ffmpeg_bin.replace('ffmpeg','ffprobe')
        except Exception:
            ffmpeg_bin, ffprobe_bin = "ffmpeg","ffprobe"

        def run_ffmpeg(cmd, desc):
            logger.info("[VideoCompose] %s: %s", desc, " ".join(cmd))
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                logger.error("[VideoCompose] %s failed rc=%s stderr_tail=%s", desc, p.returncode, p.stderr[-1000:])
                raise RuntimeError(f"{desc} failed")

        def ffprobe_dur(p: Path) -> float:
            pr = subprocess.run([ffprobe_bin,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if pr.returncode==0:
                try: return float(pr.stdout.strip())
                except Exception: return 0.0
            return 0.0

        def _wrap_text(txt: str) -> str:
            if not max_chars_line or not txt:
                return txt or ""
            if " " not in txt:
                return txt
            words = txt.split(); lines = []; cur = ""
            for w in words:
                if not cur:
                    cur = w
                elif len(cur) + 1 + len(w) <= max_chars_line:
                    cur += " " + w
                else:
                    lines.append(cur); cur = w
            if cur: lines.append(cur)
            return "\\N".join(lines)

        def write_ass(path: Path, lines):
            primary = color; outline_col = stroke_color
            secondary = "&H000000FF"; back = "&H64000000"
            header=[
                "[Script Info]",f"PlayResX: {width}",f"PlayResY: {total_height}","WrapStyle: 2","ScaledBorderAndShadow: yes","",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                f"Style: Default,{fontname},{fontsize},{primary},{secondary},{outline_col},{back},0,0,0,0,100,100,0,0,1,{outline:.2f},{shadow:.2f},{alignment},30,30,{margin_v},1",
                "",
                "[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
            body=[f"Dialogue: 0,{_format_ass_time(st)},{_format_ass_time(et)},Default,,0000,0000,0000,,{_wrap_text(str(txt))}" for st,et,txt in lines]
            path.write_text("\n".join(header+body)+"\n", encoding="utf-8")

        import shutil
        temp_dir = tempfile.mkdtemp(prefix="ffmpeg_compose_")
        logger.info("[VideoCompose] temp_dir=%s", temp_dir)
        try:
            page_videos=[]; audio_global_cursor=0
            for idx, img in enumerate(images):
                page = idx+1; need = seg_counts[idx]
                per_page_files = list((story_dir/"speech").glob(f"s{page}_*.wav")) + list((story_dir/"speech").glob(f"s{page}_*.mp3"))
                if per_page_files:
                    per_page_files = sorted(per_page_files, key=lambda p: self._numeric_key_pair(p.stem, 's'))
                    if len(per_page_files) != need:
                        raise RuntimeError(f"Page {page} audio count mismatch: expected {need}, found {len(per_page_files)}")
                    page_audios = per_page_files
                    logger.info("[VideoCompose] page=%d using per-page naming files=%d", page, len(per_page_files))
                else:
                    if audio_global_cursor+need > len(audios_global):
                        raise RuntimeError(f"Insufficient global audios for page {page}")
                    page_audios = audios_global[audio_global_cursor:audio_global_cursor+need]
                    audio_global_cursor += need
                    logger.info("[VideoCompose] page=%d using global slice need=%d", page, need)
                durs=[ffprobe_dur(p) for p in page_audios]
                t=0.0; lines=[]
                for j,d in enumerate(durs):
                    st=t; et=t+max(0.01,d); t=et
                    lines.append((st,et, seg_pages[idx][j] if j < len(seg_pages[idx]) else ""))
                ass = Path(temp_dir)/f"page_{page}.ass"
                if enable_captions:
                    write_ass(ass, lines)
                    logger.info("[VideoCompose] wrote ASS for page %d -> %s", page, ass)
                list_file = Path(temp_dir)/f"aud_list_{page}.txt"
                with open(list_file,'w',encoding='utf-8') as f:
                    for ap in page_audios: f.write(f"file '{ap.as_posix()}'\n")
                merged = Path(temp_dir)/f"merged_{page}.wav"
                run_ffmpeg([ffmpeg_bin, "-y","-f","concat","-safe","0","-i",str(list_file),"-c:a","pcm_s16le",str(merged)], f"concat_audio_page{page}")
                vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height+area_height}:(ow-iw)/2:0:black"
                if enable_captions:
                    if fontsdir:
                        vf += f",subtitles={ass.as_posix()}:fontsdir={fontsdir.as_posix()}"
                    else:
                        vf += f",subtitles={ass.as_posix()}"
                page_mp4 = Path(temp_dir)/f"page_{page}.mp4"
                run_ffmpeg([ffmpeg_bin, "-y","-loop","1","-i",str(img),"-i",str(merged),"-vf",vf,
                            "-c:v","libx264","-tune","stillimage","-pix_fmt","yuv420p","-r",str(fps),
                            "-c:a","aac","-shortest",str(page_mp4)], f"make_page_video_{page}")
                page_videos.append(page_mp4)
            concat_list = Path(temp_dir)/"list.txt"
            with open(concat_list,'w',encoding='utf-8') as f:
                for p in page_videos: f.write(f"file '{p.as_posix()}'\n")
            run_ffmpeg([ffmpeg_bin,"-y","-f","concat","-safe","0","-i",str(concat_list),"-c","copy",str(output)], "concat_pages")

            # Optional background music mixing
            bgm_path = params.get("bgm_path")
            if bgm_path:
                bgm_file = Path(bgm_path)
                logger.debug(f"bgm_file: {bgm_file}")
                if bgm_file.is_file():
                    suffix = bgm_file.suffix.lower()
                    allowed_exts = {".mp3", ".wav", ".flac"}
                    if suffix not in allowed_exts:
                        logger.warning("[VideoCompose] Unsupported BGM extension '%s'. Supported: %s", suffix, sorted(allowed_exts))
                    else:
                        try:
                            bgm_volume = params.get("bgm_volume", cfg_params.get("bgm_volume", 0.25))
                            try:
                                bgm_volume = float(bgm_volume)
                            except Exception:
                                bgm_volume = 0.25

                            mixed_output = output.with_name(output.stem + "_bgm.mp4")
                            # Loop BGM to match narration length and mix
                            filter_complex = (
                                f"[1:a]volume={bgm_volume},aloop=loop=-1:size=0[a1];"
                                f"[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                            )
                            run_ffmpeg(
                                [
                                    ffmpeg_bin,
                                    "-y",
                                    "-i", str(output),
                                    "-i", str(bgm_file),
                                    "-filter_complex", filter_complex,
                                    "-map", "0:v:0",
                                    "-map", "[aout]",
                                    "-c:v", "copy",
                                    "-c:a", cfg_params.get("audio_codec", "aac"),
                                    "-shortest",
                                    str(mixed_output),
                                ],
                                "mix_bgm",
                            )
                            shutil.move(mixed_output, output)
                            logger.info("[VideoCompose] mixed background music from %s", bgm_file)
                        except Exception as exc:
                            logger.warning("[VideoCompose] failed to mix BGM: %s", exc)
                else:
                    logger.warning("[VideoCompose] bgm_path provided but file missing: %s", bgm_file)

            logger.info("[VideoCompose] done -> %s", output)
            return str(output)
        finally:
            try: shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception: 
                pass
