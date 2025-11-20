# SPICA Architecture Directive

**Date:** 2025-10-27  
**Status:** CRITICAL - All tests disabled pending migration

---

## Core Principle

**SPICA is the foundational template LLM ("programmable stem cell") from which every testable instance is derived.**

All D-REAM and PHASE tests **must** instantiate SPICA-derived instances. No tests may run outside the SPICA template. Domains are specializations of SPICA; experiments vary via configs/behaviors on SPICA instances.

---

## What SPICA Provides (Base Template)

1. **State Management** - Consistent cognitive state tracking
2. **Telemetry Schema** - Standardized metrics collection
3. **Manifest Logic** - Reproducible configuration snapshots
4. **Lineage Tracking** - Tamper-evident evolutionary history
5. **Instance Lifecycle** - Spawn, prune, retention management

---

## Architecture

```
SPICA (Base Template Class)
└── Provides:
    ├── State management primitives
    ├── Telemetry hooks and schema
    ├── Manifest creation/validation
    ├── Lineage HMAC tracking
    └── Instance lifecycle methods

SPICA Derivatives (Domain Specializations):
├── SpicaConversation(Spica)
│   └── + conversation evaluators, dialogue state
├── SpicaRAG(Spica)
│   └── + RAG metrics, retrieval evaluators
├── SpicaSystemHealth(Spica)
│   └── + health monitoring, resource metrics
├── SpicaTTS(Spica)
│   └── + voice synthesis metrics
└── Spica<Domain>(Spica)
    └── + domain-specific logic
```

---

## Migration Checklist

### 1. Type Hierarchy
- [ ] Create `class Spica(BaseTemplate)` as foundational base
- [ ] Derive all domains: `class SpicaConversation(Spica)`, `SpicaRAG(Spica)`, etc.
- [ ] Remove standalone domain classes that bypass SPICA

### 2. Import Refactoring
- [ ] Replace direct domain runners with SPICA derivatives
- [ ] Ensure no standalone domain runtimes exist
- [ ] Update all test files to import SPICA derivatives

### 3. Telemetry Standardization
- [ ] Route all metrics via SPICA's schema/hooks
- [ ] Remove ad-hoc domain-specific loggers
- [ ] Enforce telemetry schema validation at spawn time

### 4. Manifests & Lineage
- [ ] Enforce snapshot/manifest creation at every spawn
- [ ] Tag lineage metadata on all variant spawns
- [ ] Validate HMAC integrity before tournament evaluation

### 5. PHASE Harness
- [ ] Update PHASE runner to spawn `SPICA-*` instances only
- [ ] Evaluators must read SPICA telemetry exclusively
- [ ] Remove direct domain instantiation from test harness

### 6. Configuration
- [ ] Move domain knobs under `spica.instances.<domain>`
- [ ] Support config overlays for variant generation
- [ ] Validate configs against SPICA schema at load time

### 7. CI Gate
- [ ] Add CI check: fail builds if any test bypasses SPICA hooks
- [ ] Enforce: all telemetry must use SPICA schema
- [ ] Block: non-SPICA instance creation in test suite

### 8. Deprecation
- [ ] Remove `spica_domain.py` as a peer domain
- [ ] Keep SPICA as template base only (`spica/base.py`)
- [ ] Archive old domain implementations with migration notes

---

## Key Rules

1. **No tests outside SPICA** - Every experimental instance inherits from Spica base
2. **Structural compatibility** - All domains share state/telemetry/manifest structure
3. **Domain flexibility** - Specializations add behaviors without breaking base contracts
4. **Consistent telemetry** - D-REAM fitness evaluation requires uniform metrics schema
5. **Reproducibility** - Manifests ensure any instance can be recreated exactly

---

## Current Status

**All D-REAM and PHASE tests DISABLED** pending migration to SPICA architecture.

Services stopped:
- dream.service (D-REAM runner)
- spica-phase-test.timer (3 AM PHASE tests)
- phase-heuristics.timer (heuristics controller)
- dream-sync-promotions.timer (promotion sync)

**Next Steps:**
1. Audit existing domain implementations
2. Design SPICA base class with required methods
3. Migrate domains to SPICA derivatives
4. Update PHASE runner to use SPICA instances
5. Re-enable tests with SPICA compliance enforcement

---

## File Locations

- **SPICA Template**: `/home/kloros/experiments/spica/template/`
- **SPICA Base Class**: TBD (create `/home/kloros/src/spica/base.py`)
- **Domain Derivatives**: TBD (migrate from `/home/kloros/src/phase/domains/`)
- **Instance Storage**: `/home/kloros/experiments/spica/instances/`
- **Retention Policy**: `/home/kloros/src/dream/config/dream.yaml:spica_retention`

---

## Questions for Implementation

1. Should SPICA base class live in `/home/kloros/src/spica/base.py`?
2. Domain derivatives in `/home/kloros/src/spica/domains/` or keep in `/home/kloros/src/phase/domains/` with inheritance?
3. Backward compatibility: support old domains during migration or hard cutover?
4. CI enforcement: pytest plugin or pre-commit hook?

---

**Critical**: Do not re-enable any tests until SPICA migration is complete and validated.
