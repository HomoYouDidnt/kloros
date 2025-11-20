# PHASE Hardening Roadmap

## Implemented ✓

### 1. Bandit State Persistence
- Cold-start priors (mean=0.5, n=1)
- Atomic JSON writes
- Exploration rate: 0.10 → 0.03 (after 100 selections)

### 2. Weight Capping  
- Min: 0.10, Max: 0.50
- Prevents mode collapse

### 3. Daily Snapshot
- Phase histogram, candidates/hour, acceptance ratio
- Generated: `/home/kloros/out/heuristics/summary.json`

### 4. Hints Expiry
- 2-hour TTL with HINTS_EXPIRED_FALLBACK

### 5. Timestamp Fix
- Robust parser handles all ISO-8601 formats
- 5 unit tests passing

## Next (After 2-3 Overnight Cycles)

- Reward shaping per domain (λ=0.8 decay)
- Resource pressure guard (CPU>85%, disk<15%)
- Rollback rails (canary E2E fails)
- Clock skew filter (future timestamps)

## Health Probes

```bash
# Exploration evidence
grep "Exploration rate:" /home/kloros/logs/heuristics_controller.log | tail -10

# Candidates per hour
jq '.candidates_per_hour' /home/kloros/out/heuristics/summary.json

# Phase distribution
jq '.phase_histogram' /home/kloros/out/heuristics/summary.json
```

## Status
**PHASE: OPERATIONAL + HARDENED**
Ready for autonomous multi-day operation.
