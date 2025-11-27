# KLoROS Autonomous Patterns - Quick Reference Playbook

**Purpose:** Common patterns and best practices for KLoROS autonomous development

---

## Pattern 1: The Autonomous Loop Structure

**When to use:** Implementing any self-improving system

**Structure:**
```
Detection → Question → Evolution → Deployment → Validation → Learning
    ↑                                                            ↓
    └────────────────────── FEEDBACK ──────────────────────────┘
```

**Implementation:**
```python
# 1. Detection (Observer)
observer.detect_anomaly() → emit_intent()

# 2. Question Generation (Curiosity)
curiosity.generate_question(intent) → curiosity_feed.json

# 3. Evolution (D-REAM)
dream.evolve_solution(question) → winner.json

# 4. Deployment (WinnerDeployer)
deployer.deploy_winner(winner) → update .kloros_env

# 5. Validation (ValidationLoop)
validator.test_deployment() → compare metrics

# 6. Learning (Feedback)
feedback.log_result() → curiosity_feedback.jsonl
```

**Key Points:**
- Each step must feed the next
- Failures logged, not hidden
- Loop must close (feedback critical)

---

## Pattern 2: Autonomy Gates

**When to use:** Deciding when to auto-execute vs require approval

**Structure:**
```python
def should_auto_execute(autonomy_level: int, risk_level: str) -> bool:
    """
    Autonomy Level 0: Manual approval for everything
    Autonomy Level 1: Auto-approve low-risk only
    Autonomy Level 2: Auto-approve low & medium risk
    Autonomy Level 3+: Auto-approve all
    """
    if autonomy_level >= 3:
        return True  # Full autonomy

    if autonomy_level >= 2 and risk_level in ["low", "medium"]:
        return True  # GLaDOS-level

    if autonomy_level >= 1 and risk_level == "low":
        return True  # Cautious autonomy

    return False  # Manual approval required
```

**Risk Assessment:**
```python
def assess_risk(params: Dict, domain: str) -> str:
    """Classify deployment risk."""
    # Low risk: Tuning within safe bounds
    # Medium risk: Changes that can be rolled back
    # High risk: Changes requiring manual review

    if domain in ["vllm", "tts", "conversation"]:
        return "medium"  # Config changes

    if domain in ["system", "kernel", "network"]:
        return "high"  # Infrastructure changes

    return "low"  # Default safe
```

**Example:**
```python
# In remediation_manager.py
def request_user_approval(experiments, autonomy_level):
    if autonomy_level >= 2:
        logger.info("Auto-approved at autonomy level 2")
        return experiments  # Auto-approve

    # Otherwise prompt user
    return prompt_user(experiments)
```

---

## Pattern 3: Validation With Rollback

**When to use:** After any configuration deployment

**Structure:**
```python
def validate_deployment(deployment_id: str, domain: str):
    # 1. Get baseline
    baseline = load_baseline(domain)

    # 2. Run tests
    new_metrics = run_domain_tests(domain)

    # 3. Compare
    improvement = compare(baseline, new_metrics)

    # 4. Decide
    if improvement >= min_threshold:
        update_baseline(domain, new_metrics)
        return "success"

    elif improvement < rollback_threshold:
        rollback_deployment(deployment_id)
        return "rollback"

    else:
        return "neutral"  # Keep but don't update baseline
```

**Thresholds:**
- Min improvement: +2% (keep and update baseline)
- Neutral range: -5% to +2% (keep but don't update)
- Rollback trigger: <-5% (revert deployment)

**Example:**
```python
# In validation_loop.py
result = validator.validate_deployment(
    deployment_id="abc123",
    experiment_name="vllm_tuning",
    domain="vllm",
    deployed_params={"context_length": 2048}
)

if result["status"] == "success":
    # Update baseline, feed success to curiosity
    pass
elif result["status"] == "rollback":
    # Restore previous config, feed failure to curiosity
    pass
```

---

## Pattern 4: Winner Deployment Pipeline

**When to use:** Automatically deploying D-REAM winners

**Structure:**
```python
# 1. Watch for new winners
for winner_file in winners_dir.glob("*.json"):
    winner_data = load_json(winner_file)

    # 2. Check if already deployed
    if hash(winner_data) in deployed_set:
        continue

    # 3. Extract params
    params = winner_data["best"]["params"]

    # 4. Map to config keys
    apply_map = map_params_to_config(params, experiment_name)

    # 5. Create promotion
    promotion = {
        "experiment": experiment_name,
        "apply_map": apply_map,
        "fitness": winner_data["best"]["fitness"]
    }

    # 6. Deploy
    promotion_applier.apply_promotion(promotion, hash)

    # 7. Validate
    validation_loop.validate_deployment(...)

    # 8. Mark as deployed
    deployed_set.add(hash(winner_data))
```

**Parameter Mapping:**
```python
def map_params_to_config(params: Dict, experiment: str) -> Dict:
    """Map D-REAM params to environment variables."""

    # Load param_mapping from dream.yaml
    mapping = load_dream_config()[experiment]["param_mapping"]

    apply_map = {}
    for param_name, param_value in params.items():
        config_key = mapping.get(param_name)
        if config_key:
            apply_map[config_key] = param_value

    return apply_map
```

---

## Pattern 5: Curiosity → D-REAM Bridge

**When to use:** Converting observations into experiments

**Structure:**
```python
# Observer emits intent
intent = {
    "type": "curiosity_question",
    "data": {
        "question_id": "resource.gpu.001",
        "hypothesis": "GPU_PRESSURE_HIGH",
        "dream_experiment": {
            "name": "gpu_tuning",
            "domain": "vllm",
            "search_space": {...},
            "metrics": {...}
        }
    }
}

# Coordinator processes
if intent_type.startswith("curiosity_"):
    dream_experiment = intent["data"]["dream_experiment"]

    # Spawn D-REAM experiment
    result = dream_trigger.run_once(
        experiment_name=dream_experiment["name"],
        config_override=dream_experiment
    )
```

**Question → Experiment Mapping:**
```python
def generate_experiment_from_question(question: Dict) -> Dict:
    """Convert curiosity question into D-REAM experiment config."""

    hypothesis = question["hypothesis"]

    if "DEGRADATION" in hypothesis:
        return {
            "name": f"remediation_{question['id']}",
            "type": "remediation",
            "search_space": extract_search_space(question),
            "budget": {"max_candidates": 12, "max_generations": 4}
        }

    elif "PRESSURE" in hypothesis:
        return {
            "name": f"resource_opt_{question['id']}",
            "type": "optimization",
            "search_space": extract_resource_params(question),
            "budget": {"max_candidates": 8, "max_generations": 3}
        }
```

---

## Pattern 6: Memory & Context Management

**When to use:** Maintaining conversation/system state

**Structure:**
```python
# 1. Start conversation
conversation_id = str(uuid.uuid4())
memory_logger.start_conversation(conversation_id)
repetition_checker.clear()
topic_tracker.clear()

# 2. Process user input
user_text = get_user_input()
topic_tracker.add_text(user_text, is_user=True)

# 3. Retrieve context
context = retrieve_context(
    conversation_id=conversation_id,
    max_events=20,  # Not 3!
    time_window_hours=24
)

# 4. Generate response
response = llm.generate(context + user_text)

# 5. Check repetition
is_repetitive, similar, score = repetition_checker.is_repetitive(response)
if is_repetitive:
    log_warning(f"Repetition detected: {score}")

# 6. Update tracking
repetition_checker.add_response(response)
topic_tracker.add_text(response, is_user=False)

# 7. Log to memory
memory_logger.log_llm_response(response, conversation_id)
```

**Key Limits:**
- Context events: 20 (not 3)
- Context chars: 2000 (not 500)
- Timeout: 60s (not 25s)
- Max turns: 20 (not 5)

---

## Pattern 7: Fail-Safe Error Handling

**When to use:** Any autonomous operation

**Structure:**
```python
def autonomous_operation():
    try:
        result = do_risky_operation()

        if result.success:
            log_success(result)
            update_baseline(result)
            return result

        else:
            log_failure(result)
            # Don't crash, continue with degraded mode
            return fallback_mode()

    except Exception as e:
        logger.error(f"Operation failed: {e}")

        # Log for investigation but don't stop autonomous loop
        log_error_for_review(e)

        # Continue with safe fallback
        return safe_default()
```

**Principles:**
- Log errors, don't hide them
- Fall back to safe defaults
- Never crash the autonomous loop
- Investigate later, keep running now

---

## Pattern 8: Baseline Tracking

**When to use:** Measuring improvement over time

**Structure:**
```python
def track_baseline(domain: str, metrics: Dict):
    """Update baseline metrics for a domain."""

    baseline_file = f"{baseline_dir}/{domain}_baseline.json"

    # Load current baseline
    current = load_baseline(baseline_file)

    # Compare
    if not current:
        # First run, establish baseline
        save_baseline(baseline_file, metrics)
        return "established"

    # Check improvement
    improvement = calculate_improvement(current, metrics)

    if improvement > 0:
        # Better, update baseline
        save_baseline(baseline_file, metrics)
        return "improved"
    else:
        # Worse or neutral, keep current baseline
        return "regressed"
```

**Baseline Format:**
```json
{
  "domain": "vllm",
  "metrics": {
    "throughput": 45.2,
    "latency_p50": 120.5,
    "error_rate": 0.02
  },
  "updated_at": "2025-11-01T15:42:00Z"
}
```

---

## Anti-Patterns (What NOT To Do)

### ❌ Anti-Pattern 1: Blocking Manual Gates
```python
# BAD: Always requires human approval
def deploy_winner(winner):
    if not ask_user("Deploy this?"):  # Blocks autonomy
        return
```

**Fix:** Use autonomy level gates
```python
# GOOD: Auto-approve at configured level
def deploy_winner(winner, autonomy_level):
    if autonomy_level >= 2:
        return auto_deploy(winner)
    return ask_user("Deploy this?")
```

---

### ❌ Anti-Pattern 2: Logging Without Action
```python
# BAD: Just logs, never acts
def process_intent(intent):
    logger.info(f"Got intent: {intent}")
    # TODO: Implement action  ← Never happens
    write_to_file(intent)  # Just logs
```

**Fix:** Actually execute
```python
# GOOD: Acts on intent
def process_intent(intent):
    logger.info(f"Processing intent: {intent}")
    result = execute_action(intent)  # Actually do it
    return result
```

---

### ❌ Anti-Pattern 3: Siloed Components
```python
# BAD: Components don't communicate
class Observer:
    def detect(self):
        save_to_file("problem.json")  # Dead end

class Fixer:
    def fix(self):
        # Doesn't know about observer
        pass
```

**Fix:** Connect components
```python
# GOOD: Components connected
class Observer:
    def detect(self):
        intent = create_intent("problem")
        emit_intent(intent)  # Coordinator will handle

class Coordinator:
    def process_intent(intent):
        fixer.fix(intent)  # Connected!
```

---

### ❌ Anti-Pattern 4: No Validation
```python
# BAD: Deploy and hope
def deploy(config):
    apply_config(config)
    # Hope it works!
```

**Fix:** Always validate
```python
# GOOD: Deploy → Validate → Rollback if bad
def deploy(config):
    baseline = get_baseline()
    apply_config(config)
    new_metrics = test()

    if worse_than(new_metrics, baseline):
        rollback(config)
```

---

### ❌ Anti-Pattern 5: Write-Only Feedback
```python
# BAD: Generate data nobody reads
def log_result(result):
    with open("results.jsonl", "a") as f:
        f.write(json.dumps(result))
    # Nobody reads this file
```

**Fix:** Feed back to learner
```python
# GOOD: Feedback actually used
def log_result(result):
    with open("results.jsonl", "a") as f:
        f.write(json.dumps(result))

    curiosity.learn_from_result(result)  # Actually used!
```

---

## Quick Checklist: Is Your Autonomous Loop Complete?

- [ ] Detection: Observer monitors system
- [ ] Question: Curiosity generates hypotheses
- [ ] Evolution: D-REAM optimizes solutions
- [ ] Auto-Approval: No manual gates (at level 2+)
- [ ] Deployment: Winners automatically applied
- [ ] Validation: Deployments tested
- [ ] Rollback: Bad deployments reverted
- [ ] Learning: Results fed back to Curiosity
- [ ] **LOOP CLOSES**: Feedback reaches detector

**If all checked: You have GLaDOS-level autonomy ✅**

---

## Common Debugging Commands

```bash
# Check autonomous loop status
tail -f /home/kloros/logs/orchestrator/curiosity_experiments.jsonl

# Monitor winner deployments
watch -n 60 'ls -lht /home/kloros/artifacts/dream/winners/ | head -10'

# Check validation results
tail -f /home/kloros/logs/orchestrator/validations.jsonl

# View learning feedback
tail -f /home/kloros/.kloros/curiosity_feedback.jsonl

# Check coordinator activity
journalctl -f | grep coordinator

# Verify autonomy level
grep KLR_AUTONOMY_LEVEL /home/kloros/.kloros_env
```

---

## References

**Implementation Examples:**
- Autonomous Loop: `/home/kloros/KLOROS_AUTONOMY_ANALYSIS_MASTER.md`
- Conversation Pattern: `/home/kloros/CONVERSATION_FIXES_APPLIED.md`
- Validation Logic: `/home/kloros/src/kloros/orchestration/validation_loop.py`
- Winner Deployment: `/home/kloros/src/kloros/orchestration/winner_deployer.py`

**Configuration:**
- Autonomy Gates: `/home/kloros/src/dream/remediation_manager.py`
- Context Limits: `/home/kloros/.kloros_env`
- Domain Mappings: `/home/kloros/src/dream/config/dream.yaml`

---

**Last Updated:** November 1, 2025
**Status:** Production-ready patterns
**Autonomy Level:** GLaDOS (70%+)
