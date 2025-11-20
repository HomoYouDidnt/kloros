"""
D-REAM integration shim for SPICA.

This module provides the bridge between KLoROS/D-REAM and SPICA's
neutral execution substrate. SPICA executes; D-REAM decides.
"""

from spica.core.runtime import run
import uuid

SPICA_PIPELINE = "/home/kloros/experiments/spica/configs/pipelines/current.yaml"


def run_spica(text, candidates=None, query="", domain="qa.rag",
              run_id="svc", variant_id="svc_v1"):
    """
    Execute SPICA pipeline without making promotion decisions.

    Args:
        text: Input text
        candidates: List of candidate responses
        query: Query string (for ranking/search tasks)
        domain: Domain identifier (e.g., "qa.rag", "planner", "tooling")
        run_id: Run identifier for tracking
        variant_id: Variant identifier (e.g., "ranker_v2b")

    Returns:
        Raw outputs from pipeline execution

    Note:
        This function only EXECUTES. D-REAM/KLoROS handle scoring and decisions.
    """
    ctx = {
        "run_id": run_id,
        "variant_id": variant_id,
        "domain": domain,
        "tokens_used": 0,
        "trace_id": uuid.uuid4().hex[:12]
    }
    seed = {
        "text": text,
        "candidates": candidates or [],
        "query": query
    }

    return run(seed, pipeline_path=SPICA_PIPELINE, ctx=ctx)
