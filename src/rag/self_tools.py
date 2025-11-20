"""Self-RAG tools for accessing KLoROS system information."""
import os
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Optional
import re


# Allowed filesystem roots for self-RAG
ALLOWED_ROOTS = [
    os.path.expanduser("~/.kloros"),
    "/home/kloros/src",
    "/home/kloros"
]

# Denied patterns for security
DENIED_PATTERNS = [
    "**/*.key",
    "**/*.pem",
    "**/.env",
    "**/*token*",
    "**/*secret*",
    "**/*password*",
    "**/.ssh/*",
    "**/id_rsa*",
    "**/credentials*"
]


def _is_path_allowed(path: Path) -> bool:
    """Check if path is within allowed roots and not denied.

    Args:
        path: Path to check

    Returns:
        True if allowed
    """
    try:
        resolved = path.resolve()

        # Check if within allowed roots
        in_allowed = any(
            str(resolved).startswith(str(Path(root).resolve()))
            for root in ALLOWED_ROOTS
        )

        if not in_allowed:
            return False

        # Check denied patterns
        for pattern in DENIED_PATTERNS:
            if fnmatch.fnmatch(str(resolved), pattern):
                return False

        return True

    except Exception:
        return False


def fs_search(
    pattern: str,
    roots: Optional[List[str]] = None,
    extensions: Optional[List[str]] = None,
    max_results: int = 30
) -> List[str]:
    """Search for files in allowed directories.

    Args:
        pattern: Filename pattern to search for
        roots: Custom roots to search (must be within ALLOWED_ROOTS)
        extensions: File extensions to filter (e.g., ['.py', '.yaml'])
        max_results: Maximum number of results

    Returns:
        List of matching file paths
    """
    search_roots = roots if roots else ALLOWED_ROOTS
    pattern_lower = pattern.lower()
    hits = []

    for root in search_roots:
        root_path = Path(os.path.expanduser(root))

        if not root_path.exists():
            continue

        try:
            for item in root_path.rglob("*"):
                if not item.is_file():
                    continue

                # Check extension filter
                if extensions and item.suffix not in extensions:
                    continue

                # Check pattern match
                if pattern_lower in item.name.lower():
                    if _is_path_allowed(item):
                        hits.append(str(item))

                        if len(hits) >= max_results:
                            return hits

        except PermissionError:
            continue

    return hits


def fs_read(
    path: str,
    byte_limit: int = 131072,
    redact_secrets: bool = True
) -> Dict[str, Any]:
    """Read file with safety checks and redaction.

    Args:
        path: File path to read
        byte_limit: Maximum bytes to read (default: 128KB)
        redact_secrets: Redact potential secrets

    Returns:
        Dict with 'text' or 'error' key
    """
    file_path = Path(os.path.expanduser(path))

    # Security check
    if not _is_path_allowed(file_path):
        return {"error": "access denied", "path": str(file_path)}

    if not file_path.exists():
        return {"error": "file not found", "path": str(file_path)}

    if not file_path.is_file():
        return {"error": "not a file", "path": str(file_path)}

    try:
        # Read with byte limit
        data = file_path.read_bytes()[:byte_limit]
        text = data.decode("utf-8", errors="ignore")

        # Redact potential secrets
        if redact_secrets:
            text = _redact_secrets(text)

        return {
            "path": str(file_path),
            "text": text,
            "size_bytes": len(data),
            "truncated": len(data) >= byte_limit
        }

    except Exception as e:
        return {"error": str(e), "path": str(file_path)}


def _redact_secrets(text: str) -> str:
    """Redact potential secrets from text.

    Args:
        text: Text to redact

    Returns:
        Redacted text
    """
    # Redact API keys, tokens, secrets
    patterns = [
        (r'(?:api[_-]?key|token|secret)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-]{16,})["\']?', '[REDACTED_TOKEN]'),
        (r'sk-[A-Za-z0-9]{20,}', '[REDACTED_SK]'),
        (r'password["\']?\s*[:=]\s*["\']?([^\s"\']+)["\']?', 'password="[REDACTED]"'),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def sys_status(sections: Optional[List[str]] = None) -> Dict[str, Any]:
    """Get system status information.

    Args:
        sections: Sections to include (versions, paths, config, all)

    Returns:
        System status dict
    """
    sections = sections or ["versions", "paths"]
    status = {}

    if "versions" in sections or "all" in sections:
        status["versions"] = {
            "kloros": "0.1.0",  # TODO: Read from version file
            "python": _get_python_version(),
            "components": {
                "agentflow": "active",
                "ace": "active",
                "petri": "active",
                "ra3": "active",
                "dream": "inactive",
                "toolforge": "inactive"
            }
        }

    if "paths" in sections or "all" in sections:
        status["paths"] = {
            "config": os.path.expanduser("~/.kloros"),
            "src": "/home/kloros/src",
            "logs": os.path.expanduser("~/.kloros/logs"),
            "reports": os.path.expanduser("~/.kloros/reports"),
            "chroma": os.path.expanduser("~/.kloros/chroma_data")
        }

    if "config" in sections or "all" in sections:
        config_path = Path(os.path.expanduser("~/.kloros/config.yaml"))
        if config_path.exists():
            try:
                from src.config import load_config
                config = load_config()
                status["config"] = {
                    "loaded": True,
                    "ace_enabled": config.get("ace", {}).get("k_retrieve") is not None,
                    "petri_enabled": config.get("petri", {}).get("enabled", False),
                    "ra3_enabled": config.get("ra3", {}).get("enabled", False)
                }
            except:
                status["config"] = {"loaded": False, "error": "failed to load"}
        else:
            status["config"] = {"loaded": False, "error": "not found"}

    return status


def _get_python_version() -> str:
    """Get Python version.

    Returns:
        Python version string
    """
    import sys
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def list_recent_logs(log_dir: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """List recent log files.

    Args:
        log_dir: Log directory (default: ~/.kloros/logs)
        limit: Maximum number of logs to return

    Returns:
        List of log file info dicts
    """
    log_dir = log_dir or os.path.expanduser("~/.kloros/logs")
    log_path = Path(log_dir)

    if not log_path.exists():
        return []

    logs = []
    for log_file in log_path.glob("*.jsonl"):
        if _is_path_allowed(log_file):
            stat = log_file.stat()
            logs.append({
                "path": str(log_file),
                "name": log_file.name,
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime
            })

    # Sort by modification time
    logs.sort(key=lambda x: x["modified"], reverse=True)

    return logs[:limit]
