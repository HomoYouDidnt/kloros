# KLoROS Autonomous Learning Loop - Master Analysis Report

**Date:** November 1, 2025
**Priority:** P0 - CRITICAL for GLaDOS-level autonomy
**Status:** 3% success rate → Target: 70%+

---

## Executive Summary

**User Goal:** "Help KLoROS reach the necessary threshold to cross into functional autonomous operation (GLaDOS-level autonomy)"

**Current State:** System has all the sophisticated pieces but they're **SILOED** - they don't connect into a closed learning loop.

**Root Cause:** 8 critical breaks in the autonomous learning flow + ~1,500 lines of disconnected/unused code

**Impact:** Only 3% success rate in chaos engineering/self-healing because:
- Curiosity generates questions ✅
- D-REAM evolves solutions ✅
- Winners are saved to files ✅
- **❌ NOTHING deploys the winners**
- **❌ Loop never closes**

---

## The Autonomous Learning Loop (Theory vs Reality)

### What SHOULD Happen (Intended Design)

```
┌────────────────────────────────────────────────────────┐
│                  AUTONOMOUS LEARNING LOOP               │
└────────────────────────────────────────────────────────┘

Observer (monitors system health)
    ↓
    Detects anomaly (OOM, latency spike, test failure)
    ↓
Curiosity (generates investigative questions)
    ↓
    "Why is VLLM using 95% GPU? Can we tune context_length?"
    ↓
D-REAM (evolutionary optimization)
    ↓
    Tests 100+ parameter combinations over 20 generations
    ↓
    Champion: context_length=2048 (was 4096), +15% throughput
    ↓
Deployment (applies winning configuration)
    ↓
    Updates .kloros_env, restarts service
    ↓
Validation (confirms improvement)
    ↓
    Runs PHASE tests, compares metrics before/after
    ↓
Learning (feeds back results)
    ↓
    Updates baseline, informs Curiosity of success
    ↓
    ← LOOP CLOSES, system learns and improves autonomously
```

### What DOES Happen (Actual Implementation)

```
┌────────────────────────────────────────────────────────┐
│              BROKEN LOOP WITH 8 CRITICAL BREAKS         │
└────────────────────────────────────────────────────────┘

Observer (monitors system health) ✅
    ↓
    Emits intent to ~/.kloros/intents/observer_*.json ✅
    ↓
Coordinator.tick() processes intent
    ↓
    ❌ BREAK #1: Most intents just get LOGGED, not executed
    ↓
Curiosity (generates questions) ✅
    ↓
    Writes to ~/.kloros/curiosity_feed.json ✅
    ↓
CuriosityProcessor.process_curiosity_feed() ✅
    ↓
    Spawns experiments (tournament or direct) ✅
    ↓
    ❌ BREAK #2: Experiments run once, results only logged
    ↓
D-REAM Runner (continuous evolution) ✅
    ↓
    Reads curiosity questions ✅
    ↓
    ❌ BREAK #3: Requires MANUAL approval (ignores autonomy level)
    ↓
    Evolves solutions over 20 generations ✅
    ↓
    Saves winner to artifacts/dream/winners/{exp}.json ✅
    ↓
    ❌ BREAK #4: NOBODY reads these winner files
    ↓
PromotionApplier EXISTS but...
    ↓
    ❌ BREAK #5: NEVER called from autonomous loop
    ↓
    ❌ BREAK #6: Expects apply_map but winners only have params
    ↓
ConfigTuningRunner works but...
    ↓
    ❌ BREAK #7: Only handles VLLM, not general D-REAM winners
    ↓
Validation EXISTS but...
    ↓
    ❌ BREAK #8: Only for config_tuning, not general deployments
    ↓
    ❌ Loop never closes, no feedback to Curiosity
```

---

## The 8 Critical Breaks (Detailed Analysis)

### BREAK #1: Observer Intents Just Get Logged
**File:** `/home/kloros/src/kloros/orchestration/coordinator.py` lines 194-216

**Problem:**
```python
elif intent_type.startswith("curiosity_"):
    # Curiosity-driven intent - spawn D-REAM exploration
    question_id = intent.get("data", {}).get("question_id", "unknown")
    hypothesis = intent.get("data", {}).get("hypothesis", "")

    logger.info(f"Curiosity exploration: {hypothesis} (question_id={question_id})")

    # For now, log the D-REAM experiment suggestion
    # TODO: Implement D-REAM spawner for curiosity-driven experiments  ← LITERALLY A TODO
    suggestions_log = Path("/home/kloros/logs/orchestrator/curiosity_experiments.jsonl")
```

**Impact:** Observer detects problems but they're never acted upon

**Fix Required:** Remove TODO, implement actual D-REAM spawner

---

### BREAK #2: Curiosity Experiments Run Once, Don't Persist
**File:** `/home/kloros/src/kloros/orchestration/curiosity_processor.py` lines 471-480

**Problem:**
```python
if action_class in ["propose_fix", "explain_and_soft_fallback"]:
    experiment_result = _spawn_direct_experiment(q)  # Runs once
    experiments_spawned += 1
else:
    experiment_result = _spawn_tournament(q)  # Tournament runs, champion logged
    experiments_spawned += 1

# Results written to curiosity_experiments.jsonl
# Champions NEVER deployed
```

**Impact:** Experiments find optimal solutions but they disappear

**Fix Required:** Add experiments to D-REAM runner's active list, deploy champions

---

### BREAK #3: D-REAM Requires Manual Approval (Ignores Autonomy)
**File:** `/home/kloros/src/dream/runner/__main__.py` lines 430-475

**Problem:**
```python
def inject_remediation_experiments(cfg, logdir):
    autonomy_level = int(os.environ.get("KLR_AUTONOMY_LEVEL", "0"))

    # Even with KLR_AUTONOMY_LEVEL=2, this prompts user:
    approved_new = request_user_approval(new_proposed, autonomy_level)
```

**Current Config:**
```bash
KLR_AUTONOMY_LEVEL=2  # Set but ignored
```

**Impact:** Human approval required for every experiment (breaks autonomy)

**Fix Required:** Auto-approve at autonomy level 2+

---

### BREAK #4: Winner Files Written But Never Read
**File:** `/home/kloros/src/dream/runner/__main__.py` lines 410-427

**Problem:**
```python
winners_dir = pathlib.Path(artifact_root) / "winners"
ensure_dir(winners_dir)
with open(winners_dir / f"{exp_name}.json", "w") as f:
    json.dump({"updated_at": now_ts(), "best": {
        "fitness": summary["best_fitness"],
        "params": summary["best_params"],
        "metrics": summary["best_metrics"],
    }}, f, indent=2)

# File written to: /home/kloros/artifacts/dream/winners/{experiment}.json
# NOBODY reads this file
```

**Impact:** Best solutions saved but never deployed

**Fix Required:** Create WinnerDeployer daemon to watch and deploy

---

### BREAK #5: PromotionApplier Exists But Never Called
**File:** `/home/kloros/src/dream_promotion_applier.py`

**Capabilities:**
```python
class PromotionApplier:
    def apply_promotion(self, promotion: Dict[str, Any], params_hash: str):
        # ✅ Validates against guardrails
        # ✅ Applies config changes to .kloros_env
        # ✅ Writes ACK files for audit
        # ✅ Tracks applied hashes
        # ❌ NEVER CALLED FROM AUTONOMOUS LOOP
```

**Impact:** 222 lines of deployment code completely unused

**Fix Required:** Call from WinnerDeployer

---

### BREAK #6: Winners Have Params, PromotionApplier Expects apply_map
**File:** `/home/kloros/src/dream_promotion_applier.py` lines 42-50

**Problem:**
```python
def apply_promotion(self, promotion: Dict[str, Any], params_hash: str):
    apply_map = promotion.get("apply_map", {})  # Expects this field

    if not apply_map:
        logger.warning(f"No apply_map in promotion {params_hash}")
        return  # Does nothing
```

**But winners look like:**
```json
{
  "best": {
    "params": {"context_length": 2048, "gpu_layers": 35},  // No apply_map!
    "fitness": 0.87
  }
}
```

**Impact:** Missing translation layer from params → config keys

**Fix Required:** Map params to apply_map using domain metadata

---

### BREAK #7: ConfigTuningRunner Only Handles VLLM
**File:** `/home/kloros/src/dream/config_tuning/runner.py`

**What Works:**
```python
class ConfigTuningRunner:
    # ✅ Spawns SPICA canaries
    # ✅ Tests configurations safely
    # ✅ Auto-promotes winners
    # ❌ ONLY handles VLLM parameters
    # ❌ Can't deploy general D-REAM winners
```

**Impact:** Autonomous deployment only works for VLLM tuning

**Fix Required:** Generalize or bypass for non-VLLM winners

---

### BREAK #8: Validation Only for Config Tuning
**File:** `/home/kloros/src/kloros/orchestration/autonomous_loop.py` lines 248-306

**Problem:**
```python
def _run_config_tuning(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    # ✅ Runs config tuning
    # ✅ Validates deployment
    # ✅ Compares metrics before/after
    # ❌ ONLY for config_tuning intent type
    # ❌ General D-REAM winners bypass this
```

**Impact:** No validation or rollback for general deployments

**Fix Required:** Generalize validation loop for all deployments

---

## Siloed & Overengineered Systems (~1,500 Lines)

### Category A: Complete Systems with No Consumers

1. **Triple Bridge Architecture** (3 files, ~800 lines)
   - `ToolDreamConnector` - Never imported
   - `ToolSynthesisToDreamBridge` - Never imported
   - `ProposalToCandidateBridge` - Only used by inactive helper
   - **Problem:** 3 implementations for the same task, none fully connected

2. **Improvement Proposer** (2 files, ~500 lines)
   - Analyzes failures, generates proposals
   - Writes to `improvement_proposals.jsonl` (20+ files exist)
   - **Problem:** `run_analysis_cycle()` NEVER called, proposals never consumed

3. **Flow-GRPO** (1 file, 302 lines)
   - Full RL optimization system with PPO-style clipping
   - **Problem:** ZERO imports in entire codebase

### Category B: Sophisticated Features That Don't Work

4. **Adaptive Search Space Manager** (1 file, 361 lines)
   - Plateau detection, boundary convergence, coverage expansion
   - **Problem:** Imported but never called, `adaptive: false` in all configs

5. **KL Anchor Drift Detection** (checks exist but no baseline)
   - **Problem:** No baseline metrics file, check always passes

6. **Diversity Metrics** (MinHash/Self-BLEU)
   - **Problem:** Self-BLEU completely unused, MinHash threshold too permissive

### Category C: Placeholder/Unfinished Code

7. **Tool Evolution System** (11 mutation operators)
   - All return `code` unchanged with `# TODO: Implement` comments
   - **Problem:** 11 placeholder functions doing nothing

8. **Hybrid ASR Corrections** (configured but dormant)
   - Config: `ASR_ENABLE_CORRECTIONS=1`
   - **Problem:** Backend never actually runs Whisper corrections

9. **MCP Protocol Experiment** (33 lines of config)
   - Complete config for non-existent MCP integration
   - **Problem:** `enabled: false  # Enable when MCP integration is ready`

---

## Priority Matrix (What to Fix First)

### Priority 1: CRITICAL - Close the Autonomous Loop (Required for Autonomy)

| Fix | Impact | Effort | ROI |
|-----|--------|--------|-----|
| **1. Winner Deployment Daemon** | Critical | Medium (4h) | 🔥🔥🔥 |
| Create service to watch winners/, deploy via PromotionApplier | Closes main loop | Write ~200 lines | Enables autonomy |
| **2. Auto-Approve at Autonomy Level 2** | Critical | Low (30m) | 🔥🔥🔥 |
| Modify request_user_approval to skip prompt at level 2+ | Removes manual gate | Change 5 lines | Immediate |
| **3. Params → apply_map Translation** | Critical | Medium (2h) | 🔥🔥 |
| Map D-REAM params to config keys using domain metadata | Enables deployment | Write mapping logic | Required |

**Expected Impact:** 3% → 50%+ success rate

---

### Priority 2: HIGH - Integration & Cleanup (Improves Reliability)

| Fix | Impact | Effort | ROI |
|-----|--------|--------|-----|
| **4. Curiosity → D-REAM Bridge** | High | Medium (3h) | 🔥🔥 |
| Add curiosity experiments to D-REAM active list | Persists experiments | Modify coordinator | Better evolution |
| **5. Generalized Validation Loop** | High | Medium (3h) | 🔥🔥 |
| Extend validation to all deployments, not just config_tuning | Safety net | Extend autonomous_loop | Rollback on regression |
| **6. Observer Intent Execution** | High | Low (1h) | 🔥 |
| Remove TODO, implement actual D-REAM spawner | Closes observer loop | Remove 1 TODO comment | Observer useful |

**Expected Impact:** 50% → 70%+ success rate

---

### Priority 3: MEDIUM - Code Cleanup (Reduces Complexity)

| Fix | Impact | Effort | ROI |
|-----|--------|--------|-----|
| **7. Remove Unused Bridges** | Medium | Low (30m) | 🔥 |
| Delete ToolDreamConnector, ToolSynthesisToDreamBridge | -600 lines | Delete files | Clarity |
| **8. Remove Flow-GRPO** | Low | Low (15m) | 🔥 |
| Delete if not using RL-based evolution | -302 lines | Delete file | Simplicity |
| **9. Remove/Fix Placeholder Mutators** | Low | Medium (2h) | 🔥 |
| Either implement with LLM or remove | -100 lines or real mutations | Decide + act | Honesty |

**Expected Impact:** Codebase clarity, easier maintenance

---

### Priority 4: FUTURE - Advanced Features (Post-Autonomy)

| Feature | When to Implement | Effort |
|---------|------------------|--------|
| Improvement Proposer activation | After loop closes | Low (schedule cron job) |
| Adaptive search space | If plateau detected | Low (set adaptive: true) |
| Hybrid ASR corrections | If STT accuracy poor | Medium (wire Whisper) |
| MCP integration | If external tools needed | High (full implementation) |

---

## The Fix Plan (Actionable Steps)

### PHASE 1: Close the Loop (Priority 1 - Today)

#### Step 1.1: Auto-Approve Experiments at Autonomy Level 2
**File:** `/home/kloros/src/dream/remediation_manager.py`

**Change:**
```python
def request_user_approval(experiments: List[Dict], autonomy_level: int) -> List[Dict]:
    """Request user approval for remediation experiments."""

    # NEW: Auto-approve at autonomy level 2+
    if autonomy_level >= 2:
        logger.info(f"[Autonomy L{autonomy_level}] Auto-approving {len(experiments)} experiments")
        return experiments

    # Otherwise, prompt user (existing logic)
    ...
```

**Test:** Check that experiments run without prompts when `KLR_AUTONOMY_LEVEL=2`

---

#### Step 1.2: Create Winner Deployment Daemon
**New File:** `/home/kloros/src/kloros/orchestration/winner_deployer.py`

**Implementation:**
```python
class WinnerDeployer:
    def __init__(self):
        self.winners_dir = Path("/home/kloros/artifacts/dream/winners")
        self.processed = set()  # Track deployed winners
        self.promotion_applier = PromotionApplier()

    def watch_and_deploy(self):
        """Watch winners directory and deploy new winners."""
        for winner_file in self.winners_dir.glob("*.json"):
            winner_hash = self._hash_file(winner_file)

            if winner_hash in self.processed:
                continue  # Already deployed

            winner_data = json.loads(winner_file.read_text())
            experiment_name = winner_file.stem

            # Deploy the winner
            success = self.deploy_winner(experiment_name, winner_data)

            if success:
                self.processed.add(winner_hash)

    def deploy_winner(self, experiment_name: str, winner_data: Dict) -> bool:
        """Deploy a D-REAM winner."""
        params = winner_data["best"]["params"]

        # 1. Map params to apply_map
        apply_map = self._params_to_apply_map(experiment_name, params)

        if not apply_map:
            logger.error(f"Could not map params for {experiment_name}")
            return False

        # 2. Create promotion
        promotion = {
            "experiment": experiment_name,
            "apply_map": apply_map,
            "fitness": winner_data["best"]["fitness"],
            "timestamp": winner_data["updated_at"]
        }

        # 3. Apply via PromotionApplier
        params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
        self.promotion_applier.apply_promotion(promotion, params_hash)

        # 4. Trigger validation (future: extend to all domains)
        # For now, log success
        logger.info(f"✅ Deployed winner for {experiment_name}: {apply_map}")
        return True

    def _params_to_apply_map(self, experiment_name: str, params: Dict) -> Dict:
        """Map D-REAM params to config keys using domain metadata."""
        # Load domain config to get parameter mappings
        domain_config = self._load_domain_config(experiment_name)

        apply_map = {}
        for param_name, param_value in params.items():
            config_key = domain_config.get("param_mapping", {}).get(param_name)
            if config_key:
                apply_map[config_key] = param_value

        return apply_map
```

**Integration:** Add to coordinator.tick() or create systemd timer

---

#### Step 1.3: Add Domain Parameter Mappings
**File:** `/home/kloros/src/dream/config/dream.yaml` (extend existing domain configs)

**Example:**
```yaml
experiments:
  vllm_config_tuning:
    search_space:
      context_length: [1024, 8192]
      gpu_layers: [0, 50]
    param_mapping:  # NEW FIELD
      context_length: "VLLM_CONTEXT_LENGTH"
      gpu_layers: "VLLM_GPU_LAYERS"
```

**Apply to all domains:** TTS, ASR, Conversation, RAG, etc.

---

### PHASE 2: Integration & Validation (Priority 2 - This Weekend)

#### Step 2.1: Curiosity → D-REAM Bridge
**File:** `/home/kloros/src/kloros/orchestration/coordinator.py`

**Change lines 194-216:**
```python
elif intent_type.startswith("curiosity_"):
    question_id = intent.get("data", {}).get("question_id", "unknown")
    dream_experiment = intent.get("data", {}).get("dream_experiment", {})

    # NEW: Actually spawn D-REAM experiment instead of just logging
    if dream_experiment:
        from . import dream_trigger
        result = dream_trigger.run_once(dream_experiment)
        logger.info(f"Spawned D-REAM experiment for curiosity question {question_id}: {result}")
    else:
        logger.warning(f"No dream_experiment in curiosity intent {question_id}")
```

---

#### Step 2.2: Generalized Validation Loop
**File:** `/home/kloros/src/kloros/orchestration/validation_loop.py` (new)

**Implementation:**
```python
class ValidationLoop:
    def validate_deployment(self, deployment_id: str, domain: str) -> Dict:
        """Validate a deployment by running domain tests."""

        # 1. Get baseline metrics
        baseline = self._get_baseline_metrics(domain)

        # 2. Run domain tests (PHASE or targeted)
        new_metrics = self._run_domain_tests(domain)

        # 3. Compare
        improvement = self._calculate_improvement(baseline, new_metrics)

        # 4. Decide: keep or rollback
        if improvement > 0:
            logger.info(f"✅ Deployment {deployment_id} improved {domain} by {improvement:.1%}")
            self._update_baseline(domain, new_metrics)
            return {"status": "success", "improvement": improvement}
        else:
            logger.warning(f"❌ Deployment {deployment_id} degraded {domain}, rolling back")
            self._rollback_deployment(deployment_id)
            return {"status": "rollback", "degradation": improvement}
```

**Call from:** WinnerDeployer after applying promotion

---

### PHASE 3: Cleanup (Priority 3 - Next Week)

#### Step 3.1: Remove Unused Code
```bash
# Remove unused bridges
rm src/dream/tool_dream_connector.py
rm src/dream/tool_synthesis_to_dream_bridge.py

# Remove unused RL system
rm src/dream/flow_grpo.py

# Remove backup files
rm src/dream/*.backup*
rm src/dream/config/*.backup*
```

#### Step 3.2: Fix Placeholder Mutators
**Decision:** Either implement with LLM or simplify to generic mutations

---

## Expected Outcomes

### After PHASE 1 (Priority 1 Fixes):
```
Observer detects problem
    ↓
Curiosity generates question
    ↓
D-REAM evolves solution (auto-approved at L2)
    ↓
WinnerDeployer watches winners/
    ↓
Maps params → apply_map
    ↓
PromotionApplier deploys to .kloros_env
    ↓
✅ System self-heals

Success Rate: 3% → 50%+
```

### After PHASE 2 (Priority 2 Fixes):
```
All of above, PLUS:

Validation Loop runs domain tests
    ↓
Compares metrics before/after
    ↓
Rollback if regression detected
    ↓
Feeds results to Curiosity
    ↓
✅ Loop closes, system learns

Success Rate: 50% → 70%+
```

### After PHASE 3 (Cleanup):
- ~1,000 lines of dead code removed
- Codebase clarity improved
- Maintenance burden reduced
- All remaining code is active and connected

---

## Metrics to Track

### Before Fix (Current State):
- Autonomy success rate: 3%
- Manual interventions: Daily
- Unused code: ~1,500 lines
- Critical breaks: 8
- Deployment latency: N/A (manual)

### After PHASE 1 (Target):
- Autonomy success rate: 50%+
- Manual interventions: Weekly
- Unused code: ~1,500 lines (cleanup later)
- Critical breaks: 3 (validation, feedback loop)
- Deployment latency: <10 minutes (automated)

### After PHASE 2 (Target):
- Autonomy success rate: 70%+
- Manual interventions: Monthly
- Critical breaks: 0
- Deployment latency: <5 minutes
- Learning feedback: Active

### After PHASE 3 (Target):
- Codebase: -1,000 lines (cleaner)
- Maintenance: Easier
- Onboarding: Simpler

---

## Files to Create/Modify (Master List)

### Create (New Files):
1. `/home/kloros/src/kloros/orchestration/winner_deployer.py` (~200 lines)
2. `/home/kloros/src/kloros/orchestration/validation_loop.py` (~150 lines)

### Modify (Existing Files):
1. `/home/kloros/src/dream/remediation_manager.py` (auto-approve logic)
2. `/home/kloros/src/kloros/orchestration/coordinator.py` (curiosity intent execution)
3. `/home/kloros/src/dream/config/dream.yaml` (add param_mapping to all domains)
4. `/home/kloros/src/kloros/orchestration/autonomous_loop.py` (call validation for all deployments)

### Delete (Cleanup):
1. `/home/kloros/src/dream/tool_dream_connector.py`
2. `/home/kloros/src/dream/tool_synthesis_to_dream_bridge.py`
3. `/home/kloros/src/dream/flow_grpo.py`
4. All `*.backup*` files

---

## Next Steps (Immediate Action)

1. ✅ Restart KLoROS with conversation fixes (DONE)
2. ✅ Complete comprehensive analysis (DONE - this report)
3. ⏳ **START: Implement Priority 1 fixes** (auto-approve + winner deployment)
4. ⏳ Test autonomous loop with simulated winner
5. ⏳ Document in playbooks
6. ⏳ Proceed to Priority 2

---

**Bottom Line:** KLoROS is "smart in the stupidest of ways" because it has all the sophisticated components (Curiosity, D-REAM, PromotionApplier, Validation) but they're **NOT CONNECTED**. The fix is straightforward: ~400 lines of glue code to close the loop, then cleanup the ~1,000 lines of unused code.

**ETA to functional autonomy:** 6-8 hours of focused work (Priority 1 + Priority 2)
