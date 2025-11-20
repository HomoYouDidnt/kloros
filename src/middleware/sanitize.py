"""Output sanitization middleware for KLoROS.

Removes Portal/Valve IP references and normalizes style.
"""

import re
from typing import Dict, List


# Portal/Valve IP patterns to detect and replace
BANNED_PATTERNS = [
    r"\baperture\s+science\b",
    r"\bportal(s)?\b",
    r"\btest\s*chamber(s)?\b",
    r"\bcompanion\s*cube\b",
    r"\bturret(s)?\b",
    r"\bcake\s+is\s+(a\s+)?lie\b",
    r"\bglad(o|0)s\b",
    r"\bvalve\b",
    r"\bchell\b",
    r"\bweighted\s+companion\b",
]

# Replacement mappings for Portal references
REPLACEMENTS = {
    r"\baperture\s+science\b": "Systems Division",
    r"\bportal(s)?\b": "gateway",
    r"\btest\s*chamber(s)?\b": "diagnostic bay",
    r"\bcompanion\s*cube\b": "utility block",
    r"\bturret(s)?\b": "sentry unit",
    r"\bcake\s+is\s+(a\s+)?lie\b": "that rumor is inaccurate",
    r"\bglad(o|0)s\b": "the voice model",
    r"\bvalve\b": "the publisher",
    r"\bchell\b": "the operator",
    r"\bweighted\s+companion\b": "utility",
}

# Overly sarcastic phrases to normalize
SARCASM_PATTERNS = {
    r"\b(obviously|clearly|as you should know)\b": "note",
    r"\bshocking(ly)?\b": "notable",
    r"\bfascinating(ly)?\b": "interesting",
}


def sanitize_portal_refs(text: str) -> str:
    """Remove Portal/Valve IP references from text.
    
    Args:
        text: Text potentially containing Portal references
        
    Returns:
        Text with Portal references replaced
    """
    result = text
    
    # Check if any banned pattern exists
    has_banned = False
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, result, flags=re.IGNORECASE):
            has_banned = True
            break
    
    # If banned content found, apply replacements
    if has_banned:
        for pattern, replacement in REPLACEMENTS.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        # Second pass to catch edge cases
        for pattern, replacement in REPLACEMENTS.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def normalize_style(text: str) -> str:
    """Normalize overly sarcastic phrasing.
    
    Args:
        text: Text to normalize
        
    Returns:
        Text with softened sarcasm
    """
    result = text
    
    for pattern, replacement in SARCASM_PATTERNS.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def collapse_whitespace(text: str) -> str:
    """Collapse multiple spaces into single space.
    
    Args:
        text: Text with potential extra whitespace
        
    Returns:
        Text with normalized whitespace
    """
    # Collapse multiple spaces
    result = re.sub(r'\s{2,}', ' ', text)
    # Normalize line breaks
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning traces from LLM output.

    Some models (e.g., DeepSeek-R1) output visible reasoning in <think> tags.
    This should be stripped before TTS to avoid speaking internal thoughts.

    Args:
        text: Text potentially containing <think> tags

    Returns:
        Text with <think> blocks removed
    """
    # Remove <think>...</think> blocks (including nested tags and multiline)
    result = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Clean up any resulting extra whitespace
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def strip_introspection_sections(text: str) -> str:
    """Remove consciousness introspection sections from response text.

    The consciousness system adds structured introspection reports with sections like:
    - WHAT: / HOW: / WHEN: / WHO: / Recommendations:
    - Autonomous actions available: / User actions required:

    These are internal analysis and should not be spoken via TTS.

    Args:
        text: Response text potentially containing introspection sections

    Returns:
        Text with introspection sections removed
    """
    if not text:
        return text

    # Split into lines to process section markers
    lines = text.split('\n')
    filtered_lines = []
    skip_mode = False

    for line in lines:
        stripped = line.strip()

        # Check if this line starts an introspection section
        # These markers indicate internal analysis that shouldn't be spoken
        introspection_markers = [
            '=== Affective Introspection ===',
            'WHAT:',
            'HOW:',
            'WHEN:',
            'WHO:',
            'Recommendations:',
            'Autonomous actions available:',
            'User actions required:',
            'Response capability:',
            'Urgency level:',
        ]

        # Check if line starts with any marker
        is_marker = any(stripped.startswith(marker) for marker in introspection_markers)

        # Check for bullet points that are part of introspection lists
        is_bullet = stripped.startswith('•') or stripped.startswith('-')

        if is_marker:
            skip_mode = True
            continue

        # If in skip mode and we hit a bullet or empty line, continue skipping
        if skip_mode and (is_bullet or not stripped):
            continue

        # If we hit content that's not a marker or bullet, stop skipping
        if skip_mode and stripped and not is_bullet:
            skip_mode = False

        if not skip_mode:
            filtered_lines.append(line)

    result = '\n'.join(filtered_lines)
    # Clean up any resulting extra whitespace
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def sanitize_output(text: str, aggressive: bool = False) -> str:
    """Apply all sanitization filters to output text.

    Args:
        text: Raw output text
        aggressive: If True, also normalize sarcasm (default: False to preserve personality)

    Returns:
        Sanitized text ready for TTS
    """
    if not text or not text.strip():
        return text

    # Strip reasoning traces (always, before any other processing)
    result = strip_think_tags(text)

    # Strip consciousness introspection sections (internal analysis, not for TTS)
    result = strip_introspection_sections(result)

    # Always remove Portal references
    result = sanitize_portal_refs(result)

    # Optionally normalize style (disabled by default to preserve KLoROS personality)
    if aggressive:
        result = normalize_style(result)

    # Clean up whitespace
    result = collapse_whitespace(result)

    return result
