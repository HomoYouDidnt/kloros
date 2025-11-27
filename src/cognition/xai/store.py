import os, json
from typing import Iterator, Optional
from .record import DecisionRecord

def _path(cfg)->str:
    p = os.path.expanduser(cfg.get("store",{}).get("path","~/.kloros/xai_traces.jsonl"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p

def write(cfg, rec: DecisionRecord):
    p = _path(cfg)
    with open(p, "a", encoding="utf-8") as f:
        f.write(rec.model_dump_json() + "\n")

def read_all(cfg)->Iterator[DecisionRecord]:
    p = _path(cfg)
    if not os.path.exists(p): 
        def gen(): 
            if False: yield None
        return gen()
    def gen():
        with open(p,"r",encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if line:
                    yield DecisionRecord.model_validate_json(line)
    return gen()

def get_by_id(cfg, rec_id: str)->Optional[DecisionRecord]:
    for rec in read_all(cfg):
        if rec.id == rec_id:
            return rec
    return None
