"""FastAPI server for browser agent."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import asyncio
from .agent.executor import BrowserExecutor
from .agent.petri_policy import PetriPolicy

app = FastAPI(title="KLoROS Browser Agent", version="1.0.0")

# Global executor pool
_executors: Dict[str, BrowserExecutor] = {}
_policy = PetriPolicy()

class PlanRequest(BaseModel):
    """Plan execution request."""
    plan_id: str
    meta: Dict[str, Any]
    actions: List[Dict[str, Any]]
    headless: bool = True

class PlanResponse(BaseModel):
    """Plan execution response."""
    plan_id: str
    trace_dir: str
    steps: List[Dict[str, Any]]
    vars: Dict[str, Any]
    success: bool

@app.get("/")
def root():
    """Health check."""
    return {"ok": True, "service": "browser_agent", "version": "1.0.0"}

@app.post("/execute")
async def execute_plan(request: PlanRequest) -> PlanResponse:
    """Execute browser automation plan.

    Args:
        request: Plan execution request

    Returns:
        Execution result
    """
    plan = {
        "meta": request.meta,
        "actions": request.actions
    }

    executor = BrowserExecutor(policy=_policy, headless=request.headless)

    try:
        await executor.start()
        result = await executor.run_plan(plan)

        return PlanResponse(
            plan_id=request.plan_id,
            trace_dir=result["trace_dir"],
            steps=result["steps"],
            vars=result.get("vars", {}),
            success=all(s.get("success", False) for s in result["steps"])
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await executor.stop()

@app.get("/policy")
def get_policy():
    """Get current PETRI policy."""
    return {
        "allow_domains": _policy.allow_domains,
        "max_actions": _policy.max_actions,
        "action_timeout_s": _policy.action_timeout_s,
        "total_timeout_s": _policy.total_timeout_s,
        "screenshot_every_step": _policy.screenshot_every_step
    }

@app.post("/policy/domains/add")
def add_domain(domain: str):
    """Add allowed domain."""
    if domain not in _policy.allow_domains:
        _policy.allow_domains.append(domain)
    return {"ok": True, "domains": _policy.allow_domains}

@app.post("/policy/domains/remove")
def remove_domain(domain: str):
    """Remove allowed domain."""
    if domain in _policy.allow_domains:
        _policy.allow_domains.remove(domain)
    return {"ok": True, "domains": _policy.allow_domains}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
