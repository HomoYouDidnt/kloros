# KLoROS Module Integration Action Plan

**Generated**: 2025-11-20
**Objective**: Wire 12 high-value orphaned modules into active system

---

## Quick Reference

**Immediate Deletions** (empty dirs):
```bash
rm -rf /home/kloros/src/synthesized_tools
rm -rf /home/kloros/src/vad
```

**Integration Order** (by priority):
1. mcp → 2. self_heal → 3. petri → 4. tool_synthesis → 5. dev_agent → 6. meta_cognition

---

## Integration Checklist

### Phase 1: Critical Infrastructure (3 modules)

#### 1. MCP (Model Context Protocol) ✅ CRITICAL
- **Why**: System introspection and capability awareness
- **Dependencies**: None (foundational)
- **Files**: `src/mcp/` (164K, 6 files)
- **Integration Points**:
  - [ ] Add `from src.mcp import MCPClient, CapabilityGraph` to registry init
  - [ ] Initialize `MCPClient` in startup sequence
  - [ ] Wire `CapabilityGraph` to capabilities.yaml loader
  - [ ] Add MCP introspection endpoints to ChemBus
- **Testing**: `pytest tests/test_mcp*.py`
- **Risk**: Low - standalone module with clean interfaces

#### 2. Self-Heal (Autonomous Repair) ✅ CRITICAL
- **Why**: Event-driven failure detection and repair
- **Dependencies**: ChemBus (already active)
- **Files**: `src/self_heal/` (260K, 18 files)
- **Integration Points**:
  - [ ] Subscribe `HealBus` to ChemBus error channels
  - [ ] Load healing playbooks from `config/self_heal_playbooks/`
  - [ ] Initialize `SystemHealthMonitor` as daemon
  - [ ] Wire `HealExecutor` to execute repair actions
  - [ ] Add outcomes logging to observability
- **Testing**: `pytest tests/test_self_heal*.py`
- **Risk**: Medium - needs careful ChemBus integration

#### 3. PETRI (Safety Sandbox) ✅ CRITICAL
- **Why**: Sandbox tool execution before enabling synthesis
- **Dependencies**: None (safety layer)
- **Files**: `src/petri/` (92K, 7 files)
- **Integration Points**:
  - [ ] Wrap all tool execution through `check_tool_safety()`
  - [ ] Add PETRI risk assessment to tool registry
  - [ ] Configure safety policies in `config/petri_policies.yaml`
- **Testing**: `pytest tests/test_petri*.py`
- **Risk**: Low - wrapper layer, doesn't break existing code

---

### Phase 2: Capability Expansion (3 modules)

#### 4. Tool Synthesis (Autonomous Tool Creation) 🔧 HIGH
- **Why**: Enable self-expanding capabilities
- **Dependencies**: PETRI (for safety), MCP (for registration)
- **Files**: `src/tool_synthesis/` (336K, 26 files)
- **Integration Points**:
  - [ ] Initialize `ToolSynthesizer` in registry
  - [ ] Wire `ToolValidator` → PETRI for safety checks
  - [ ] Configure `SynthesizedToolStorage` location
  - [ ] Add synthesis events to ChemBus
  - [ ] Enable synthesis in curiosity loop
- **Testing**: `pytest tests/test_tool_synthesis*.py`
- **Risk**: High - generates code dynamically, needs PETRI first

#### 5. Dev Agent (Code Repair) 🔧 HIGH
- **Why**: Self-repair broken code automatically
- **Dependencies**: Tool registry
- **Files**: `src/dev_agent/` (260K, 22 files)
- **Integration Points**:
  - [ ] Add `CodingAgent` to agent registry
  - [ ] Wire to self_heal for code repair actions
  - [ ] Configure repo indexer for KLoROS codebase
  - [ ] Add validation pipeline (tests + linters)
- **Testing**: `pytest tests/test_dev_agent*.py`
- **Risk**: High - modifies code, needs careful testing

#### 6. Meta-Cognition (Self-Awareness) 🧠 HIGH
- **Why**: Conversational self-awareness and quality monitoring
- **Dependencies**: Consciousness, memory systems (already active)
- **Files**: `src/meta_cognition/` (72K, 5 files)
- **Integration Points**:
  - [ ] Call `init_meta_cognition(kloros_instance)` in startup
  - [ ] Wrap response generation with `process_with_meta_awareness()`
  - [ ] Add meta-stream output to dashboard
  - [ ] Wire to reflective memory system
- **Testing**: `pytest tests/test_meta_cognition*.py`
- **Risk**: Low - augments existing systems without breaking them

---

### Phase 3: Enhanced Features (6 modules)

#### 7. Scholar (Report Generation) 📊 MEDIUM
- **Why**: Generate reports with citations
- **Dependencies**: TUMIX reviewers (check if active)
- **Files**: `src/scholar/` (60K, 11 files)
- **Integration Points**:
  - [ ] Add scholar commands to CLI
  - [ ] Wire `Collector` to memory/metrics systems
  - [ ] Configure report templates
- **Testing**: `pytest tests/test_scholar*.py`
- **Risk**: Low - utility module

#### 8. Dream Lab (Chaos Testing) 🧪 MEDIUM
- **Why**: Systematic failure injection for resilience testing
- **Dependencies**: self_heal (for testing healing responses)
- **Files**: `src/dream_lab/` (140K, 9 files)
- **Integration Points**:
  - [ ] Load failure specs from `config/chaos_specs/`
  - [ ] Initialize `ChaosOrchestrator` as optional daemon
  - [ ] Wire `TraceObserver` to observability
  - [ ] Add chaos controls to dashboard
- **Testing**: `pytest tests/test_dream_lab*.py`
- **Risk**: Medium - intentionally breaks things (sandbox required)

#### 9. ACE (Context Engineering) 🎯 MEDIUM
- **Why**: Self-improving context hints for LLM calls
- **Dependencies**: LLM registry
- **Files**: `src/ace/` (60K, 5 files)
- **Integration Points**:
  - [ ] Wrap LLM calls with ACE context injection
  - [ ] Store context hints in ACE database
  - [ ] Add feedback loop for hint evolution
- **Testing**: `pytest tests/test_ace*.py`
- **Risk**: Low - wrapper layer

#### 10. STT (Speech-to-Text) 🎤 MEDIUM
- **Why**: Enable voice input (Vosk/Whisper)
- **Dependencies**: Audio input stream
- **Files**: `src/stt/` (200K, 13 files)
- **Integration Points**:
  - [ ] Initialize `create_stt_backend()` in voice pipeline
  - [ ] Configure Vosk/Whisper model paths
  - [ ] Wire STT output to conversation input
- **Testing**: `pytest tests/test_stt*.py`
- **Risk**: Low - input layer only

#### 11. C2C (Cache-to-Cache Communication) 🔄 MEDIUM
- **Why**: Semantic context transfer between LLM subsystems
- **Dependencies**: LLM registry
- **Files**: `src/c2c/` (36K, 4 files)
- **Integration Points**:
  - [ ] Initialize `C2CManager` globally
  - [ ] Wrap Ollama/Claude calls with `inject_context_into_ollama_call()`
  - [ ] Configure context cache size/TTL
- **Testing**: `pytest tests/test_c2c*.py`
- **Risk**: Low - optional enhancement

#### 12. Core (Conversation Flow) 💬 MEDIUM
- **Why**: Structured conversation and dialogue management
- **Dependencies**: None (may already be partially integrated)
- **Files**: `src/core/` (84K, 4 files)
- **Integration Points**:
  - [ ] Check if `ConversationFlow` is already active
  - [ ] If not: initialize in KLoROS main loop
  - [ ] Wire to memory system for persistence
- **Testing**: `pytest tests/test_core*.py`
- **Risk**: Low - check for existing integration first

---

## Risk Mitigation

### High-Risk Integrations
- **tool_synthesis**: MUST integrate PETRI safety first
- **dev_agent**: Test in isolated branch before main
- **dream_lab**: Only enable in dev/test environments initially

### Testing Strategy
1. **Unit Tests**: Run module's own test suite first
2. **Integration Tests**: Test interactions with existing modules
3. **Smoke Tests**: Full system boot with module enabled
4. **Rollback Plan**: Git tag before each integration

### Rollback Procedure
```bash
# Before each integration
git tag -a pre-integration-<module> -m "Before integrating <module>"

# If integration fails
git reset --hard pre-integration-<module>
systemctl restart kloros
```

---

## Dependencies Graph

```
Legend: → depends on

mcp (standalone)
├→ tool_synthesis → petri, mcp
├→ self_heal → chembus (active)
└→ dev_agent → tool_registry (active)

petri (standalone)

meta_cognition → consciousness (active), memory (active)

scholar → tumix (check if active)
dream_lab → self_heal
ace → llm_registry (active)
stt → audio_stream (check if active)
c2c → llm_registry (active)
core → memory (active)
```

**Critical Path**: mcp → petri → self_heal → tool_synthesis

---

## Success Metrics

### Module Integration Success
- [ ] Module imports without errors
- [ ] All module tests pass
- [ ] System boots with module enabled
- [ ] Module appears in MCP capability graph
- [ ] No regression in existing functionality

### System Health Post-Integration
- [ ] No new errors in journalctl logs
- [ ] ChemBus message flow stable
- [ ] Memory usage within bounds
- [ ] Response latency unchanged

---

## Timeline Estimate

- **Phase 1** (mcp, self_heal, petri): 3-5 hours
- **Phase 2** (tool_synthesis, dev_agent, meta_cognition): 5-8 hours
- **Phase 3** (6 modules): 8-12 hours

**Total**: 16-25 hours of integration work

---

## Post-Integration Tasks

1. **Update Documentation**:
   - [ ] Add module docs to `docs/modules/`
   - [ ] Update architecture diagrams
   - [ ] Update capabilities.yaml with `enabled: true`

2. **Monitoring**:
   - [ ] Add module metrics to dashboard
   - [ ] Configure alerting for module failures
   - [ ] Add module health checks

3. **User-Facing**:
   - [ ] Update CLI help with new commands
   - [ ] Add module features to README.md
   - [ ] Document new capabilities in CHANGELOG.md

---

## Questions for User

1. **Voice Features**: Are voice input/output active? (affects stt/speaker priority)
2. **TUMIX**: Is TUMIX active? (affects scholar integration)
3. **Integration Strategy**: Prefer sequential (safer) or parallel (faster)?
4. **Testing Environment**: Dev/staging environment available for high-risk modules?
5. **Deprecated Modules**: Confirm deletion of dream_legacy_domains/?
