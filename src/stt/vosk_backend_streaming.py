"""Vosk-based STT backend for KLoROS."""

from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

from .base import SttResult


class VoskSttBackend:
    """Vosk speech-to-text backend with lazy initialization."""

    def __init__(self, model_dir: Optional[str] = None):
        """Initialize Vosk STT backend.

        Args:
            model_dir: Path to Vosk model directory

        Raises:
            RuntimeError: If vosk is unavailable or model cannot be loaded
        """
        # Lazy import vosk to avoid hard dependency
        try:
            import vosk
        except ImportError as e:
            raise RuntimeError("vosk library not available") from e

        # Determine model path
        if model_dir is None:
            model_dir = os.getenv("KLR_VOSK_MODEL_DIR") or os.path.expanduser("~/KLoROS/models/vosk/model")

        if not model_dir:
            raise RuntimeError(
                "vosk model directory not specified (set KLR_VOSK_MODEL_DIR or pass model_dir)"
            )

        if not os.path.exists(model_dir):
            raise RuntimeError(f"vosk model directory not found: {model_dir}")

        # Initialize Vosk model
        try:
            self._model = vosk.Model(model_dir)
        except Exception as e:
            raise RuntimeError(f"failed to load vosk model from {model_dir}: {e}") from e

        self._vosk = vosk
        # Streaming state for progressive transcription
        self._streaming_recognizer = None
        self._partial_transcript = ""
        self._streaming_mode = False
        self.model_dir = model_dir

    def transcribe(
        self, audio: np.ndarray, sample_rate: int, lang: Optional[str] = None
    ) -> SttResult:
        """Transcribe audio using Vosk.

        Args:
            audio: Audio samples as float32 mono array in range [-1, 1]
            sample_rate: Sample rate in Hz
            lang: Language code (ignored - model determines language)

        Returns:
            SttResult with transcript and confidence
        """
        # Convert float32 to PCM16 bytes for Vosk
        pcm16_audio = self._float32_to_pcm16(audio)

        # Create recognizer
        recognizer = self._vosk.KaldiRecognizer(self._model, sample_rate)

        # Feed audio data to recognizer
        recognizer.AcceptWaveform(pcm16_audio)

        # Get final result
        result_json = recognizer.FinalResult()
        result_data = json.loads(result_json)

        # Extract transcript and confidence
        transcript = result_data.get("text", "").strip()

        # Calculate average confidence from word-level confidences
        confidence = self._calculate_confidence(result_data)

        # Determine language (use provided lang or default)
        result_lang = lang or "en-US"

        return SttResult(
            transcript=transcript, confidence=confidence, lang=result_lang, raw=result_data
        )

    def _float32_to_pcm16(self, audio: np.ndarray) -> bytes:
        """Convert float32 audio to PCM16 bytes for Vosk.

        Args:
            audio: Audio samples as float32 array in range [-1, 1]

        Returns:
            PCM16 audio data as bytes
        """
        # Clip to valid range and convert to int16
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767).astype(np.int16)
        return pcm16.tobytes()

    def _calculate_confidence(self, result_data: dict) -> float:
        """Calculate overall confidence from Vosk result.

        Args:
            result_data: Parsed JSON result from Vosk

        Returns:
            Average confidence score (0.0-1.0)
        """
        # Get word-level results if available
        word_results = result_data.get("result", [])

        if not word_results:
            # No word-level data, use overall confidence if available
            return result_data.get("confidence", 1.0)

        # Calculate average confidence from words
        confidences = []
        for word_result in word_results:
            if isinstance(word_result, dict) and "conf" in word_result:
                confidences.append(word_result["conf"])

        if confidences:
            return sum(confidences) / len(confidences)
        else:
            return 1.0  # Default confidence if no data available

    def start_streaming(self, sample_rate: int = 16000) -> None:
        """Start streaming transcription mode.
        
        Args:
            sample_rate: Audio sample rate in Hz
        """
        self._streaming_recognizer = self._vosk.KaldiRecognizer(self._model, sample_rate)
        self._partial_transcript = ""
        self._streaming_mode = True
        print("🎯 Streaming transcription started", flush=True)

    def stream_chunk(self, audio_chunk: np.ndarray) -> str:
        """Process audio chunk and return partial transcript.
        
        Args:
            audio_chunk: Audio samples as float32 mono array
            
        Returns:
            Current partial transcript
        """
        if not self._streaming_mode or not self._streaming_recognizer:
            raise RuntimeError("Streaming mode not initialized - call start_streaming() first")
            
        # Convert chunk to PCM16
        pcm16_chunk = self._float32_to_pcm16(audio_chunk)
        
        # Process chunk
        if self._streaming_recognizer.AcceptWaveform(pcm16_chunk):
            # Got complete phrase - update transcript
            result = json.loads(self._streaming_recognizer.Result())
            new_text = result.get("text", "").strip()
            if new_text:
                self._partial_transcript += new_text + " "
                print(f"📝 {new_text}", flush=True)
        else:
            # Get partial result for real-time feedback
            partial = json.loads(self._streaming_recognizer.PartialResult())
            partial_text = partial.get("partial", "").strip()
            if partial_text:
                print(f"🎤 {partial_text}...", end="\r", flush=True)
                
        return self._partial_transcript.strip()

    def get_partial_result(self) -> str:
        """Get current partial transcript without processing new audio."""
        return self._partial_transcript.strip()

    def get_confidence(self) -> float:
        """Get current confidence score from streaming recognizer state.

        Returns:
            Current confidence score (0.0-1.0), or 0.8 as fallback
        """
        if not self._streaming_mode or not self._streaming_recognizer:
            return 0.8  # Default confidence when not streaming

        try:
            # Get current partial result with confidence data
            partial_result = json.loads(self._streaming_recognizer.PartialResult())

            # Try to extract confidence from partial result
            if "confidence" in partial_result:
                return float(partial_result["confidence"])

            # If no direct confidence, try to estimate from partial words
            if "partial" in partial_result:
                # This is a simplified confidence estimate
                # Real implementation could analyze word-level confidences
                partial_text = partial_result["partial"].strip()
                if len(partial_text) > 0:
                    return 0.85  # Higher confidence for active speech
                else:
                    return 0.7   # Lower confidence for silence/unclear

        except Exception:
            pass  # Fall back to default on any error

        return 0.8  # Default fallback confidence

    def end_streaming(self) -> SttResult:
        """End streaming mode and return final result."""
        if not self._streaming_mode or not self._streaming_recognizer:
            raise RuntimeError("Streaming mode not active")
            
        # Get final result
        final_result = json.loads(self._streaming_recognizer.FinalResult())
        final_text = final_result.get("text", "").strip()
        
        # Add any remaining text to transcript
        if final_text:
            self._partial_transcript += final_text
            
        # Calculate confidence
        confidence = self._calculate_confidence(final_result)
        
        # Clean up transcript
        full_transcript = self._partial_transcript.strip()
        
        # Reset streaming state
        self._streaming_recognizer = None
        self._partial_transcript = ""
        self._streaming_mode = False
        
        print(f"\n✅ Final transcript: {full_transcript}")
        
        return SttResult(
            transcript=full_transcript,
            confidence=confidence, 
            lang="en-US",
            raw=final_result
        )

    def get_info(self) -> dict:
        """Get backend information."""
        return {
            "backend": "vosk_streaming",
            "model_dir": self.model_dir,
            "streaming_active": self._streaming_mode,
            "partial_length": len(self._partial_transcript)
        }
