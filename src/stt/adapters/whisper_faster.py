"""faster-whisper adapter for real-time STT with word timestamps.

This adapter uses faster-whisper (CTranslate2) which is 2-3x faster than
OpenAI Whisper and provides native word-level timestamps.

Installation:
    pip install faster-whisper

Recommended models for RTX 3060:
    - small.en (fast, good accuracy)
    - medium.en (slower but better accuracy)
"""
from typing import Dict, Any, List, Optional
import numpy as np

class FasterWhisperAdapter:
    """faster-whisper adapter for streaming STT with word timestamps."""

    def __init__(
        self,
        model_name: str = "small.en",
        device: str = "cuda",
        compute_type: str = "float16",
        chunk_seconds: float = 4.0,
        vad_filter: bool = True,
        beam_size: int = 1
    ):
        """Initialize faster-whisper adapter.

        Args:
            model_name: Model size (tiny.en, base.en, small.en, medium.en, large-v2, large-v3)
            device: Device to run on (cuda, cpu, auto)
            compute_type: Compute precision (float16, int8, int8_float16)
            chunk_seconds: Chunk length in seconds for streaming
            vad_filter: Whether to use VAD filtering
            beam_size: Beam size for decoding (1 = greedy, higher = more accurate but slower)
        """
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type
        )
        self.chunk_seconds = chunk_seconds
        self.vad_filter = vad_filter
        self.beam_size = beam_size
        self.lang_hint = "en"

    def start(self, lang_hint: Optional[str] = "en"):
        """Start transcription session.

        Args:
            lang_hint: Language hint for transcription
        """
        self.lang_hint = lang_hint or "en"

    def decode(self, pcm_tail: bytes) -> Dict[str, Any]:
        """Decode PCM audio to text with word timestamps.

        Args:
            pcm_tail: 16kHz mono int16 little-endian PCM audio

        Returns:
            Dict with 'words' key containing list of word dicts:
                - w: word text
                - start: start time in seconds
                - end: end time in seconds
                - conf: confidence score
        """
        # Convert PCM bytes to float32 array
        audio = np.frombuffer(pcm_tail, dtype=np.int16).astype("float32") / 32768.0

        # Transcribe with word timestamps
        segments, info = self.model.transcribe(
            audio,
            language=self.lang_hint,
            vad_filter=self.vad_filter,
            beam_size=self.beam_size,
            word_timestamps=True,
            chunk_length=self.chunk_seconds,
            no_speech_threshold=0.6,
        )

        # Extract words
        words: List[Dict[str, Any]] = []
        for seg in segments:
            for w in seg.words or []:
                words.append({
                    "w": w.word.strip(),
                    "start": float(w.start or seg.start),
                    "end": float(w.end or seg.end),
                    "conf": float(getattr(w, "probability", 0.7))
                })

        return {"words": words}

    def reset(self):
        """Reset transcription state."""
        pass

    def transcribe(self, pcm_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe audio to text (simplified interface).

        Args:
            pcm_data: PCM audio data (16-bit mono)
            sample_rate: Sample rate (must be 16000)

        Returns:
            Transcribed text
        """
        result = self.decode(pcm_data)
        return " ".join(w["w"] for w in result["words"])


class FasterWhisperChunker:
    """Alias for backward compatibility with Voice Loop pack."""

    def __init__(self, *args, **kwargs):
        self.adapter = FasterWhisperAdapter(*args, **kwargs)

    def start(self, lang_hint: Optional[str] = "en"):
        self.adapter.start(lang_hint)

    def decode(self, pcm_tail: bytes) -> Dict[str, Any]:
        return self.adapter.decode(pcm_tail)

    def reset(self):
        self.adapter.reset()
