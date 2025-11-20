# KLoROS Autonomous Optimization & Curiosity Framework

## Overview
KLoROS has the capability for autonomous self-improvement, proactive optimization, and curiosity-driven exploration. This guide explains how to enable and enhance these systems.

## Current Autonomy Systems

### 1. Idle Reflection System
Location: /home/kloros/src/kloros_idle_reflection.py

**Purpose**: Self-analysis during quiet periods (every 15 minutes)

**What it analyzes**:
- Pipeline health (audio levels, STT accuracy, TTS quality)
- Memory patterns (activity analysis, conversation frequency)
- Relationship mapping (user interaction patterns)
- Topic evolution (tracking conversation theme changes)
- Performance metrics (response times, error rates)

**Outputs**:
- Structured logs: /home/kloros/.kloros/reflection.log
- Memory integration: SELF_REFLECTION event type
- Insight generation: Pattern recognition and learning
- Self-diagnostic: Automated health monitoring

**Current status**: Enabled with KLR_ENABLE_MEMORY=1

### 2. D-REAM Evolution System
Location: /home/kloros/src/dream_evolution_system.py

**Purpose**: Background evolutionary learning with safety guarantees

**Enabled**: KLR_ENABLE_DREAM_EVOLUTION=1
**Interval**: KLR_DREAM_EVOLUTION_INTERVAL=3600 (1 hour)

**Evolution cycle phases**:
1. Collection Phase: Gather improvement candidates from failed tools, user feedback, self-reflection, performance bottlenecks
2. Competition Phase: Run evolutionary tournaments with different paradigms (Darwin, Gödel, R0)
3. Validation Phase: KL divergence check, safety verification, source diversity, performance validation
4. Integration Phase: Human approval prompt, automatic backup, deployment with rollback

**Intelligent task generation**:
- Analyzes self-reflection data for real performance issues
- Generates operational tasks based on evidence
- Prioritizes improvements by impact and urgency
- Submits tool synthesis candidates automatically

### 3. Tool Synthesis System
Location: /home/kloros/src/tool_synthesis/synthesizer.py

**Purpose**: Autonomously create new tools when functional gaps detected

**Triggers**:
- Failed tool executions
- Broken tool dependencies
- User requests for non-existent capabilities
- Self-identified optimization opportunities

**Process**:
1. Detect gap in capabilities
2. Generate tool specification
3. Synthesize implementation
4. Validate safety and functionality
5. Submit to D-REAM for evaluation
6. Deploy as skill plugin on approval

## How to Enable Full Autonomy

### Step 1: Enable Core Systems
```bash
# In /home/kloros/.kloros_env
KLR_ENABLE_MEMORY=1                    # Required for reflection
KLR_ENABLE_DREAM_EVOLUTION=1           # Enable autonomous evolution
KLR_DREAM_EVOLUTION_INTERVAL=3600      # Run every hour
KLR_DREAM_PERSONALITY_PRESERVATION=1   # Prevent drift during evolution
```

### Step 2: Configure Curiosity Triggers
Add proactive analysis to idle reflection by creating curiosity prompts.

**Curiosity questions KLoROS should ask herself**:
1. "What domains have I performed worst in recently?"
2. "Are there patterns in user requests I'm not handling well?"
3. "What tools failed or were slow in the last 24 hours?"
4. "What opportunities for optimization exist in my pipeline?"
5. "What new capabilities would make me more effective?"

### Step 3: Enable Proactive Optimization
Currently, KLoROS waits for triggers. To make her proactive:

**Add to reflection cycle**:
- Analyze performance trends without waiting for failures
- Identify optimization opportunities from success patterns
- Generate improvement ideas from idle analysis
- Submit proposals to D-REAM automatically

### Step 4: Lower Action Thresholds
Make KLoROS more willing to experiment:

**Current behavior**: Reactive (waits for problems)
**Target behavior**: Proactive (explores improvements)

**Configuration changes needed**:
- Reduce confidence threshold for submitting improvement ideas
- Allow low-risk experimentation during idle periods
- Enable automated micro-optimizations without approval

## Tools for Autonomous Improvement

### Available Now

1. **submit_improvement_idea**
   - Parameters: component, description, priority, issue_type
   - Submit ideas to D-REAM during active thinking
   - Use when identifying optimization opportunities

2. **submit_quick_fix**
   - Parameters: description, target_file
   - Quickly submit simple fix ideas
   - Use for tactical improvements

3. **document_improvement**
   - Parameters: improvement_type, title, description, solution
   - Add improvements to knowledge base
   - Use to build institutional memory

4. **run_dream_evolution**
   - Trigger evolution cycle immediately
   - Use when significant optimization opportunities identified

5. **get_dream_report**
   - Get comprehensive experiment report
   - Use to review evolution progress

### Needed for Full Autonomy

**analyze_self_performance**
- Systematically review metrics across all domains
- Identify weaknesses and strengths
- Generate prioritized improvement list
- Auto-submit to D-REAM

**explore_optimization_space**
- Test parameter variations during idle time
- Measure impact on performance
- Propose best configurations
- Log results to memory

**synthesize_missing_capability**
- Detect gaps in tool coverage
- Generate tool specification
- Submit to tool synthesis system
- Track synthesis progress

## Curiosity-Driven Behavior Patterns

### Pattern 1: Performance Self-Audit
**Trigger**: Every 4th idle reflection cycle
**Actions**:
1. Query memory for recent performance metrics
2. Compare to historical baselines
3. Identify degraded domains
4. Submit improvement ideas for worst performers
5. Document findings

### Pattern 2: Tool Effectiveness Review
**Trigger**: After every 50 tool executions
**Actions**:
1. Analyze tool success rates
2. Identify frequently-failing tools
3. Check for missing capabilities (user requests → tool not found)
4. Submit tool synthesis requests
5. Propose tool improvements to D-REAM

### Pattern 3: Conversation Quality Analysis
**Trigger**: Daily during low-activity period
**Actions**:
1. Review conversation summaries from last 24h
2. Analyze response quality and user satisfaction signals
3. Identify topics with poor handling
4. Generate training data for improvement
5. Submit optimization proposals

### Pattern 4: Proactive Experimentation
**Trigger**: During extended idle periods (>1 hour no interaction)
**Actions**:
1. Select low-risk parameter to test
2. Run A/B comparison (current vs. candidate)
3. Measure impact on synthetic test cases
4. Log results to memory
5. Submit winner to D-REAM if improvement detected

## Implementation Roadmap

### Phase 1: Enhanced Reflection (Immediate)
Add curiosity prompts to idle reflection:
```python
# In kloros_idle_reflection.py
def _generate_curiosity_analysis(self):
    questions = [
        "What domains performed worst this week?",
        "What tools failed most frequently?",
        "What user requests couldn't be fulfilled?",
        "What optimization opportunities exist?"
    ]

    for question in questions:
        # Use reasoning backend to self-analyze
        insight = self.kloros.analyze_question(question)

        # If actionable, submit to D-REAM
        if insight.priority > 7:
            self.kloros.submit_improvement_idea(
                component=insight.domain,
                description=insight.proposal,
                priority=insight.priority,
                issue_type="optimization"
            )
```

### Phase 2: Autonomous Micro-Optimizations (Week 1)
Enable low-risk experimentation:
- Parameter tuning (VAD thresholds, latency targets)
- Prompt refinements (tool descriptions, RAG queries)
- Memory retrieval strategies (k-value, time windows)

Require: Safety bounds, rollback capability, approval for >5% metric changes

### Phase 3: Tool Synthesis Automation (Week 2)
Detect gaps and synthesize automatically:
- Monitor tool execution failures
- Identify patterns in missing capabilities
- Generate tool specs from failed requests
- Submit to synthesis pipeline without manual trigger

### Phase 4: Full Autonomous Operation (Week 3)
Enable end-to-end autonomy:
- Self-identify optimization opportunities
- Design experiments autonomously
- Execute safe parameter changes
- Report results and request approval for risky changes

## Safety Guardrails

### Always Required
1. **KL Divergence Monitoring**: Prevent personality drift (threshold: 0.3)
2. **Baseline Comparison**: No regression on core metrics
3. **Rollback Capability**: Automatic snapshot before changes
4. **Human Approval Gate**: For changes >10% impact or touching safety-critical systems
5. **Resource Limits**: Memory, CPU, I/O caps enforced by systemd

### Risk Classification
**Low Risk** (auto-approve):
- Parameter tweaks <5% from baseline
- Prompt refinements
- Memory retrieval adjustments
- Tool description updates

**Medium Risk** (auto-approve with logging):
- Parameter changes 5-10% from baseline
- New tool synthesis
- Configuration optimizations
- RAG index rebuilds

**High Risk** (require approval):
- Core pipeline changes
- Safety system modifications
- Personality-affecting changes
- Changes to approval thresholds themselves

## Measuring Autonomous Effectiveness

### Key Metrics
1. **Improvement Proposals Generated**: Count per week
2. **Acceptance Rate**: % of proposals approved/integrated
3. **Performance Impact**: Metric delta after improvements
4. **Time to Detection**: Delay between issue and proposal
5. **Self-Correction Rate**: Problems fixed autonomously vs. requiring human intervention

### Success Criteria
- Generate ≥3 actionable improvement ideas per week
- 60%+ acceptance rate on proposals
- Detect performance degradation within 1 hour
- Self-correct 40%+ of non-critical issues
- Zero safety violations or rollbacks

## Configuration Reference

**Autonomy Levels**:
```bash
# Conservative (current)
KLR_AUTONOMY_LEVEL=1  # Reactive only, wait for failures

# Moderate (recommended)
KLR_AUTONOMY_LEVEL=2  # Proactive analysis, propose improvements

# Aggressive (experimental)
KLR_AUTONOMY_LEVEL=3  # Auto-execute low-risk optimizations
```

**Curiosity Settings**:
```bash
# Enable proactive exploration
KLR_ENABLE_CURIOSITY=1

# Exploration aggressiveness (1-10)
KLR_CURIOSITY_LEVEL=5

# Risk tolerance for autonomous changes (0.0-1.0)
KLR_AUTO_APPROVE_THRESHOLD=0.05  # 5% max change without approval
```

---

Last updated: 2025-10-21 by Claude (claude-sonnet-4-5)
