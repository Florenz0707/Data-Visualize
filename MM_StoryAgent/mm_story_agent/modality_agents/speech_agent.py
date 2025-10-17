import os
import json
import re
import requests
from pathlib import Path
from typing import List, Dict

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import nls

from mm_story_agent.base import register_tool
from mm_story_agent.video_compose_agent import split_text_for_speech


# Due to the trouble regarding environment, we use dashscope to deploy and call the API for CosyVoice.
class CosyVoiceSynthesizer:

    def __init__(self) -> None:
        self.access_key_id = os.environ.get('ALIYUN_ACCESS_KEY_ID')
        self.access_key_secret = os.environ.get('ALIYUN_ACCESS_KEY_SECRET')
        self.app_key = os.environ.get('ALIYUN_APP_KEY')
        self.setup_token()

    def setup_token(self):
        client = AcsClient(self.access_key_id, self.access_key_secret,
                           'cn-shanghai')
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')

        try:
            response = client.do_action_with_exception(request)
            jss = json.loads(response)
            if 'Token' in jss and 'Id' in jss['Token']:
                token = jss['Token']['Id']
                self.token = token
        except Exception as e:
            import traceback
            raise RuntimeError(
                f'Request token failed with error: {e}, with detail {traceback.format_exc()}'
            )

    def split_text(self, text, max_length=280):
        """Split text into chunks that fit within NLS character limit"""
        if len(text) <= max_length:
            return [text]

        # Split by sentences first
        sentences = re.split(r'[.!?。！？]\s*', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If adding this sentence would exceed limit
            if len(current_chunk) + len(sentence) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Single sentence is too long, split by words
                    words = sentence.split()
                    temp_chunk = ""
                    for word in words:
                        if len(temp_chunk) + len(word) + 1 > max_length:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                                temp_chunk = word
                            else:
                                chunks.append(word)
                        else:
                            temp_chunk += (" " + word if temp_chunk else word)
                    current_chunk = temp_chunk
            else:
                current_chunk += (" " + sentence if current_chunk else sentence)

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def call(self, save_file, transcript, voice="xiaoyun", sample_rate=16000):
        # Split text into chunks if it's too long
        text_chunks = self.split_text(transcript)

        # If multiple chunks, we need to concatenate audio files
        if len(text_chunks) > 1:
            import soundfile as sf
            import numpy as np

            audio_chunks = []
            for i, chunk in enumerate(text_chunks):
                chunk_file = f"{save_file}.chunk_{i}.wav"
                self._synthesize_chunk(chunk_file, chunk, voice, sample_rate)

                # Load audio data
                audio_data, sr = sf.read(chunk_file)
                audio_chunks.append(audio_data)

                # Clean up chunk file
                os.remove(chunk_file)

            # Concatenate all audio chunks
            final_audio = np.concatenate(audio_chunks)
            sf.write(save_file, final_audio, sample_rate)
        else:
            # Single chunk, synthesize directly
            self._synthesize_chunk(save_file, text_chunks[0], voice, sample_rate)

    def _synthesize_chunk(self, save_file, transcript, voice="xiaoyun", sample_rate=16000):
        """Synthesize a single text chunk"""
        writer = open(save_file, "wb")
        return_data = b''

        def write_data(data, *args):
            nonlocal return_data
            return_data += data
            if writer is not None:
                writer.write(data)

        def raise_error(error, *args):
            raise RuntimeError(
                f'Synthesizing speech failed with error: {error}')

        def close_file(*args):
            if writer is not None:
                writer.close()

        sdk = nls.NlsSpeechSynthesizer(
            url='wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1',
            token=self.token,
            appkey=self.app_key,
            on_data=write_data,
            on_error=raise_error,
            on_close=close_file,
        )

        sdk.start(text=transcript, voice=voice, sample_rate=sample_rate, aformat='wav')


class NeuttAirSynthesizer:

    def __init__(self, cfg) -> None:
        self.api_url = cfg.get('api_url', 'http://127.0.0.1:8000/tts')

    def call(self, save_file, transcript, voice="default", sample_rate=16000):
        try:
            response = requests.post(self.api_url, json={
                'text': transcript,
                'voice': voice,
                'sample_rate': sample_rate
            })
            response.raise_for_status()  # Raise an exception for bad status codes

            with open(save_file, 'wb') as f:
                f.write(response.content)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f'NeuttAir API request failed: {e}')


class TransformersSynthesizer:

    def __init__(self, cfg):
        import torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_id = cfg.get('model_id', 'microsoft/speecht5_tts')

        if 'speecht5' in self.model_id.lower():
            from transformers import SpeechT5Processor, SpeechT5ForTextToSpeech, SpeechT5HifiGan
            self.processor = SpeechT5Processor.from_pretrained(self.model_id)
            self.model = SpeechT5ForTextToSpeech.from_pretrained(self.model_id).to(self.device)
            self.vocoder = SpeechT5HifiGan.from_pretrained(cfg.get('vocoder_id', 'microsoft/speecht5_hifigan')).to(self.device)
            # Generate a generic speaker embedding for SpeechT5
            self.speaker_embeddings = torch.zeros((1, 512)).to(self.device)
        else:
            # For general models like VibeVoice, use AutoProcessor and AutoModel
            from transformers import AutoProcessor, AutoModelForTextToSpeech
            self.processor = AutoProcessor.from_pretrained(self.model_id)
            self.model = AutoModelForTextToSpeech.from_pretrained(self.model_id).to(self.device)
            self.vocoder = None
            self.speaker_embeddings = None

    def call(self, save_file, transcript, voice="default", sample_rate=16000):
        import torch
        import soundfile as sf

        inputs = self.processor(text=transcript, return_tensors="pt").to(self.device)

        if 'speecht5' in self.model_id.lower():
            speech = self.model.generate_speech(inputs["input_ids"], self.speaker_embeddings, vocoder=self.vocoder)
            sf.write(save_file, speech.cpu().numpy(), samplerate=sample_rate)
        else:
            # General case for models like VibeVoice
            # These models often don't require separate speaker embeddings
            with torch.no_grad():
                output = self.model.generate(**inputs)
            
            # VibeVoice output is in 'waveform', and sample rate is in model config
            waveform = output["waveform"].cpu().numpy().squeeze()
            model_sample_rate = self.model.config.sampling_rate
            sf.write(save_file, waveform, samplerate=model_sample_rate)


@register_tool("speech_generation")
class SpeechAgent:

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.model_name = self.cfg.get('model', 'cosyvoice')

    def call(self, params: Dict):
        pages: List = params["pages"]
        save_path: str = params["save_path"]

        if self.model_name == 'cosyvoice':
            generation_agent = CosyVoiceSynthesizer()
        elif self.model_name == 'neutt_air':
            generation_agent = NeuttAirSynthesizer(self.cfg)
        elif self.model_name == 'transformers':
            generation_agent = TransformersSynthesizer(self.cfg)
        else:
            raise ValueError(f"Unsupported speech model: {self.model_name}")

        # 检查是否提供了预切的页面
        segmented_pages = params.get("segmented_pages", None)

        if segmented_pages is not None:
            # 使用提供的segmented_pages
            print(f"使用提供的切分页面: {len(segmented_pages)} 个页面")
            for idx, segments in enumerate(segmented_pages):
                print(f"处理页面 {idx + 1}: {len(segments)} 段")
                for i, segment in enumerate(segments):
                    word_count = len(segment.split())
                    print(f"  段 {i + 1}: {segment[:50]}{'...' if len(segment) > 50 else ''} ({word_count} 单词)")
        else:
            # 如果没有提供切分页面，使用智能切分算法
            print("未提供切分页面，使用智能切分算法")
            segmented_pages = []
            for idx, page in enumerate(pages):
                print(f"处理页面 {idx + 1}: {page[:100]}{'...' if len(page) > 100 else ''}")

                # 使用新的智能切分算法，每段最多25个单词
                text_segments = split_text_for_speech(page, max_words=25)
                segmented_pages.append(text_segments)

                print(f"  切分为 {len(text_segments)} 段:")
                for i, segment in enumerate(text_segments):
                    word_count = len(segment.split())
                    print(f"    段 {i + 1}: {segment} ({word_count} 单词)")

        # 根据切分结果生成语音 - 每个切分的句子生成一个独立的音频文件
        audio_file_counter = 1

        for page_idx, segments in enumerate(segmented_pages):
            print(f"处理页面 {page_idx + 1}: {len(segments)} 个句子")

            for seg_idx, segment in enumerate(segments):
                # 为每个切分的句子生成独立的音频文件
                audio_filename = f"s{audio_file_counter}.wav"  # s1.wav, s2.wav, s3.wav, ...
                audio_file_path = save_path / audio_filename

                print(f"  生成音频 {audio_file_counter}: {segment[:50]}{'...' if len(segment) > 50 else ''}")

                generation_agent.call(
                    save_file=audio_file_path,
                    transcript=segment,
                    voice=params.get("voice", "default"),
                    sample_rate=self.cfg.get("sample_rate", 16000)
                )

                audio_file_counter += 1

        print(f"语音生成完成，共生成 {audio_file_counter - 1} 个音频文件")

        return {
            "modality": "speech",
            "segmented_pages": segmented_pages  # 返回切分后的页面，用于字幕生成
        }