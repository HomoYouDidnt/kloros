# D-REAM Judge SHA Registry

This file tracks frozen judge versions for lineage auditing.

## Active Judges

**Current:** `frozen-2025-10-18`

### frozen-2025-10-18
- **Date:** October 18, 2025
- **Implementation:** `src/dream/judges/frozen.py`
- **Scoring:** Weighted sum of metrics
- **Weights:** `{"score": 1.0}` (default)
- **Constraints:**
  - ASR/TTS: WER ≤ 0.25, VAD boundary ≤ 50ms
  - Score threshold: ≥ 0.78
  - Novelty threshold: ≥ 0.20
- **First Use:** Run cf7bd134 (smoke test)
- **Status:** ✅ Active

## Judge Evolution

Judges should remain frozen to ensure consistent evaluation across time. Create a new SHA when:
- Scoring algorithm changes
- Constraint thresholds change
- New domain constraints added

## Verification

To verify judge implementation matches registry:
```bash
cat /home/kloros/.kloros/dream_config.json | jq '.runtime.judge_sha'
```

Current artifacts using this judge can be found with:
```bash
rg -l "frozen-2025-10-18" /home/kloros/src/dream/artifacts/candidates/*/pack.json
```
