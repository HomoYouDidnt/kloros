# Autonomous Self-Healing Loop - Integration Complete

## Architecture: Closed Feedback Loop

The autonomous loop integrates PHASE (scheduled regression) with Config Tuning (autonomous optimization) in a closed feedback system:

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS LOOP CYCLE                         │
│                     (Nightly at 3 AM)                            │
└─────────────────────────────────────────────────────────────────┘

┌────────────────┐
│  1. PHASE RUN  │  Scheduled Regression Testing (3-5 AM)
│   (2-4 hours)  │  - Run all 11 SPICA test domains
└───────┬────────┘  - Predictive mode (no canary VLLM, no downtime)
        │           - Write phase_report.jsonl
        │           - Completion signal with SHA256 validation
        ↓
┌────────────────┐
│  2. ANALYSIS   │  Degradation Detection (<10 seconds)
│    (<10s)      │  - Compare current metrics to 7-day baseline
└───────┬────────┘  - Detect: OOM events, latency regression, throughput drop
        │           - Calculate delta percentages
        │           - Record symptoms if thresholds exceeded
        ↓
        ┌─────────────────────────────────────┐
        │ Degradation Detected?               │
        └──┬──────────────────────────────┬───┘
           │ Yes                          │ No
           │ (3+ symptoms in 24h)         │ (System healthy)
           ↓                              ↓
   ┌───────────────┐              ┌──────────────┐
   │ SET ESCALATION│              │ END: Success │
   │     FLAG      │              │ No action    │
   └───────┬───────┘              └──────────────┘
           │
           ↓
   ┌───────────────┐
   │ 3. ELIGIBILITY│  Check Constraints (~1 second)
   │    CHECK      │  - Maintenance window? (3-7 AM)
   └───────┬───────┘  - Budget available? (60s/night)
           │           - Cooldown expired? (6h minimum)
           │
           ┌─────────────────────────────┐
           │ Eligible to Run Canary?     │
           └──┬──────────────────────┬───┘
              │ Yes                  │ No
              │                      │ (Defer to next cycle)
              ↓                      ↓
      ┌──────────────┐      ┌──────────────┐
      │ 4. CONFIG    │      │ END: Deferred│
      │    TUNING    │      │ Flag remains │
      │  (5-30 min)  │      └──────────────┘
      └──────┬───────┘
             │  - Generate 6 candidates via actuators
             │  - Test with SPICA canary (GPU mode)
             │  - Compute fitness scores
             │  - Promote best candidate
             ↓
      ┌──────────────┐
      │ Candidate    │
      │ Promoted?    │
      └──┬───────┬───┘
         │ Yes   │ No
         │       │ (All failed)
         ↓       ↓
   ┌─────────┐  ┌─────────────┐
   │ CLEAR   │  │ END: Failed │
   │ FLAG    │  │ Flag remains│
   └─────────┘  └─────────────┘
         │
         ↓
   ┌─────────────────────────────┐
   │ 5. VALIDATION (Next Night)  │
   │    - PHASE runs again       │
   │    - Test with promoted cfg │
   │    - Still degraded?        │
   │      → Loop continues        │
   │    - Improved?              │
   │      → SUCCESS! ✓           │
   └─────────────────────────────┘
```

## Key Components

### 1. PHASE (Scheduled Regression Testing)
**File:** `/home/kloros/src/kloros/orchestration/phase_trigger.py`

- **When:** 3 AM nightly (timer-triggered)
- **What:** Runs all 11 SPICA test domains
- **Mode:** Predictive only (no canary VLLM, no downtime)
- **Duration:** 2-4 hours (depends on domain count)
- **Output:** `phase_report.jsonl` with completion signal

**Purpose:** Validate system health, detect regression

---

### 2. Post-PHASE Analyzer
**File:** `/home/kloros/src/phase/post_phase_analyzer.py`

- **When:** Immediately after PHASE completion
- **What:** Compare current metrics to 7-day baseline
- **Detection:**
  - OOM events (GPU domain): critical if new, warning if >50% increase
  - Latency regression: warning if >20%, critical if >50%
  - Throughput drop: warning if >15%, critical if >30%
  - Pass rate drop: warning if >15%, critical if >30%
- **Duration:** <10 seconds
- **Output:** Symptoms recorded to Observer ledger, escalation flags armed

**Purpose:** Detect degradation patterns, trigger escalation

---

### 3. Escalation System
**Files:**
- `/home/kloros/src/observer/symptoms.py` (symptom tracking)
- `/home/kloros/src/kloros/orchestration/escalation.py` (flag management)

- **Symptom Ledger:** 24h rolling window (`.kloros/observer/symptoms/YYYYMMDD.jsonl`)
- **Threshold:** 3 symptoms in 24h → escalation flag armed
- **Flag TTL:** 4 hours (prevents stale escalations)
- **Flags:** `.kloros/flags/escalate_{kind}.json`

**Purpose:** Gate between detection and remediation

---

### 4. Config Tuning Runner
**File:** `/home/kloros/src/dream/config_tuning/runner.py`

- **When:** 5-7 AM if escalation flag armed + eligible
- **Eligibility:**
  - Maintenance window active (3-7 AM)
  - Budget available (60s/night max)
  - Cooldown expired (6h minimum)
- **Process:**
  1. Check escalation flag
  2. Generate 6 candidates via actuators (bounded)
  3. Test each with isolated SPICA canary
  4. Promote best passing candidate
  5. Clear escalation flag if successful
- **Duration:** 5-30 minutes (depends on candidate count)
- **Output:** Promotion to `/home/kloros/out/promotions/`

**Purpose:** Autonomous remediation with bounded risk

---

### 5. Autonomous Loop Orchestrator
**File:** `/home/kloros/src/kloros/orchestration/autonomous_loop.py`

- **Coordinates:** PHASE → Analysis → Eligibility → Config Tuning
- **Audit Trail:** `.kloros/autonomous_loop/cycles.jsonl`
- **Exit Codes:**
  - 0: Healthy (no degradation)
  - 1: Degraded (escalation armed but not fixed)
  - 2: Fixed (promotion successful)

**Purpose:** End-to-end orchestration, visibility

---

## System Integration

### Systemd Units

**Service:** `kloros-autonomous-loop.service`
- **Type:** oneshot
- **User:** kloros
- **Timeout:** 4 hours
- **Resources:** 8G mem, 400% CPU
- **ExecStart:** `python3 -m src.kloros.orchestration.autonomous_loop`

**Timer:** `kloros-autonomous-loop.timer`
- **Schedule:** `*-*-* 03:00:00` (3 AM daily)
- **Persistent:** Yes (run on boot if missed)
- **Accuracy:** 5 minutes

### Installation

```bash
# Copy service files
sudo cp /tmp/kloros-autonomous-loop.service /etc/systemd/system/
sudo cp /tmp/kloros-autonomous-loop.timer /etc/systemd/system/

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable kloros-autonomous-loop.timer
sudo systemctl start kloros-autonomous-loop.timer

# Verify timer
systemctl list-timers kloros-autonomous-loop.timer
```

---

## Safety Guarantees

### Bounded Execution
1. **PHASE:** Predictive mode only, no production impact, timeout 2h
2. **Analysis:** Read-only, fast (<10s)
3. **Config Tuning:** Canary mode with:
   - Budget limit: 60s/night
   - Rate limit: 3 runs/24h
   - Cooldown: 6h minimum
   - Timeout: 30s per candidate
   - Restore SLA: 15s

### Escalation Gates
- Symptom threshold: 3 in 24h (prevents spurious alerts)
- Flag TTL: 4h (prevents stale escalations)
- Eligibility check: window + budget + cooldown

### Validation Loop
- Promotions are ephemeral until next PHASE validates
- If still degraded → loop continues
- If improved → flag clears, success

---

## Operational Runbook

### Daily Operations

**Morning Check (8 AM):**
```bash
# Check last night's autonomous loop
sudo journalctl -u kloros-autonomous-loop.service --since "3:00" --until "8:00" | tail -50

# View cycle summary
tail -1 /home/kloros/.kloros/autonomous_loop/cycles.jsonl | jq .

# Check escalation status
ls -lh /home/kloros/.kloros/flags/
```

---

## Success Metrics

**Loop Health:**
- % of cycles with degradation signals (target: <10%)
- % of escalations resolved by config tuning (target: >80%)
- Time to resolution (detection → fix) (target: <24h)

**System Health:**
- OOM events trend (target: decreasing)
- Latency trend (target: stable or improving)
- Pass rate trend (target: >95%)

The autonomous loop is now **fully integrated and production-ready**. 🚀
