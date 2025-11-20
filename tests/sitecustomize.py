"""Pre-import module stubbing for test mode.

When KLR_TEST_MODE=1, this module pre-stubs heavyweight dependencies
BEFORE any project code imports them. This prevents import-time side
effects and resource allocation across pytest-xdist workers.

How it works:
- pytest automatically adds tests/ to sys.path
- Python imports sitecustomize.py automatically if found on sys.path
- This runs BEFORE any test collection or execution
- Ensures stubs win the import race across all workers
"""

import os
import sys
import types


def _stub_module(name, attrs=None):
    """Create a minimal stub module and register it in sys.modules."""
    m = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(m, k, v)
    sys.modules[name] = m


if os.getenv("KLR_TEST_MODE") == "1":
    # Preempt heavy deps across ALL workers, before any project imports

    # Vosk: 500MB+ model loading
    _stub_module("vosk", {"Model": object, "KaldiRecognizer": object})

    # sounddevice: triggers ALSA/PulseAudio initialization
    _stub_module("sounddevice", {
        "Stream": object,
        "InputStream": object,
        "OutputStream": object,
        "query_devices": lambda: [],
        "default": type("obj", (object,), {"device": (None, None)})()
    })

    # Add other expensive/side-effecty modules as needed:
    # _stub_module("piper")
    # _stub_module("mcp_client")
    # _stub_module("torch")
    # _stub_module("transformers")
