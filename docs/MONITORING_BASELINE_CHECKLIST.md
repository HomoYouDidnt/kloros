# Monitoring Baseline Setup Checklist

**Pre-Deployment Requirement**

Before switching from verification → PHASE testing → shadow deployment, confirm all telemetry infrastructure is operational.

---

## Required Components

### 1. Metrics Streaming

- [ ] **niche_health.json streaming to dashboard**
- [ ] **Baseline metrics captured** ✅

### 2. Alert Thresholds

- [ ] **Drift detection** (5% warn, 10% freeze, 20% rollback)
- [ ] **Error rate alerts** (5% warn, 10% critical)
- [ ] **Fitness degradation** (10% warn, 25% critical)

### 3. Log Retention

- [ ] **PHASE comparison logs** (30 days minimum)
- [ ] **Shadow mode logs** (90 days minimum)  
- [ ] **Mutation history** (indefinite)

### 4. Metric Aggregation

- [ ] **Granularity ≤ 5 minutes** ✅
- [ ] **Per-niche dimensions tracked**
- [ ] **System-wide metrics tracked**

### 5. Dashboard Panels

- [ ] Niche health overview
- [ ] Evolution velocity
- [ ] Stability metrics
- [ ] Resource utilization

### 6. Operational Runbooks

- [ ] Drift incident response documented
- [ ] Rollback execution procedures tested
- [ ] Mutation review process defined

---

## Sign-Off

**Verified By**: ____________________  
**Date**: ____________________

**Status**: Pending completion before shadow deployment
