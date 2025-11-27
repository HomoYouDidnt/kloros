"""Text ingress for sending prompts to KLoROS."""
import json
import subprocess

import requests

from .util import cfg


def send_text_prompt(text: str) -> dict:
    """
    Send text prompt to KLoROS.

    Supports both HTTP and CLI modes.

    Args:
        text: User prompt text

    Returns:
        dict with result (final_text, latency_ms, tool_calls)
    """
    mode = cfg("ingress_mode")

    if mode == "http":
        url = cfg("ingress_http_url")
        r = requests.post(url, json={"text": text}, timeout=30)
        r.raise_for_status()
        return r.json()

    elif mode == "cli":
        bin_path = cfg("ingress_cli_bin")
        p = subprocess.run(
            [bin_path, text],
            capture_output=True,
            text=True,
            check=True
        )
        try:
            return json.loads(p.stdout.strip())
        except Exception:
            return {"ok": True, "raw": p.stdout}

    else:
        raise RuntimeError(f"Unknown ingress_mode={mode}")
