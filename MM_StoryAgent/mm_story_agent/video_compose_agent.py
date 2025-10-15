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
        
        # FFmpeg转换进度监控 - 使用更准确的方法
        def ffmpeg_progress_monitor():
            """FFmpeg转换进度监控 - 基于实际文件大小"""
            start_time = time.time()
            last_size = 0
            while not hasattr(ffmpeg_progress_monitor, 'stop'):
                elapsed = time.time() - start_time
                
                # 检查输出文件是否存在及其大小
                if os.path.exists(output_path):
                    current_size = os.path.getsize(output_path)
                    if current_size > last_size:
                        # 基于文件大小估算进度（粗略估算）
                        estimated_total_size = frame_count * 50000  # 假设每帧约50KB
                        percent = min(100, (current_size / estimated_total_size) * 100)
                        print(f"\rFFmpeg转换进度: {percent:.1f}% - {elapsed:.1f}s (文件大小: {current_size/1024:.1f}KB)", end='', flush=True)
                        last_size = current_size
                    else:
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
    """测试智能分割功能"""
    test_caption = "Under the moonlit sky, Timmy Turtle lay in his cozy bed, dreaming of center stage at the Forest Talent Show. His heart swelled with excitement as he imagined the spotlight on him, performing a dance that would leave the audience breathless."
    
    print("测试智能分割功能:")
    print(f"原始文本: {test_caption}")
    print(f"单词数: {len(test_caption.split())}")
    
    lines = split_caption_smart(test_caption, max_words=20)
    print(f"\n分割结果 ({len(lines)} 行):")
    for i, line in enumerate(lines, 1):
        word_count = len(line.split())
        print(f"  {i}. {line} ({word_count} 单词)")


def validate_captions_and_timestamps(captions: List, timestamps: List, story_dir: Path):
    """验证字幕和时间轴的匹配度"""
    print("\n" + "=" * 50)
    print("字幕和时间轴验证")
    print("=" * 50)
    
    print(f"字幕数量: {len(captions)}")
    print(f"时间轴数量: {len(timestamps)}")
    
    if len(captions) != len(timestamps):
        print(f"❌ 数量不匹配！字幕({len(captions)}) vs 时间轴({len(timestamps)})")
        return False
    
    print("✓ 数量匹配")
    
    # 检查每个字幕的时间轴和分割效果
    for i, (caption, timestamp) in enumerate(zip(captions, timestamps)):
        start_time, end_time = timestamp
        duration = end_time - start_time
        
        # 测试智能分割
        caption_lines = split_caption_smart(caption, max_words=20)
        
        print(f"页面 {i+1}:")
        print(f"  原始字幕: {caption[:50]}{'...' if len(caption) > 50 else ''}")
        print(f"  分割为 {len(caption_lines)} 行，每行最多20个单词")
        print(f"  时间轴: {start_time:.2f}s - {end_time:.2f}s (时长: {duration:.2f}s)")
        
        # 显示分割结果和时间分配
        line_duration = duration / len(caption_lines) if caption_lines else 0
        for j, line in enumerate(caption_lines):
            word_count = len(line.split())
            line_start = start_time + line_duration * j
            line_end = start_time + line_duration * (j + 1)
            print(f"    行 {j+1}: {line_start:.2f}s - {line_end:.2f}s: {line} ({word_count} 单词)")
        
        # 检查时间轴是否合理
        if duration <= 0:
            print(f"  ❌ 时间轴错误：时长为 {duration:.2f}s")
            return False
        elif duration > 60:  # 超过60秒可能有问题
            print(f"  ⚠️  时间轴过长：{duration:.2f}s")
    
    print("✓ 时间轴验证通过")
    return True


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
                duration, sr = librosa.get_duration(filename=str(speech_file), sr=None)
                print(f"  语音文件时长: {duration:.2f}s")
                print(f"  时间轴时长: {end_time - start_time:.2f}s")
                
                if abs(duration - (end_time - start_time)) > 0.5:
                    print(f"  ⚠️  时长不匹配！差异: {abs(duration - (end_time - start_time)):.2f}s")
                else:
                    print(f"  ✓ 时长匹配")
            except Exception as e:
                print(f"  ❌ 无法读取语音文件: {e}")
        else:
            print(f"  ❌ 语音文件不存在: {speech_file}")
    
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
                    actual_duration = librosa.get_duration(path=str(audio_file))
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
            actual_duration = librosa.get_duration(path=str(audio_file))
            
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
            print(f"  ❌ 无法读取语音文件 {audio_file}: {e}")
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
                 max_single_length: int = 30):
    """
    保留原函数用于向后兼容，但建议使用 generate_srt_from_subtitle_items
    """
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
            print(f"句子 {idx+1}: 直接使用语音生成的句子（避免重复切分）")
        else:
            # 只有在传统页面级流程中才进行智能分割
            max_words = caption_config.get("max_words_per_line", 20)
            caption_lines = split_caption_smart(caption_text, max_words=max_words)
            print(f"页面 {idx+1}: 使用智能分割")
        
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
        
        print(f"页面 {idx+1}: 语音时长 {total_duration:.2f}s, 分割为 {len(caption_lines)} 行, 每行显示 {line_duration:.2f}s, 过渡 {transition_duration:.2f}s")
        
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
                srt_path: Union[str, Path],
                timestamps: List,
                video_clip: VideoClip,
                segmented_pages: List = None,
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

    # Build subtitle timing and text - 使用智能分割，基于实际语音时长
    subtitle_items = []  # list of ((start, end), text)
    num_caps = len(timestamps)
    
    print(f"开始处理字幕：{num_caps} 个页面")
    
    for idx in range(num_caps):
        start_time, end_time = timestamps[idx]
        caption_text = captions[idx].strip()
        
        if not caption_text:
            print(f"页面 {idx+1}: 空字幕，跳过")
            continue
        
        # 当使用segmented_pages流程时，captions已经是句子级别，直接使用不再切分
        # 这避免了重复切分导致的字幕过度分割问题
        if segmented_pages is not None:
            # 在segmented_pages流程中，每个caption就是一个完整的句子，不需要再切分
            caption_lines = [caption_text]
            print(f"句子 {idx+1}: 直接使用语音生成的句子（避免重复切分）")
        else:
            # 只有在传统页面级流程中才进行智能分割
            caption_lines = split_caption_smart(caption_text, max_words=20)
            print(f"页面 {idx+1}: 使用智能分割")
        
        print(f"页面 {idx+1}: 原始文本 '{caption_text[:50]}{'...' if len(caption_text) > 50 else ''}'")
        print(f"  分割为 {len(caption_lines)} 行:")
        
        # 直接使用传入的时间轴，不进行内部重新计算
        # 这确保字幕时间轴与实际音频文件完全同步
        total_duration = end_time - start_time
        
        if len(caption_lines) > 1:
            # 简单平均分配时间给每行，不添加额外的过渡时间
            line_duration = total_duration / len(caption_lines)
        else:
            line_duration = total_duration
        
        print(f"  语音时长: {total_duration:.2f}s, 分割为 {len(caption_lines)} 行, 每行显示: {line_duration:.2f}s")
        
        for line_idx, line in enumerate(caption_lines):
            # 直接基于传入的时间轴计算每行时间，确保与音频同步
            line_start = start_time + line_duration * line_idx
            line_end = start_time + line_duration * (line_idx + 1)
            
            print(f"    行 {line_idx+1}: {line_start:.2f}s - {line_end:.2f}s: '{line}' ({len(line.split())} 单词)")
            subtitle_items.append(((line_start, line_end), line))
    
    print(f"字幕项目总数: {len(subtitle_items)}")

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
    return captioned_clip, subtitle_items


def split_keep_separator(text, separator):
    pattern = f'([{re.escape(separator)}])'
    pieces = re.split(pattern, text)
    return pieces


def split_text_for_speech(text, max_words=20):
    """
    为语音生成切分文本：优先保持完整句子，每句不超过max_words个单词
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
    
    # 定义标点符号分割点（按优先级排序，从强到弱）
    # 句号、感叹号、问号是强分割点
    # 分号、冒号是中等分割点  
    # 逗号是弱分割点
    strong_punctuation = r'[.!?]+'
    medium_punctuation = r'[;:]+'
    weak_punctuation = r'[,]+'
    
    # 第一步：按强标点符号分割，保持标点符号
    sentences = re.split(r'([.!?]+)', protected_text)
    # 重新组合句子和标点符号
    complete_sentences = []
    for i in range(0, len(sentences)-1, 2):
        if i+1 < len(sentences):
            sentence = (sentences[i] + sentences[i+1]).strip()
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
            for i in range(0, len(sub_sentences)-1, 2):
                if i+1 < len(sub_sentences):
                    sub_sentence = (sub_sentences[i] + sub_sentences[i+1]).strip()
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
                    for i in range(0, len(comma_parts)-1, 2):
                        if i+1 < len(comma_parts):
                            part = (comma_parts[i] + comma_parts[i+1]).strip()
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


def split_caption_smart(caption, max_words=20):
    """
    智能分割字幕：优先按标点符号分割，每句不超过max_words个单词
    这个函数保持向后兼容，内部调用新的语音切分算法
    """
    # 使用新的语音切分算法，但调整最大单词数
    return split_text_for_speech(caption, max_words)


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
    cur_duration = 0
    timestamps = []

    # 新的逻辑：按句子处理音频，而不是按页面
    if segmented_pages is not None:
        # 使用新的按句子处理逻辑
        print("使用新的按句子处理逻辑")
        audio_file_counter = 1
        
        for page_idx, segments in enumerate(segmented_pages):
            print(f"处理页面 {page_idx + 1}: {len(segments)} 个句子")
            
            for seg_idx, segment in enumerate(segments):
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
                    
                    # 计算时间轴 - 基于实际音频文件时长
                    # 添加slide_duration（除了第一个音频文件）
                    if audio_file_counter == 1:
                        # 第一个音频：只有fade_duration
                        speech_start_time = cur_duration + fade_duration
                        speech_end_time = speech_start_time + actual_audio_duration
                        cur_duration += fade_duration + actual_audio_duration + fade_duration
                    else:
                        # 其他音频：slide_duration + fade_duration
                        speech_start_time = cur_duration + slide_duration + fade_duration
                        speech_end_time = speech_start_time + actual_audio_duration
                        cur_duration += slide_duration + fade_duration + actual_audio_duration + fade_duration
                    
                    timestamps.append([speech_start_time, speech_end_time])
                    
                    print(f"  音频文件 {audio_file_counter} ({audio_filename}): {segment[:50]}{'...' if len(segment) > 50 else ''}")
                    print(f"    实际音频时长: {actual_audio_duration:.2f}s")
                    print(f"    字幕时间轴: [{speech_start_time:.2f}s - {speech_end_time:.2f}s]")
                    print(f"    总音频时长（含效果）: {speech_clip.duration:.2f}s")
                    
                    # 加载对应的图像（使用页面图像）
                    image_file = (image_dir / f"./p{page_idx + 1}.png").__str__()
                    image_clip = ImageClip(image_file)
                    image_clip = image_clip.set_duration(speech_clip.duration).set_fps(fps)
                    
                    # Fit image into target canvas without stretching (letterbox if needed)
                    img_w, img_h = image_clip.size
                    scale = min(target_width / img_w, target_height / img_h)
                    fitted_clip = image_clip.resize(scale)
                    image_clip = fitted_clip.on_color(size=(target_width, target_height), color=(0, 0, 0), pos='center')
                    image_clip = image_clip.crossfadein(fade_duration).crossfadeout(fade_duration)
                    
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
                    audio_clip = speech_clip.set_fps(audio_sample_rate)
                    
                    video_clip = image_clip.set_audio(audio_clip)
                    video_clips.append(video_clip)
                    
                    audio_file_counter += 1
                else:
                    print(f"  警告：音频文件不存在 {audio_file_path}")
    else:
        # 回退到原来的按页面处理逻辑
        print("使用原来的按页面处理逻辑")
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
            
            # 调试信息：打印每页的时间轴信息
            print(f"页面 {page}: 语音时长 {actual_speech_duration:.2f}s, 时间轴 [{speech_start_time:.2f}s - {speech_end_time:.2f}s]")
            print(f"  实际语音在speech_clip中的位置: fade_duration={fade_duration:.2f}s 后开始")

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
                print(f"警告：句子级字幕数量({len(sentence_captions)})与时间轴数量({len(corrected_timestamps)})不匹配，正在调整...")
                
                # 取较小的数量，避免索引越界
                min_count = min(len(sentence_captions), len(corrected_timestamps))
                sentence_captions = sentence_captions[:min_count]
                corrected_timestamps = corrected_timestamps[:min_count]
                print(f"调整后：句子级字幕数量: {len(sentence_captions)}, 时间轴数量: {len(corrected_timestamps)}")
            
            # 验证修正后的字幕和时间轴匹配度
            if not validate_captions_and_timestamps(sentence_captions, corrected_timestamps, story_dir):
                print("❌ 字幕和时间轴验证失败，跳过字幕生成")
                enable_captions = False
            else:
                # 使用修正后的时间轴和句子级字幕
                timestamps = corrected_timestamps
                captions = sentence_captions
                
                # 先生成字幕，获取实际的subtitle_items
                composite_clip, subtitle_items = add_caption(
                    captions,
                    story_dir / "captions.srt",
                    timestamps,
                    composite_clip,
                    segmented_pages,
                    max_caption_length,
                    **caption_config
                )
                
                # 使用实际的subtitle_items生成SRT文件，确保完全一致
                generate_srt_from_subtitle_items(subtitle_items, story_dir / "captions.srt")
                print(f"SRT文件已生成: {story_dir / 'captions.srt'}")
        else:
            # 回退到原来的页面级字幕处理
            if not validate_captions_and_timestamps(captions, corrected_timestamps, story_dir):
                print("❌ 字幕和时间轴验证失败，跳过字幕生成")
                enable_captions = False
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
                    story_dir / "captions.srt",
                    timestamps,
                    composite_clip,
                    segmented_pages,
                    max_caption_length,
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
        
        # 合并进度监控 - 基于文件存在性
        def merge_progress_monitor():
            """合并进度监控器 - 基于输出文件状态"""
            start_time = time.time()
            while not hasattr(merge_progress_monitor, 'stop'):
                elapsed = time.time() - start_time
                
                # 检查输出文件是否存在
                if os.path.exists(save_path.__str__()):
                    file_size = os.path.getsize(save_path.__str__())
                    print(f"\r合并进度: 完成 - {elapsed:.1f}s (输出文件: {file_size/1024/1024:.1f}MB)", end='', flush=True)
                    break
                else:
                    # 基于时间估算，但更保守
                    estimated_total = 60  # 增加到60秒
                    percent = min(95, (elapsed / estimated_total) * 100)  # 最多显示95%
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
        
        # 获取切分后的页面信息（如果存在）
        segmented_pages = params.get("segmented_pages", None)
        
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
