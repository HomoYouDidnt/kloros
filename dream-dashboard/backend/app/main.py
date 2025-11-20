import json, os, asyncio, time, sys
from datetime import datetime
from fastapi import FastAPI, Request, Depends, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from .storage import init_db, add_improvement, list_improvements, update_improvement_status
from .storage import add_queue_item, list_queue, update_queue_status
from .storage import claim_next_queue_item, claim_specific_queue_item
from .metrics import get_all_metrics
from .observations import observation_manager

# Add D-REAM imports
sys.path.insert(0, "/home/kloros")
try:
    from src.dream.adopt import adopt_candidates
    DREAM_ADOPTION_AVAILABLE = True
except ImportError:
    DREAM_ADOPTION_AVAILABLE = False

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "dev-token-change-me")
DB_PATH = os.getenv("DB_PATH", "/data/dream.db")
EXPERIMENT_TYPES_FILE = os.getenv("EXPERIMENT_TYPES_FILE", "/data/experiment_types.json")
DREAM_ARTIFACTS = os.getenv("DREAM_ARTIFACTS", "/dream_artifacts")

app = FastAPI(title="KLoROS D-REAM Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
init_db(DB_PATH)

# SSE subscriptions
subscribers = set()

def auth_guard(request: Request):
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    if token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

def sse_message(event: str, data):
    return {"event": event, "data": json.dumps(data), "id": str(time.time())}

@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Preload data for initial render
    pending = list_improvements(DB_PATH, status="pending")
    queue = list_queue(DB_PATH)
    exp_types = await get_experiment_types()
    return templates.TemplateResponse("index.html", {"request": request, "pending": pending, "queue": queue, "exp_types": exp_types})

@app.get("/observations", response_class=HTMLResponse)
async def observations_page(request: Request):
    """Render the observations page showing KLoROS autonomous insights."""
    observations_data = observation_manager.get_observations(hours=48, limit=100)
    return templates.TemplateResponse("observations.html", {
        "request": request,
        "observations": observations_data
    })

@app.get("/api/observations")
async def api_observations(hours: int = 48, phase: int | None = None, limit: int = 100):
    """
    Get observations data.

    Query params:
        hours: Number of hours to look back (default: 48)
        phase: Filter by specific phase 1-4 (default: all phases)
        limit: Maximum number of observations to return (default: 100)
    """
    return observation_manager.get_observations(hours=hours, phase=phase, limit=limit)

@app.get("/api/pending")
async def api_pending():
    return list_improvements(DB_PATH, status="pending")

@app.post("/api/approve/{iid}")
async def api_approve(iid: int, request: Request, _=Depends(auth_guard)):
    # Get improvement meta to extract run_id
    improvements = list_improvements(DB_PATH)
    improvement = next((i for i in improvements if i["id"] == iid), None)
    
    update_improvement_status(DB_PATH, iid, "approved")
    
    # If D-REAM adoption is available and improvement has run_id, adopt it
    if DREAM_ADOPTION_AVAILABLE and improvement and "run_id" in improvement.get("meta", {}):
        run_id = improvement["meta"]["run_id"]
        try:
            result = adopt_candidates(run_id)
            if not result.get("ok"):
                # Log warning but don't fail the approval
                print(f"[WARN] Adoption failed for {run_id}: {result.get('error')}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Adoption exception for {run_id}: {e}", file=sys.stderr)
    
    payload = {"id": iid, "status": "approved"}
    await broadcast("improvement_update", payload)
    return {"ok": True, **payload}

@app.post("/api/decline/{iid}")
async def api_decline(iid: int, request: Request, _=Depends(auth_guard)):
    update_improvement_status(DB_PATH, iid, "declined")
    payload = {"id": iid, "status": "declined"}
    await broadcast("improvement_update", payload)
    return {"ok": True, **payload}

@app.get("/api/queue")
async def api_queue(status: str | None = None):
    return list_queue(DB_PATH, status=status)

@app.post("/api/queue")
async def api_queue_add(request: Request, _=Depends(auth_guard)):
    form = await request.form()
    type_key = form.get("type_key")
    params_raw = form.get("params_json") or "{}"
    note = form.get("note") or None
    try:
        params = json.loads(params_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="params_json must be valid JSON")
    qid = add_queue_item(DB_PATH, type_key, params, note)
    payload = {"id": qid, "type_key": type_key, "params": params, "status": "queued", "note": note}
    await broadcast("queue_update", payload)
    return {"ok": True, **payload}

@app.post("/api/queue/{qid}/status")
async def api_queue_status(qid: int, request: Request, _=Depends(auth_guard)):
    data = await request.json()
    status = data.get("status")
    note = data.get("note")
    if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail="invalid status")
    update_queue_status(DB_PATH, qid, status, note)
    payload = {"id": qid, "status": status, "note": note}
    await broadcast("queue_update", payload)
    return {"ok": True, **payload}

@app.get("/api/experiment-types")
async def api_experiment_types():
    return await get_experiment_types()

async def get_experiment_types():
    if not os.path.exists(EXPERIMENT_TYPES_FILE):
        # Seed a default set if missing
        default = [
            {
                "key": "stt_benchmark",
                "name": "Benchmark STT Pipeline",
                "description": "Measure latency/accuracy of Whisper–Vosk hybrid across sample set.",
                "params_schema": {"dataset_path": {"type": "string"}, "language": {"type": "string", "default": "en"}}
            },
            {
                "key": "tts_retrain",
                "name": "Retrain TTS",
                "description": "Partial finetune of Piper voice with new dataset chunk.",
                "params_schema": {"epochs": {"type": "integer", "default": 3}, "lr": {"type": "number", "default": 1e-4}}
            },
            {
                "key": "vad_sweep",
                "name": "VAD Threshold Sweep",
                "description": "Grid-search for optimal VAD thresholds and min-silence.",
                "params_schema": {"thresh": {"type": "array", "items": "number"}, "min_silence_ms": {"type": "array", "items": "integer"}}
            },
            {
                "key": "hyperparam_search",
                "name": "Hyperparam Search (D-REAM)",
                "description": "Run D-REAM domain hyperparam evolution over N generations.",
                "params_schema": {"domain": {"type": "string"}, "generations": {"type": "integer", "default": 5}}
            },
            {
                "key": "failure_injection",
                "name": "Simulated Failure Injection",
                "description": "Inject controlled failures into modules to harden self-heal loops.",
                "params_schema": {"module": {"type": "string"}, "mode": {"type": "string", "enum": ["timeout","echo_loop","validation_block"]}}
            }
        ]
        os.makedirs(os.path.dirname(EXPERIMENT_TYPES_FILE), exist_ok=True)
        with open(EXPERIMENT_TYPES_FILE, "w") as f:
            json.dump(default, f, indent=2)
    with open(EXPERIMENT_TYPES_FILE) as f:
        return json.load(f)

@app.get("/events")
async def sse(request: Request):
    async def event_generator():
        # Add client to subscribers
        queue = asyncio.Queue()
        subscribers.add(queue)
        last_observation_check = time.time()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event
                except asyncio.TimeoutError:
                    # Check for new observations every 15 seconds
                    now = time.time()
                    if now - last_observation_check >= 15:
                        new_observations = observation_manager.get_new_since(last_observation_check)
                        for obs in new_observations:
                            yield sse_message("observation", {
                                "id": obs.id,
                                "title": obs.title,
                                "phase": obs.phase,
                                "confidence": obs.confidence,
                                "timestamp": obs.timestamp
                            })
                        last_observation_check = now

                    # keep-alive ping
                    yield sse_message("ping", {"time": datetime.utcnow().isoformat()})
        finally:
            subscribers.remove(queue)
    return EventSourceResponse(event_generator())

async def broadcast(event_type: str, data):
    msg = sse_message(event_type, data)
    for q in list(subscribers):
        await q.put(msg)

# Demo: add sample improvements if DB is empty
@app.on_event("startup")
async def seed_data():
    if not list_improvements(DB_PATH):
        add_improvement(DB_PATH, title="Refactor ASR buffer ring", description="Reduce latency by 12–18% by lowering buffer size and adding lock-free queue.", domain="audio", score=0.67)
        add_improvement(DB_PATH, title="Cache RAG embeddings", description="Memoize hot queries to reduce Chroma calls.", domain="memory", score=0.54)

# Simple auth helper for HTMX calls
async def auth_headers_ok(request: Request):
    # For HTMX form posts, users can include ?token=... or header Authorization: Bearer ... or in form body
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        # Check form body (for hx-vals)
        try:
            form = await request.form()
            token = form.get("token", "")
        except:
            pass
    print(f"[AUTH DEBUG] Received token: '{token}', Expected: '{AUTH_TOKEN}', Match: {token == AUTH_TOKEN}")
    return token == AUTH_TOKEN

# --- HTMX partial routes (HTML fragments) ---
@app.post("/x/approve/{iid}", response_class=HTMLResponse)
async def x_approve(iid: int, request: Request):
    if not await auth_headers_ok(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Get improvement meta to extract run_id
    improvements = list_improvements(DB_PATH)
    improvement = next((i for i in improvements if i["id"] == iid), None)
    
    update_improvement_status(DB_PATH, iid, "approved")
    
    # If D-REAM adoption is available and improvement has run_id, adopt it
    if DREAM_ADOPTION_AVAILABLE and improvement and "run_id" in improvement.get("meta", {}):
        run_id = improvement["meta"]["run_id"]
        try:
            result = adopt_candidates(run_id)
            if not result.get("ok"):
                print(f"[WARN] Adoption failed for {run_id}: {result.get('error')}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Adoption exception for {run_id}: {e}", file=sys.stderr)
    
    await broadcast("improvement_update", {"id": iid, "status": "approved"})
    # Return updated pending list fragment
    pend = list_improvements(DB_PATH, status="pending")
    return templates.TemplateResponse("_pending_table.html", {"request": request, "pending": pend})

@app.post("/x/decline/{iid}", response_class=HTMLResponse)
async def x_decline(iid: int, request: Request):
    if not await auth_headers_ok(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    update_improvement_status(DB_PATH, iid, "declined")
    await broadcast("improvement_update", {"id": iid, "status": "declined"})
    pend = list_improvements(DB_PATH, status="pending")
    return templates.TemplateResponse("_pending_table.html", {"request": request, "pending": pend})

def validate_experiment_params(exp_type: dict, params: dict):
    """Validate params against experiment type fields with conditional logic."""
    if "fields" not in exp_type:
        return True, params
    fields = {f["name"]: f for f in exp_type["fields"]}
    clean = {}
    for name, field in fields.items():
        show_if = field.get("show_if", {})
        if show_if and any(params.get(k) != v for k, v in show_if.items()):
            continue
        value = params.get(name, field.get("default"))
        if field.get("type") == "number":
            try:
                value = float(value) if isinstance(value, (str, int, float)) and "." in str(value) else int(value)
            except (ValueError, TypeError):
                value = field.get("default", 0)
        elif field.get("type") == "multiselect":
            value = value if isinstance(value, list) else [value] if value else []
        if field.get("type") == "number":
            if "min" in field and value < field["min"]:
                return False, f"{name} below minimum {field['min']}"
            if "max" in field and value > field["max"]:
                return False, f"{name} above maximum {field['max']}"
        clean[name] = value
    return True, clean


@app.post("/x/queue", response_class=HTMLResponse)
async def x_queue(request: Request):
    if not await auth_headers_ok(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    form = await request.form()
    type_key = form.get("type_key")
    params_json = form.get("params_json") or "{}"
    note = form.get("note") or None
    auto_adopt = form.get("auto_adopt") == "on"
    safe_mode = form.get("safe_mode") == "on"
    try:
        params = json.loads(params_json)
    except Exception:
        raise HTTPException(status_code=400, detail="params_json must be valid JSON")
    exp_types = await get_experiment_types()
    exp_type = next((t for t in exp_types if t["key"] == type_key), None)
    if exp_type:
        ok, result = validate_experiment_params(exp_type, params)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Invalid params: {result}")
        params = result
    meta = {"auto_adopt": auto_adopt, "safe_mode": safe_mode}
    qid = add_queue_item(DB_PATH, type_key, params, note, meta)
    await broadcast("queue_update", {"id": qid, "type_key": type_key, "params": params, "status": "queued", "note": note, "meta": meta})
    queue = list_queue(DB_PATH)
    return templates.TemplateResponse("_queue_table.html", {"request": request, "queue": queue})

# --- API Routes ---

@app.post("/api/improvements")
async def api_add_improvement(payload: dict = Body(...), _=Depends(auth_guard)):
    title = payload.get("title")
    description = payload.get("description", "")
    domain = payload.get("domain", "general")
    score = float(payload.get("score", 0.0))
    meta = payload.get("meta", {})
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    iid = add_improvement(DB_PATH, title=title, description=description, domain=domain, score=score, meta=meta)
    await broadcast("improvement_update", {"id": iid, "status": "pending"})
    return {"ok": True, "id": iid}

@app.post("/api/queue/claim")
async def api_queue_claim(worker_id: str = Form(...), _=Depends(auth_guard)):
    row = claim_next_queue_item(DB_PATH, worker_id)
    if not row:
        return JSONResponse({"ok": True, "job": None})
    return {"ok": True, "job": row}

@app.post("/api/queue/{qid}/claim")
async def api_queue_claim_id(qid: int, worker_id: str = Form(...), _=Depends(auth_guard)):
    row = claim_specific_queue_item(DB_PATH, qid, worker_id)
    if not row:
        raise HTTPException(status_code=409, detail="not claimable")
    return {"ok": True, "job": row}

@app.get("/api/metrics")
async def api_metrics():
    """Get system metrics for KLoROS."""
    return get_all_metrics()

@app.get("/api/metrics/evidence")
async def api_metrics_evidence():
    """Get evidence bundle metrics only."""
    from .metrics import get_evidence_metrics
    return get_evidence_metrics()

@app.get("/api/metrics/quota")
async def api_metrics_quota():
    """Get quota metrics only."""
    from .metrics import get_quota_metrics
    return get_quota_metrics()

@app.get("/api/xai")
async def api_xai(limit: int = 100, phase: str | None = None):
    """
    Retrieve XAI traces from structured logs.

    Query params:
        limit: Max number of traces to return (default 100)
        phase: Filter by phase ("routing" or "execution")

    Returns:
        JSON with traces array, count, and filter info
    """
    from pathlib import Path

    log_path = Path("/var/log/kloros/structured.jsonl")

    if not log_path.exists():
        return JSONResponse({"traces": [], "count": 0, "filtered_by": phase})

    traces = []
    try:
        with open(log_path, "r") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("event") == "xai.trace":
                        if phase is None or event.get("phase") == phase:
                            traces.append(event)
                            if len(traces) >= limit:
                                break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        return JSONResponse(
            {"traces": [], "count": 0, "error": str(e), "filtered_by": phase},
            status_code=500
        )

    # Reverse to get newest first
    traces.reverse()

    return JSONResponse({
        "traces": traces,
        "count": len(traces),
        "filtered_by": phase
    })

@app.get("/api/compare")
async def api_compare(run_id: str):
    """
    Compare a D-REAM run to baseline metrics.

    Query params:
        run_id: The run ID to compare

    Returns:
        JSON with current metrics, baseline metrics, and deltas
    """
    from pathlib import Path

    baseline_path = Path("/home/kloros/src/dream/artifacts/baseline_metrics.json")

    def load_json(p):
        try:
            with open(p, 'r') as f:
                return json.load(f)
        except:
            return None

    # Load current run
    artifacts_dir = Path(DREAM_ARTIFACTS)
    run_dir = artifacts_dir / "candidates" / run_id

    pack_file = run_dir / "pack.json"
    admitted_file = run_dir / "admitted.json"

    # Try to load from admitted first, fallback to pack
    admitted_data = load_json(admitted_file)
    pack_data = load_json(pack_file)

    if not admitted_data and not pack_data:
        raise HTTPException(status_code=404, detail=f"no data found for run {run_id}")

    # Get best candidate (first admitted or first in pack)
    if admitted_data and admitted_data.get("admitted"):
        cur = admitted_data["admitted"][0]
    elif pack_data and pack_data.get("candidates"):
        cur = pack_data["candidates"][0]
    else:
        raise HTTPException(status_code=404, detail="no candidates in run")

    # Load baseline
    baseline = load_json(baseline_path)
    if not baseline:
        raise HTTPException(status_code=404, detail="baseline metrics not found")

    # Extract metrics
    cur_metrics = cur.get("metrics", {})

    # Calculate deltas
    def delta(k):
        cur_val = cur_metrics.get(k)
        base_val = baseline.get(k)
        if cur_val is None or base_val is None:
            return None
        return round(cur_val - base_val, 3)

    return {
        "ok": True,
        "run_id": run_id,
        "current": {
            "wer": cur_metrics.get("wer"),
            "latency_ms": cur_metrics.get("latency_ms"),
            "vad_boundary_ms": cur_metrics.get("vad_boundary_ms"),
            "score": cur_metrics.get("score")
        },
        "baseline": {
            "wer": baseline.get("wer"),
            "latency_ms": baseline.get("latency_ms"),
            "vad_boundary_ms": baseline.get("vad_boundary_ms"),
            "score": baseline.get("score"),
            "run_id": baseline.get("run_id"),
            "timestamp": baseline.get("timestamp")
        },
        "delta": {
            "wer": delta("wer"),
            "latency_ms": delta("latency_ms"),
            "vad_boundary_ms": delta("vad_boundary_ms"),
            "score": delta("score")
        }
    }

@app.get("/api/candidates")
async def api_candidates(limit: int = 100, domain: str | None = None):
    """
    List D-REAM candidate runs from artifacts directory.

    Query params:
        limit: Max number of runs to return (default 100)
        domain: Filter by domain (e.g., "audio", "conversation", "tool", "rag")

    Returns:
        JSON with array of candidate run summaries
    """
    from pathlib import Path

    artifacts_dir = Path(DREAM_ARTIFACTS)
    candidates_dir = artifacts_dir / "candidates"

    if not candidates_dir.exists():
        return JSONResponse({"candidates": [], "count": 0, "error": "candidates directory not found"})

    # Helper to load JSON safely
    def load_json(p):
        try:
            with open(p, 'r') as f:
                return json.load(f)
        except:
            return None

    candidates = []
    try:
        # List all run directories
        run_dirs = sorted(candidates_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

        for run_dir in run_dirs[:limit]:
            if not run_dir.is_dir():
                continue

            run_id = run_dir.name
            pack_file = run_dir / "pack.json"
            admitted_file = run_dir / "admitted.json"

            # Load pack data
            pack_data = load_json(pack_file)
            admitted_data = load_json(admitted_file)

            if not pack_data:
                continue

            # Extract summary info
            candidate_count = len(pack_data.get("candidates", []))
            admitted_count = len(admitted_data.get("admitted", [])) if admitted_data else 0

            # Get best candidate metrics
            best_metrics = {}
            if admitted_data and admitted_data.get("admitted"):
                best_metrics = admitted_data["admitted"][0].get("metrics", {})
            elif pack_data.get("candidates"):
                best_metrics = pack_data["candidates"][0].get("metrics", {})

            # Determine domain (from first candidate)
            run_domain = "unknown"
            if pack_data.get("candidates"):
                run_domain = pack_data["candidates"][0].get("domain", "unknown")

            # Filter by domain if specified
            if domain and run_domain != domain:
                continue

            candidates.append({
                "run_id": run_id,
                "domain": run_domain,
                "candidate_count": candidate_count,
                "admitted_count": admitted_count,
                "best_score": best_metrics.get("score"),
                "best_wer": best_metrics.get("wer"),
                "best_latency_ms": best_metrics.get("latency_ms"),
                "modified_at": run_dir.stat().st_mtime
            })

    except Exception as e:
        return JSONResponse(
            {"candidates": [], "count": 0, "error": str(e)},
            status_code=500
        )

    return {
        "candidates": candidates,
        "count": len(candidates),
        "filtered_by_domain": domain
    }

@app.get("/api/experiments/{run_id}")
async def api_experiment_detail(run_id: str):
    """
    Get detailed D-REAM experiment data for a specific run.

    Path params:
        run_id: The run ID to fetch

    Returns:
        JSON with full pack.json data including all candidates
    """
    from pathlib import Path

    artifacts_dir = Path(DREAM_ARTIFACTS)
    run_dir = artifacts_dir / "candidates" / run_id

    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    pack_file = run_dir / "pack.json"
    admitted_file = run_dir / "admitted.json"

    def load_json(p):
        try:
            with open(p, 'r') as f:
                return json.load(f)
        except:
            return None

    pack_data = load_json(pack_file)
    admitted_data = load_json(admitted_file)

    if not pack_data:
        raise HTTPException(status_code=404, detail=f"pack.json not found for run {run_id}")

    return {
        "ok": True,
        "run_id": run_id,
        "pack": pack_data,
        "admitted": admitted_data,
        "has_admitted": bool(admitted_data and admitted_data.get("admitted"))
    }
