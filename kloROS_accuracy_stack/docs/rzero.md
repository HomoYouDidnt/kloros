# RZERO Self-Improvement (Sandboxed)

Propose small config/prompt changes, evaluate on held-out sets, gatekeep by win criteria,
and only then stage a profile. No automatic code rewrites or guardrail weakening.

## CLI helper

```
scripts/rzero_run.py --dry-run
scripts/rzero_run.py propose --config kloROS_accuracy_stack/config/accuracy.yml --out out/rzero --count 4
scripts/rzero_run.py evaluate --config kloROS_accuracy_stack/config/accuracy.yml --candidates out/rzero/candidates/candidates.jsonl --out out/rzero
scripts/rzero_run.py gatekeep --config kloROS_accuracy_stack/config/accuracy.yml --reports out/rzero/reports
```

The CLI exits early if `self_improve.rzero_enabled` remains `false`. Enable it to drive
offline experiments while keeping production paths untouched.
