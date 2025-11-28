import json
import logging
import os
import datetime as dt
import re

LOGGER = logging.getLogger("kloros.tools")
LOGGER.setLevel(logging.INFO)

_log_path = os.environ.get("KLR_STRUCTURED_LOG", "/var/log/kloros/structured.jsonl")
_log_fallback = os.path.expanduser("~/.kloros/logs/structured.jsonl")

try:
    os.makedirs(os.path.dirname(_log_path), exist_ok=True)
    _handler = logging.FileHandler(_log_path)
except (PermissionError, OSError):
    _log_path = _log_fallback
    os.makedirs(os.path.dirname(_log_path), exist_ok=True)
    _handler = logging.FileHandler(_log_path)

_handler.setFormatter(logging.Formatter("%(message)s"))
LOGGER.addHandler(_handler)


# Secret redaction patterns (raw strings to avoid escape sequence warnings)
SECRET_PATTERNS = [
    (r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'}\s,]{8,})(["\']?)', r'\1****\3'),
    (r'(token["\']?\s*[:=]\s*["\']?)([^"\'}\s,]{8,})(["\']?)', r'\1****\3'),
    (r'(auth["\']?\s*[:=]\s*["\']?)([^"\'}\s,]{8,})(["\']?)', r'\1****\3'),
    (r'(password["\']?\s*[:=]\s*["\']?)([^"\'}\s,]{4,})(["\']?)', r'\1****\3'),
    (r'(secret["\']?\s*[:=]\s*["\']?)([^"\'}\s,]{8,})(["\']?)', r'\1****\3'),
    (r'(bearer\s+)([^\s,}]{8,})', r'\1****'),
    (r'(basic\s+)([^\s,}]{8,})', r'\1****'),
]


def redact_secrets(data):
    """
    Redact sensitive fields from data before logging.

    Args:
        data: Dict or string to redact

    Returns:
        Redacted data
    """
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            # Redact keys that look sensitive
            key_lower = key.lower()
            if any(secret in key_lower for secret in ['api_key', 'token', 'auth', 'password', 'secret', 'credential']):
                redacted[key] = "****"
            elif isinstance(value, dict):
                redacted[key] = redact_secrets(value)
            elif isinstance(value, list):
                redacted[key] = [redact_secrets(item) if isinstance(item, (dict, str)) else item for item in value]
            elif isinstance(value, str):
                redacted[key] = redact_secrets_str(value)
            else:
                redacted[key] = value
        return redacted
    elif isinstance(data, str):
        return redact_secrets_str(data)
    else:
        return data


def redact_secrets_str(text):
    """
    Redact secrets from string using pattern matching.

    Args:
        text: String to redact

    Returns:
        Redacted string
    """
    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def log(event: str, **fields):
    """Log a structured event in JSON format with secret redaction."""
    payload = {
        "ts": dt.datetime.utcnow().isoformat() + "Z",
        "event": event,
        **fields
    }

    # Redact secrets before logging
    redacted_payload = redact_secrets(payload)

    LOGGER.info(json.dumps(redacted_payload))
