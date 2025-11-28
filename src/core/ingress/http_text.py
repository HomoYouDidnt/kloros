#!/usr/bin/env python3
"""HTTP text ingress for KLoROS E2E testing."""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

# Add KLoROS to path
_repo_root = Path(__file__).resolve().parents[1]  # /home/kloros
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Change to KLoROS directory so relative imports work
os.chdir(_repo_root)

from src.kloros_voice import KLoROS
from src.mqtt_client import KLoROSMQTTClient

app = FastAPI()
kloros_instance: KLoROS | None = None
mqtt_client: KLoROSMQTTClient | None = None


class IngestPayload(BaseModel):
    text: str
    session_id: str | None = None


class MemorySeedPayload(BaseModel):
    session_id: str
    semantic: list[str] = []
    episodic: list[str] = []
    ttl_s: int | None = None


class ExperimentRunPayload(BaseModel):
    """Payload for running experiments on the host with GPU access."""
    experiment_type: str
    params: dict
    output_file: str


class DeploymentPayload(BaseModel):
    """Payload for deploying an improvement."""
    improvement: dict


@app.on_event("startup")
def startup():
    """Initialize KLoROS instance on startup."""
    global kloros_instance, mqtt_client
    print("[http_text] Initializing KLoROS instance...")
    kloros_instance = KLoROS()
    print("[http_text] KLoROS initialized successfully")

    # Initialize MQTT client
    mqtt_client = KLoROSMQTTClient()
    print(f"[http_text] MQTT client initialized (enabled: {mqtt_client.enabled})")


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
        # Publish turn_started event
        if mqtt_client:
            mqtt_client.publish_turn_started(payload.text)

        # Run through normal chat pipeline
        response = kloros_instance.chat(payload.text)

        latency_ms = int((time.time() - t_start) * 1000)

        # Extract metrics from last turn if available
        tool_calls = 0
        if hasattr(kloros_instance, '_last_tool_calls'):
            tool_calls = kloros_instance._last_tool_calls

        # Publish turn_completed event
        if mqtt_client:
            mqtt_client.publish_turn_completed(
                user_text=payload.text,
                response_text=response,
                latency_ms=latency_ms,
                tool_calls=tool_calls
            )

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


@app.post("/ingest-audio")
async def ingest_audio(file: UploadFile = File(...)):
    """
    Ingest audio WAV file, transcribe via STT, then process via chat pipeline.

    Accepts WAV file upload, transcribes it using KLoROS's STT backend,
    then passes the transcript through the normal chat pipeline.
    """
    if not kloros_instance:
        return {"ok": False, "error": "KLoROS not initialized"}

    if not kloros_instance.stt_backend:
        return {"ok": False, "error": "STT backend not initialized"}

    t_start = time.time()

    try:
        # Read WAV file
        audio_bytes = await file.read()

        # Load WAV using scipy
        try:
            from scipy.io import wavfile

            # Convert bytes to file-like object
            audio_io = io.BytesIO(audio_bytes)
            sample_rate, audio_data = wavfile.read(audio_io)

            # Convert to float32 in range [-1, 1]
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_data = audio_data.astype(np.float32) / 2147483648.0
            elif audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Ensure mono
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)

        except Exception as e:
            return {"ok": False, "error": f"Failed to load WAV file: {e}"}

        # Transcribe using STT backend
        try:
            stt_result = kloros_instance.stt_backend.transcribe(
                audio=audio_data,
                sample_rate=sample_rate,
                lang=None  # Auto-detect
            )
            transcript = stt_result.text if hasattr(stt_result, 'text') else str(stt_result)

            if not transcript or not transcript.strip():
                return {"ok": False, "error": "STT returned empty transcript"}

        except Exception as e:
            return {"ok": False, "error": f"STT transcription failed: {e}"}

        # Pass transcript through chat pipeline
        try:
            # Publish turn_started event
            if mqtt_client:
                mqtt_client.publish_turn_started(transcript)

            response = kloros_instance.chat(transcript)
            latency_ms = int((time.time() - t_start) * 1000)

            # Extract metrics
            tool_calls = 0
            if hasattr(kloros_instance, '_last_tool_calls'):
                tool_calls = kloros_instance._last_tool_calls

            # Publish turn_completed event
            if mqtt_client:
                mqtt_client.publish_turn_completed(
                    user_text=transcript,
                    response_text=response,
                    latency_ms=latency_ms,
                    tool_calls=tool_calls
                )

            return {
                "ok": True,
                "result": {
                    "transcript": transcript,
                    "final_text": response,
                    "latency_ms": latency_ms,
                    "tool_calls": tool_calls
                }
            }
        except Exception as e:
            return {"ok": False, "error": f"Chat pipeline failed: {e}"}

    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@app.post("/memory/seed")
def seed_memory(payload: MemorySeedPayload):
    """
    Seed semantic and episodic memory for a session.

    This endpoint allows dialog tests to pre-populate KLoROS memory with facts
    and context before running evaluation dialogues.

    Semantic memories are stored in long-term memory (with optional TTL).
    Episodic memories are stored as session context.
    """
    if not kloros_instance:
        return {"ok": False, "error": "KLoROS not initialized"}

    try:
        # For now, we'll add semantic facts to memory using the memory system
        # and episodic as conversational context

        if hasattr(kloros_instance, 'memory_system') and kloros_instance.memory_system:
            mem_sys = kloros_instance.memory_system

            # Add semantic memories (long-term facts)
            for fact in payload.semantic:
                try:
                    # Store semantic fact in memory with optional TTL
                    mem_sys.store_semantic(
                        content=fact,
                        session_id=payload.session_id,
                        ttl_seconds=payload.ttl_s
                    )
                except Exception as e:
                    print(f"[memory/seed] Warning: Failed to store semantic fact '{fact}': {e}")

            # Add episodic memories (session context)
            for episode in payload.episodic:
                try:
                    # Store episodic memory linked to session
                    mem_sys.store_episodic(
                        content=episode,
                        session_id=payload.session_id
                    )
                except Exception as e:
                    print(f"[memory/seed] Warning: Failed to store episodic memory '{episode}': {e}")

        return {
            "ok": True,
            "session_id": payload.session_id,
            "semantic_count": len(payload.semantic),
            "episodic_count": len(payload.episodic),
            "ttl_s": payload.ttl_s
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


@app.post("/experiment/run")
def run_experiment(payload: ExperimentRunPayload):
    """
    Execute an experiment script on the host with full GPU access.

    This endpoint allows the dashboard sidecar to trigger experiments that require
    GPU access and the KLoROS environment (like HeteroVRAM).
    """
    import subprocess
    import json

    exp_type = payload.experiment_type
    params = payload.params
    output_file = payload.output_file

    try:
        if exp_type == "gpu.hetero_vram_utilization":
            # Extract parameters
            model = params.get("model", "Qwen/Qwen2.5-7B-Instruct")
            prompt = params.get("prompt", "You are KLoROS. Briefly explain heterogenous multi-GPU execution.")
            max_new = int(params.get("max_new_tokens", 128))
            mm0 = params.get("mm0", "9GiB")
            mm1 = params.get("mm1", "22GiB")
            split = int(params.get("split_at", 8))

            # Build command
            script_path = str(_repo_root / "src" / "experiments" / "hetero_vram" / "run_hetero_vram.py")
            python_path = str(_repo_root / ".venv" / "bin" / "python")

            cmd = [
                python_path, script_path,
                "--model", model,
                "--prompt", prompt,
                "--max_new_tokens", str(max_new),
                "--mm0", mm0,
                "--mm1", mm1,
                "--split_at", str(split),
                "--out", output_file
            ]

            # Execute with timeout
            result = subprocess.run(
                cmd,
                cwd=str(_repo_root),
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            # Parse results
            results = []
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            results.append(json.loads(line))

            # Extract summary
            summary = next((r for r in results if r.get("event") == "summary"), {})
            flags = summary.get("flags", {})

            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "results": results,
                "flags": flags,
                "output_file": output_file
            }
        else:
            return {
                "ok": False,
                "error": f"Unknown experiment type: {exp_type}"
            }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "Experiment timed out after 10 minutes"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


@app.get("/attestation")
def attestation():
    """
    Runtime attestation endpoint - returns current model IDs and configuration.

    This allows E2E tests to verify that the running instance matches expected config.
    Includes governance information about tool synthesis status.
    """
    try:
        from src.ssot.loader import get_ssot
        ssot = get_ssot()
        attestation_data = ssot.attestation()

        # Add governance information
        try:
            from src.tool_synthesis.governance import SynthesisGovernance
            governance = SynthesisGovernance()

            quarantined = governance.list_quarantined_tools()
            promoted = governance.list_promoted_tools()

            attestation_data["governance"] = {
                "enabled": True,
                "quarantined_tools": len(quarantined),
                "promoted_tools": len(promoted),
                "daily_quota_remaining": 2,
                "weekly_quota_remaining": 6,
                "quarantined_tool_names": [t["name"] for t in quarantined[:5]],
                "promoted_tool_names": [t["name"] for t in promoted[:5]]
            }
        except Exception as gov_error:
            attestation_data["governance"] = {
                "enabled": False,
                "error": str(gov_error)
            }

        return attestation_data

    except Exception as e:
        return {
            "error": str(e),
            "note": "SSOT not available - run kloros-vec-rebuild"
        }


@app.post("/api/deploy")
def deploy_improvement(payload: DeploymentPayload):
    """
    Deploy an approved improvement to the system.

    This endpoint triggers the Alert Manager's deployment pipeline to apply
    the improvement and update system configuration.
    """
    if not kloros_instance:
        return {"ok": False, "error": "KLoROS not initialized"}

    if not kloros_instance.alert_manager:
        return {"ok": False, "error": "Alert Manager not available"}

    if not kloros_instance.alert_manager.deployer:
        return {"ok": False, "error": "Deployment pipeline not available"}

    try:
        result = kloros_instance.alert_manager.deployer.deploy_improvement(payload.improvement)

        return {
            "ok": result.success,
            "rollback_performed": result.rollback_performed,
            "changes_applied": result.changes_applied if hasattr(result, 'changes_applied') else [],
            "message": "Deployment completed successfully" if result.success else "Deployment failed"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn

    print("[http_text] Starting HTTP text ingress on http://127.0.0.1:8124")
    print("[http_text] Test with: curl -X POST http://127.0.0.1:8124/ingest-text -H 'Content-Type: application/json' -d '{\"text\":\"system diagnostic\"}'")

    uvicorn.run(app, host="127.0.0.1", port=8124, log_level="info")
