import platform
import random
import re
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import List, Union

import cv2
import librosa
# transitions module removed in MoviePy v2; use slide_in/slide_out instead
import numpy as np
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.audio.AudioClip import concatenate_audioclips

try:
    from moviepy import vfx

    slide_in = vfx.slide_in
    slide_out = vfx.slide_out
except Exception:
    # Fallback no-op implementations if slide effects are unavailable
    def slide_in(clip):
        return clip


    def slide_out(clip):
        return clip

from moviepy.video.VideoClip import ImageClip, ColorClip, VideoClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.tools.subtitles import SubtitlesClip
from tqdm import trange, tqdm

from mm_story_agent.base import register_tool


@contextmanager
def timeout_context(seconds):
    """跨平台超时上下文管理器"""
    if platform.system() == 'Windows':
        # Windows 使用线程超时
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
        # Unix/Linux 使用信号
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Operation timed out after {seconds} seconds")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)

        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


class ProgressTracker:
    """自定义进度跟踪器，用于替代 moviepy 的 progress_bar"""

    def __init__(self, total_steps: int, description: str = "Processing"):
        self.total_steps = total_steps
        self.current_step = 0
        self.description = description
        self.start_time = time.time()
        self.pbar = tqdm(total=total_steps, desc=description, unit="step")
        self.frame_pbar = None

    def update(self, step: int = 1):
        """更新进度"""
        self.current_step += step
        self.pbar.update(step)

    def set_description(self, desc: str):
        """更新描述"""
        self.pbar.set_description(desc)

    def start_frame_progress(self, total_frames: int, description: str = "Writing frames"):
        """开始帧级进度显示"""
        if self.frame_pbar:
            self.frame_pbar.close()
        self.frame_pbar = tqdm(total=total_frames, desc=description, unit="frame",
                               position=1, leave=False)

    def update_frame_progress(self, frames: int = 1):
        """更新帧进度"""
        if self.frame_pbar:
            self.frame_pbar.update(frames)

    def close_frame_progress(self):
        """关闭帧进度条"""
        if self.frame_pbar:
            self.frame_pbar.close()
            self.frame_pbar = None

    def close(self):
        """关闭进度条"""
        self.close_frame_progress()
        self.pbar.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def _write_video_with_ffmpeg(composite_clip, output_path, fps):
    """使用 FFmpeg 直接写入视频，避免 moviepy 卡住的问题"""
    import subprocess
    import tempfile
    import os

    # 创建临时图像序列
    temp_dir = tempfile.mkdtemp()
    try:
        # 将视频帧保存为图像序列
        frame_count = int(composite_clip.duration * fps)
        print(f"Writing {frame_count} frames to temporary directory...")

        for i in range(frame_count):
            t = i / fps
            frame = composite_clip.get_frame(t)
            frame_path = os.path.join(temp_dir, f"frame_{i:06d}.png")
            cv2.imwrite(frame_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

        # 使用 FFmpeg 将图像序列转换为视频
        cmd = [
            'ffmpeg', '-y',
            '-framerate', str(fps),
            '-i', os.path.join(temp_dir, 'frame_%06d.png'),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'fast',
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"FFmpeg failed: {result.stderr}")

    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def _write_video_with_ffmpeg_detailed(composite_clip, output_path, fps, total_frames):
    """使用 FFmpeg 直接写入视频，带详细进度显示"""
    import subprocess
    import tempfile
    import os
    import threading
    import time

    # 创建临时图像序列
    temp_dir = tempfile.mkdtemp()
    try:
        # 将视频帧保存为图像序列
        frame_count = int(composite_clip.duration * fps)
        print(f"写入 {frame_count} 帧到临时目录...")

        # 帧写入进度监控
        def frame_write_progress():
            """帧写入进度监控"""
            start_time = time.time()
            for i in range(frame_count):
                t = i / fps
                frame = composite_clip.get_frame(t)
                frame_path = os.path.join(temp_dir, f"frame_{i:06d}.png")
                cv2.imwrite(frame_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

                # 显示进度
                percent = ((i + 1) / frame_count) * 100
                elapsed = time.time() - start_time
                print(f"\r写入帧进度: {i + 1}/{frame_count} 帧 ({percent:.1f}%) - {elapsed:.1f}s", end='', flush=True)

        frame_write_progress()
        print(f"\n✓ 帧写入完成")

        # 使用 FFmpeg 将图像序列转换为视频，带进度显示
        print("使用FFmpeg转换帧为视频...")

        # FFmpeg转换进度监控 - 使用更准确的方法
        def ffmpeg_progress_monitor():
            """FFmpeg转换进度监控 - 基于实际文件大小"""
            start_time = time.time()
            last_size = 0
            while not hasattr(ffmpeg_progress_monitor, 'stop'):
                elapsed = time.time() - start_time

                # 检查输出文件是否存在及其大小
                if os.path.exists(output_path):
                    print(f"\rFFmpeg转换进度: 处理中... - {elapsed:.1f}s", end='', flush=True)
                else:
                    print(f"\rFFmpeg转换进度: 启动中... - {elapsed:.1f}s", end='', flush=True)

                time.sleep(0.5)

        cmd = [
            'ffmpeg', '-y',
            '-framerate', str(fps),
            '-i', os.path.join(temp_dir, 'frame_%06d.png'),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'fast',
            output_path
        ]

        # 启动进度监控
        progress_thread = threading.Thread(target=ffmpeg_progress_monitor)
        progress_thread.daemon = True
        progress_thread.start()

        # 运行 FFmpeg
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        # 停止进度监控
        ffmpeg_progress_monitor.stop = True
        progress_thread.join(timeout=1)

        if result.returncode != 0:
            raise Exception(f"FFmpeg失败: {result.stderr}")

        print(f"\n✓ FFmpeg转换完成")

    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def _load_wav_as_stereo_clip(file_path: str, target_sr: int) -> AudioArrayClip:
    """
    Load an audio file using librosa and return a stereo AudioArrayClip at target_sr.
    Ensures shape (num_samples, 2).
    """
    # mono=False to keep channels if present
    samples, sr = librosa.load(file_path, sr=target_sr, mono=False)
    # librosa returns (n,) or (channels, n)
    if samples.ndim == 1:
        # mono -> duplicate to stereo
        samples = np.stack([samples, samples], axis=0)
    elif samples.shape[0] == 1:
        samples = np.repeat(samples, 2, axis=0)
    # transpose to (n, 2)
    samples = samples.T.astype(np.float32)
    return AudioArrayClip(samples, fps=target_sr)


def test_smart_splitting():
    """测试智能分割功能（按字符切分）"""
    test_caption = "Under the moonlit sky, Timmy Turtle lay in his cozy bed, dreaming of center stage at the Forest Talent Show. His heart swelled with excitement as he imagined the spotlight on him, performing a dance that would leave the audience breathless."

    print("测试智能分割功能:")
    print(f"原始文本: {test_caption}")
    print(f"字符数: {len(test_caption)}")

    lines = split_caption_smart_chars(test_caption, max_chars=40)
    print(f"\n分割结果 ({len(lines)} 行):")
    for i, line in enumerate(lines, 1):
        char_count = len(line)
        print(f"  {i}. {line} ({char_count} 字符)")


def verify_audio_subtitle_sync(story_dir: Path, timestamps: List):
    """验证音频与字幕的同步情况"""
    print("\n" + "=" * 50)
    print("音频与字幕同步验证")
    print("=" * 50)

    speech_dir = story_dir / "speech"

    for i, (start_time, end_time) in enumerate(timestamps, 1):
        print(f"页面 {i}: {start_time:.2f}s - {end_time:.2f}s")

        # 检查对应的语音文件
        speech_file = speech_dir / f"p{i}.wav"
        if speech_file.exists():
            try:
                import librosa
                duration = librosa.get_duration(filename=str(speech_file))
                print(f"  语音文件时长: {duration:.2f}s")
                print(f"  时间轴时长: {end_time - start_time:.2f}s")

                if abs(duration - (end_time - start_time)) > 0.5:
                    print(f"  时长不匹配！差异: {abs(duration - (end_time - start_time)):.2f}s")
                else:
                    print(f"  时长匹配")
            except Exception as e:
                print(f"  无法读取语音文件: {e}")
        else:
            print(f"  语音文件不存在: {speech_file}")

    print("✓ 同步验证完成")


def correct_timestamps_with_audio(story_dir: Path, timestamps: List, fade_duration: float, slide_duration: float):
    """基于实际音频文件时长修正时间轴"""
    print("\n" + "=" * 50)
    print("基于实际音频修正时间轴")
    print("=" * 50)

    speech_dir = story_dir / "speech"

    # 如果已经有正确的时间轴，直接使用（避免双重计算）
    if timestamps and len(timestamps) > 0:
        print(f"使用已计算的时间轴，共 {len(timestamps)} 个时间轴")

        # 验证时间轴是否与语音文件匹配
        audio_files = sorted(speech_dir.glob("s*.wav"), key=lambda x: int(x.stem[1:]))
        if len(timestamps) == len(audio_files):
            print("✓ 时间轴数量与语音文件数量匹配，直接使用")
            for i, (timestamp, audio_file) in enumerate(zip(timestamps, audio_files)):
                try:
                    import librosa
                    actual_duration = librosa.get_duration(filename=str(audio_file))
                    print(f"语音文件 {audio_file.name}:")
                    print(f"  实际语音时长: {actual_duration:.2f}s")
                    print(f"  使用时间轴: {timestamp[0]:.2f}s - {timestamp[1]:.2f}s")
                except Exception as e:
                    print(f"  ❌ 无法读取语音文件 {audio_file}: {e}")

            return timestamps
        else:
            print(f"⚠️ 时间轴数量({len(timestamps)})与语音文件数量({len(audio_files)})不匹配，重新计算")

    # 如果没有时间轴或数量不匹配，重新计算
    corrected_timestamps = []
    current_time = 0

    # 查找所有语音文件，按s{i}.wav格式
    audio_files = sorted(speech_dir.glob("s*.wav"), key=lambda x: int(x.stem[1:]))
    print(f"找到 {len(audio_files)} 个语音文件")

    for i, audio_file in enumerate(audio_files):
        try:
            import librosa
            actual_duration = librosa.get_duration(filename=str(audio_file))

            # 计算修正后的时间轴
            if i == 0:
                # 第一个语音：slide_duration + 实际语音时长
                corrected_start = current_time + slide_duration
                corrected_end = corrected_start + actual_duration
                current_time += slide_duration + actual_duration
            else:
                # 其他语音：slide_duration + fade_duration + 实际语音时长
                corrected_start = current_time + slide_duration + fade_duration
                corrected_end = corrected_start + actual_duration
                current_time += slide_duration + actual_duration + fade_duration

            corrected_timestamps.append([corrected_start, corrected_end])

            print(f"语音文件 {audio_file.name}:")
            print(f"  实际语音时长: {actual_duration:.2f}s")
            print(f"  修正时间轴: {corrected_start:.2f}s - {corrected_end:.2f}s")

        except Exception as e:
            print(f"  无法读取语音文件 {audio_file}: {e}")
            # 如果无法读取，使用原始时间轴或跳过
            if i < len(timestamps):
                corrected_timestamps.append(timestamps[i])
            else:
                # 如果没有原始时间轴，使用当前时间
                corrected_timestamps.append([current_time, current_time + 1.0])
                current_time += 1.0

    print(f"✓ 时间轴修正完成，共 {len(corrected_timestamps)} 个语音文件")
    return corrected_timestamps


def generate_srt_from_subtitle_items(subtitle_items: List, save_path: Union[str, Path]):
    """
    从 add_caption 生成的 subtitle_items 直接生成 SRT 文件，确保完全一致
    """

    def format_time(seconds: float) -> str:
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        millis = int((td.total_seconds() - total_seconds) * 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

    srt_content = []

    print(f"从subtitle_items生成SRT文件：{len(subtitle_items)} 条字幕")

    for srt_index, ((start_time, end_time), text) in enumerate(subtitle_items, 1):
        start_time_str = format_time(start_time)
        end_time_str = format_time(end_time)

        srt_content.append(f"{srt_index}\n{start_time_str} --> {end_time_str}\n{text}\n\n")
        print(f"  SRT {srt_index}: {start_time:.2f}s - {end_time:.2f}s: {text}")

    with open(save_path, 'w', encoding='utf-8') as srt_file:
        srt_file.writelines(srt_content)

    print(f"SRT文件已保存到: {save_path} (共 {len(subtitle_items)} 条字幕)")


def generate_srt(timestamps: List,
                 captions: List,
                 save_path: Union[str, Path],
                 segmented_pages: List = None,
                 caption_config: dict | None = None):
    """
    保留原函数用于向后兼容，但建议使用 generate_srt_from_subtitle_items
    """
    if caption_config is None:
        caption_config = {}

    def format_time(seconds: float) -> str:
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        millis = int((td.total_seconds() - total_seconds) * 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

    srt_content = []
    num_caps = len(timestamps)
    srt_index = 1

    # 统一使用页面级处理，与add_caption函数保持一致
    print(f"生成SRT文件：{num_caps} 个页面（页面级处理）")

    for idx in range(num_caps):
        start_time, end_time = timestamps[idx]
        caption_text = captions[idx].strip()

        if not caption_text:
            continue

        # 当使用segmented_pages流程时，captions已经是句子级别，直接使用不再切分
        # 这避免了重复切分导致的字幕过度分割问题
        if segmented_pages is not None:
            # 在segmented_pages流程中，每个caption就是一个完整的句子，不需要再切分
            caption_lines = [caption_text]
            print(f"句子 {idx + 1}: 直接使用语音生成的句子（避免重复切分）")
        else:
            # 只有在传统页面级流程中才进行智能分割（按字符）
            max_chars = caption_config.get("max_chars_per_line")
            if not max_chars:
                legacy_words = caption_config.get("max_words_per_line", 0)
                try:
                    max_chars = int(legacy_words) * 5 if legacy_words else 40
                except Exception:
                    max_chars = 40
            caption_lines = split_caption_smart_chars(caption_text, max_chars=max_chars)
            print(f"页面 {idx + 1}: 使用智能分割（按字符，每行≤{max_chars} 字符）")

        # 基于实际语音时长计算每行的时间分配，添加过渡时间
        total_duration = end_time - start_time
        transition_duration = 0.3  # 每行之间的过渡时间（秒），减少过渡时间

        if len(caption_lines) > 1:
            # 计算每行的实际显示时间（扣除过渡时间）
            total_transition_time = transition_duration * (len(caption_lines) - 1)
            available_time = total_duration - total_transition_time
            line_duration = available_time / len(caption_lines) if caption_lines else 0
        else:
            line_duration = total_duration

        print(
            f"页面 {idx + 1}: 语音时长 {total_duration:.2f}s, 分割为 {len(caption_lines)} 行, 每行显示 {line_duration:.2f}s, 过渡 {transition_duration:.2f}s")

        for line_idx, line in enumerate(caption_lines):
            # 计算每行的开始和结束时间，包含过渡
            line_start = start_time + (line_duration + transition_duration) * line_idx
            line_end = line_start + line_duration

            start_time_str = format_time(line_start)
            end_time_str = format_time(line_end)

            srt_content.append(f"{srt_index}\n{start_time_str} --> {end_time_str}\n{line}\n\n")
            print(f"  SRT {srt_index}: {line_start:.2f}s - {line_end:.2f}s: {line} ({len(line.split())} 单词)")
            srt_index += 1

    with open(save_path, 'w', encoding='utf-8') as srt_file:
        srt_file.writelines(srt_content)

    print(f"SRT文件已保存到: {save_path} (共 {srt_index - 1} 条字幕)")


def add_caption(captions: List,
                timestamps: List,
                video_clip: VideoClip,
                segmented_pages: List = None,
                **caption_config):
    # Build subtitle timing and text - 使用智能分割，基于实际语音时长
    subtitle_items = []  # list of ((start, end), text)
    num_caps = len(timestamps)

    print(f"开始处理字幕：{num_caps} 个页面")

    for idx in range(num_caps):
        start_time, end_time = timestamps[idx]
        caption_text = captions[idx].strip()

        if not caption_text:
            continue

        # 当使用segmented_pages流程时，captions已经是句子级别，直接使用不再切分
        # 这避免了重复切分导致的字幕过度分割问题
        if segmented_pages is not None:
            # 在segmented_pages流程中，每个caption就是一个完整的句子，不需要再切分
            caption_lines = [caption_text]
        else:
            # 只有在传统页面级流程中才进行智能分割（按字符）
            max_chars = caption_config.get("max_chars_per_line")
            if not max_chars:
                # 兼容旧配置：将 max_words_per_line 粗略换算为字符数（约5字符/词）
                legacy_words = caption_config.get("max_words_per_line")
                if legacy_words:
                    try:
                        max_chars = int(legacy_words) * 5
                    except Exception:
                        max_chars = 40
                else:
                    max_chars = 40
            caption_lines = split_caption_smart_chars(caption_text, max_chars=max_chars)

        # 直接使用传入的时间轴，不进行内部重新计算
        # 这确保字幕时间轴与实际音频文件完全同步
        total_duration = end_time - start_time

        if len(caption_lines) > 1:
            # 简单平均分配时间给每行，不添加额外的过渡时间
            line_duration = total_duration / len(caption_lines)
        else:
            line_duration = total_duration

        for line_idx, line in enumerate(caption_lines):
            # 直接基于传入的时间轴计算每行时间，确保与音频同步
            line_start = start_time + line_duration * line_idx
            line_end = start_time + line_duration * (line_idx + 1)
            subtitle_items.append(((line_start, line_end), line))

    # Remove the custom argument before passing to TextClip to avoid TypeError
    caption_config.pop('max_words_per_line', None)

    # Pre-render unique texts in parallel to speed up creation
    unique_texts = sorted({text for _, text in subtitle_items})

    # Number of parallel workers for text rendering
    workers = caption_config.get('workers', 1)

    def render_text_clip(text: str):
        # Render text to an image using PIL, honoring caption_config (font, fontsize, color)
        from PIL import Image, ImageDraw, ImageFont, ImageColor
        # Read style from caption_config
        font_path = caption_config.get('font') or caption_config.get('font_path')
        fontsize = int(caption_config.get('fontsize', 32))
        color_val = caption_config.get('color', 'white')
        try:
            fill_rgba = ImageColor.getrgb(color_val)
            if len(fill_rgba) == 3:
                fill_rgba = (*fill_rgba, 255)
        except Exception:
            fill_rgba = (255, 255, 255, 255)
        # Padding around text
        pad_x, pad_y = 20, 10
        # Select font
        try:
            if font_path:
                font = ImageFont.truetype(font_path, fontsize)
            else:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        # Measure text box
        dummy_img = Image.new('L', (1, 1), 0)
        draw = ImageDraw.Draw(dummy_img)
        # textbbox available in recent Pillow; fallback to textsize if needed
        try:
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_w = max(1, text_bbox[2] - text_bbox[0])
            text_h = max(1, text_bbox[3] - text_bbox[1])
        except Exception:
            text_w, text_h = draw.textsize(text, font=font)
        img_w = text_w + pad_x * 2
        img_h = text_h + pad_y * 2
        # Draw text on transparent canvas
        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((pad_x, pad_y), text, font=font, fill=fill_rgba)
        # Convert to numpy array and wrap as ImageClip
        arr = np.array(img)
        return ImageClip(arr)

    text_to_clip = {}
    if unique_texts:
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
            futures = {executor.submit(render_text_clip, text): text for text in unique_texts}
            for future in as_completed(futures):
                text = futures[future]
                try:
                    text_to_clip[text] = future.result()
                except Exception:
                    # Fallback: create minimal clip on failure
                    try:
                        text_to_clip[text] = render_text_clip(text)
                    except Exception:
                        # As a last resort, skip this text
                        text_to_clip[text] = render_text_clip("")

    # Construct subtitles from text, using cached pre-rendered clips
    def make_textclip_from_cache(txt: str) -> ImageClip:
        clip = text_to_clip.get(txt)
        if clip is None:
            clip = render_text_clip(txt)
            text_to_clip[txt] = clip
        return clip

    subtitles = SubtitlesClip(subtitle_items, make_textclip=make_textclip_from_cache)
    captioned_clip = CompositeVideoClip([video_clip,
                                         subtitles.with_position(("center", "bottom"), relative=True)])
    return captioned_clip, subtitle_items


def split_keep_separator(text, separator):
    pattern = f'([{re.escape(separator)}])'
    pieces = re.split(pattern, text)
    return pieces


def split_text_for_speech(text, max_words=20):
    """
    为语音生成切分文本, 优先保持完整句子。每句不超过max_words个单词
    这是专门用于语音生成时的文本切分算法，优先保持句子的完整性
    改进版本：正确处理缩写词，避免在缩写词后错误分割
    """
    import re

    if not text or not text.strip():
        return []

    # 定义常见的缩写词（不在此处分割）
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

    # 预处理：保护缩写词，用特殊标记替换
    protected_text = text
    abbreviation_markers = {}

    for i, abbr in enumerate(common_abbreviations):
        # 查找缩写词后跟句号的模式
        pattern = re.escape(abbr) + r'\.'
        if re.search(pattern, protected_text):
            marker = f"__ABBR_{i}__"
            abbreviation_markers[marker] = abbr + '.'
            protected_text = re.sub(pattern, marker, protected_text)

    # 第一步：按强标点符号分割，保持标点符号
    sentences = re.split(r'([.!?]+)', protected_text)
    # 重新组合句子和标点符号
    complete_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            sentence = (sentences[i] + sentences[i + 1]).strip()
            if sentence:
                complete_sentences.append(sentence)

    # 处理最后一部分（如果没有强标点符号结尾）
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        complete_sentences.append(sentences[-1].strip())

    # 如果没有找到强标点符号，将整个文本作为一个句子
    if not complete_sentences:
        complete_sentences = [protected_text.strip()]

    # 恢复缩写词标记
    for i, sentence in enumerate(complete_sentences):
        for marker, original in abbreviation_markers.items():
            sentence = sentence.replace(marker, original)
        complete_sentences[i] = sentence

    # 检查是否所有句子都很短，如果是则不进行切分
    all_sentences_short = all(len(sentence.split()) <= max_words for sentence in complete_sentences)
    if all_sentences_short:
        return complete_sentences

    result_segments = []

    for sentence in complete_sentences:
        if not sentence:
            continue

        # 计算单词数
        words = sentence.split()
        word_count = len(words)

        if word_count <= max_words:
            # 句子长度合适，直接添加
            result_segments.append(sentence)
        else:
            # 句子太长，需要进一步分割
            # 第二步：尝试按中等标点符号分割
            # 先保护当前句子中的缩写词
            protected_sentence = sentence
            sentence_abbreviation_markers = {}

            for i, abbr in enumerate(common_abbreviations):
                pattern = re.escape(abbr) + r'\.'
                if re.search(pattern, protected_sentence):
                    marker = f"__SENT_ABBR_{i}__"
                    sentence_abbreviation_markers[marker] = abbr + '.'
                    protected_sentence = re.sub(pattern, marker, protected_sentence)

            sub_sentences = re.split(r'([;:]+)', protected_sentence)
            # 重新组合子句和标点符号
            complete_sub_sentences = []
            for i in range(0, len(sub_sentences) - 1, 2):
                if i + 1 < len(sub_sentences):
                    sub_sentence = (sub_sentences[i] + sub_sentences[i + 1]).strip()
                    if sub_sentence:
                        complete_sub_sentences.append(sub_sentence)

            # 处理最后一部分（如果没有中等标点符号结尾）
            if len(sub_sentences) % 2 == 1 and sub_sentences[-1].strip():
                complete_sub_sentences.append(sub_sentences[-1].strip())

            # 如果没有找到中等标点符号，将原句作为一个子句
            if not complete_sub_sentences:
                complete_sub_sentences = [protected_sentence]

            # 恢复子句中的缩写词
            for i, sub_sentence in enumerate(complete_sub_sentences):
                for marker, original in sentence_abbreviation_markers.items():
                    sub_sentence = sub_sentence.replace(marker, original)
                complete_sub_sentences[i] = sub_sentence

            for sub_sentence in complete_sub_sentences:
                sub_words = sub_sentence.split()
                if len(sub_words) <= max_words:
                    result_segments.append(sub_sentence)
                else:
                    # 第三步：按弱标点符号分割
                    # 先保护当前子句中的缩写词
                    protected_sub_sentence = sub_sentence
                    sub_sentence_abbreviation_markers = {}

                    for i, abbr in enumerate(common_abbreviations):
                        pattern = re.escape(abbr) + r'\.'
                        if re.search(pattern, protected_sub_sentence):
                            marker = f"__SUB_ABBR_{i}__"
                            sub_sentence_abbreviation_markers[marker] = abbr + '.'
                            protected_sub_sentence = re.sub(pattern, marker, protected_sub_sentence)

                    comma_parts = re.split(r'([,]+)', protected_sub_sentence)
                    # 重新组合部分和逗号
                    complete_comma_parts = []
                    for i in range(0, len(comma_parts) - 1, 2):
                        if i + 1 < len(comma_parts):
                            part = (comma_parts[i] + comma_parts[i + 1]).strip()
                            if part:
                                complete_comma_parts.append(part)

                    # 处理最后一部分（如果没有逗号结尾）
                    if len(comma_parts) % 2 == 1 and comma_parts[-1].strip():
                        complete_comma_parts.append(comma_parts[-1].strip())

                    # 如果没有找到逗号，将原子句作为一个部分
                    if not complete_comma_parts:
                        complete_comma_parts = [protected_sub_sentence]

                    # 恢复逗号分割中的缩写词
                    for i, part in enumerate(complete_comma_parts):
                        for marker, original in sub_sentence_abbreviation_markers.items():
                            part = part.replace(marker, original)
                        complete_comma_parts[i] = part

                    # 尝试合并短的部分，形成更长的段落
                    current_segment = ""
                    for part in complete_comma_parts:
                        part_words = part.split()

                        # 如果当前部分本身就超过限制，需要强制分割
                        if len(part_words) > max_words:
                            # 先保存之前累积的段落
                            if current_segment:
                                result_segments.append(current_segment.strip())
                                current_segment = ""

                            # 强制分割超长的部分
                            current_words = []
                            for word in part_words:
                                if len(current_words) < max_words:
                                    current_words.append(word)
                                else:
                                    # 检查是否需要添加标点符号
                                    segment_text = " ".join(current_words)
                                    if not segment_text.endswith(('.', '!', '?', ';', ':', ',')):
                                        segment_text += "."
                                    result_segments.append(segment_text)
                                    current_words = [word]

                            # 将剩余单词作为新的当前段落
                            current_segment = " ".join(current_words)
                        else:
                            # 尝试将当前部分添加到当前段落
                            test_segment = current_segment + (" " + part if current_segment else part)
                            test_words = test_segment.split()

                            if len(test_words) <= max_words:
                                # 可以合并，更新当前段落
                                current_segment = test_segment
                            else:
                                # 不能合并，保存当前段落，开始新段落
                                if current_segment:
                                    result_segments.append(current_segment.strip())
                                current_segment = part

                    # 保存最后一个段落
                    if current_segment:
                        result_segments.append(current_segment.strip())

    return result_segments


def split_caption_smart_chars(text: str, max_chars: int = 40) -> List[str]:
    """
    按“字符”为最小单位的智能字幕分割：
    - 优先在强/中/弱标点处断句
    - 每行不超过 max_chars 字符
    - 若在自然断点前已达到上限，则在上限处硬切
    适用于中英文混排。
    """
    if not text:
        return []

    # 定义分隔优先级：强 -> 中 -> 弱
    strong = set(list("。！？.!?"))
    medium = set(list("；;：:"))
    weak = set(list("，,、;"))

    pieces = []
    buf = ""

    def flush_buffer():
        nonlocal buf
        while buf:
            if len(buf) <= max_chars:
                pieces.append(buf)
                buf = ""
                break
            else:
                # 尝试在 max_chars 范围内寻找最近的空格或自然分隔
                cut = -1
                # 优先找强/中/弱标点作为切分点
                for i in range(min(len(buf), max_chars), 0, -1):
                    ch = buf[i - 1]
                    if ch in strong or ch in medium or ch in weak or ch.isspace():
                        cut = i
                        break
                if cut == -1:
                    cut = max_chars
                pieces.append(buf[:cut])
                buf = buf[cut:]

    for ch in text:
        buf += ch
        if len(buf) >= max_chars:
            # 达到上限，优先在标点处分割
            flush_buffer()
            continue
        # 若遇到强/中/弱标点且当前长度达到一定比例，进行自然断句
        if ch in strong:
            if len(buf) >= max(1, int(max_chars * 0.5)):
                flush_buffer()
        elif ch in medium:
            if len(buf) >= max(1, int(max_chars * 0.7)):
                flush_buffer()
        elif ch in weak:
            if len(buf) >= max(1, int(max_chars * 0.9)):
                flush_buffer()

    if buf:
        flush_buffer()

    # 保留原始字符，不去除空白，确保拼接后与原文一致
    return [p for p in pieces if p != ""]


def split_caption(caption, max_length=30):
    """
    保持原有函数兼容性，但内部使用新的智能分割
    """
    # 使用智能分割，然后转换为原有格式
    lines = split_caption_smart(caption, max_words=20)
    return '\n'.join(lines)


def add_bottom_black_area(clip: VideoFileClip,
                          black_area_height: int = 64):
    """
    Add a black area at the bottom of the video clip (for captions).

    Args:
        clip (VideoFileClip): Video clip to be processed.
        black_area_height (int): Height of the black area.

    Returns:
        VideoFileClip: Processed video clip.
    """
    black_bar = ColorClip(size=(clip.w, black_area_height), color=(0, 0, 0), duration=clip.duration)
    extended_clip = CompositeVideoClip([clip, black_bar.with_position(("center", "bottom"))])
    return extended_clip


def add_zoom_effect(clip, speed=1.0, mode='in', position='center', fps=None):
    """Safe no-op zoom effect for environments lacking clip.fl on CompositeVideoClip.
    Keep pipeline stable without per-frame transforms."""
    return clip


def add_move_effect(clip, direction="left", move_raito=0.95):
    orig_width = clip.size[0]
    orig_height = clip.size[1]

    new_width = int(orig_width / move_raito)
    new_height = int(orig_height / move_raito)
    clip = clip.resized(width=new_width, height=new_height)

    if direction == "left":
        start_position = (0, 0)
        end_position = (orig_width - new_width, 0)
    elif direction == "right":
        start_position = (orig_width - new_width, 0)
        end_position = (0, 0)

    duration = clip.duration
    moving_clip = clip.with_position(
        lambda t: (start_position[0] + (
                end_position[0] - start_position[0]) / duration * t, start_position[1])
    )

    final_clip = CompositeVideoClip([moving_clip], size=(orig_width, orig_height))

    return final_clip


def add_slide_effect(clips, slide_duration):
    ####### CAUTION: requires at least `slide_duration` of silence at the end of each clip #######
    durations = [clip.duration for clip in clips]
    first_clip = CompositeVideoClip(
        [slide_out(clips[0])]
    ).with_start(0)

    slide_out_sides = ["left"]
    videos = [first_clip]

    for idx, clip in enumerate(clips[1: -1], start=1):
        # For all other clips in the middle, we need them to slide in to the previous clip and out for the next one

        # determine `slide_in_side` according to the `slide_out_side` of the previous clip

        slide_out_side = "left" if random.random() <= 0.5 else "right"
        slide_out_sides.append(slide_out_side)

        middle_clip = (
            CompositeVideoClip([
                slide_in(clip)
            ]).with_start(sum(durations[:idx]) - slide_duration * idx)
        )
        videos.append(middle_clip)
        videos[-1] = slide_out(videos[-1])

    last_clip = CompositeVideoClip(
        [slide_in(clips[-1])]
    ).with_start(sum(durations[:-1]) - slide_duration * (len(clips) - 1))
    videos.append(last_clip)

    video = CompositeVideoClip(videos)
    return video


def compose_video(story_dir: Union[str, Path],
                  save_path: Union[str, Path],
                  captions: List,
                  num_pages: int,
                  fps: int = 10,
                  target_width: int = 1280,
                  target_height: int = 720,
                  audio_sample_rate: int = 44100,
                  audio_codec: str = "aac",
                  caption_config: dict = {},
                  segmented_pages: List = None,
                  fade_duration: float = 1.0,
                  slide_duration: float = 0.4,
                  zoom_speed: float = 0.5,
                  move_ratio: float = 0.95):
    if not isinstance(story_dir, Path):
        story_dir = Path(story_dir)

    image_dir = story_dir / "image"
    speech_dir = story_dir / "speech"

    video_clips = []
    # audio_durations = []
    timestamps = []
    actual_audio_durations = []  # 用于存储每个片段的真实音频时长

    # 新的逻辑：按句子处理音频，而不是按页面
    if segmented_pages is not None:
        # 使用新的按句子处理逻辑
        print("使用新的按句子处理逻辑")
        audio_file_counter = 1

        for page_idx, segments in enumerate(segmented_pages):
            for _, segment in enumerate(segments):
                # 为每个句子创建视频片段
                audio_filename = f"s{audio_file_counter}.wav"
                audio_file_path = speech_dir / audio_filename

                if audio_file_path.exists():
                    # 加载音频并获取实际时长
                    speech_clip = _load_wav_as_stereo_clip(str(audio_file_path), audio_sample_rate)
                    actual_audio_duration = speech_clip.duration

                    # 添加淡入淡出效果
                    fade_silence_array = np.zeros((int(audio_sample_rate * fade_duration), 2), dtype=np.float32)
                    fade_silence = AudioArrayClip(fade_silence_array, fps=audio_sample_rate)
                    speech_clip = concatenate_audioclips([fade_silence, speech_clip, fade_silence])

                    actual_audio_durations.append(actual_audio_duration)  # 存储真实音频时长，后续统一计算

                    # 加载对应的图像（使用页面图像）
                    image_file = (image_dir / f"./p{page_idx + 1}.png").__str__()
                    image_clip = ImageClip(image_file)
                    image_clip = image_clip.with_duration(speech_clip.duration).with_fps(fps)

                    # Fit image into target canvas without stretching (letterbox if needed)
                    img_w, img_h = image_clip.size
                    scale = min(target_width / img_w, target_height / img_h)
                    new_w, new_h = int(img_w * scale), int(img_h * scale)
                    fitted_clip = image_clip.resized(width=new_w, height=new_h)
                    bg = ColorClip(size=(target_width, target_height), color=(0, 0, 0)).with_duration(
                        fitted_clip.duration)
                    image_clip = CompositeVideoClip([bg, fitted_clip.with_position('center')])
                    image_clip = image_clip

                    # 添加视觉效果
                    if random.random() <= 0.5:  # zoom in or zoom out
                        if random.random() <= 0.5:
                            zoom_mode = "in"
                        else:
                            zoom_mode = "out"
                        image_clip = add_zoom_effect(image_clip, zoom_speed, zoom_mode, fps=fps)
                    else:  # move left or right
                        if random.random() <= 0.5:
                            direction = "left"
                        else:
                            direction = "right"
                        image_clip = add_move_effect(image_clip, direction=direction, move_raito=move_ratio)

                    # 确保音频有正确的采样率
                    audio_clip = speech_clip.with_fps(audio_sample_rate)

                    video_clip = image_clip.with_audio(audio_clip)
                    video_clips.append(video_clip)

                    audio_file_counter += 1
                else:
                    print(f"  警告：音频文件不存在 {audio_file_path}")
    else:
        # 回退到原来的按页面处理逻辑
        print("使用原来的按页面处理逻辑")
        cur_duration = 0.0  # 累计当前已添加到时间线的总时长
        for page in trange(1, num_pages + 1):
            # speech track
            # Create stereo silence to avoid channel mismatches
            slide_silence_array = np.zeros((int(audio_sample_rate * slide_duration), 2), dtype=np.float32)
            fade_silence_array = np.zeros((int(audio_sample_rate * fade_duration), 2), dtype=np.float32)
            slide_silence = AudioArrayClip(slide_silence_array, fps=audio_sample_rate)
            fade_silence = AudioArrayClip(fade_silence_array, fps=audio_sample_rate)

            # Calculate the start time for this page's speech content (excluding effects)
            page_speech_start = cur_duration

            if (speech_dir / f"p{page}.wav").exists():  # single speech file
                single_utterance = True
                speech_file = (speech_dir / f"./p{page}.wav").__str__()
                original_speech_clip = _load_wav_as_stereo_clip(speech_file, audio_sample_rate)

                # Add fade effects to speech
                speech_clip = concatenate_audioclips([fade_silence, original_speech_clip, fade_silence])

            else:  # multiple speech files
                single_utterance = False
                speech_files = list(speech_dir.glob(f"s{page}_*.wav"))
                speech_files = sorted(speech_files, key=lambda x: int(x.stem.split("_")[-1]))
                speech_clips = []

                for speech_file in speech_files:
                    temp_clip = _load_wav_as_stereo_clip(speech_file.__str__(), audio_sample_rate)
                    speech_clips.append(temp_clip)

                speech_clip = concatenate_audioclips([fade_silence] + speech_clips + [fade_silence])
                speech_file = speech_files[0]  # for energy calculation

            # Add slide silence and update duration
            if page == 1:
                speech_clip = concatenate_audioclips([speech_clip, slide_silence])
                # For first page: timestamp starts after the initial slide silence
                speech_start_time = page_speech_start + slide_duration
            else:
                speech_clip = concatenate_audioclips([slide_silence, speech_clip, slide_silence])
                # For other pages: timestamp starts after slide silence + fade silence
                speech_start_time = page_speech_start + slide_duration + fade_duration

            # Calculate the actual speech duration (excluding fade effects)
            if single_utterance:
                actual_speech_duration = original_speech_clip.duration
            else:
                actual_speech_duration = sum(temp_clip.duration for temp_clip in speech_clips)

            actual_audio_durations.append(actual_speech_duration)  # 存储真实音频时长，后续统一计算

            # set image as the main content, align the duration
            image_file = (image_dir / f"./p{page}.png").__str__()
            image_clip = ImageClip(image_file)
            image_clip = image_clip.with_duration(speech_clip.duration).with_fps(fps)

            # Fit image into target canvas without stretching (letterbox if needed)
            img_w, img_h = image_clip.size
            scale = min(target_width / img_w, target_height / img_h)
            new_w, new_h = int(img_w * scale), int(img_h * scale)
            fitted_clip = image_clip.resized(width=new_w, height=new_h)
            bg = ColorClip(size=(target_width, target_height), color=(0, 0, 0)).with_duration(fitted_clip.duration)
            image_clip = CompositeVideoClip([bg, fitted_clip.with_position('center')])
            # Crossfade not available on CompositeVideoClip in this environment; no-op
            image_clip = image_clip

            if random.random() <= 0.5:  # zoom in or zoom out
                if random.random() <= 0.5:
                    zoom_mode = "in"
                else:
                    zoom_mode = "out"
                image_clip = add_zoom_effect(image_clip, zoom_speed, zoom_mode, fps=fps)
            else:  # move left or right
                if random.random() <= 0.5:
                    direction = "left"
                else:
                    direction = "right"
                image_clip = add_move_effect(image_clip, direction=direction, move_raito=move_ratio)

            # Ensure audio has consistent sample rate (already set above)
            audio_clip = speech_clip.with_fps(audio_sample_rate)

            video_clip = image_clip.with_audio(audio_clip)
            video_clips.append(video_clip)

            # 更新累计时长，供下一页的起始时间参考
            cur_duration += speech_clip.duration

            # audio_durations.append(audio_clip.duration)

    # final_clip = concatenate_videoclips(video_clips, method="compose")
    composite_clip = add_slide_effect(video_clips, slide_duration=slide_duration)

    # --- 重构：从合成后的视频中提取精确时间戳 ---
    # 放弃手动累加时间，以MoviePy的计算结果为准，根除累积误差
    print("\n--- 从合成视频中提取精确时间戳 ---")
    timestamps = []
    # composite_clip.clips 包含了所有经过转场效果计算后的子片段
    # 我们需要确保这里的片段顺序和我们之前记录的 actual_audio_durations 顺序一致
    if len(composite_clip.clips) == len(actual_audio_durations):
        for i, subclip in enumerate(composite_clip.clips):
            actual_audio_duration = actual_audio_durations[i]

            # 计算语音在子片段中的实际开始时间
            # MoviePy的 subclip.start 是整个片段（含静音转场）的开始时间
            if i == 0:
                # 第一个片段只有淡入
                speech_start_time = subclip.start + fade_duration
            else:
                # 后续片段有转场+淡入
                # 注意：add_slide_effect 的实现已经将 slide_duration 包含在了 subclip.start 中
                # 我们创建的 video_clips 音频部分是 [fade, audio, fade]，所以语音总是从 fade_duration 之后开始
                speech_start_time = subclip.start + fade_duration

            speech_end_time = speech_start_time + actual_audio_duration
            timestamps.append([speech_start_time, speech_end_time])
            print(f"片段 {i + 1}: 精确语音时间轴 [{speech_start_time:.3f}s - {speech_end_time:.3f}s]")
    else:
        print(
            f"❌ 错误：合成后的片段数量 ({len(composite_clip.clips)}) 与音频数量 ({len(actual_audio_durations)}) 不匹配！")
        # 此处可以考虑是否抛出异常或使用旧逻辑作为回退

    # --- 精确时间戳提取完毕 ---
    # Ensure final composite has the exact target size
    bg = ColorClip(size=(target_width, target_height), color=(0, 0, 0)).with_duration(composite_clip.duration)
    composite_clip = CompositeVideoClip([bg, composite_clip.with_position('center')])
    composite_clip = add_bottom_black_area(composite_clip, black_area_height=caption_config["area_height"])
    del caption_config["area_height"]
    max_caption_length = caption_config["max_length"]
    del caption_config["max_length"]

    # Check if captions are enabled
    enable_captions = caption_config.get("enable_captions", True)

    if enable_captions and timestamps:
        # 测试智能分割功能
        print("\n" + "=" * 50)
        print("测试智能分割功能")
        print("=" * 50)
        test_smart_splitting()

        # 验证音频与字幕的同步情况
        verify_audio_subtitle_sync(story_dir, timestamps)

        # 直接使用compose_video中已经正确计算的时间轴，避免双重计算
        corrected_timestamps = timestamps
        print(f"使用compose_video中已计算的时间轴，共 {len(corrected_timestamps)} 个时间轴")

        # 为新的按句子处理逻辑准备字幕文本
        if segmented_pages is not None:
            # 从segmented_pages中提取所有句子作为字幕文本
            sentence_captions = []
            for page_segments in segmented_pages:
                sentence_captions.extend(page_segments)

            print(f"句子级字幕数量: {len(sentence_captions)}, 时间轴数量: {len(corrected_timestamps)}")

            # 确保字幕数量与时间轴数量匹配
            if len(sentence_captions) != len(corrected_timestamps):
                print(
                    f"警告：句子级字幕数量({len(sentence_captions)})与时间轴数量({len(corrected_timestamps)})不匹配，正在调整...")

                # 取较小的数量，避免索引越界
                min_count = min(len(sentence_captions), len(corrected_timestamps))
                sentence_captions = sentence_captions[:min_count]
                corrected_timestamps = corrected_timestamps[:min_count]
                print(f"调整后：句子级字幕数量: {len(sentence_captions)}, 时间轴数量: {len(corrected_timestamps)}")

            # 使用修正后的时间轴和句子级字幕
            timestamps = corrected_timestamps
            captions = sentence_captions

            # 先生成字幕，获取实际的subtitle_items
            composite_clip, subtitle_items = add_caption(
                captions,
                timestamps,
                composite_clip,
                segmented_pages,
                **caption_config
            )

            # 使用实际的subtitle_items生成SRT文件，确保完全一致
            generate_srt_from_subtitle_items(subtitle_items, story_dir / "captions.srt")
            print(f"SRT文件已生成: {story_dir / 'captions.srt'}")
        else:
            # 使用修正后的时间轴
            timestamps = corrected_timestamps
            # 确保字幕数量与时间轴数量匹配
            print(f"页面级字幕数量: {len(captions)}, 时间轴数量: {len(timestamps)}")

            # 如果数量不匹配，进行调整
            if len(captions) != len(timestamps):
                print(f"警告：页面级字幕数量({len(captions)})与时间轴数量({len(timestamps)})不匹配，正在调整...")

                # 取较小的数量，避免索引越界
                min_count = min(len(captions), len(timestamps))
                captions = captions[:min_count]
                timestamps = timestamps[:min_count]
                print(f"调整后：页面级字幕数量: {len(captions)}, 时间轴数量: {len(timestamps)}")

            # 先生成字幕，获取实际的subtitle_items
            composite_clip, subtitle_items = add_caption(
                captions,
                timestamps,
                composite_clip,
                segmented_pages,
                **caption_config
            )

            # 使用实际的subtitle_items生成SRT文件，确保完全一致
            generate_srt_from_subtitle_items(subtitle_items, story_dir / "captions.srt")
            print(f"SRT文件已生成: {story_dir / 'captions.srt'}")

    if not enable_captions:
        print("Captions disabled - generating video without subtitles")

    # Write video with audio using improved method
    temp_video_path = save_path.__str__().replace('.mp4', '_temp_video.mp4')
    temp_audio_path = save_path.__str__().replace('.mp4', '_temp_audio.wav')

    try:
        print(f"Writing video to: {save_path}")
        print(f"Video duration: {composite_clip.duration:.2f}s")

        # Ensure audio has the correct fps and duration
        audio_clip = composite_clip.audio.with_fps(audio_sample_rate)

        # 提前打印所有调试信息
        print(f"Audio clip duration: {audio_clip.duration:.2f}s")
        print(f"Audio clip fps: {audio_clip.fps}")
        print(f"Writing audio to: {temp_audio_path}")
        print(f"Writing video to: {temp_video_path}")
        print(f"Final output: {save_path}")

        # 分别处理音频、视频和合并，每个都有独立的进度显示

        # 1. 写入音频文件
        print("=" * 50)
        print("步骤 1/3: 写入音频文件")
        print("=" * 50)

        try:
            # 使用更简单的音频写入参数
            audio_clip.write_audiofile(
                temp_audio_path,
                codec='pcm_s16le',  # 使用简单的PCM编码
                ffmpeg_params=['-ac', '2']  # 确保立体声
            )
            print("✓ 音频文件写入完成")
        except Exception as e:
            print(f"\n音频写入失败: {e}")
            print("尝试备用音频方法...")
            # 备用方法：使用更简单的参数
            audio_clip.write_audiofile(
                temp_audio_path,
                verbose=True,
                codec='mp3'  # 使用MP3编码
            )
            print("✓ 音频文件写入完成（备用方法）")

        # 2. 写入视频文件（以帧为单位显示进度）
        print("\n" + "=" * 50)
        print("步骤 2/3: 写入视频文件")
        print("=" * 50)

        # 计算总帧数
        total_frames = int(composite_clip.duration * fps)
        print(f"总帧数: {total_frames}")

        # 直接使用FFmpeg方法，避免moviepy卡住问题
        _write_video_with_ffmpeg_detailed(composite_clip, temp_video_path, fps, total_frames)
        print(f"\n✓ 视频文件写入完成 ({total_frames} 帧)")

        # 3. 合并音频和视频
        print("\n" + "=" * 50)
        print("步骤 3/3: 合并音频和视频")
        print("=" * 50)

        # Check if both files were created successfully
        import os
        if not os.path.exists(temp_video_path) or os.path.getsize(temp_video_path) == 0:
            raise Exception("视频文件未创建或为空")
        if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
            raise Exception("音频文件未创建或为空")

        print(f"视频文件大小: {os.path.getsize(temp_video_path)} 字节")
        print(f"音频文件大小: {os.path.getsize(temp_audio_path)} 字节")

        # 合并进度监控 - 基于文件存在性
        def merge_progress_monitor():
            """合并进度监控器 - 基于输出文件状态"""
            start_time = time.time()
            while not hasattr(merge_progress_monitor, 'stop'):
                elapsed = time.time() - start_time

                # 检查输出文件是否存在
                if os.path.exists(save_path.__str__()):
                    file_size = os.path.getsize(save_path.__str__())
                    print(f"\r合并进度: 完成 - {elapsed:.1f}s (输出文件: {file_size / 1024 / 1024:.1f}MB)", end='',
                          flush=True)
                    break
                else:
                    # 基于时间估算，但更保守
                    estimated_total = 60  # 增加到60秒
                    percent = min(95, int((elapsed / estimated_total) * 100))  # 最多显示95%
                    print(f"\r合并进度: {percent:.1f}% - {elapsed:.1f}s", end='', flush=True)

                time.sleep(0.5)

        print("开始合并音频和视频...")
        merge_thread = threading.Thread(target=merge_progress_monitor)
        merge_thread.daemon = True
        merge_thread.start()

        import subprocess
        try:
            # 方法1：使用copy编解码器（最快）
            cmd = [
                'ffmpeg',
                '-i', temp_video_path,
                '-i', temp_audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-shortest',  # 使用较短的流长度
                save_path.__str__()
            ]
            print(f"FFmpeg命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            merge_progress_monitor.stop = True
            merge_thread.join(timeout=1)

            print(f"\nFFmpeg返回码: {result.returncode}")
            if result.stderr:
                print(f"FFmpeg错误信息:\n{result.stderr}")

            if result.returncode == 0:
                print("✓ 音频视频合并成功!")
            else:
                raise Exception(f"FFmpeg失败，返回码 {result.returncode}")

        except subprocess.TimeoutExpired:
            print("\nFFmpeg超时，尝试备用方法...")
            # 备用方法
            cmd_alt = [
                'ffmpeg', '-y',
                '-i', temp_video_path,
                '-i', temp_audio_path,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-shortest',
                save_path.__str__()
            ]
            result = subprocess.run(cmd_alt, capture_output=True, text=True, timeout=300)

            merge_progress_monitor.stop = True
            merge_thread.join(timeout=1)

            print(f"\n备用FFmpeg返回码: {result.returncode}")
            if result.stderr:
                print(f"备用FFmpeg错误信息:\n{result.stderr}")

        except Exception as e:
            print(f"\nFFmpeg合并失败: {e}")
            raise

        print("\n" + "=" * 50)
        print("✓ 视频合成完成!")
        print("=" * 50)

        # Cleanup temporary files
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

    except Exception as e:
        print(f"Error in audio-video combination: {e}")
        # Fallback to original method
        print("Using fallback method...")
        try:
            composite_clip.write_videofile(save_path.__str__(),
                                           fps=fps,
                                           codec='libx264',
                                           audio_fps=audio_sample_rate,
                                           audio_codec=audio_codec,
                                           audio_bitrate='192k',
                                           )
        except Exception as fallback_error:
            print(f"Fallback method also failed: {fallback_error}")
            raise


@register_tool("slideshow_video_compose")
class SlideshowVideoComposeAgent:

    def __init__(self, cfg) -> None:
        self.cfg = cfg

    def adjust_caption_config(self, width, height, existing: dict | None = None):
        # Provide sane defaults based on resolution, but do NOT overwrite user-provided values
        existing = dict(existing or {})
        area_height_default = int(height * 0.06)
        fontsize_default = int((width + height) / 2 * 0.025)
        if "area_height" not in existing:
            existing["area_height"] = area_height_default
        if "fontsize" not in existing:
            existing["fontsize"] = fontsize_default
        return existing

    def call(self, params):
        import json
        height = params["height"]
        width = params["width"]
        pages = params["pages"]
        story_dir = Path(params["story_dir"])
        # Handle caption configuration safely
        if "caption" in params:
            params["caption"].update(self.adjust_caption_config(width, height))
        else:
            # If no caption config, create a default one
            params["caption"] = self.adjust_caption_config(width, height)

        # 优先从 script_data.json 读取 segmented_pages（如果存在且结构匹配）
        segmented_pages = None
        script_json = story_dir / "script_data.json"
        if script_json.exists():
            try:
                with open(script_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 常见结构1：{"segmented_pages": [["sent1", "sent2"], ...]}
                if isinstance(data, dict) and isinstance(data.get("segmented_pages"), list):
                    segmented_pages = data["segmented_pages"]
                # 常见结构2：{"pages": [{"segments": [...]}, ...]}
                elif isinstance(data, dict) and isinstance(data.get("pages"), list):
                    pages_list = data["pages"]
                    if all(isinstance(p, dict) and isinstance(p.get("segments"), list) for p in pages_list):
                        segmented_pages = [p.get("segments", []) for p in pages_list]
                # 常见结构3：根就是列表（已经是分段后的页面）
                elif isinstance(data, list) and all(isinstance(p, list) for p in data):
                    segmented_pages = data
                if segmented_pages is not None:
                    print(
                        f"从 script_data.json 读取 segmented_pages：{sum(len(s) for s in segmented_pages)} 个句子，{len(segmented_pages)} 个页面")
                else:
                    print("script_data.json 存在，但未找到可识别的 segmented_pages 结构，回退到参数/默认")
            except Exception as e:
                print(f"读取 script_data.json 失败：{e}，回退到参数/默认")
        # 若脚本文件不可用，则回退到 params 里的 segmented_pages（若有）

        compose_video(
            story_dir=Path(params["story_dir"]),
            save_path=Path(params["story_dir"]) / "output.mp4",
            captions=pages,
            num_pages=len(pages),
            fps=params["fps"],
            target_width=width,
            target_height=height,
            audio_sample_rate=params.get("audio_sample_rate", 44100),
            audio_codec=params.get("audio_codec", "aac"),
            caption_config=params["caption"],
            segmented_pages=segmented_pages,
            **params["slideshow_effect"]
        )
