#!/usr/bin/env python3
"""
Streaming voice features for low-latency interaction.

Salvaged from kloros_voice_streaming.py (2025-11-25).

These features reduce perceived latency by pipelining:
- LLM response streaming with sentence-by-sentence TTS
- Real-time STT with partial transcript updates

Integration: These can be used as drop-in replacements for batch methods
in the main voice service when KLR_STREAMING_MODE=1.
"""

import json
import os
import logging
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)


class StreamingLLMResponse:
    """
    Stream LLM tokens and trigger TTS on sentence boundaries.

    Instead of waiting for full response, speaks sentence-by-sentence
    as tokens arrive. Reduces perceived latency significantly.

    Usage:
        streamer = StreamingLLMResponse(
            ollama_url="http://localhost:11434/api/generate",
            model="llama3.2",
            speak_callback=voice_service.speak
        )
        full_response = streamer.stream_response(context)
    """

    def __init__(
        self,
        ollama_url: str,
        model: str,
        speak_callback: Callable[[str], None],
        min_sentence_length: int = 20,
        timeout: int = 60
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.speak_callback = speak_callback
        self.min_sentence_length = min_sentence_length
        self.timeout = timeout
        self.sentence_endings = {'.', '!', '?'}

    def stream_response(self, context: str, num_ctx: int = 4096) -> str:
        """
        Stream LLM tokens and speak sentence-by-sentence.

        Args:
            context: The prompt/context to send to LLM
            num_ctx: Context window size

        Returns:
            Complete response text
        """
        buffer = ""
        complete_response = ""

        try:
            r = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": context,
                    "stream": True,
                    "options": {
                        "temperature": 0.8,
                        "top_p": 0.9,
                        "repeat_penalty": 1.1,
                        "num_ctx": num_ctx
                    }
                },
                stream=True,
                timeout=self.timeout,
            )

            if r.status_code != 200:
                return f"Error: Ollama HTTP {r.status_code}"

            for line in r.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    buffer += token
                    complete_response += token

                    if token.strip() and token.strip()[-1] in self.sentence_endings:
                        sentence = buffer.strip()
                        if len(sentence) > self.min_sentence_length:
                            logger.debug(f"[streaming] Sentence complete, queuing TTS: {sentence[:50]}...")
                            self.speak_callback(sentence)
                            buffer = ""

                    if chunk.get("done", False):
                        break

                except json.JSONDecodeError as e:
                    logger.warning(f"[streaming] JSON decode error: {e}")
                    continue

            if buffer.strip():
                logger.debug(f"[streaming] Final buffer, queuing TTS: {buffer.strip()[:50]}...")
                self.speak_callback(buffer.strip())

            return complete_response.strip()

        except requests.RequestException as e:
            return f"Ollama error: {e}"


class StreamingSTT:
    """
    Real-time STT with partial transcript updates.

    Instead of batch transcription after recording completes,
    provides partial results as speech is captured.

    Requires STT backend that supports streaming (e.g., VoskSttBackend).

    Usage:
        streamer = StreamingSTT(stt_backend, sample_rate=16000)
        streamer.start()

        # In audio callback:
        partial = streamer.feed_audio(audio_chunk)
        if partial:
            print(f"Partial: {partial}")

        final_transcript = streamer.stop()
    """

    def __init__(self, stt_backend, sample_rate: int = 16000):
        self.stt_backend = stt_backend
        self.sample_rate = sample_rate
        self.streaming_active = False
        self.last_partial = ""

    def start(self) -> bool:
        """Start streaming STT session."""
        if not hasattr(self.stt_backend, 'start_streaming'):
            logger.warning("[streaming_stt] Backend doesn't support streaming")
            return False

        try:
            self.stt_backend.start_streaming(self.sample_rate)
            self.streaming_active = True
            self.last_partial = ""
            logger.debug("[streaming_stt] Started streaming session")
            return True
        except Exception as e:
            logger.error(f"[streaming_stt] Failed to start: {e}")
            return False

    def feed_audio(self, audio_chunk: bytes) -> Optional[str]:
        """
        Feed audio chunk and get partial transcript if available.

        Args:
            audio_chunk: Raw PCM audio bytes

        Returns:
            Partial transcript if updated, None otherwise
        """
        if not self.streaming_active:
            return None

        try:
            if hasattr(self.stt_backend, 'feed_audio'):
                result = self.stt_backend.feed_audio(audio_chunk)
                if result and result != self.last_partial:
                    self.last_partial = result
                    return result
        except Exception as e:
            logger.warning(f"[streaming_stt] Feed error: {e}")

        return None

    def stop(self) -> str:
        """
        Stop streaming and get final transcript.

        Returns:
            Final transcript text
        """
        if not self.streaming_active:
            return self.last_partial

        try:
            if hasattr(self.stt_backend, 'end_streaming'):
                final = self.stt_backend.end_streaming()
                self.streaming_active = False
                logger.debug(f"[streaming_stt] Final transcript: {final[:50] if final else '(empty)'}...")
                return final or self.last_partial
        except Exception as e:
            logger.error(f"[streaming_stt] Failed to get final: {e}")

        self.streaming_active = False
        return self.last_partial


def is_streaming_enabled() -> bool:
    """Check if streaming mode is enabled via environment."""
    return os.getenv("KLR_STREAMING_MODE", "0") == "1"


def is_streaming_tts_enabled() -> bool:
    """Check if streaming TTS is enabled via environment."""
    return os.getenv("KLR_ENABLE_STREAMING_TTS", "0") == "1"
