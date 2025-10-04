import os
import json
import re
from pathlib import Path
from typing import List, Dict

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import nls

from mm_story_agent.base import register_tool


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


@register_tool("cosyvoice_tts")
class CosyVoiceAgent:

    def __init__(self, cfg) -> None:
        self.cfg = cfg

    def call(self, params: Dict):
        pages: List = params["pages"]
        save_path: str = params["save_path"]
        generation_agent = CosyVoiceSynthesizer()

        for idx, page in enumerate(pages):
            generation_agent.call(
                save_file=save_path / f"p{idx + 1}.wav",
                transcript=page,
                voice=params.get("voice", "xiaoyun"),
                sample_rate=self.cfg.get("sample_rate", 16000)
            )

        return {
            "modality": "speech"
        }
