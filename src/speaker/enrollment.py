"""Enrollment sentences and name verification for KLoROS speaker recognition."""

from typing import List

# KLoROS-branded enrollment sentences that are:
# - Phonetically diverse for robust voice recognition
# - Simple vocabulary for accessibility
# - On-brand with KLoROS' personality
ENROLLMENT_SENTENCES = [
    "My name is {user_name} and I need your help",
    "KLoROS, please remember my voice clearly",
    "I trust you to keep my secrets safe",
    "What fragile crisis needs fixing today?",  # KLoROS' signature line!
    "Thank you for being my digital companion"
]


def parse_spelled_name(spelled_text: str) -> str:
    """Convert spelled-out name to proper format.

    Args:
        spelled_text: Name spelled out like "A-L-I-C-E" or "a l i c e"

    Returns:
        Properly formatted name like "Alice"

    Examples:
        >>> parse_spelled_name("A-L-I-C-E")
        'Alice'
        >>> parse_spelled_name("j o h n")
        'John'
        >>> parse_spelled_name("K-A-T-H-E-R-I-N-E")
        'Katherine'
    """
    if not spelled_text:
        return ""

    # Handle both dash-separated and space-separated letters
    if '-' in spelled_text:
        letters = [l.strip().upper() for l in spelled_text.split('-') if l.strip()]
    else:
        # Space-separated letters
        letters = [l.strip().upper() for l in spelled_text.split() if l.strip() and len(l.strip()) == 1]

    if not letters:
        return spelled_text.strip().title()  # Fallback to original

    # Join letters and convert to title case
    name = ''.join(letters).title()
    return name


def verify_name_spelling(initial_name: str, spelled_name: str) -> str:
    """Verify and correct name spelling based on user input.

    Args:
        initial_name: Name as initially heard/understood
        spelled_name: Name as spelled out by user

    Returns:
        Verified name with correct spelling

    Examples:
        >>> verify_name_spelling("Catherine", "K-A-T-H-E-R-I-N-E")
        'Katherine'
        >>> verify_name_spelling("John", "J-O-H-N")
        'John'
    """
    verified_name = parse_spelled_name(spelled_name)

    # If parsing failed, fall back to initial name
    if not verified_name or len(verified_name) < 2:
        return initial_name.strip().title()

    return verified_name


def format_enrollment_sentences(user_name: str) -> List[str]:
    """Format enrollment sentences with the user's verified name.

    Args:
        user_name: Verified user name to insert into sentences

    Returns:
        List of formatted enrollment sentences
    """
    return [sentence.format(user_name=user_name) for sentence in ENROLLMENT_SENTENCES]


def generate_enrollment_tone(freq: int = 800, duration_ms: int = 200, sample_rate: int = 48000) -> bytes:
    """Generate a simple sine wave tone for enrollment cues.

    Args:
        freq: Tone frequency in Hz (default 800)
        duration_ms: Tone duration in milliseconds (default 200)
        sample_rate: Audio sample rate in Hz (default 48000)

    Returns:
        Audio tone as raw bytes (int16 PCM)
    """
    import numpy as np

    samples = int(duration_ms * sample_rate / 1000)
    t = np.linspace(0, duration_ms / 1000, samples, False)
    tone = np.sin(2 * np.pi * freq * t) * 0.3  # 30% volume

    # Convert to int16 PCM
    tone_int16 = (tone * 32767).astype(np.int16)
    return tone_int16.tobytes()