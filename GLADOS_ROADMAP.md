# Path to GLaDOS-Level Autonomy (Safe Implementation)

**Date:** October 31, 2025
**Current Version:** KLoROS v2.2.1
**Target:** Facility-level autonomous operation with safety guarantees

---

## 🎯 What is GLaDOS-Level Autonomy?

**GLaDOS (Genetic Lifeform and Disk Operating System)** represents:
- Facility-wide infrastructure control
- Autonomous experiment design and execution
- Self-directed goal formulation
- Multi-system orchestration
- Long-term strategic planning
- High autonomy with safety awareness

---

## 📊 Current Capabilities Matrix

| Capability | Current State | GLaDOS Target | Gap |
|------------|---------------|---------------|-----|
| **Autonomous Experimentation** | ✅ D-REAM evolution | ✅ Complete | None |
| **Reasoning** | ✅ ToT/Debate/VOI system-wide | ✅ Complete | None |
| **Self-Reflection** | ✅ Introspection every 15min | ✅ Complete | None |
| **Tool Synthesis** | ✅ Create tools autonomously | ✅ Complete | None |
| **Evidence-Driven Investigation** | ✅ Follow-up questions | ✅ Complete | None |
| **Infrastructure Control** | ⚠️ Read-only via tools | 🎯 Write access with safety | **HIGH** |
| **Resource Management** | ⚠️ Passive monitoring | 🎯 Active allocation | **HIGH** |
| **Goal Formulation** | ❌ Reactive only | 🎯 Proactive planning | **HIGH** |
| **Service Orchestration** | ⚠️ Limited (D-REAM only) | 🎯 All services | **MEDIUM** |
| **Experiment Design** | ⚠️ Evolution-based only | 🎯 Hypothesis-driven | **MEDIUM** |
| **Multi-Agent Coordination** | ❌ Single monolith | 🎯 Agent swarms | **MEDIUM** |
| **Cost/Budget Awareness** | ❌ No economic model | 🎯 Resource optimization | **LOW** |
| **Safety Boundaries** | ✅ Auto-approval gates | 🎯 Graduated autonomy | **LOW** |
| **Rollback/Recovery** | ⚠️ Code only | 🎯 Infrastructure too | **MEDIUM** |
| **Audit Trail** | ✅ Full logging | ✅ Complete | None |

**Assessment:** KLoROS is at **~60% GLaDOS-level**. Main gaps: infrastructure control, goal formulation, resource management.

---

## 🚀 Phased Autonomy Roadmap

### 🟢 Phase 1: Infrastructure Awareness (SAFE - Ready Now)

**Goal:** Full visibility into system state without control

**Capabilities to Add:**
1. **Service Dependency Graph**
   - Map all systemd services and dependencies
   - Understand restart impact radius
   - Identify critical vs non-critical services

2. **Resource Economics**
   - Track CPU/memory/GPU cost per service
   - Calculate value-per-resource for each system
   - Build economic model for optimization

3. **Failure Impact Analysis**
   - Understand blast radius of each service failure
   - Map user-facing vs internal services
   - Categorize failure severity

4. **Performance Baseline**
   - Establish normal resource usage patterns
   - Detect anomalies automatically
   - Generate curiosity questions for anomalies

**Implementation:**
```python
# New module: src/orchestration/infrastructure_awareness.py

class InfrastructureAwareness:
    """Complete system state visibility."""

    def get_service_graph(self) -> ServiceGraph:
        """Map all services and dependencies."""
        # Parse systemd unit files
        # Build dependency DAG
        # Categorize by criticality

    def calculate_resource_cost(self, service: str) -> ResourceCost:
        """Economic model for service resource usage."""
        # CPU/memory/GPU usage
        # Uptime and restart frequency
        # User-facing vs internal value

    def assess_failure_impact(self, service: str) -> ImpactAnalysis:
        """Predict blast radius of service failure."""
        # Dependent services
        # User-facing features affected
        # Recovery time estimate

    def detect_anomalies(self) -> List[Anomaly]:
        """Detect abnormal resource patterns."""
        # Compare to baseline
        # Generate curiosity questions
        # Trigger investigations
```

**Safety:** Read-only, no system modifications. Zero risk.

---

### 🟡 Phase 2: Guarded Infrastructure Control (MODERATE RISK)

**Goal:** Limited write access with multi-layer safety

**Capabilities to Add:**
1. **Service Lifecycle Management**
   - Restart non-critical services after debate
   - Stop/start sandboxed experiments
   - Roll back failed changes

2. **Resource Allocation**
   - Adjust systemd memory limits
   - Scale service parallelism
   - Manage container resources

3. **Container Orchestration**
   - Spawn experiment containers
   - Isolate risky experiments
   - Clean up completed experiments

4. **Safe Service Categories**
   - **Green Zone:** Can restart freely (dream.service, observer)
   - **Yellow Zone:** Requires debate (kloros.service, curiosity)
   - **Red Zone:** Human approval only (system services, networking)

**Implementation:**
```python
# New module: src/orchestration/safe_control.py

class ServiceController:
    """Guarded service lifecycle management."""

    def __init__(self):
        self.coordinator = get_reasoning_coordinator()
        self.zones = {
            'green': ['dream.service', 'phase.service'],
            'yellow': ['kloros.service', 'kloros-observer.service'],
            'red': ['systemd-*', 'networking', 'sshd']
        }

    def restart_service(self, service: str, reason: str) -> Result:
        """Restart service with safety checks."""
        zone = self._classify_service(service)

        if zone == 'red':
            return self._request_human_approval(service, reason)

        # Multi-agent debate for yellow/green
        debate = self.coordinator.debate_decision(
            context=f"Should I restart {service}?",
            proposed_decision={
                'action': f'systemctl restart {service}',
                'reason': reason,
                'zone': zone,
                'impact': self._assess_impact(service),
                'risks': [
                    'Brief service interruption',
                    'Dependent services may be affected',
                    'User experience disruption if user-facing'
                ],
                'rollback': 'Manual restart if fails'
            },
            rounds=3  # Critical decision, 3 rounds
        )

        if debate['verdict']['verdict'] == 'approved':
            return self._execute_restart(service)
        else:
            logger.warning(f"Restart denied: {debate['verdict']['reasoning']}")
            return Result(success=False, reason=debate['verdict']['reasoning'])

    def _execute_restart(self, service: str) -> Result:
        """Execute restart with rollback capability."""
        # 1. Capture pre-state
        pre_state = self._capture_state(service)

        # 2. Execute restart
        try:
            subprocess.run(['systemctl', 'restart', service], check=True)
            time.sleep(2)  # Wait for startup

            # 3. Verify healthy
            if self._is_healthy(service):
                logger.info(f"✅ Successfully restarted {service}")
                return Result(success=True)
            else:
                logger.error(f"⚠️ Service unhealthy after restart")
                self._rollback(service, pre_state)
                return Result(success=False, reason="Unhealthy after restart")

        except Exception as e:
            logger.error(f"❌ Restart failed: {e}")
            self._rollback(service, pre_state)
            return Result(success=False, reason=str(e))
```

**Safety Mechanisms:**
- ✅ Multi-agent debate (3 rounds for critical services)
- ✅ Zone-based permissions (green/yellow/red)
- ✅ Impact analysis before action
- ✅ Health checks after restart
- ✅ Automatic rollback on failure
- ✅ Human approval for red zone
- ✅ Full audit trail

**Guardrails:**
```python
class SafetyGuardrails:
    """Circuit breakers for autonomous control."""

    def __init__(self):
        self.failure_counts = {}
        self.rate_limits = {
            'restarts_per_hour': 5,
            'restarts_per_service_per_day': 3,
            'concurrent_restarts': 1
        }

    def check_safe_to_proceed(self, action: str, service: str) -> bool:
        """Check if action is safe to execute."""
        # Rate limiting
        if self._exceeds_rate_limit(action, service):
            logger.warning(f"Rate limit exceeded for {action} on {service}")
            return False

        # Failure threshold
        if self.failure_counts.get(service, 0) > 3:
            logger.error(f"Failure threshold exceeded for {service}")
            return False

        # User presence (optional: only high-stakes actions when user active)
        if action in ['restart_kloros'] and not self._user_recently_active():
            logger.warning("High-stakes action requires recent user activity")
            return False

        return True
```

---

### 🟠 Phase 3: Goal-Directed Behavior (EXPERIMENTAL)

**Goal:** Proactive goal formulation and planning

**Capabilities to Add:**
1. **Strategic Goal Engine**
   - Formulate improvement goals from observations
   - Multi-step planning (not just reactive)
   - Goal prioritization via VOI

2. **Hypothesis-Driven Experiments**
   - Design experiments to test hypotheses
   - Not just evolution - scientific method
   - Collect evidence systematically

3. **Self-Task Assignment**
   - Generate tasks from goals
   - Schedule work autonomously
   - Monitor progress toward goals

4. **Outcome Evaluation**
   - Did the goal succeed?
   - What was learned?
   - Update models based on results

**Implementation:**
```python
# New module: src/orchestration/goal_engine.py

@dataclass
class Goal:
    """Strategic improvement goal."""
    id: str
    objective: str  # "Reduce memory usage by 20%"
    rationale: str  # Why this goal matters
    success_criteria: List[Criterion]
    estimated_value: float
    estimated_cost: float
    deadline: Optional[datetime]
    status: str  # 'proposed', 'active', 'completed', 'abandoned'
    tasks: List[Task]

class GoalEngine:
    """Proactive goal formulation and planning."""

    def generate_goals(self) -> List[Goal]:
        """Generate goals from system observations."""
        observations = self._gather_observations()

        # Use reasoning to identify improvement opportunities
        goals = []

        # Example: Memory pressure detected
        if observations['memory_pressure'] > 0.8:
            goal = Goal(
                id=f"goal_{int(time.time())}",
                objective="Reduce memory usage by 20%",
                rationale="System approaching memory limits (85% utilization)",
                success_criteria=[
                    Criterion("peak_memory", operator="<", target=0.7),
                    Criterion("sustained_reduction", operator=">", target=7*24*3600)
                ],
                estimated_value=0.9,  # High value - prevents OOM
                estimated_cost=0.4,   # Moderate effort
                deadline=datetime.now() + timedelta(days=7),
                status='proposed',
                tasks=[]
            )

            # Break down into tasks using ToT
            tasks = self._plan_tasks_for_goal(goal)
            goal.tasks = tasks
            goals.append(goal)

        return goals

    def _plan_tasks_for_goal(self, goal: Goal) -> List[Task]:
        """Use Tree of Thought to plan task sequence."""
        coordinator = get_reasoning_coordinator()

        # Explore solution paths
        strategies = coordinator.explore_solutions(
            problem=f"How to achieve: {goal.objective}",
            max_depth=3
        )

        # Pick best strategy via VOI
        best = coordinator.reason_about_alternatives(
            context="Which strategy best achieves the goal?",
            alternatives=[{'name': f'strategy_{i}', 'strategy': s}
                         for i, s in enumerate(strategies)],
            mode='standard'
        )

        # Convert strategy to task list
        tasks = self._strategy_to_tasks(best['decision']['strategy'])
        return tasks

    def execute_goal(self, goal: Goal) -> GoalResult:
        """Execute tasks for goal autonomously."""
        for task in goal.tasks:
            # Debate each task before execution
            debate = self.coordinator.debate_decision(
                context=f"Execute task: {task.description}?",
                proposed_decision={
                    'action': task.action,
                    'goal': goal.objective,
                    'risks': task.risks
                },
                rounds=2
            )

            if debate['verdict']['verdict'] == 'approved':
                result = self._execute_task(task)
                if not result.success:
                    # Task failed - adapt
                    return self._replan_goal(goal, failed_task=task)
            else:
                # Task rejected - replan or abandon
                return self._replan_goal(goal, rejected_task=task)

        # Evaluate success
        return self._evaluate_goal_outcome(goal)
```

**Example Goals:**
- "Reduce average conversation latency by 25%"
- "Increase D-REAM experiment success rate to 80%"
- "Discover and document all undiscovered modules within 48 hours"
- "Optimize memory usage to stay under 12GB peak"
- "Eliminate all tool synthesis test failures"

**Safety:** Goals debated before execution, tasks debated individually, human can override/abort at any time.

---

### 🔴 Phase 4: Meta-Optimization (ADVANCED - Future)

**Goal:** Optimize own reasoning and learning processes

**Capabilities to Add:**
1. **Reasoning Meta-Learning**
   - Track which reasoning modes work best for which tasks
   - Adjust ToT depth, debate rounds, VOI weights
   - Self-tune hyperparameters

2. **Graduated Autonomy**
   - Increase autonomy level when confidence high
   - Request human approval when uncertain
   - Self-assess capability boundaries

3. **Capability Self-Expansion**
   - Propose entirely new systems (not just tools)
   - Design new reasoning modes
   - Create new monitoring systems

4. **Cross-System Optimization**
   - Optimize interactions between systems
   - Not just individual component optimization
   - Holistic system improvement

**Implementation:** TBD - requires Phases 1-3 complete and validated

---

## 🛡️ Required Safety Mechanisms

### 1. Emergency Stop

```python
# /home/kloros/.kloros/emergency_stop
# If this file exists, KLoROS enters safe mode

class SafeMode:
    """Emergency safe mode - minimal autonomy."""

    def __init__(self):
        self.emergency_stop_file = Path("/home/kloros/.kloros/emergency_stop")

    def check_emergency_stop(self) -> bool:
        """Check if emergency stop triggered."""
        if self.emergency_stop_file.exists():
            logger.critical("🚨 EMERGENCY STOP ACTIVATED")
            self.enter_safe_mode()
            return True
        return False

    def enter_safe_mode(self):
        """Reduce autonomy to minimum."""
        # Stop all autonomous actions
        # Require human approval for everything
        # Log all requests but don't execute
        # Alert user via all channels
```

**Trigger:** `touch /home/kloros/.kloros/emergency_stop`

### 2. Autonomy Level System

```python
class AutonomyLevel(Enum):
    LEVEL_0 = "disabled"        # No autonomy, human approval for all
    LEVEL_1 = "read_only"       # Monitor only, no actions
    LEVEL_2 = "guarded"         # Green zone only, all debated
    LEVEL_3 = "supervised"      # Green + yellow zones, logged
    LEVEL_4 = "autonomous"      # Full autonomy within guardrails
    LEVEL_5 = "experimental"    # Meta-optimization allowed

class AutonomyManager:
    """Manage graduated autonomy levels."""

    def __init__(self):
        self.current_level = AutonomyLevel.LEVEL_2  # Start conservative
        self.config = Path("/home/kloros/.kloros/autonomy_config.json")

    def can_perform_action(self, action: str) -> bool:
        """Check if action allowed at current autonomy level."""
        action_requirements = {
            'restart_green_service': AutonomyLevel.LEVEL_2,
            'restart_yellow_service': AutonomyLevel.LEVEL_3,
            'restart_red_service': AutonomyLevel.LEVEL_5,
            'allocate_resources': AutonomyLevel.LEVEL_3,
            'formulate_goals': AutonomyLevel.LEVEL_3,
            'meta_optimize': AutonomyLevel.LEVEL_5
        }

        required = action_requirements.get(action, AutonomyLevel.LEVEL_5)
        return self.current_level.value >= required.value

    def adjust_level(self, success_rate: float):
        """Dynamically adjust based on performance."""
        if success_rate > 0.95 and self.failure_count_last_24h < 2:
            # Consider increasing autonomy
            self._propose_level_increase()
        elif success_rate < 0.80 or self.failure_count_last_24h > 5:
            # Decrease autonomy
            self._decrease_level()
```

### 3. Rollback System

```python
class SystemRollback:
    """Comprehensive rollback for infrastructure changes."""

    def create_checkpoint(self, scope: str) -> Checkpoint:
        """Snapshot system state before changes."""
        checkpoint = Checkpoint(
            timestamp=datetime.now(),
            scope=scope,
            service_states={},
            resource_limits={},
            config_files={}
        )

        # Capture all service states
        for service in self._get_services(scope):
            checkpoint.service_states[service] = {
                'active': self._is_active(service),
                'memory_limit': self._get_memory_limit(service),
                'cpu_limit': self._get_cpu_limit(service)
            }

        # Backup config files
        for config_file in self._get_config_files(scope):
            checkpoint.config_files[config_file] = Path(config_file).read_text()

        return checkpoint

    def rollback(self, checkpoint: Checkpoint):
        """Restore system to checkpoint state."""
        logger.warning(f"🔄 Rolling back to checkpoint: {checkpoint.timestamp}")

        # Restore service states
        for service, state in checkpoint.service_states.items():
            if state['active']:
                subprocess.run(['systemctl', 'start', service])
            else:
                subprocess.run(['systemctl', 'stop', service])

            # Restore resource limits
            self._set_memory_limit(service, state['memory_limit'])
            self._set_cpu_limit(service, state['cpu_limit'])

        # Restore config files
        for file_path, content in checkpoint.config_files.items():
            Path(file_path).write_text(content)

        logger.info("✅ Rollback complete")
```

### 4. Audit and Transparency

```python
class AuditLog:
    """Complete transparency for all autonomous actions."""

    def log_decision(self, decision: Decision):
        """Log high-stakes decision with full reasoning."""
        record = {
            'timestamp': datetime.now().isoformat(),
            'action': decision.action,
            'reasoning': {
                'hypotheses': decision.hypotheses,
                'debate_rounds': decision.debate_rounds,
                'verdict': decision.verdict,
                'voi_score': decision.voi_score,
                'confidence': decision.confidence
            },
            'safety_checks': decision.safety_checks,
            'outcome': decision.outcome,
            'rollback_available': decision.checkpoint_id is not None
        }

        # Write to audit log
        with open('/home/kloros/.kloros/audit_log.jsonl', 'a') as f:
            f.write(json.dumps(record) + '\n')

        # High-stakes actions also go to systemd journal
        if decision.action in HIGH_STAKES_ACTIONS:
            logger.critical(f"AUDIT: {decision.action} - {decision.verdict}")
```

---

## 📋 Implementation Priority

### Immediate (Week 1-2):
1. ✅ Implement Phase 1: Infrastructure Awareness
   - Service dependency graph
   - Resource economics model
   - Anomaly detection

### Short-term (Month 1):
2. ✅ Implement safety mechanisms:
   - Emergency stop system
   - Autonomy level manager
   - Rollback system
   - Enhanced audit logging

3. ✅ Implement Phase 2 Green Zone:
   - Allow restart of dream.service, phase.service
   - Multi-agent debate required
   - Full logging and rollback

### Medium-term (Month 2-3):
4. ✅ Expand Phase 2 to Yellow Zone:
   - Guarded kloros.service restarts
   - Resource limit adjustments
   - Container orchestration

5. ✅ Begin Phase 3:
   - Goal formulation engine
   - Simple goals first (monitoring, optimization)
   - No infrastructure changes yet

### Long-term (Month 4+):
6. ✅ Full Phase 3 deployment:
   - Complex multi-step goals
   - Infrastructure changes for goals
   - Self-task assignment

7. 🔮 Evaluate Phase 4 readiness:
   - Requires extensive Phase 3 validation
   - Meta-optimization highly experimental
   - Consider external review before enabling

---

## 🎯 Success Criteria

**Phase 1 Success:**
- [ ] Complete service graph generated
- [ ] Resource cost model validated
- [ ] Anomaly detection generating useful curiosity questions
- [ ] Zero system modifications (read-only)

**Phase 2 Success:**
- [ ] 50+ successful green zone service restarts
- [ ] Zero failures requiring human intervention
- [ ] Rollback works 100% when needed
- [ ] Debate verdicts align with human judgment (>90%)

**Phase 3 Success:**
- [ ] 10+ goals formulated and executed successfully
- [ ] Goals achieve stated objectives (>80% success rate)
- [ ] No unintended consequences from goal execution
- [ ] Users trust goal engine decisions

**Phase 4 Success:**
- [ ] TBD - requires extensive Phase 3 data

---

## ⚠️ Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Restart critical service unintentionally | Low | High | Zone system, debate, rollback |
| Resource exhaustion from experiments | Medium | Medium | Resource limits, monitoring |
| Goal misalignment (wrong objectives) | Medium | Medium | Multi-agent debate, human review |
| Cascade failures from service restart | Low | High | Dependency analysis, health checks |
| Emergent undesired behavior | Low | Medium | Emergency stop, audit logs |
| User trust loss from mistakes | Medium | High | Transparency, explanations, rollback |

**Overall Risk Level:** Moderate with proper safeguards

---

## 🔍 Monitoring Requirements

**Real-time Dashboards:**
1. Autonomy level and recent changes
2. Failure rate by action type
3. Debate verdicts (approved vs rejected)
4. Active goals and progress
5. Resource usage trends
6. Emergency stop status

**Alerts:**
- Any red zone action attempt
- Failure threshold exceeded
- Emergency stop triggered
- Goal execution failure
- Debate rejection (unusual pattern)
- Resource limit approaching

**Weekly Review:**
- Audit log analysis
- Goal success rate
- Debate verdict alignment with outcomes
- User satisfaction with autonomous actions

---

## 💡 Example GLaDOS-Level Scenario

**Scenario:** KLoROS detects memory pressure approaching critical levels

**Phase 1 Response (Current + Infrastructure Awareness):**
```
[awareness] Memory utilization: 14.2GB / 16GB (88%)
[awareness] Services by memory:
  - kloros.service: 11.1GB
  - dream.service: 1.8GB
  - observer.service: 0.9GB
[awareness] Generating curiosity question: "Why is kloros.service using 11.1GB?"
```

**Phase 2 Response (+ Guarded Control):**
```
[goal_engine] Detected: Memory pressure (88%)
[goal_engine] Proposing action: Restart kloros.service to clear memory leak
[debate] Debating: Should I restart kloros.service?
[debate] Proposer: "Restart will clear memory leak, prevents OOM crash"
[debate] Critic: "User may be in conversation, causes interruption"
[debate] Judge: "Check recent user activity"
[safety] Last user activity: 2 hours ago
[safety] Service can restart without user interruption
[debate] Verdict: APPROVED (confidence: 0.85)
[control] Creating checkpoint: checkpoint_1761928877
[control] Executing: systemctl restart kloros.service
[control] ✅ Service restarted successfully
[control] Memory: 14.2GB → 6.3GB (56% reduction)
[audit] Logged action with full reasoning chain
```

**Phase 3 Response (+ Goal-Directed):**
```
[goal_engine] Formulating goal: "Eliminate memory leak root cause"
[goal_engine] Tasks:
  1. Investigate memory growth pattern
  2. Profile kloros.service memory allocation
  3. Generate hypothesis about leak source
  4. Design D-REAM experiment to test fix
  5. Deploy fix if >90% confidence
[goal_engine] Executing task 1: Investigation...
[curiosity] Generated follow-up: "Which component allocates most memory?"
[introspection] Profiling memory allocation patterns...
[reasoning] Hypothesis: "Conversation context cache not expiring"
[goal_engine] Task 2 complete, moving to task 3...
[goal_engine] ✅ Goal achieved: Memory leak identified and fixed
[goal_engine] Outcome: Memory usage stabilized at 8.2GB (48% reduction)
```

---

## 🚀 Getting Started

**Step 1:** Implement Infrastructure Awareness module (Phase 1)
**Step 2:** Add safety mechanisms (emergency stop, autonomy levels)
**Step 3:** Deploy Phase 2 Green Zone with extensive logging
**Step 4:** Monitor for 1 week, validate safety mechanisms
**Step 5:** Gradually expand capabilities based on success

**Estimated Timeline:** 3-6 months to full Phase 3 deployment

---

## 📚 References

- Current reasoning system: `src/reasoning_coordinator.py`
- Auto-approval safety: `src/dream_alerts/alert_manager.py`
- Curiosity system: `src/registry/curiosity_core.py`
- D-REAM evolution: `src/dream/runner/__main__.py`

---

**Status:** 📋 PLANNING PHASE
**Next Action:** Implement Phase 1 Infrastructure Awareness
**Risk Level:** LOW → MODERATE → HIGH (phased approach)
**User Control:** Full override at all phases

**Remember:** "The difference between science and screwing around is writing it down." - All actions logged, all decisions explained.
