"""
REST API endpoints for KLoROS Dashboard.

Provides real-time and historical meta-cognitive state data.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timedelta
import json
from models import (
    MetaState, EnhancedMetaState, HistoricalData, HistoricalSample, DashboardSummary,
    CuriosityState, CuriosityQuestion, InternalDialogue, XAITrace, ExternalLLMConfig
)
from kloros_bridge import bridge

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    kloros_running = bridge.is_kloros_running()
    return {
        "status": "healthy",
        "kloros_running": kloros_running,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/meta-state", response_model=EnhancedMetaState)
async def get_meta_state():
    """
    Get current enhanced meta-cognitive state snapshot.

    Returns:
        Current EnhancedMetaState object with all meta-cognitive metrics and enhanced data
    """
    state = bridge.get_meta_state()
    if not state:
        raise HTTPException(status_code=503, detail="KLoROS meta-state unavailable")
    return state


@router.get("/consciousness")
async def get_consciousness():
    """
    Get current consciousness state (affect, emotions).
    
    Returns:
        Consciousness state including affect and emotions
    """
    state = bridge.get_meta_state()
    if not state:
        raise HTTPException(status_code=503, detail="KLoROS unavailable")
    
    return {
        "affect": state.affect.model_dump(),
        "timestamp": state.timestamp.isoformat()
    }


@router.get("/session")
async def get_session():
    """
    Get current conversation session info.
    
    Returns:
        Session information (turn count, duration, topics, entities)
    """
    state = bridge.get_meta_state()
    if not state:
        raise HTTPException(status_code=503, detail="KLoROS unavailable")
    
    return state.session.model_dump()


@router.get("/quality-scores")
async def get_quality_scores():
    """
    Get current conversation quality scores.
    
    Returns:
        Quality scores (progress, clarity, engagement)
    """
    state = bridge.get_meta_state()
    if not state:
        raise HTTPException(status_code=503, detail="KLoROS unavailable")
    
    return {
        "scores": state.quality_scores.model_dump(),
        "conversation_health": state.conversation_health,
        "timestamp": state.timestamp.isoformat()
    }


@router.get("/issues")
async def get_issues():
    """
    Get current conversation issues.
    
    Returns:
        Detected issues (repetition, stuck, confusion)
    """
    state = bridge.get_meta_state()
    if not state:
        raise HTTPException(status_code=503, detail="KLoROS unavailable")
    
    return {
        "issues": state.issues.model_dump(),
        "interventions": state.interventions.model_dump(),
        "timestamp": state.timestamp.isoformat()
    }


@router.get("/summary", response_model=DashboardSummary)
async def get_summary():
    """
    Get dashboard summary statistics.
    
    Returns:
        Summary stats (uptime, total turns, avg health, etc.)
    """
    state = bridge.get_meta_state()
    if not state:
        raise HTTPException(status_code=503, detail="KLoROS unavailable")
    
    # Calculate uptime (using bridge last update time)
    uptime = 0
    if bridge.last_update:
        uptime = int((datetime.now() - bridge.last_update).total_seconds())
    
    # Count interventions triggered (simplification - just check current state)
    interventions_triggered = sum(1 for v in [
        state.interventions.clarify,
        state.interventions.change_approach,
        state.interventions.summarize,
        state.interventions.confirm,
        state.interventions.break_suggested
    ] if v)
    
    return DashboardSummary(
        uptime_seconds=uptime,
        total_turns=state.session.turn_count,
        interventions_triggered=interventions_triggered,
        avg_conversation_health=state.conversation_health,
        current_status="active" if bridge.is_kloros_running() else "inactive"
    )


@router.get("/history")
async def get_history(
    metric: str = Query("conversation_health", description="Metric name to retrieve"),
    hours: int = Query(1, ge=1, le=24, description="Hours of history to retrieve")
):
    """
    Get historical metrics data.
    
    NOTE: This is a placeholder. Real implementation would query
    a time-series database or log files. For now, returns empty.
    
    Args:
        metric: Metric name (e.g., 'conversation_health', 'progress', 'clarity')
        hours: Number of hours of history to retrieve (1-24)
    
    Returns:
        Historical data samples
    """
    # TODO: Implement historical data storage and retrieval
    # For now, return empty historical data
    return {
        "metric": metric,
        "samples": [],
        "average": 0.0,
        "min_value": 0.0,
        "max_value": 0.0,
        "note": "Historical data persistence not yet implemented"
    }


@router.get("/curiosity", response_model=CuriosityState)
async def get_curiosity_state():
    """
    Get current curiosity and introspection state.

    Returns:
        Current curiosity questions, internal dialogue, and investigation status
    """
    curiosity_data = bridge.get_curiosity_state()
    if not curiosity_data:
        # Return empty state if not available
        state = bridge.get_meta_state()
        curiosity_level = 0.5
        if state and hasattr(state.affect, 'curiosity'):
            curiosity_level = state.affect.curiosity

        return CuriosityState(
            curiosity_level=curiosity_level,
            active_questions=[],
            recent_investigations=[],
            internal_dialogue=[],
            total_questions_generated=0,
            total_questions_answered=0
        )
    return curiosity_data


@router.get("/internal-dialogue", response_model=List[InternalDialogue])
async def get_internal_dialogue(
    limit: int = Query(10, ge=1, le=50, description="Number of recent thoughts to retrieve")
):
    """
    Get recent internal dialogue/thoughts from KLoROS.

    Args:
        limit: Maximum number of thoughts to return (1-50)

    Returns:
        List of recent internal thoughts
    """
    dialogue = bridge.get_internal_dialogue(limit=limit)
    if not dialogue:
        return []
    return dialogue


@router.get("/xai-traces", response_model=List[XAITrace])
async def get_xai_traces(
    limit: int = Query(5, ge=1, le=20, description="Number of recent traces to retrieve"),
    decision_type: Optional[str] = Query(None, description="Filter by decision type")
):
    """
    Get recent XAI reasoning traces.

    Args:
        limit: Maximum number of traces to return (1-20)
        decision_type: Optional filter by decision type

    Returns:
        List of XAI reasoning traces showing step-by-step decision making
    """
    traces = bridge.get_xai_traces(limit=limit, decision_type=decision_type)
    if not traces:
        return []
    return traces


@router.get("/xai-trace/{decision_id}", response_model=XAITrace)
async def get_xai_trace_by_id(decision_id: str):
    """
    Get a specific XAI trace by decision ID.

    Args:
        decision_id: The unique decision ID

    Returns:
        Complete XAI reasoning trace for that decision
    """
    trace = bridge.get_xai_trace_by_id(decision_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"XAI trace not found for decision_id: {decision_id}")
    return trace


# ===== EXTERNAL LLM CONFIGURATION =====
# Configuration file path
EXTERNAL_LLM_CONFIG_PATH = "/tmp/kloros_external_llm_config.json"


def load_external_llm_config():
    """Load external LLM configuration from disk."""
    try:
        with open(EXTERNAL_LLM_CONFIG_PATH, 'r') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        # Return default config if file doesn't exist
        return {
            "enabled": False,
            "endpoint_url": None,
            "model_name": None,
            "description": "External LLM for enhanced curiosity processing",
            "last_updated": None
        }
    except Exception as e:
        print(f"[api] Error loading external LLM config: {e}")
        return {
            "enabled": False,
            "endpoint_url": None,
            "model_name": None,
            "description": "External LLM for enhanced curiosity processing",
            "last_updated": None
        }


def save_external_llm_config(config_data: dict):
    """Save external LLM configuration to disk."""
    try:
        config_data["last_updated"] = datetime.now().isoformat()
        with open(EXTERNAL_LLM_CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"[api] Error saving external LLM config: {e}")
        return False


@router.get("/external-llm-config")
async def get_external_llm_config():
    """
    Get current external LLM configuration.
    
    Returns:
        Current external LLM configuration including enabled status and endpoint details
    """
    from models import ExternalLLMConfig
    config = load_external_llm_config()
    return ExternalLLMConfig(**config)


@router.post("/external-llm-config")
async def update_external_llm_config(enabled: bool = None, endpoint_url: str = None, 
                                      model_name: str = None, description: str = None):
    """
    Update external LLM configuration.
    
    Args:
        enabled: Whether to enable external LLM access
        endpoint_url: URL of the external LLM endpoint
        model_name: Name of the external model
        description: Human-readable description
    
    Returns:
        Updated configuration
    """
    from models import ExternalLLMConfig
    
    # Load current config
    config = load_external_llm_config()
    
    # Update only provided fields
    if enabled is not None:
        config["enabled"] = enabled
    if endpoint_url is not None:
        config["endpoint_url"] = endpoint_url
    if model_name is not None:
        config["model_name"] = model_name
    if description is not None:
        config["description"] = description
    
    # Save updated config
    if save_external_llm_config(config):
        return ExternalLLMConfig(**config)
    else:
        raise HTTPException(status_code=500, detail="Failed to save configuration")


# ===== REMOTE LLM ENDPOINTS =====
# Remote LLM configuration file path
REMOTE_LLM_CONFIG_PATH = "/tmp/kloros_remote_llm_config.json"

# Available models on ALTIMITOS
AVAILABLE_MODELS = [
    "qwen2.5:72b",
    "deepseek-r1:70b", 
    "qwen2.5-coder:32b"
]


def load_remote_llm_config():
    """Load remote LLM configuration from disk."""
    try:
        with open(REMOTE_LLM_CONFIG_PATH, 'r') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        # Return default config if file doesn't exist
        return {
            "enabled": False,
            "selected_model": "qwen2.5:72b",
            "server_url": "http://100.67.244.66:11434",
            "last_updated": None
        }
    except Exception as e:
        print(f"[api] Error loading remote LLM config: {e}")
        return {
            "enabled": False,
            "selected_model": "qwen2.5:72b",
            "server_url": "http://100.67.244.66:11434",
            "last_updated": None
        }


def save_remote_llm_config(config_data: dict):
    """Save remote LLM configuration to disk."""
    try:
        config_data["last_updated"] = datetime.now().isoformat()
        with open(REMOTE_LLM_CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"[api] Error saving remote LLM config: {e}")
        return False


@router.get("/curiosity/remote-llm-config")
async def get_remote_llm_config():
    """
    Get current remote LLM configuration.
    
    Returns:
        Current remote LLM configuration including enabled status and selected model
    """
    from models import RemoteLLMConfig
    config = load_remote_llm_config()
    return RemoteLLMConfig(**config)


@router.post("/curiosity/remote-llm-config")
async def update_remote_llm_config(
    enabled: bool = None, 
    selected_model: str = None,
    server_url: str = None
):
    """
    Update remote LLM configuration.
    
    Args:
        enabled: Whether to enable remote LLM access
        selected_model: Which model to use (qwen2.5:72b, deepseek-r1:70b, qwen2.5-coder:32b)
        server_url: URL of the remote Ollama server
    
    Returns:
        Updated configuration
    """
    from models import RemoteLLMConfig
    
    # Load current config
    config = load_remote_llm_config()
    
    # Update only provided fields
    if enabled is not None:
        config["enabled"] = enabled
    if selected_model is not None:
        if selected_model not in AVAILABLE_MODELS:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid model. Must be one of: {', '.join(AVAILABLE_MODELS)}"
            )
        config["selected_model"] = selected_model
    if server_url is not None:
        config["server_url"] = server_url
    
    # Save updated config
    if save_remote_llm_config(config):
        return RemoteLLMConfig(**config)
    else:
        raise HTTPException(status_code=500, detail="Failed to save configuration")


@router.get("/curiosity/remote-status")
async def get_remote_llm_status():
    """
    Check if remote LLM server is reachable and get available models.
    
    Returns:
        Status including reachability and available models
    """
    from models import RemoteLLMStatus
    import httpx
    
    config = load_remote_llm_config()
    server_url = config.get("server_url", "http://100.67.244.66:11434")
    
    try:
        # Try to connect to the server with a short timeout
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{server_url}/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                return RemoteLLMStatus(
                    reachable=True,
                    available_models=models,
                    error=None
                )
            else:
                return RemoteLLMStatus(
                    reachable=False,
                    available_models=[],
                    error=f"Server returned status code {response.status_code}"
                )
    except httpx.TimeoutException:
        return RemoteLLMStatus(
            reachable=False,
            available_models=[],
            error="Connection timeout - server may be unreachable"
        )
    except httpx.ConnectError:
        return RemoteLLMStatus(
            reachable=False,
            available_models=[],
            error="Connection refused - server may be offline"
        )
    except Exception as e:
        return RemoteLLMStatus(
            reachable=False,
            available_models=[],
            error=f"Error connecting to server: {str(e)}"
        )


@router.post("/curiosity/remote-query")
async def query_remote_llm(query: dict):
    """
    Send a query to the remote LLM server.
    
    Args:
        query: Dictionary with 'model', 'prompt', and optional 'enabled' fields
    
    Returns:
        Response from the remote LLM including generated text and metadata
    """
    from models import RemoteLLMResponse
    import httpx
    import time
    
    # Extract parameters
    model = query.get("model")
    prompt = query.get("prompt")
    enabled = query.get("enabled", True)
    
    if not model or not prompt:
        raise HTTPException(
            status_code=400,
            detail="Both 'model' and 'prompt' are required"
        )
    
    # Check if remote LLM is enabled
    config = load_remote_llm_config()
    if not enabled and not config.get("enabled", False):
        return RemoteLLMResponse(
            success=False,
            response=None,
            error="Remote LLM access is disabled",
            model_used=model,
            response_time_ms=None
        )
    
    server_url = config.get("server_url", "http://100.67.244.66:11434")
    
    try:
        start_time = time.time()
        
        # Make request to Ollama API
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{server_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                return RemoteLLMResponse(
                    success=True,
                    response=data.get("response", ""),
                    error=None,
                    model_used=model,
                    response_time_ms=response_time_ms
                )
            else:
                return RemoteLLMResponse(
                    success=False,
                    response=None,
                    error=f"Server returned status code {response.status_code}",
                    model_used=model,
                    response_time_ms=response_time_ms
                )
    except httpx.TimeoutException:
        return RemoteLLMResponse(
            success=False,
            response=None,
            error="Request timeout - query took too long",
            model_used=model,
            response_time_ms=None
        )
    except httpx.ConnectError:
        return RemoteLLMResponse(
            success=False,
            response=None,
            error="Connection refused - server may be offline",
            model_used=model,
            response_time_ms=None
        )
    except Exception as e:
        return RemoteLLMResponse(
            success=False,
            response=None,
            error=f"Error querying remote LLM: {str(e)}",
            model_used=model,
            response_time_ms=None
        )
