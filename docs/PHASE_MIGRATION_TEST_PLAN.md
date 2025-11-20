# PHASE Migration Test Plan
**Evolutionary Ingestion System - Production Deployment**

**Date**: 2025-11-08
**Version**: 1.0
**Status**: Pre-deployment validation framework

---

## Overview

This document defines the two-track testing approach, promotion gates, and rollback procedures for migrating legacy KLoROS services into the evolvable zooid ecology.

**Principle**: V0 wrapper zooids must demonstrate behavioral equivalence to legacy implementations before PHASE promotion. Mutation is only enabled after shadow-mode stability is proven.

---

## Migration Cohorts

### Cohort 1: Low-Risk Infrastructure (Deploy First)

**Niches**: `maintenance_housekeeping`, `observability_logging`

**Rationale**: These services have well-defined external contracts and observable outputs. Failures are recoverable and don't cascade.

**Timeline**: 2-4 weeks validation → ACTIVE → 2 weeks shadow → mutation enabled

### Cohort 2: Medium-Risk Cognitive Layer (Deploy Second)

**Niche**: `memory_decay`

**Rationale**: Affects long-term cognitive profile but changes are gradual and reversible. Requires longer observation window.

**Timeline**: 4-6 weeks validation → ACTIVE → 4 weeks shadow → conservative mutation only

### Cohort 3: High-Risk Immune System (Deploy Last)

**Niche**: `promotion_validation`

**Rationale**: Controls D-REAM's evolutionary gates. Bad mutations could destabilize the entire lifecycle system.

**Timeline**: 6-8 weeks validation → ACTIVE → 8 weeks shadow → parameter-only mutation

---

## Two-Track PHASE Testing

### Test Architecture

```
PHASE Test Execution:
├── Track A (Legacy Baseline)
│   ├── Run legacy daemon/scheduler
│   ├── Capture: outputs, side effects, timing, errors
│   └── Generate behavioral signature
│
├── Track B (Wrapper Zooid)
│   ├── Run v0 wrapper zooid
│   ├── Capture: same metrics as Track A
│   └── Generate behavioral signature
│
└── Comparison Engine
    ├── Diff outputs (exact match required)
    ├── Diff side effects (files, DB state, ChemBus signals)
    ├── Compare timing (within threshold)
    └── Compare error behavior
```

### Success Criteria (Per Niche)

**Pass threshold**: 3 consecutive PHASE cycles with:
- Output equivalence: 100%
- Side effect equivalence: ≥99%
- Timing variance: ≤10%
- Error equivalence: 100%

**Failure modes**:
- Any output mismatch → immediate failure
- Silent errors (zooid succeeds but wrong state) → critical failure
- Timing variance >25% → warning, re-test

---

## Risk Matrix

| Niche | Risk Level | Failure Impact | Rollback Speed | Mutation Priority |
|-------|-----------|----------------|----------------|-------------------|
| maintenance_housekeeping | Low-Medium | Disk space, maintenance delays | Fast (<5min) | High |
| observability_logging | Medium | Debugging blind spots | Fast (<2min) | Medium |
| memory_decay | Medium-High | Cognitive drift (gradual) | Medium (1h) | Low |
| promotion_validation | HIGH | D-REAM instability | Immediate | Very Low |

---

## Success Metrics (System-Wide)

### Evolutionary Metabolism Health

**Target State (6 months)**:
- 4/4 niches migrated to zooid ecology
- ≥2 niches with mutation enabled
- 0 critical failures from evolved zooids
- Fitness improvements: +10-30% vs v0 baseline
- Zero legacy daemon dependencies

---

**Document Owner**: KLoROS Evolutionary Metabolism Team
**Last Updated**: 2025-11-08
**Next Review**: After first cohort deployment
