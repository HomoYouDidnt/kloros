"""Faster-Whisper STT backend for KLoROS - CTranslate2-based, optimized for CPU/GPU."""

from __future__ import annotations

import os
import warnings
from typing import Optional, Union

import numpy as np

from .base import SttResult


class FasterWhisperSttBackend:
    """Faster-Whisper speech-to-text backend using CTranslate2."""

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
        compute_type: str = "auto",
        model_dir: Optional[str] = None,
        device_index: Union[int, list] = 0,
        cpu_threads: int = 4,
        num_workers: int = 1,
    ):
        """Initialize Faster-Whisper STT backend.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
            device: Device to run on ("auto", "cuda", "cpu")
            compute_type: Quantization type ("auto", "int8", "int8_float16", "float16", "float32")
            model_dir: Directory to store/load models from
            device_index: GPU device index to use
            cpu_threads: Number of CPU threads for inference
            num_workers: Number of workers for transcription
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError(
                "faster-whisper library not available. Install with: pip install faster-whisper"
            ) from e

        if device == "auto":
            device = self._auto_detect_device()

        self.device = device
        self.device_index = device_index if isinstance(device_index, int) else 0
        self.model_dir = model_dir or "/home/kloros/models/asr/whisper"
        self.cpu_threads = cpu_threads
        self.num_workers = num_workers

        if compute_type == "auto":
            compute_type = "int8" if device == "cpu" else "int8_float16"

        try:
            self._model = WhisperModel(
                model_size,
                device=device,
                device_index=self.device_index,
                compute_type=compute_type,
                download_root=self.model_dir,
                cpu_threads=cpu_threads,
                num_workers=num_workers,
            )
            print(f"[faster-whisper] Loaded {model_size} model on {device} ({compute_type})")
        except Exception as e:
            if device != "cpu":
                warnings.warn(f"GPU initialization failed: {e}. Falling back to CPU.")
                try:
                    self._model = WhisperModel(
                        model_size,
                        device="cpu",
                        compute_type="int8",
                        download_root=self.model_dir,
                        cpu_threads=cpu_threads,
                        num_workers=num_workers,
                    )
                    self.device = "cpu"
                    print(f"[faster-whisper] Loaded {model_size} model on CPU (fallback)")
                except Exception as cpu_e:
                    raise RuntimeError(
                        f"Failed to load Faster-Whisper model on CPU: {cpu_e}"
                    ) from cpu_e
            else:
                raise RuntimeError(f"Failed to load Faster-Whisper model: {e}") from e

        self.model_size = model_size
        self.compute_type = compute_type

    def transcribe(
        self, audio: np.ndarray, sample_rate: int, lang: Optional[str] = None
    ) -> SttResult:
        """Transcribe audio using Faster-Whisper.

        Args:
            audio: Audio samples as float32 mono array in range [-1, 1]
            sample_rate: Sample rate in Hz
            lang: Language code (e.g., "en", "es", "fr")

        Returns:
            SttResult with transcript and confidence
        """
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        if abs(sample_rate - 16000) > 100:
            import scipy.signal
            target_length = int(len(audio) * 16000 / sample_rate)
            audio = scipy.signal.resample(audio, target_length).astype(np.float32)

        segments, info = self._model.transcribe(
            audio,
            language=lang,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )

        segments_list = list(segments)

        transcript_parts = []
        confidences = []
        raw_segments = []

        for segment in segments_list:
            transcript_parts.append(segment.text)
            if hasattr(segment, 'avg_logprob'):
                prob = np.exp(segment.avg_logprob)
                confidences.append(min(1.0, max(0.0, prob)))
            raw_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "avg_logprob": getattr(segment, 'avg_logprob', None),
                "compression_ratio": getattr(segment, 'compression_ratio', None),
                "no_speech_prob": getattr(segment, 'no_speech_prob', None),
            })

        transcript = " ".join(transcript_parts).strip()
        confidence = sum(confidences) / len(confidences) if confidences else 0.8
        detected_lang = info.language if hasattr(info, 'language') else (lang or "en")

        return SttResult(
            transcript=transcript,
            confidence=confidence,
            lang=detected_lang,
            raw={
                "segments": raw_segments,
                "device": self.device,
                "language_probability": getattr(info, 'language_probability', None),
                "duration": getattr(info, 'duration', None),
            },
        )

    def _auto_detect_device(self) -> str:
        """Auto-detect the best available device."""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    def get_info(self) -> dict:
        """Get backend information."""
        return {
            "backend": "faster-whisper",
            "model_size": self.model_size,
            "device": self.device,
            "device_index": self.device_index,
            "compute_type": self.compute_type,
            "model_dir": self.model_dir,
            "cpu_threads": self.cpu_threads,
        }
