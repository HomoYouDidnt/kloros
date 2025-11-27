"""
KLoROS Voice Interface Services.

Infrastructure services for voice I/O - audio capture, STT, TTS.
These are services (not cognitive agents) that handle voice I/O infrastructure.

Services:
    audio_io        - Audio capture/playback via PulseAudio
    stt_service     - Speech-to-text transcription (VOSK/Whisper hybrid)
    tts_service     - Text-to-speech synthesis (Piper)
    gateway         - Voice gateway coordinator
    intent_service  - Intent classification (command routing)
    emotion_service - Sentiment/emotion analysis
    session_service - Conversation session management
    knowledge_service - RAG retrieval for voice context
    llm_service     - LLM integration (backend)

    voice_daemon    - Unified daemon that starts all services

Helpers:
    half_duplex     - Anti-echo coordination
    streaming       - Streaming response helpers

Usage:
    # Run unified daemon:
    python -m kloros.interfaces.voice.voice_daemon

    # Or run individual services:
    python -m kloros.interfaces.voice.stt_service
"""

from .base import SpeakerBackend, SpeakerResult, create_speaker_backend

__all__ = [
    "SpeakerBackend",
    "SpeakerResult",
    "create_speaker_backend",
]
