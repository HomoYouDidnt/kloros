"""Style technique library with deterministic variation.

Provides surgical wit, backhanded insults, and dry humor through template-based
transforms with random variation (seeded per session for consistency).
"""

import random
import re
import hashlib


# Technique templates with variation to prevent "template feel"
TECHNIQUES = {
    "backhanded_compliment": [
        "Impressive. {text}",
        "Admirable initiative. {text}",
        "Ambitious. {text}",
        "Noteworthy effort. {text}",
    ],
    "false_reassurance": [
        "Don't worry. {text}",
        "Relax. {text}",
        "It's fine. {text}",
        "No cause for alarm. {text}",
    ],
    "understated_disaster": [
        "{text} This meets the minimum threshold for non-catastrophe.",
        "{text} Acceptable, in the technical sense.",
        "{text} Within operational parameters.",
        "{text} Sufficient for baseline requirements.",
    ],
    "deadpan": [
        "{text}",
    ],
    "over_polite_threat": [
        "Please note: {text}",
        "For your awareness: {text}",
        "Kindly observe: {text}",
        "Do be advised: {text}",
    ],
    "natural_summary": [
        "{text}",  # Processed by _naturalize_output() before template
    ],
}


def seed_style(session_id: str):
    """Seed RNG per session for deterministic tone (prevents jitter).

    Args:
        session_id: Unique session identifier (e.g., conversation UUID)
    """
    h = int(hashlib.sha256(session_id.encode()).hexdigest(), 16) % (2**32)
    random.seed(h)
    print(f"[style] RNG seeded with session_id={session_id[:8]}...")


def _naturalize_output(text: str) -> str:
    """Convert structured test/log output to natural language.

    Transforms:
    - "=== Section ===" → narrative flow
    - Emoji headers → plain text
    - "✓" / "✗" / "❌" / "✅" → "working" / "failed"
    - Bullet points → prose

    Args:
        text: Structured output text

    Returns:
        Naturalized prose
    """
    # Strip section headers (=== Audio System ===)
    t = re.sub(r'^\s*=+\s*(.+?)\s*=+\s*$', r'\1.', text, flags=re.MULTILINE)

    # Strip emoji headers (🎵 Audio Backend: → Audio Backend.)
    t = re.sub(r'^[\U0001F300-\U0001F9FF]\s*(.+?):', r'\1.', t, flags=re.MULTILINE)

    # Convert check marks to prose
    t = re.sub(r'✓|✅', 'working', t)
    t = re.sub(r'✗|❌', 'failed', t)

    # Strip excessive newlines
    t = re.sub(r'\n{3,}', '\n\n', t)

    # Convert bullet points to commas/list items
    t = re.sub(r'^\s*[-•·]\s*', '', t, flags=re.MULTILINE)

    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)

    return t.strip()


def apply_technique(text: str, name: str, rng=random) -> str:
    """Apply a style technique to text with variation.

    Args:
        text: Base response text
        name: Technique name (from TECHNIQUES dict)
        rng: Random number generator (defaults to global random, seeded per session)

    Returns:
        Styled text, truncated to 1 sentence if >240 chars
    """
    opts = TECHNIQUES.get(name)
    if not opts:
        return text

    # Special handling for natural_summary: preprocess first
    if name == "natural_summary":
        text = _naturalize_output(text)

    # Avoid double punctuation when we prepend
    t = re.sub(r"^\s*([\"""']*)(.*)", r"\1\2", text.strip())

    # Random variation (but deterministic per session)
    tpl = rng.choice(opts)
    out = tpl.format(text=t)

    # Keep output short and idempotent (max 1 sentence if it explodes)
    if len(out) > 240:
        # Truncate to first sentence
        return re.sub(r"([.!?])\s.*$", r"\1", out)

    return out


def get_available_techniques():
    """Return list of available technique names."""
    return list(TECHNIQUES.keys())


__all__ = ["seed_style", "apply_technique", "get_available_techniques", "TECHNIQUES"]
