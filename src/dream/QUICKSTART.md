# D-REAM Quick Start Guide

## Manual Trigger (Smoke Test)

```bash
# Set environment
export DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts
export PYTHONPATH=/home/kloros:$PYTHONPATH

# Create test PHASE report
cat > /home/kloros/src/phase/phase_report.jsonl <<'EOF'
{"epoch_id":"test_run","run_id":"t1","test_id":"asr_test","status":"pass","latency_ms":120,"score":0.85,"wer":0.18,"vad_boundary_ms":42,"novelty":0.35,"holdout_ok":true}
{"epoch_id":"test_run","run_id":"t2","test_id":"asr_test","status":"pass","latency_ms":180,"score":0.60,"wer":0.32,"vad_boundary_ms":65,"novelty":0.15,"holdout_ok":true}
EOF

# Run D-REAM evaluation
python3 -c "from src.phase.hooks import on_phase_window_complete; on_phase_window_complete('test_run')"

# Check results
ls $DREAM_ARTIFACTS/candidates/
curl http://localhost:5000/api/dream/candidates | jq
```

## Verify Setup

```bash
# Check config
cat ~/.kloros/dream_config.json | jq '.runtime'

# Check banned tools (should pass)
/home/kloros/src/dream/check_banned_tools.sh

# View smoke test results
cat $DREAM_ARTIFACTS/candidates/cf7bd134/pack.json | jq '.summary'
```

## Key Files

- **Config:** `~/.kloros/dream_config.json`
- **Judge Registry:** `/home/kloros/src/dream/JUDGE_SHA_REGISTRY.md`
- **Unit Check:** `/home/kloros/src/dream/check_banned_tools.sh`
- **Summary:** `/home/kloros/src/dream/UNIFICATION_FIX_SUMMARY.md`

## Active Domains

Only cognitive domains are active (banned tools quarantined):
- ✅ asr_tts_domain_evaluator.py
- ✅ audio_domain_evaluator.py
- ✅ conversation_domain_evaluator.py
- ✅ rag_context_domain_evaluator.py

## Governance Gates

- Score threshold: ≥ 0.78
- Novelty threshold: ≥ 0.20
- ASR/TTS constraints: WER ≤ 0.25, VAD ≤ 50ms
- Holdout regression blocking: enabled

## Dashboard

- URL: http://localhost:5000
- List candidates: `GET /api/dream/candidates`
- Approve: `POST /api/dream/approve` with `{"run_id":"<id>"}`

## Next Steps

1. Wire approval to adoption (uncomment in `routes_dream.py`)
2. Capture baseline PHASE window for deltas
3. Automate with phase-heuristics.timer (guards in place)
