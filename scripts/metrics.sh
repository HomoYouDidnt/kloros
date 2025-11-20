#!/usr/bin/env bash
set -euo pipefail
mkdir -p /home/kloros/metrics

VOICE_LOG=/home/kloros/metrics/voice.csv
RAG_LOG=/home/kloros/metrics/rag.csv

[ -f "$VOICE_LOG" ] || echo "ts,verify_ms,asr_ms,tts_ms,backend" > "$VOICE_LOG"
[ -f "$RAG_LOG" ] || echo "ts,hit_rate5,mrr5,notes" > "$RAG_LOG"

ASR_RAW="$(python /home/kloros/scripts/verify_asr_vad.py /tmp/e2e_voice_reply.wav || true)"
ASR_MS="$(echo "$ASR_RAW" | sed -n 's/.*(\([0-9.]\+\)s).*/\1/p' | awk '{printf "%d",$1*1000}')"
BKND="$(rg -n 'XTTS|Mimic3' -S /home/kloros/src/voice/tts 2>/dev/null | head -1 | awk '{print $1}')"
echo "$(date +%FT%T),0,${ASR_MS:-0},0,${BKND:-unknown}" >> "$VOICE_LOG"

python - <<'PY' >> /home/kloros/metrics/rag.csv
import json, importlib, datetime
from pathlib import Path
gold = Path("/home/kloros/dream/golden/rag_golden.json")
rag = importlib.import_module("rag.pipeline")
data = json.load(open(gold))
total=hits=0; mrr=0.0
for item in data:
    res = rag.retrieve(item["query"], topk=5)
    docs = " ".join(r.get("text","") for r in res)
    ok = all(kw.lower() in docs.lower() for kw in item["keywords"])
    hits += 1 if ok else 0
    rr=0.0
    for i,r in enumerate(res,1):
        t=r.get("text","").lower()
        if any(kw.lower() in t for kw in item["keywords"]):
            rr=1.0/i; break
    mrr += rr; total += 1
ts = datetime.datetime.now().isoformat(timespec="seconds")
print(f"{ts},{hits/max(1,total):.4f},{mrr/max(1,total):.4f},auto-log")
PY

echo "[metrics] voice -> $VOICE_LOG"
echo "[metrics] rag   -> $RAG_LOG"
