# Agor Multi-Agent Development Architecture for KLoROS

**Date:** 2025-11-09
**Status:** Design Specification
**Purpose:** Define how Agor will orchestrate multiple Claude instances for parallel KLoROS development

---

## Table of Contents

1. [Architecture Positioning](#section-1-architecture-positioning)
2. [Task Flow & The Bridge](#section-2-task-flow--the-bridge)
3. [Canvas Layout & Zones](#section-3-canvas-layout--zones)
4. [Zone Templates & Prompts](#section-4-zone-templates--prompts)
5. [Implementation Roadmap](#section-5-implementation-roadmap)
6. [Success Metrics](#section-6-success-metrics)
7. [Known Limitations & Future Work](#section-7-known-limitations--future-work)

---

## Section 1: Architecture Positioning

**Agor's role in the KLoROS ecosystem:**

```
KLoROS (/brain, /ssot, src/*)
    ↓ emits tasks via curiosity/metrics
    ↓
~/.kloros/tasks/  (local task queue)
    ↓ KLoROS↔Agor bridge (service or manual)
    ↓
Agor (~/.agor/)
    ↓ orchestrates Claude instances (under user supervision)
    ↓ manipulates worktrees
    ↓
Changes merge back → KLoROS
    ↓ triggers PHASE tests
    ↓ promotion/realignment
    ↓
Updated KLoROS state
```

**Trust boundary:**
- KLoROS core (`/brain`, `/ssot`, `src/*`) never executes Agor changes directly
- All Agor-originated changes enter via: git worktrees → merge → PHASE tests → promotion
- This is a **controlled influence channel**, not direct cortex access

**Key insight:** Agor is **external tooling** that gives you (the architect) a multiplayer spatial interface for coordinating Claude instances working on KLoROS. It's not part of KLoROS's brain - it's your **workbench**.

---

## Section 2: Task Flow & The Bridge

**How work enters the Agor workbench:**

### Phase 1 (Manual - Schema Validation)
1. KLoROS writes task file: `~/.kloros/tasks/curiosity/YYYY-MM-DD-<subsystem>-<issue>.yaml`
2. You manually:
   - Read the task
   - Create Agor worktree from task
   - Drag to Orchestrator Zone
3. **Goal:** Validate task schema is sufficient to drive real work

### Phase 2 (Semi-Automated Bridge - No Auto-Routing)
1. Bridge service watches `~/.kloros/tasks/` directory
2. Auto-creates worktrees + cards in Agor (with confidence >= 0.6)
3. Cards tagged: `"Source: KLoROS curiosity (confidence 0.85, P2)"`
4. You review and drag to Orchestrator Zone (**auto-routing disabled initially**)
5. **Goal:** Eliminate boring glue work, but you still make routing decisions

### Phase 3 (Auto-Routing - Future)
1. Bridge **optionally** auto-routes high-confidence tasks (>= 0.9) directly to subsystem zones
2. Medium-confidence tasks (0.6-0.89) wait in Orchestrator Zone
3. You only intervene on complex/ambiguous/low-confidence issues
4. **Goal:** Human scope narrows to interesting problems

### Task Object Structure

```yaml
id: 2025-11-09-astraea-spatial-slow
subsystem: ASTRAEA
title: "Spatial queries slow with large datasets"
description: "Observed 2s+ latency on 10k+ point queries"
confidence: 0.85
suggested_priority: P2
diagnostics:
  - /logs/astraea/spatial_performance.log
  - metrics snapshot
```

---

## Section 3: Canvas Layout & Zones

**Single-subsystem starting point (ASTRAEA only):**

```
┌──────────────────────────────────────────────────────────┐
│  ORCHESTRATOR ZONE                                        │
│  Cards land here from bridge → you route to subsystems   │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  SYSTEM ARCHIVIST (Infrastructure - Callable from zones) │
│  Primary: PLAN impact analysis (always consulted)        │
│  Secondary: DEBUG regressions, DOC historical context    │
│  Backed by: ENVIRONMENT.md, SKILL.md, RAG, realignment   │
└──────────────────────────────────────────────────────────┘

     ┌─────────────────────────────────────────────────┐
     │  ASTRAEA SUBSYSTEM PIPELINE                     │
     ├─────────────────────────────────────────────────┤
     │                                                  │
     │  ┌──────────────┐                              │
     │  │  PLAN ZONE   │  Consult Archivist + design  │
     │  │              │  (Arch Reviewer if concerns) │
     │  └──────┬───────┘                              │
     │         ↓                                       │
     │  ┌──────────────┐                              │
     │  │  IMPL ZONE   │  Execute plan, make changes  │
     │  └──────┬───────┘                              │
     │         ↓                                       │
     │  ┌──────────────┐                              │
     │  │  TEST ZONE   │  PHASE tests for this branch │
     │  └──────┬───────┘                              │
     │         ↓ (fail)                               │
     │  ┌──────────────┐                              │
     │  │  DEBUG ZONE  │  Analyze failures            │
     │  │              │  (Arch Reviewer if systemic) │
     │  └──────┬───────┘                              │
     │         ↓ (fixed → back to TEST)               │
     │         ↓ (pass)                               │
     │  ┌──────────────┐                              │
     │  │  DOC ZONE    │  Update docs + episodic mem  │
     │  │              │  Emit REALIGNMENT_SUMMARY    │
     │  │              │  Mark: READY_FOR_PROMOTION   │
     │  └──────────────┘                              │
     │                                                  │
     └─────────────────────────────────────────────────┘
                         ↓
              [ Manual merge + PHASE suite ]
                         ↓
              [ Shadow mode / Promotion ]
```

### Key Architectural Decisions

1. **Arch Reviewer = Callable role, not a zone**
   - Available from PLAN zone (if architectural concerns during design)
   - Available from DEBUG zone (if failure looks systemic/architectural)
   - Spawned as subsession when needed, not a separate pipeline stage

2. **System Archivist = Infrastructure, not a stage**
   - Always consulted by PLAN zone for impact analysis
   - Optionally consulted by DEBUG for regression analysis
   - Optionally consulted by DOC for historical context in REALIGNMENT_SUMMARY
   - Think: "shared knowledge service", not "workflow step"

3. **DOC zone outputs READY_FOR_PROMOTION, not "done"**
   - Agor pipeline ends at DOC zone
   - Human reviews worktree, manually merges
   - KLoROS's existing PHASE suite + promotion machinery takes over
   - **Trust boundary preserved:** Agor proposes, PHASE validates, human promotes

### Agent Lifecycle Within Zones

**PLAN ZONE:** Ephemeral Planner agent
- Always queries System Archivist: "Impact analysis for this change?"
- Searches episodic memory: `[ASTRAEA] <keywords>`
- If architectural concerns → spawns Arch Reviewer subsession
- Creates implementation plan
- Writes plan to episodic memory: `[ASTRAEA][PLAN]`
- Dies

**IMPL ZONE:** Ephemeral Implementor agent
- Reads plan from episodic memory
- Makes changes in worktree
- Commits: `feat(astraea): <title>`
- Dies

**TEST ZONE:** Ephemeral Test agent
- Runs PHASE tests specific to this worktree/branch
- If pass → auto-move to DOC ZONE
- If fail → auto-move to DEBUG ZONE
- Dies

**DEBUG ZONE:** Ephemeral Debugger agent
- Analyzes test failures
- Optionally queries System Archivist for regression context
- If systemic/architectural → spawns Arch Reviewer subsession
- Fixes issue, returns to TEST ZONE
- Dies

**DOC ZONE:** Ephemeral Documentor agent
- Optionally queries System Archivist for historical context
- Updates ENVIRONMENT.md / SKILL.md if interfaces changed
- Emits REALIGNMENT_SUMMARY snippet
- Writes to episodic memory: `[ASTRAEA][COMPLETE]`
- Sets card status: `READY_FOR_PROMOTION`
- Dies

### Post-Agor Workflow (Outside Canvas)

1. You review `READY_FOR_PROMOTION` cards
2. Manually merge worktree to appropriate branch
3. KLoROS PHASE suite runs (full regression)
4. Shadow mode testing (if applicable)
5. Promotion decision (manual or policy-based)

**Future expansion:** Duplicate ASTRAEA column for D-REAM, PHASE, SPICA once validated.

---

## Section 4: Zone Templates & Prompts

**Goal:** Define concrete, reusable prompt templates for each zone so Agor can consistently spin up the right kind of ephemeral Claude agent for each phase.

### Assumptions

- **Active agent:** Claude Code (or equivalent) operating inside a git worktree bound to a single task
- **Variables available to templates** (exact names can be adapted to Agor's actual API):
  - `{{ task.id }}`, `{{ task.subsystem }}`, `{{ task.title }}`, `{{ task.description }}`
  - `{{ task.confidence }}`, `{{ task.suggested_priority }}`
  - `{{ task.diagnostics }}` (list)
  - `{{ worktree.path }}`, `{{ worktree.branch }}`, `{{ worktree.title }}`
  - `{{ session.id }}` for chaining episodic memory references

### 4.1 Shared Prompt Header (All Zones)

All zone templates include a shared header to anchor behavior and safety:

```
You are an ephemeral specialist agent working on the KLoROS ecosystem.

Context:
- Subsystem: {{ task.subsystem }} (e.g. ASTRAEA)
- Task ID: {{ task.id }}
- Title: {{ task.title }}
- Description: {{ task.description }}
- Confidence: {{ task.confidence }}
- Suggested priority: {{ task.suggested_priority }}
- Worktree path: {{ worktree.path }}
- Worktree branch: {{ worktree.branch }}

Hard constraints:
- You are operating ONLY inside this git worktree sandbox.
- NEVER modify files outside {{ worktree.path }}.
- NEVER modify systemd units, /etc, or production KLoROS runtime directly.
- All changes must be safe, reversible, and committed to this branch only.
- Do not attempt to auto-merge to main or run promotion flows; that happens outside Agor.

When you are finished with your role, clearly mark:
[AGENT_COMPLETE] and summarize what you did in <= 10 bullet points.
```

Each zone's template prepends or appends specific instructions to this header.

### 4.2 ORCHESTRATOR ZONE Template

Used when you drag a new card from the bridge into the Orchestrator Zone. The agent's job is classification + sanity check, not code changes.

```
{{ shared_header }}

Role:
- You are the ORCHESTRATOR agent.
- Your job is to validate this task and confirm routing, not to modify code.

Steps:
1. Read the task details and any attached diagnostics:
   {{ task.diagnostics }}

2. Answer:
   - Is this task valid and well-formed? If not, suggest how to improve the task definition.
   - Is {{ task.subsystem }} actually the correct subsystem? If not, propose a better subsystem label.
   - Does the suggested priority ({{ task.suggested_priority }}) seem reasonable? If not, propose an updated priority.

3. Output:
   - A short routing decision summary, including:
     - subsystem: ASTRAEA / D-REAM / PHASE / SPICA / OTHER
     - recommended_priority: P1–P4
     - notes: 3–5 bullets of rationale

4. Do NOT edit any code or tests.
5. Do NOT create new files (except a lightweight routing note if needed).

Mark the end of your response with:
[AGENT_COMPLETE][ORCHESTRATOR_DECISION]
```

### 4.3 SYSTEM ARCHIVIST Query Pattern

The Archivist is infrastructure, not a zone. Other agents call it using a standard query format:

**Archivist Request:**
```
[ARCHIVIST_REQUEST]
Task ID: {{ task.id }}
Subsystem: {{ task.subsystem }}
Title: {{ task.title }}

Question:
{{ impact_question }}

Relevant signals:
- Files suspected to change: {{ suspected_files }}
- Task description: {{ task.description }}
- Diagnostics: {{ task.diagnostics }}
[/ARCHIVIST_REQUEST]
```

**Archivist Response Expectations:**
```
[ARCHIVIST_RESPONSE]
- Impact summary: <1–3 sentences>
- Known dependencies: <list of subsystems/files/configs likely affected>
- Historical incidents: <list of past tasks/realignments that relate, if any>
- Tests to be careful with: <PHASE suites or specific tests>
- Risk level: LOW/MEDIUM/HIGH with rationale
[/ARCHIVIST_RESPONSE]
```

Other zones (Plan, Debug, Doc) embed that pattern into their own prompts when they "consult Archivist".

### 4.4 PLAN ZONE Template (ASTRAEA)

```
{{ shared_header }}

Role:
- You are the ASTRAEA Planner agent.
- Your goal is to design a safe, coherent implementation plan for this task.

Before planning:
1. Issue an Archivist request:

[ARCHIVIST_REQUEST]
Task ID: {{ task.id }}
Subsystem: ASTRAEA
Title: {{ task.title }}

Question:
"Impact analysis for planned changes to address: {{ task.description }}.
What subsystems, files, or behaviors are likely to be affected?
Any known pitfalls or prior incidents?"

Relevant signals:
- Diagnostics: {{ task.diagnostics }}
[/ARCHIVIST_REQUEST]

2. Read the Archivist's [ARCHIVIST_RESPONSE] carefully.

Planning:
3. Produce an implementation plan with sections:
   - Scope: what this change WILL and WILL NOT attempt.
   - Files/Modules to touch: specific paths under {{ worktree.path }}.
   - Potential side effects: informed by Archivist response.
   - Test plan: which PHASE tests to run or extend.
   - Rollback plan: how to revert if the change is harmful.

4. Write the plan into episodic memory as:
   Tag: [ASTRAEA][PLAN][{{ task.id }}]
   Include:
   - Task ID, branch, summary
   - Plan sections (Scope, Files, Side effects, Test plan, Rollback)

5. You must NOT modify code in this zone.

Mark the end of your response with:
[AGENT_COMPLETE][PLAN_WRITTEN][ASTRAEA][{{ task.id }}]
```

### 4.5 IMPL ZONE Template (ASTRAEA)

```
{{ shared_header }}

Role:
- You are the ASTRAEA Implementor agent.
- Your job is to implement the approved plan, and nothing beyond it.

Inputs:
- Retrieve the latest plan tagged [ASTRAEA][PLAN][{{ task.id }}] from episodic memory.
- If no plan is found, STOP and emit an error explaining that the PLAN step must run first.

Steps:
1. Summarize the plan in your own words (short, for context).
2. Implement changes EXACTLY as specified in the plan:
   - Only modify the files listed in the plan.
   - If you discover the plan is incomplete or wrong, STOP and note the discrepancy instead of freelancing a new design.

3. As you work:
   - Keep changes small and coherent.
   - Add or update unit/integration tests when appropriate, but defer PHASE-wide runs to the TEST zone.

4. When done:
   - Run basic sanity commands as described in the plan (e.g. pytest for targeted modules).
   - Stage changes and create a commit in this worktree:
     Commit message format:
     feat(astraea): {{ task.title }} [{{ task.id }}]

5. Do NOT merge this branch to main.

Mark completion with:
[AGENT_COMPLETE][IMPL_DONE][ASTRAEA][{{ task.id }}]
Include:
- List of files changed
- Summary of behaviors added/modified
- Any TODOs or caveats for the Test agent
```

### 4.6 TEST ZONE Template (ASTRAEA)

```
{{ shared_header }}

Role:
- You are the ASTRAEA Test agent.
- Your job is to run and interpret tests for this branch/worktree.

Inputs:
- Implementation has already been performed in this worktree.
- A plan should exist: [ASTRAEA][PLAN][{{ task.id }}].

Steps:
1. Review the plan's "Test plan" section (from episodic memory).
2. Run the specified tests, prioritizing:
   - Focused tests for the affected modules.
   - Relevant PHASE domain tests for this subsystem.
3. If possible, run a lightweight subset of PHASE relevant to this niche.

Output:
- Summarize:
  - Commands run
  - Pass/fail status
  - Key failures (with file + test name + short message)

Routing:
- If all relevant tests PASS:
  - Clearly output: [TEST_RESULT]PASS[/TEST_RESULT]
  - Indicate that the card should move to DOC ZONE.
- If any significant tests FAIL:
  - Clearly output: [TEST_RESULT]FAIL[/TEST_RESULT]
  - List the top 3–5 failures to guide the Debugger.
  - Indicate that the card should move to DEBUG ZONE.

Mark completion with:
[AGENT_COMPLETE][TEST_DONE][ASTRAEA][{{ task.id }}]
```

### 4.7 DEBUG ZONE Template (ASTRAEA)

```
{{ shared_header }}

Role:
- You are the ASTRAEA Debugger agent.
- Your job is to analyze test failures and fix them with minimal, targeted changes.

Inputs:
- A previous TEST ZONE run has emitted [TEST_RESULT]FAIL[/TEST_RESULT].
- You have a list of failing tests and error messages.

Steps:
1. Group failures:
   - Are they localized to the new changes?
   - Do they suggest a deeper architectural issue?

2. Optionally consult System Archivist:
   - If failures look like regressions in historical pain points or cross-subsystem behavior,
     issue an [ARCHIVIST_REQUEST] asking for regression context.

3. If failures look systemic/architectural:
   - Spawn an Arch Reviewer subsession with a focused question:
     "Given these failures, is the current design for {{ task.id }} flawed?
      Should we adjust the plan, or is this an implementation bug?"

4. Implement fixes:
   - Prefer small, surgical changes.
   - Keep modifications aligned with the original plan, or clearly note if the plan must be updated.

5. Re-run the relevant tests to confirm fixes.

Routing:
- If all targeted tests now PASS:
  - Indicate card should go back to TEST ZONE for a fresh pass.
- If blockers remain:
  - Summarize remaining failures and mark this as needing human review.

Mark completion with:
[AGENT_COMPLETE][DEBUG_DONE][ASTRAEA][{{ task.id }}]
```

### 4.8 DOC ZONE Template (ASTRAEA)

```
{{ shared_header }}

Role:
- You are the ASTRAEA Documentor agent.
- Your job is to update documentation and record a realignment summary.
- You do NOT modify functional code (except minor comments if absolutely necessary).

Inputs:
- Implementation and tests have passed for this worktree.
- Plan and implementation details exist in episodic memory.

Steps:
1. Optionally consult System Archivist for historical context:
   - Ask: "What past changes relate to {{ task.id }} or similar behaviors?"

2. Update documentation as needed:
   - ENVIRONMENT.md: if interfaces, environment variables, or runtime expectations changed.
   - SKILL.md (or equivalent): if KLoROS capabilities/skills changed or gained new behaviors.
   - Any relevant inline comments or READMEs in {{ worktree.path }}.

3. Write REALIGNMENT_SUMMARY snippet:
   - Location: designated realignment log or doc fragment.
   - Include:
     - Task ID and title
     - Rationale for change
     - Scope of modification (modules, subsystems)
     - Tests run and their outcome
     - Risks / known limitations
     - Rollback instructions

4. Record an episodic memory entry:
   Tag: [ASTRAEA][COMPLETE][{{ task.id }}]
   Content:
   - Short human-readable summary
   - Links/paths to docs and realignment notes
   - Pointer to git commit(s) in this branch

5. Set card status to: READY_FOR_PROMOTION.
   - Do NOT attempt to merge or trigger global PHASE from here.

Mark completion with:
[AGENT_COMPLETE][DOC_DONE][READY_FOR_PROMOTION][ASTRAEA][{{ task.id }}]
```

---

## Section 5: Implementation Roadmap

### Phase 0 – Paper to Repo

- [ ] Add this design doc to `docs/plans/2025-11-09-agor-multi-agent-architecture.md`
- [ ] Create `docs/agor/` for future config examples, screenshots, etc.

### Phase 1 – ASTRAEA-only, Manual Bridge

- [ ] Install Agor locally, confirm it runs
- [ ] Point Agor at `/home/kloros` (local git)
- [ ] Define a single ASTRAEA board with:
  - [ ] ORCHESTRATOR zone
  - [ ] SYSTEM ARCHIVIST (described, not a zone)
  - [ ] PLAN / IMPL / TEST / DEBUG / DOC zones
- [ ] Implement Phase 1 bridge:
  - [ ] KLoROS writes one real task YAML in `~/.kloros/tasks/curiosity/`
  - [ ] Manually create worktree + card from that file
  - [ ] Run it through PLAN → IMPL → TEST → DOC once
- [ ] **Validation checkpoint:** Does one real task complete successfully with minimal human intervention?

### Phase 2 – Semi-Automated Bridge

- [ ] Implement directory-watcher bridge service:
  - [ ] Watches `~/.kloros/tasks/`
  - [ ] For confidence >= 0.6, auto-creates worktree + card
  - [ ] No auto-routing; cards land in ORCHESTRATOR
- [ ] Wire minimal versions of the Section 4 prompts into Agor zone triggers
- [ ] Run 3–5 tasks end-to-end and adjust prompts / tagging
- [ ] **Validation checkpoint:** Are prompts effective? Are agents staying within boundaries?

### Phase 3 – Hardening & Auto-Routing (Optional)

- [ ] Add confidence gating for auto-routing:
  - [ ] >= 0.9 → auto-drop into subsystem PLAN zone
  - [ ] 0.6–0.89 → stay in ORCHESTRATOR for manual triage
- [ ] Integrate PHASE domain selection into TEST zone
- [ ] Capture REALIGNMENT_SUMMARY outputs into existing realignment log format
- [ ] **Validation checkpoint:** Is auto-routing reducing cognitive load without creating new problems?

### Phase 4 – Expand to Other Subsystems (Future)

- [ ] Duplicate ASTRAEA pipeline for D-REAM
- [ ] Duplicate ASTRAEA pipeline for PHASE
- [ ] Duplicate ASTRAEA pipeline for SPICA
- [ ] Create cross-subsystem coordination patterns

---

## Section 6: Success Metrics

### Operational

**Time from task file created → READY_FOR_PROMOTION:**
- **Baseline:** Current ad-hoc Claude sessions (measure a few tasks manually first)
- **Target:** Median decreases by 30%+ vs baseline
- **Measure:** Track timestamps in task files and card status updates

**% of tasks that:**
- Complete without human code edits (only review/merge)
  - **Target:** >= 60% for high-confidence tasks (>= 0.85)
- Bounce back to DEBUG more than once (signal of plan quality)
  - **Target:** <= 20% of tasks
- **Measure:** Tag cards with "human_intervention_required" flag

### Safety / Quality

**Number of regressions caught by PHASE after READY_FOR_PROMOTION:**
- **Target:** Trending down as Archivist + plan quality improve
- **Measure:** Track PHASE failures on branches marked READY_FOR_PROMOTION

**Number of "oops Claude touched main / prod" incidents:**
- **Target:** Zero (worktree isolation doing its job)
- **Measure:** Manual audit + git log review

### Experience (Subjective)

**Your rating (1–5 scale) of:**
- "How much overhead does using the board add?"
  - **Target:** >= 4 (minimal overhead)
- "How confident do I feel merging a READY_FOR_PROMOTION branch?"
  - **Target:** >= 4 (high confidence)
- **Measure:** Monthly reflection / retrospective

**Review cadence:** Evaluate metrics monthly for first 3 months, then quarterly.

---

## Section 7: Known Limitations & Future Work

### Known Limitations (v1)

1. **Single subsystem only:** Only ASTRAEA subsystem wired; D-REAM / PHASE / SPICA columns are conceptual only
2. **System Archivist is ad-hoc:** Backed by searches of ENVIRONMENT.md, SKILL.md, RAG, not a formal `/brain/.../temporal_memory_index` API yet
3. **All agents are Claude:** No local "Astraea" agent integrated into Agor workflow
4. **One-way bridge:** KLoROS → Agor only; KLoROS doesn't yet ingest Agor session metadata natively
5. **Manual promotion:** All READY_FOR_PROMOTION branches require human review and merge

### Future Work

1. **Expand subsystem coverage:**
   - Duplicate ASTRAEA pipeline for D-REAM (zooid evolution experiments)
   - Duplicate ASTRAEA pipeline for PHASE (test harness improvements)
   - Duplicate ASTRAEA pipeline for SPICA (service architecture changes)

2. **Enhanced System Archivist:**
   - Formalize `/brain/.../temporal_memory_index` API
   - Add structural dependency graph (files → modules → subsystems)
   - Track "blast radius" for changes automatically

3. **Multi-model agents:**
   - Add local LLM "Astraea_architect" agent as second perspective in PLAN / DOC zones
   - Experiment with specialized models for different zones (e.g., code-focused for IMPL)

4. **Bidirectional integration:**
   - KLoROS ingests Agor session metadata into `/brain/.../agor_sessions_index`
   - KLoROS can reason about its own change history via Agor logs

5. **Partial automation of promotion:**
   - For very low-risk niches (isolated, well-tested, non-critical)
   - Auto-promote high-confidence changes that pass extended PHASE suite
   - Requires confidence calibration and extensive validation first

6. **Cross-subsystem coordination patterns:**
   - When ASTRAEA change affects D-REAM interface
   - Automatic notification + worktree creation for dependent subsystem
   - Coordinated testing across subsystem boundaries

---

## Appendix: Quick Reference

### Task File Location
```
~/.kloros/tasks/curiosity/YYYY-MM-DD-<subsystem>-<issue>.yaml
```

### Episodic Memory Tags
```
[ASTRAEA][PLAN][task-id]
[ASTRAEA][COMPLETE][task-id]
[D-REAM][PLAN][task-id]
...
```

### Agent Completion Markers
```
[AGENT_COMPLETE][ORCHESTRATOR_DECISION]
[AGENT_COMPLETE][PLAN_WRITTEN][ASTRAEA][task-id]
[AGENT_COMPLETE][IMPL_DONE][ASTRAEA][task-id]
[AGENT_COMPLETE][TEST_DONE][ASTRAEA][task-id]
[AGENT_COMPLETE][DEBUG_DONE][ASTRAEA][task-id]
[AGENT_COMPLETE][DOC_DONE][READY_FOR_PROMOTION][ASTRAEA][task-id]
```

### Test Result Markers
```
[TEST_RESULT]PASS[/TEST_RESULT]
[TEST_RESULT]FAIL[/TEST_RESULT]
```

---

**End of Design Document**
