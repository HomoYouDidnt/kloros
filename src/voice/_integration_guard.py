"""Voice stack integration guard - prevents regressions to openai-whisper."""

def assert_voice_stack(asr, vad):
    """Assert voice stack is using production backends.

    Args:
        asr: STT backend instance
        vad: VAD backend instance

    Raises:
        AssertionError: If voice stack uses deprecated or mock backends
    """
    # Check ASR backend
    if asr is not None:
        backend_type = type(asr).__name__

        # Block openai-whisper usage
        if hasattr(asr, '_model'):
            model_type = type(asr._model).__name__
            if model_type == "Whisper":  # openai-whisper model class
                raise AssertionError(
                    f"Voice stack regression detected: Using deprecated openai-whisper backend. "
                    f"Use faster-whisper instead (WhisperModel from faster_whisper)"
                )

        # Verify faster-whisper
        if backend_type == "WhisperSttBackend":
            if not hasattr(asr, '_model'):
                raise AssertionError(
                    f"WhisperSttBackend missing _model attribute"
                )

            model_module = type(asr._model).__module__
            if "faster_whisper" not in model_module:
                raise AssertionError(
                    f"WhisperSttBackend not using faster-whisper: model module is {model_module}"
                )

    # Check VAD backend (ensure it's not None or mock)
    if vad is None:
        raise AssertionError(
            f"Voice stack missing VAD backend (None)"
        )

    # Block mock VAD
    vad_type = type(vad).__name__
    if "mock" in vad_type.lower():
        raise AssertionError(
            f"Voice stack using mock VAD backend: {vad_type}"
        )

    # All checks passed
    return True
