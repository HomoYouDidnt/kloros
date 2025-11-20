def passes_constraints(domain: str, metrics: dict, params: dict) -> bool:
    """Check if candidate passes domain-specific constraints."""

    if domain == "asr_tts":
        # Voice assistant quality gates
        if metrics.get("vad_boundary_ms", 999) > 50:
            return False  # VAD boundary too high
        if metrics.get("wer", 1.0) > 0.25:
            return False  # Word error rate too high

    # Add more domain-specific constraints as needed
    # if domain == "conversation":
    #     if metrics.get("coherence_score", 0.0) < 0.6:
    #         return False

    return True
