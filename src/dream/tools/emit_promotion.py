#!/usr/bin/env python3
"""
Promotion Emitter - Transforms external runner winners into explicit promotions with apply_map.

Usage: python emit_promotion.py <experiment_name> <winners_file> <output_file>
"""

import json
import sys
import time
import hashlib
from pathlib import Path
import os


# Experiment-specific apply_map configurations
APPLY_MAPS = {
    "rag_opt_baseline": {
        "top_k_values": "KLR_RAG_TOP_K",
        "chunk_sizes": "KLR_RAG_CHUNK_SIZE",
        "similarity_thresholds": "KLR_RAG_SIM_THRESHOLD",
        "embedder": "KLR_RAG_EMBEDDER"
    },
    "audio_latency_trim": {
        "sample_rates": "KLR_AUDIO_SAMPLE_RATE",
        "frame_sizes": "KLR_AUDIO_FRAME_SIZE",
        "buffering_strategy": "KLR_AUDIO_BUFFERING",
        "resampler": "KLR_AUDIO_RESAMPLER"
    },
    "conv_quality_tune": {
        "max_context_turns": "KLR_MAX_CONTEXT_TURNS",
        "response_length_tokens": "KLR_RESPONSE_LENGTH",
        "anti_hallucination_mode": "KLR_ANTI_HALLUCINATION",
        "cite_threshold": "KLR_CITE_THRESHOLD"
    },
    "tool_evolution": {
        # Tool evolution uses special promotion type (not config params)
        # apply_map will be: {"tool_code": "TOOL_FILE:<tool_name>"}
        # This signals to applier to write code file instead of config var
    }
}


def emit_promotion(experiment: str, winners_path: str, output_path: str):
    """Transform winner file into promotion with apply_map."""

    # Load winner
    winners_file = Path(winners_path)
    if not winners_file.exists():
        print(f"Winners file not found: {winners_path}")
        return False

    winner_data = json.loads(winners_file.read_text())
    best = winner_data.get("best", {})

    if not best:
        print(f"No best winner found in {winners_path}")
        return False

    params = best.get("params", {})
    metrics = best.get("metrics", {})
    fitness = best.get("fitness")

    # Queue to alert system (NEW - makes D-REAM discoveries visible)
    _queue_dream_alert(experiment, best, metrics)

    # Get apply_map for this experiment
    apply_map = APPLY_MAPS.get(experiment, {})
    if not apply_map:
        print(f"Warning: No apply_map defined for experiment '{experiment}'")
        # Use identity mapping as fallback
        apply_map = {k: k for k in params.keys()}

    # Create promotion
    promotion_id = f"{experiment}:{int(time.time())}"
    signature = "sha256:" + hashlib.sha256(
        json.dumps(best, sort_keys=True).encode()
    ).hexdigest()

    promotion = {
        "experiment": experiment,
        "updated_at": int(time.time()),
        "source": "external_runner",
        "winner": {
            "fitness": fitness,
            "params": params,
            "metrics": metrics
        },
        "apply_map": apply_map,
        "ttl_seconds": 604800,  # 7 days
        "promotion_id": promotion_id,
        "signature": signature
    }

    # Write promotion
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(promotion, indent=2))

    print(f"✓ Emitted promotion: {promotion_id}")
    print(f"  Fitness: {fitness:.3f}")
    print(f"  Params: {len(params)} configured")
    print(f"  Output: {output_path}")

    return True


def _queue_dream_alert(experiment: str, best: dict, metrics: dict) -> None:
    """
    Queue D-REAM discovery to alert system for user notification.

    Args:
        experiment: Experiment name
        best: Best winner data
        metrics: Winner metrics
    """
    try:
        # Check if D-REAM alerts are enabled
        enable_alerts = int(os.getenv("KLR_DREAM_ALERTS", "1"))  # Default enabled
        if not enable_alerts:
            return

        # Load alert system
        sys.path.insert(0, '/home/kloros')
        from src.dream_alerts.alert_manager import DreamAlertManager

        # Check if alert manager exists
        alert_file = Path("/tmp/.kloros_alert_manager.pid")
        if not alert_file.exists():
            # Alert manager not running - skip
            return

        # Create improvement alert from D-REAM winner
        fitness = best.get("fitness", 0.0)
        params = best.get("params", {})

        # Human-readable experiment names
        exp_names = {
            "rag_opt_baseline": "RAG Optimization",
            "audio_latency_trim": "Audio Latency",
            "conv_quality_tune": "Conversation Quality",
            "tool_evolution": "Tool Evolution"
        }
        component = exp_names.get(experiment, experiment)

        # Calculate improvement benefit
        benefit_msg = _format_improvement_benefit(experiment, metrics)

        improvement = {
            "task_id": f"dream_{experiment}_{int(time.time())}",
            "description": f"D-REAM discovered improvement in {component}",
            "component": component.lower().replace(" ", "_"),
            "expected_benefit": benefit_msg,
            "risk_level": "low",  # D-REAM improvements are tested
            "confidence": min(fitness, 1.0),  # Normalized fitness as confidence
            "source": "d_ream_evolution"
        }

        # Queue to alert manager
        alert_manager = DreamAlertManager()
        result = alert_manager.notify_improvement_ready(improvement)

        if result.get("status") == "processed":
            print(f"[dream_alert] ✓ Queued D-REAM discovery for user notification")
        else:
            print(f"[dream_alert] Alert system disabled or unavailable")

    except Exception as e:
        # Non-fatal - continue without alert
        print(f"[dream_alert] Failed to queue alert: {e}")


def _format_improvement_benefit(experiment: str, metrics: dict) -> str:
    """Format improvement benefit message from metrics."""
    # Extract key metrics based on experiment type
    if experiment == "rag_opt_baseline":
        accuracy = metrics.get("accuracy", 0.0)
        latency = metrics.get("latency_ms_p95", 0.0)
        return f"Improved retrieval accuracy to {accuracy:.1%} (latency: {latency:.0f}ms)"

    elif experiment == "audio_latency_trim":
        latency = metrics.get("latency_ms_p95", 0.0)
        quality = metrics.get("audio_quality", 0.0)
        return f"Reduced audio latency to {latency:.0f}ms (quality: {quality:.2f})"

    elif experiment == "conv_quality_tune":
        coherence = metrics.get("coherence_score", 0.0)
        relevance = metrics.get("relevance_score", 0.0)
        return f"Enhanced conversation quality (coherence: {coherence:.1%}, relevance: {relevance:.1%})"

    elif experiment == "tool_evolution":
        success_rate = metrics.get("success_rate", 0.0)
        return f"Optimized tool performance (success rate: {success_rate:.1%})"

    else:
        # Generic fallback
        return f"Performance improvement detected (fitness: {metrics.get('fitness', 0.0):.3f})"


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: emit_promotion.py <experiment> <winners_file> <output_file>")
        sys.exit(1)

    experiment, winners_file, output_file = sys.argv[1], sys.argv[2], sys.argv[3]
    success = emit_promotion(experiment, winners_file, output_file)
    sys.exit(0 if success else 1)
