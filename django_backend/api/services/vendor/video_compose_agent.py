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


def ffmpeg_has_filter(bin_path: str, name: str) -> bool:
    try:
        pr = subprocess.run([bin_path, "-hide_banner", "-filters"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if pr.returncode != 0:
            return False
        out = pr.stdout or ""
        name_l = name.strip().lower()
        for line in out.splitlines():
            if name_l in line.lower():
                return True
        return False
    except Exception:
        return False


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
def split_text_for_speech(text: str, max_chars: int = 60, **kwargs):
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
        # Allow passing through all params (not just a whitelist) so new effects are configurable
        cfg_params = {**base_params, **(params or {})}
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

        # Effects configuration
        enable_fade = bool(cfg_params.get("enable_fade", False))
        try:
            fade_in = float(cfg_params.get("fade_in", 0.5))
        except Exception:
            fade_in = 0.5
        try:
            fade_out = float(cfg_params.get("fade_out", 0.5))
        except Exception:
            fade_out = 0.5
        try:
            fade_mode = str(cfg_params.get("fade_mode", "ends")).lower()
        except Exception:
            fade_mode = "ends"

        enable_kb = bool(cfg_params.get("enable_ken_burns", False))
        try:
            kb_zoom_start = float(cfg_params.get("kb_zoom_start", 1.0))
        except Exception:
            kb_zoom_start = 1.0
        try:
            kb_zoom_end = float(cfg_params.get("kb_zoom_end", 1.1))
        except Exception:
            kb_zoom_end = 1.1
        try:
            kb_direction = str(cfg_params.get("kb_direction", "center")).lower()
        except Exception:
            kb_direction = "center"
        # normalize values
        if kb_zoom_end < kb_zoom_start:
            kb_zoom_end, kb_zoom_start = kb_zoom_start, kb_zoom_end

        # Crossfade between pages
        enable_crossfade = bool(cfg_params.get("enable_crossfade", False))
        try:
            crossfade = float(cfg_params.get("crossfade", 0.25))
        except Exception:
            crossfade = 0.25
        enable_audio_crossfade = bool(cfg_params.get("enable_audio_crossfade", False))

        # Caption config: base then call override
        caption_cfg = {}
        caption_cfg.update(base_params.get("caption") or {})
        caption_cfg.update((params.get("caption") or {}))

        enable_captions = bool(caption_cfg.get("enable_captions", True))
        use_global_captions = bool(cfg_params.get("use_global_captions", True))  # generate a global SRT (single timeline)
        burn_in_captions = bool(cfg_params.get("burn_in_captions", False))  # if true, burn SRT into final video; default off to avoid duplicates
        export_srt_on_burn = bool(cfg_params.get("export_srt_on_burn", False))  # when burning in, whether to keep output.srt on disk
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
        logger.info("[VideoCompose][Captions] enable=%s use_global=%s burn_in=%s area_height=%d font=%s fontsize=%d color=%s outline=%.2f shadow=%.2f align=%d margin_v=%d max_chars_line=%d fontsdir=%s",
                    enable_captions, use_global_captions, bool(cfg_params.get("burn_in_captions", False)), area_height, fontname, fontsize, color, outline, shadow, alignment, margin_v, max_chars_line, str(fontsdir) if fontsdir else "(system)")
        if enable_captions:
            if use_global_captions:
                logger.info("[VideoCompose][Captions] mode=global_srt burn_in=%s", bool(cfg_params.get("burn_in_captions", False)))
            else:
                logger.info("[VideoCompose][Captions] mode=per_page_ass")

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
        # Allow explicit override via params (e.g., to point to a custom static ffmpeg build)
        user_ffmpeg = cfg_params.get("ffmpeg_bin")
        if user_ffmpeg:
            ffmpeg_bin = str(user_ffmpeg)
            ffprobe_bin = "ffprobe" if ffmpeg_bin == "ffmpeg" else ffmpeg_bin.replace("ffmpeg", "ffprobe")
        # Prefer an ffmpeg that has required filters when crossfade is enabled
        if enable_crossfade and not user_ffmpeg:
            candidates = []
            seen = set()
            for c in [ffmpeg_bin, "ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
                if c and c not in seen:
                    candidates.append(c); seen.add(c)
            chosen = None
            for cand in candidates:
                if ffmpeg_has_filter(cand, "xfade"):
                    chosen = cand; break
            if chosen and chosen != ffmpeg_bin:
                ffmpeg_bin = chosen
                ffprobe_bin = "ffprobe" if chosen == "ffmpeg" else chosen.replace("ffmpeg", "ffprobe")

        def run_ffmpeg(cmd, desc):
            logger.info("[VideoCompose] %s: %s", desc, " ".join(cmd))
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                logger.error("[VideoCompose] %s failed rc=%s stderr_tail=%s", desc, p.returncode, p.stderr[-1000:])
                raise RuntimeError(f"{desc} failed")

        def ffmpeg_has_filter_LOCAL_SHADOW(bin_path: str, name: str) -> bool:
            try:
                pr = subprocess.run([bin_path, "-hide_banner", "-filters"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if pr.returncode != 0:
                    return False
                out = pr.stdout or ""
                name_l = name.strip().lower()
                for line in out.splitlines():
                    if name_l in line.lower().split():
                        if name_l in line.lower():
                            return True
                return False
            except Exception:
                return False

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

        def _fmt_srt_time(seconds: float) -> str:
            if seconds < 0:
                seconds = 0
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int(round((seconds - int(seconds)) * 1000))
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        def write_srt(path: Path, entries: list[tuple[float, float, str]]):
            # entries: list of (abs_start, abs_end, text)
            # 1) normalize & filter blanks
            norm = []
            for (st, et, txt) in entries:
                try:
                    s = max(0.0, float(st)); e = float(et)
                except Exception:
                    continue
                t = (txt or "").replace("\r\n", "\n").replace("\r", "\n").strip()
                if not t:
                    continue
                if not (e > s):
                    e = s + 0.01
                norm.append((s, e, t))
            # 2) sort by time
            norm.sort(key=lambda x: (x[0], x[1]))
            # 3) merge adjacent/overlapping duplicates
            merged = []
            MERGE_GAP = 0.05  # seconds tolerance for joining
            for (s, e, t) in norm:
                if not merged:
                    merged.append([s, e, t])
                    continue
                ps, pe, pt = merged[-1]
                if t == pt and s <= pe + MERGE_GAP:
                    # extend previous
                    merged[-1][1] = max(pe, e)
                else:
                    merged.append([s, e, t])
            # 4) drop ultra-short lines (<60ms) after merge
            cleaned = []
            for s, e, t in merged:
                if (e - s) >= 0.06:
                    cleaned.append((s, e, t))
            # 5) write SRT
            lines_out = []
            idx = 1
            for (st, et, txt) in cleaned:
                lines_out.append(str(idx))
                lines_out.append(f"{_fmt_srt_time(st)} --> {_fmt_srt_time(et)}")
                lines_out.append(txt)
                lines_out.append("")
                idx += 1
            path.write_text("\n".join(lines_out), encoding="utf-8")

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
            # For global captions timeline
            global_captions = []  # list of (abs_start, abs_end, text)
            timeline = 0.0
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
                if enable_captions and not use_global_captions:
                    write_ass(ass, lines)
                    logger.info("[VideoCompose] wrote ASS for page %d -> %s", page, ass)
                list_file = Path(temp_dir)/f"aud_list_{page}.txt"
                with open(list_file,'w',encoding='utf-8') as f:
                    for ap in page_audios: f.write(f"file '{ap.as_posix()}'\n")
                merged = Path(temp_dir)/f"merged_{page}.wav"
                run_ffmpeg([ffmpeg_bin, "-y","-f","concat","-safe","0","-i",str(list_file),"-c:a","pcm_s16le",str(merged)], f"concat_audio_page{page}")
                # Build per-page video filter
                total_h = height + area_height
                import math
                frames = max(1, int(math.ceil(fps * max(0.01, t))))
                if enable_kb:
                    # ratio expression across frames [0..1]
                    if frames > 1:
                        ratio_expr = f"on/{frames-1}"
                        z_expr = f"{kb_zoom_start}+({kb_zoom_end - kb_zoom_start})*({ratio_expr})"
                    else:
                        ratio_expr = "0"
                        z_expr = f"{kb_zoom_end}"
                    # directional pan
                    if kb_direction in ("lr", "left-right"):
                        x_expr = f"(iw - iw/zoom)*({ratio_expr})"; y_expr = "(ih - ih/zoom)/2"
                    elif kb_direction in ("rl", "right-left"):
                        x_expr = f"(iw - iw/zoom)*(1-({ratio_expr}))"; y_expr = "(ih - ih/zoom)/2"
                    elif kb_direction in ("tb", "top-bottom"):
                        x_expr = "(iw - iw/zoom)/2"; y_expr = f"(ih - ih/zoom)*({ratio_expr})"
                    elif kb_direction in ("bt", "bottom-top"):
                        x_expr = "(iw - iw/zoom)/2"; y_expr = f"(ih - ih/zoom)*(1-({ratio_expr}))"
                    else:  # center
                        x_expr = "(iw - iw/zoom)/2"; y_expr = "(ih - ih/zoom)/2"
                    vf_core = (
                        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height},fps={fps},setsar=1"
                    )
                else:
                    vf_core = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps},setsar=1"
                vf = f"{vf_core},pad={width}:{total_h}:(ow-iw)/2:0:black"
                if enable_captions and not use_global_captions:
                    if fontsdir:
                        vf += f",subtitles={ass.as_posix()}:fontsdir={fontsdir.as_posix()}"
                    else:
                        vf += f",subtitles={ass.as_posix()}"
                # Add fade in/out if enabled and duration is sufficient
                if enable_fade and t > 0.05:
                    # Determine fade application mode
                    is_first = (idx == 0)
                    is_last = (idx == len(images) - 1)
                    apply_in = (fade_mode in ("all", "in_only")) or (fade_mode in ("first_last", "ends") and is_first)
                    apply_out = (fade_mode in ("all", "out_only")) or (fade_mode in ("first_last", "ends") and is_last)
                    # Compute safe durations
                    fi = max(0.0, min(float(fade_in), max(0.0, t - 0.01))) if apply_in else 0.0
                    # Reserve head fade if applied, ensure we don't exceed t
                    max_out = max(0.0, t - fi - 0.01)
                    fo = max(0.0, min(float(fade_out), max_out)) if apply_out else 0.0
                    if fi > 0.0:
                        vf += f",fade=t=in:st=0:d={fi:.3f}"
                    if fo > 0.0:
                        st_out = max(0.0, t - fo)
                        vf += f",fade=t=out:st={st_out:.3f}:d={fo:.3f}"
                page_mp4 = Path(temp_dir)/f"page_{page}.mp4"
                run_ffmpeg([ffmpeg_bin, "-y","-loop","1","-i",str(img),"-i",str(merged),"-vf",vf,
                            "-c:v","libx264","-pix_fmt","yuv420p",
                            "-c:a","aac","-shortest",str(page_mp4)], f"make_page_video_{page}")
                # Probe actual encoded page duration to account for codec rounding
                pv_d = ffprobe_dur(page_mp4) or float(t)
                # accumulate global captions with scaled times per page (if enabled)
                if enable_captions and use_global_captions:
                    scale = (pv_d / float(t)) if float(t) > 0 else 1.0
                    # If we use video crossfade but DO NOT acrossfade audio, trim last segments to 'off' (t - crossfade)
                    off_local = float(t) - float(crossfade) if (enable_crossfade and crossfade > 0 and not enable_audio_crossfade) else float(t)
                    off_local = max(0.0, off_local)
                    for (st, et, txt) in lines:
                        st_f = float(st); et_f = float(et)
                        if et_f > off_local:
                            et_f = off_local
                        if et_f <= st_f + 1e-3:
                            continue
                        abs_st = timeline + st_f * scale
                        abs_et = timeline + et_f * scale
                        global_captions.append((abs_st, abs_et, str(txt)))
                page_videos.append(page_mp4)
                # advance global timeline by encoded duration (account for crossfade overlap)
                if enable_crossfade and crossfade > 0:
                    timeline += max(0.0, float(pv_d) - float(crossfade))
                else:
                    timeline += float(pv_d)
            # Crossfade between pages if enabled; otherwise fast concat
            if enable_crossfade and crossfade > 0 and len(page_videos) > 1:
                if not ffmpeg_has_filter(ffmpeg_bin, "xfade"):
                    logger.warning("[VideoCompose] ffmpeg has no 'xfade' filter; falling back to concat without crossfade")
                    enable_crossfade = False
                else:
                    # Probe durations for offsets
                    durs_pages = [ffprobe_dur(p) for p in page_videos]
                    # Prepare inputs
                    inputs = []
                    for p in page_videos:
                        inputs += ["-i", str(p)]
                    # Build filter graph
                    filter_parts = []
                    ar = int(cfg_params.get("audio_sample_rate", 44100))
                    for i in range(len(page_videos)):
                        filter_parts.append(f"[{i}:v]format=yuv420p,setsar=1[v{i}]")
                        filter_parts.append(f"[{i}:a]aresample={ar},aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
                    cur_v = "v0"; cur_a = "a0"; cur_d = durs_pages[0]
                    for i in range(1, len(page_videos)):
                        off = max(0.0, cur_d - crossfade)
                        out_v = f"vxf{i}"; out_a = f"axf{i}"
                        # Video crossfade
                        filter_parts.append(f"[{cur_v}][v{i}]xfade=transition=fade:duration={crossfade:.3f}:offset={off:.3f}[{out_v}]")
                        # Audio handling: either acrossfade or hard cut (no overlap)
                        if enable_audio_crossfade:
                            filter_parts.append(f"[{cur_a}][a{i}]acrossfade=d={crossfade:.3f}[{out_a}]")
                        else:
                            # Trim current audio to 'off' (start of crossfade), then append next audio without overlap
                            filter_parts.append(f"[{cur_a}]atrim=end={off:.3f},asetpts=PTS-STARTPTS[{out_a}p1]")
                            filter_parts.append(f"[a{i}]asetpts=PTS-STARTPTS[{out_a}p2]")
                            filter_parts.append(f"[{out_a}p1][{out_a}p2]concat=n=2:v=0:a=1[{out_a}]")
                        cur_v = out_v; cur_a = out_a; cur_d = cur_d + durs_pages[i] - crossfade
                    filter_complex = ",".join(filter_parts)
                    xfade_out = Path(temp_dir) / "xfaded.mp4"
                    run_ffmpeg([
                        ffmpeg_bin, "-y", *inputs,
                        "-filter_complex", filter_complex,
                        "-map", f"[{cur_v}]", "-map", f"[{cur_a}]",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", cfg_params.get("audio_codec", "aac"),
                        str(xfade_out)
                    ], "xfade_pages")
                    shutil.move(xfade_out, output)
            if not enable_crossfade:
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

            # Global captions export and optional burn-in
            if enable_captions and use_global_captions and global_captions:
                try:
                    # Write SRT next to output with same basename so players auto-load
                    srt_path = output.with_suffix(".srt")
                    write_srt(srt_path, global_captions)
                    logger.info("[VideoCompose] wrote global SRT: %s (entries=%d)", srt_path, len(global_captions))
                    if burn_in_captions:
                        subbed = output.with_name(output.stem + "_sub.mp4")
                        # Build subtitles filter with fontsdir and force_style to ensure caption styles take effect
                        try:
                            fontsdir_abs = Path(fontsdir).resolve() if fontsdir else None
                        except Exception:
                            fontsdir_abs = None
                        force_style = (
                            f"FontName={fontname},FontSize={fontsize},Outline={outline:.2f},"
                            f"Shadow={shadow:.2f},Alignment={alignment},MarginV={margin_v}"
                        )
                        if fontsdir_abs:
                            sub_filter = f"subtitles='{srt_path.as_posix()}':fontsdir='{fontsdir_abs.as_posix()}':force_style='{force_style}'"
                        else:
                            sub_filter = f"subtitles='{srt_path.as_posix()}':force_style='{force_style}'"
                        run_ffmpeg([
                            ffmpeg_bin,
                            "-y",
                            "-i", str(output),
                            "-vf", sub_filter,
                            "-c:v", "libx264",
                            "-pix_fmt", "yuv420p",
                            "-c:a", "copy",
                            str(subbed)
                        ], "overlay_srt")
                        shutil.move(subbed, output)
                        # Optionally remove SRT to avoid duplicate loading by players
                        try:
                            if not export_srt_on_burn and srt_path.exists():
                                srt_path.unlink()
                                logger.info("[VideoCompose] removed SRT after burn-in to avoid duplication: %s", srt_path)
                        except Exception:
                            pass
                except Exception as exc:
                    logger.warning("[VideoCompose] failed to write/overlay SRT: %s", exc)

            logger.info("[VideoCompose] done -> %s", output)
            return str(output)
        finally:
            try: shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception: 
                pass
