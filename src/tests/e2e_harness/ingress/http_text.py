#!/usr/bin/env python3
"""HTTP text ingress for KLoROS E2E testing."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

# Add KLoROS to path
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.kloros_voice import KLoROS

app = FastAPI()
kloros_instance: KLoROS | None = None


class IngestPayload(BaseModel):
    text: str


@app.on_event("startup")
def startup():
    """Initialize KLoROS instance on startup."""
    global kloros_instance
    print("[http_text] Initializing KLoROS instance...")
    kloros_instance = KLoROS()
    print("[http_text] KLoROS initialized successfully")


@app.post("/ingest-text")
def ingest_text(payload: IngestPayload):
    """
    Ingest text as if it were a user utterance.

    Runs through normal KLoROS chat pipeline and returns metrics.
    """
    if not kloros_instance:
        return {"ok": False, "error": "KLoROS not initialized"}

    t_start = time.time()

    try:
        # Run through normal chat pipeline
        response = kloros_instance.chat(payload.text)

        latency_ms = int((time.time() - t_start) * 1000)

        # Extract metrics from last turn if available
        tool_calls = 0
        if hasattr(kloros_instance, '_last_tool_calls'):
            tool_calls = kloros_instance._last_tool_calls

        return {
            "ok": True,
            "result": {
                "final_text": response,
                "latency_ms": latency_ms,
                "tool_calls": tool_calls
            }
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "kloros_initialized": kloros_instance is not None
    }


if __name__ == "__main__":
    import uvicorn

    print("[http_text] Starting HTTP text ingress on http://127.0.0.1:8124")
    print("[http_text] Test with: curl -X POST http://127.0.0.1:8124/ingest-text -H 'Content-Type: application/json' -d '{\"text\":\"system diagnostic\"}'")

    uvicorn.run(app, host="127.0.0.1", port=8124, log_level="info")
