from pathlib import Path
from typing import List, Union
import random
import re
from datetime import timedelta

from tqdm import trange, tqdm
import numpy as np
import librosa
import cv2
from zhon.hanzi import punctuation as zh_punc
from moviepy.editor import ImageClip, AudioFileClip, \
    CompositeVideoClip, ColorClip, VideoFileClip, VideoClip, TextClip, concatenate_audioclips
import moviepy.video.compositing.transitions as transfx
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.video.tools.subtitles import SubtitlesClip
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import signal
import platform
from contextlib import contextmanager

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
                print(f"\r写入帧进度: {i+1}/{frame_count} 帧 ({percent:.1f}%) - {elapsed:.1f}s", end='', flush=True)
        
        frame_write_progress()
        print(f"\n✓ 帧写入完成")
        
        # 使用 FFmpeg 将图像序列转换为视频，带进度显示
        print("使用FFmpeg转换帧为视频...")
        
        # FFmpeg转换进度监控
        def ffmpeg_progress_monitor():
            """FFmpeg转换进度监控"""
            start_time = time.time()
            while not hasattr(ffmpeg_progress_monitor, 'stop'):
                elapsed = time.time() - start_time
                # 估算转换时间（通常比写入快）
                estimated_total = frame_count / 20  # 假设20fps转换速度
                percent = min(100, (elapsed / estimated_total) * 100)
                print(f"\rFFmpeg转换进度: {percent:.1f}% - {elapsed:.1f}s", end='', flush=True)
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

def generate_srt(timestamps: List,
                 captions: List,
                 save_path: Union[str, Path],
                 max_single_length: int = 30):
    def format_time(seconds: float) -> str:
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        millis = int((td.total_seconds() - total_seconds) * 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

    srt_content = []
    num_caps = len(timestamps)

    for idx in range(num_caps):
        start_time, end_time = timestamps[idx]
        caption_chunks = split_caption(captions[idx], max_single_length).split("\n")
        num_chunks = len(caption_chunks)

        if num_chunks == 0:
            continue

        segment_duration = (end_time - start_time) / num_chunks

        for chunk_idx, chunk in enumerate(caption_chunks):
            chunk_start_time = start_time + segment_duration * chunk_idx
            chunk_end_time = start_time + segment_duration * (chunk_idx + 1)
            start_time_str = format_time(chunk_start_time)
            end_time_str = format_time(chunk_end_time)
            srt_content.append(f"{len(srt_content) // 2 + 1}\n{start_time_str} --> {end_time_str}\n{chunk}\n\n")

    with open(save_path, 'w') as srt_file:
        srt_file.writelines(srt_content)


def add_caption(captions: List,
                srt_path: Union[str, Path],
                timestamps: List,
                video_clip: VideoClip,
                max_single_length: int = 30,
                workers: int = 4,
                **caption_config):
    # Configure ImageMagick path for MoviePy
    import os
    import moviepy.config as config

    imagemagick_path = r'D:\ImageMagick-7.1.2-Q16-HDRI\magick.exe'
    os.environ['IMAGEMAGICK_BINARY'] = imagemagick_path
    try:
        config.change_settings({'IMAGEMAGICK_BINARY': imagemagick_path})
        print(f"ImageMagick configured: {imagemagick_path}")
    except Exception as e:
        print(f"ImageMagick config warning: {e}")

    # Build per-chunk subtitle timing and text (same logic as SRT)
    subtitle_items = []  # list of ((start, end), text)
    num_caps = len(timestamps)
    for idx in range(num_caps):
        start_time, end_time = timestamps[idx]
        caption_chunks = split_caption(captions[idx], max_single_length).split("\n")
        if not caption_chunks:
            continue
        segment_duration = (end_time - start_time) / len(caption_chunks)
        for chunk_idx, chunk in enumerate(caption_chunks):
            chunk_start_time = start_time + segment_duration * chunk_idx
            chunk_end_time = start_time + segment_duration * (chunk_idx + 1)
            subtitle_items.append(((chunk_start_time, chunk_end_time), chunk))

    # Pre-render unique texts in parallel to speed up creation
    unique_texts = sorted({text for _, text in subtitle_items})

    def render_text_clip(text: str) -> TextClip:
        return TextClip(text, **caption_config)

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
                        text_to_clip[text] = TextClip(text, fontsize=caption_config.get('fontsize', 24), color=caption_config.get('color', 'white'))
                    except Exception:
                        # As a last resort, skip this text
                        text_to_clip[text] = TextClip("", fontsize=caption_config.get('fontsize', 24), color=caption_config.get('color', 'white'))

    # Construct subtitles from text, using cached pre-rendered clips
    def make_textclip_from_cache(txt: str) -> TextClip:
        clip = text_to_clip.get(txt)
        if clip is None:
            clip = TextClip(txt, **caption_config)
            text_to_clip[txt] = clip
        return clip

    subtitles = SubtitlesClip(subtitle_items, make_textclip=make_textclip_from_cache)
    captioned_clip = CompositeVideoClip([video_clip,
                                         subtitles.set_position(("center", "bottom"), relative=True)])
    return captioned_clip


def split_keep_separator(text, separator):
    pattern = f'([{re.escape(separator)}])'
    pieces = re.split(pattern, text)
    return pieces


def split_caption(caption, max_length=30):
    lines = []
    if ord(caption[0]) >= ord("a") and ord(caption[0]) <= ord("z") or ord(caption[0]) >= ord("A") and ord(
            caption[0]) <= ord("Z"):
        words = caption.split(" ")
        current_words = []
        for word in words:
            if len(" ".join(current_words + [word])) <= max_length:
                current_words += [word]
            else:
                if current_words:
                    lines.append(" ".join(current_words))
                    current_words = []

        if current_words:
            lines.append(" ".join(current_words))
    else:
        sentences = split_keep_separator(caption, zh_punc)
        current_line = ""
        for sentence in sentences:
            if len(current_line + sentence) <= max_length:
                current_line += sentence
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                if sentence.startswith(tuple(zh_punc)):
                    if lines:
                        lines[-1] += sentence[0]
                    current_line = sentence[1:]
                else:
                    current_line = sentence

        if current_line:
            lines.append(current_line.strip())

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
    extended_clip = CompositeVideoClip([clip, black_bar.set_position(("center", "bottom"))])
    return extended_clip


def add_zoom_effect(clip, speed=1.0, mode='in', position='center', fps=None):
    if fps is None:
        fps = getattr(clip, 'fps', 24)
    duration = clip.duration
    total_frames = int(duration * fps)

    def main(getframe, t):
        frame = getframe(t)
        h, w = frame.shape[: 2]
        i = t * fps
        if mode == 'out':
            i = total_frames - i
        zoom = 1 + (i * ((0.1 * speed) / total_frames))
        positions = {'center': [(w - (w * zoom)) / 2, (h - (h * zoom)) / 2],
                     'left': [0, (h - (h * zoom)) / 2],
                     'right': [(w - (w * zoom)), (h - (h * zoom)) / 2],
                     'top': [(w - (w * zoom)) / 2, 0],
                     'topleft': [0, 0],
                     'topright': [(w - (w * zoom)), 0],
                     'bottom': [(w - (w * zoom)) / 2, (h - (h * zoom))],
                     'bottomleft': [0, (h - (h * zoom))],
                     'bottomright': [(w - (w * zoom)), (h - (h * zoom))]}
        tx, ty = positions[position]
        M = np.array([[zoom, 0, tx], [0, zoom, ty]])
        frame = cv2.warpAffine(frame, M, (w, h))
        return frame

    return clip.fl(main)


def add_move_effect(clip, direction="left", move_raito=0.95):
    orig_width = clip.size[0]
    orig_height = clip.size[1]

    new_width = int(orig_width / move_raito)
    new_height = int(orig_height / move_raito)
    clip = clip.resize(width=new_width, height=new_height)

    if direction == "left":
        start_position = (0, 0)
        end_position = (orig_width - new_width, 0)
    elif direction == "right":
        start_position = (orig_width - new_width, 0)
        end_position = (0, 0)

    duration = clip.duration
    moving_clip = clip.set_position(
        lambda t: (start_position[0] + (
                end_position[0] - start_position[0]) / duration * t, start_position[1])
    )

    final_clip = CompositeVideoClip([moving_clip], size=(orig_width, orig_height))

    return final_clip


def add_slide_effect(clips, slide_duration):
    ####### CAUTION: requires at least `slide_duration` of silence at the end of each clip #######
    durations = [clip.duration for clip in clips]
    first_clip = CompositeVideoClip(
        [clips[0].fx(transfx.slide_out, duration=slide_duration, side="left")]
    ).set_start(0)

    slide_out_sides = ["left"]
    videos = [first_clip]

    out_to_in_mapping = {"left": "right", "right": "left"}

    for idx, clip in enumerate(clips[1: -1], start=1):
        # For all other clips in the middle, we need them to slide in to the previous clip and out for the next one

        # determine `slide_in_side` according to the `slide_out_side` of the previous clip
        slide_in_side = out_to_in_mapping[slide_out_sides[-1]]

        slide_out_side = "left" if random.random() <= 0.5 else "right"
        slide_out_sides.append(slide_out_side)

        videos.append(
            (
                CompositeVideoClip(
                    [clip.fx(transfx.slide_in, duration=slide_duration, side=slide_in_side)]
                )
                .set_start(sum(durations[:idx]) - (slide_duration) * idx)
                .fx(transfx.slide_out, duration=slide_duration, side=slide_out_side)
            )
        )

    last_clip = CompositeVideoClip(
        [clips[-1].fx(transfx.slide_in, duration=slide_duration, side=out_to_in_mapping[slide_out_sides[-1]])]
    ).set_start(sum(durations[:-1]) - slide_duration * (len(clips) - 1))
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
    cur_duration = 0
    timestamps = []

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
            speech_files = list(speech_dir.glob(f"p{page}_*.wav"))
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
        
        speech_end_time = speech_start_time + actual_speech_duration
        timestamps.append([speech_start_time, speech_end_time])

        # Update current duration for next iteration
        cur_duration += speech_clip.duration

        speech_array, _ = librosa.core.load(speech_file, sr=None)
        speech_rms = librosa.feature.rms(y=speech_array)[0].mean()

        # set image as the main content, align the duration
        image_file = (image_dir / f"./p{page}.png").__str__()
        image_clip = ImageClip(image_file)
        image_clip = image_clip.set_duration(speech_clip.duration).set_fps(fps)

        # Fit image into target canvas without stretching (letterbox if needed)
        img_w, img_h = image_clip.size
        scale = min(target_width / img_w, target_height / img_h)
        fitted_clip = image_clip.resize(scale)
        image_clip = fitted_clip.on_color(size=(target_width, target_height), color=(0, 0, 0), pos='center')
        image_clip = image_clip.crossfadein(fade_duration).crossfadeout(fade_duration)

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
        audio_clip = speech_clip.set_fps(audio_sample_rate)

        video_clip = image_clip.set_audio(audio_clip)
        video_clips.append(video_clip)

        # audio_durations.append(audio_clip.duration)

    # final_clip = concatenate_videoclips(video_clips, method="compose")
    composite_clip = add_slide_effect(video_clips, slide_duration=slide_duration)
    # Ensure final composite has the exact target size
    composite_clip = composite_clip.on_color(size=(target_width, target_height), color=(0, 0, 0), pos='center')
    composite_clip = add_bottom_black_area(composite_clip, black_area_height=caption_config["area_height"])
    del caption_config["area_height"]
    max_caption_length = caption_config["max_length"]
    del caption_config["max_length"]
    
    # Check if captions are enabled
    enable_captions = caption_config.get("enable_captions", True)
    
    if enable_captions and captions and timestamps:
        composite_clip = add_caption(
            captions,
            story_dir / "captions.srt",
            timestamps,
            composite_clip,
            max_caption_length,
            **caption_config
        )
    else:
        print("Captions disabled - generating video without subtitles")


    # Write video with audio using improved method
    temp_video_path = save_path.__str__().replace('.mp4', '_temp_video.mp4')
    temp_audio_path = save_path.__str__().replace('.mp4', '_temp_audio.wav')
    
    try:
        print(f"Writing video to: {save_path}")
        print(f"Video duration: {composite_clip.duration:.2f}s")
        
        # Ensure audio has the correct fps and duration
        audio_clip = composite_clip.audio.set_fps(audio_sample_rate)
        
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
                verbose=True,  # 启用详细输出显示进度
                logger=None,
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
        print("使用直接FFmpeg方法写入视频（避免moviepy卡住问题）...")
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
        
        # 合并进度监控
        def merge_progress_monitor():
            """合并进度监控器"""
            start_time = time.time()
            while not hasattr(merge_progress_monitor, 'stop'):
                elapsed = time.time() - start_time
                # 合并通常很快，估算30秒内完成
                estimated_total = 30
                percent = min(100, (elapsed / estimated_total) * 100)
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
                'ffmpeg', '-y',
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

    def adjust_caption_config(self, width, height):
        area_height = int(height * 0.06)
        fontsize = int((width + height) / 2 * 0.025)
        return {
            "fontsize": fontsize,
            "area_height": area_height
        }

    def call(self, params):
        height = params["height"]
        width = params["width"]
        pages = params["pages"]
        # Handle caption configuration safely
        if "caption" in params:
            params["caption"].update(self.adjust_caption_config(width, height))
        else:
            # If no caption config, create a default one
            params["caption"] = self.adjust_caption_config(width, height)
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
            **params["slideshow_effect"]
        )
