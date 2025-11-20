# Pre-Unification Baseline

**Date:** October 18, 2025
**Run ID:** 74217edc
**Episode:** baseline_2025-10-18
**Purpose:** Capture pre-unification performance metrics for delta tracking

## Baseline Metrics

### Test Candidates (3 total)

| ID | Score | WER | VAD (ms) | Latency (ms) | Novelty | Result |
|----|-------|-----|----------|--------------|---------|--------|
| asr_baseline_1 | 0.75 | 0.22 | 45 | 125 | 0.25 | ❌ Rejected (score < 0.78) |
| asr_baseline_2 | 0.73 | 0.24 | 48 | 130 | 0.23 | ❌ Rejected (score < 0.78) |
| asr_baseline_3 | 0.76 | 0.23 | 42 | 118 | 0.24 | ❌ Rejected (score < 0.78) |

### Summary Statistics

- **Average Score:** 0.747
- **Average WER:** 0.230
- **Average VAD:** 45ms
- **Average Latency:** 124ms
- **Average Novelty:** 0.240

## Governance Results

- **Admitted:** 0 (none met score threshold of 0.78)
- **Rejected:** 3 (all below score threshold)

## Artifacts

- **Candidates:** `/home/kloros/src/dream/artifacts/PRE_UNIFICATION_BASELINE_74217edc/`
- **Report:** `/home/kloros/src/dream/artifacts/PRE_UNIFICATION_BASELINE_REPORT_74217edc/`
- **Raw Data:** `/home/kloros/src/dream/artifacts/phase_raw/baseline_2025-10-18.jsonl`

## Usage

This baseline represents the **pre-unification** state of ASR/TTS performance.
Future D-REAM runs can be compared against these metrics to measure improvement:

```bash
# Compare new run to baseline
NEW_SCORE=$(cat artifacts/candidates/$NEW_RUN_ID/pack.json | jq -r '.candidates[0].metrics.score')
BASELINE_SCORE=0.747
DELTA=$(echo "$NEW_SCORE - $BASELINE_SCORE" | bc)
echo "Score delta vs baseline: $DELTA"
```

## Notes

- All candidates below admission threshold (0.78) as expected for baseline
- WER values in acceptable range (< 0.25)
- VAD boundaries within acceptable range (< 50ms)
- Novelty scores modest (0.23-0.25)
- This establishes the floor for post-unification improvements

## Lineage

- **Origin:** phase
- **Episode ID:** baseline_2025-10-18
- **Generator SHA:** content-0c6e02f76090
- **Judge SHA:** frozen-2025-10-18
