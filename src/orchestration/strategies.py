# src/orchestrator/strategies.py
import os, time, logging
log = logging.getLogger("brainmods")

USE_TOT   = os.getenv("KLR_USE_TOT","0") == "1"
USE_DEB   = os.getenv("KLR_USE_DEBATE","0") == "1"
USE_VOI   = os.getenv("KLR_USE_VOI","0") == "1"
USE_SAFE  = os.getenv("KLR_USE_SAFETY","0") == "1"
USE_PROV  = os.getenv("KLR_USE_PROVENANCE","0") == "1"

def enrich_plan(user_goal: str, options: list[str] = None) -> list[str]:
    """Enrich planning with brainmod strategies.

    Args:
        user_goal: User's goal/query
        options: Existing options list (optional)

    Returns:
        Enriched options list
    """
    options = options or []
    ideas = []

    if USE_TOT:
        try:
            from brainmods.tot_search import propose
            t0 = time.time()
            ideas = propose(user_goal)[:5]
            log.info({"brainmod": "tot_search", "ms": int((time.time()-t0)*1000), "n": len(ideas)})
        except Exception as e:
            log.warning({"brainmod": "tot_search", "error": str(e)})

    if USE_DEB and options:
        try:
            from brainmods.debate import debate
            t0 = time.time()
            _ = debate(user_goal)
            log.info({"brainmod": "debate", "ms": int((time.time()-t0)*1000)})
        except Exception as e:
            log.warning({"brainmod": "debate", "error": str(e)})

    if USE_VOI and options:
        try:
            from brainmods.voi import score
            t0 = time.time()
            _ = score(user_goal, options)
            log.info({"brainmod": "voi", "ms": int((time.time()-t0)*1000)})
        except Exception as e:
            log.warning({"brainmod": "voi", "error": str(e)})

    if USE_SAFE:
        try:
            from brainmods.safety_value import assess
            t0 = time.time()
            _ = assess(user_goal)
            log.info({"brainmod": "safety_value", "ms": int((time.time()-t0)*1000)})
        except Exception as e:
            log.warning({"brainmod": "safety_value", "error": str(e)})

    if USE_PROV:
        try:
            from brainmods.provenance import start_trace
            t0 = time.time()
            start_trace(context={"goal": user_goal})
            log.info({"brainmod": "provenance", "ms": int((time.time()-t0)*1000)})
        except Exception as e:
            log.warning({"brainmod": "provenance", "error": str(e)})

    return ideas or options
