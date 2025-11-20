from fastapi import FastAPI, HTTPException, Query
from .middleware import load_cfg
from .store import get_by_id
from .explain import render
app = FastAPI(title="KLoROS XAI", version="0.1.0")
_cfg = load_cfg()
@app.get("/xai/why")
def why(id: str = Query(...)):
    rec = get_by_id(_cfg, id)
    if not rec: raise HTTPException(404, "not found")
    return render(rec, _cfg)
@app.get("/xai/trace/{rec_id}")
def trace(rec_id: str):
    rec = get_by_id(_cfg, rec_id)
    if not rec: raise HTTPException(404, "not found")
    return rec
