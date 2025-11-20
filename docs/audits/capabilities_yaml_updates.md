# Capabilities.yaml Update Plan

**Objective**: Mark orphaned modules with accurate status and integration notes

---

## Modules to Update

### Mark as `enabled: false` with Integration Notes

```yaml
# HIGH PRIORITY - INTEGRATE
mcp:
  enabled: false  # ORPHANED: Not imported. HIGH PRIORITY - system introspection
  status: orphaned
  priority: critical
  integration_notes: "Enable MCP for system introspection and capability awareness"

self_heal:
  enabled: false  # ORPHANED: Not imported. HIGH PRIORITY - autonomous repair
  status: orphaned
  priority: critical
  integration_notes: "Enable self-healing for autonomous failure recovery"

petri:
  enabled: false  # ORPHANED: Not imported. HIGH PRIORITY - safety sandbox
  status: orphaned
  priority: critical
  integration_notes: "Enable PETRI safety sandbox before tool synthesis"

tool_synthesis:
  enabled: false  # ORPHANED: Not imported. HIGH PRIORITY - autonomous capabilities
  status: orphaned
  priority: high
  integration_notes: "Enable tool synthesis for autonomous capability expansion. Requires PETRI."

dev_agent:
  enabled: false  # ORPHANED: Not imported. HIGH PRIORITY - code repair
  status: orphaned
  priority: high
  integration_notes: "Enable dev agent for autonomous code repair"

meta_cognition:
  enabled: false  # ORPHANED: Not imported. HIGH PRIORITY - self-awareness
  status: orphaned
  priority: high
  integration_notes: "Enable meta-cognition for conversational self-awareness"

scholar:
  enabled: false  # ORPHANED: Not imported. MEDIUM PRIORITY - reports
  status: orphaned
  priority: medium
  integration_notes: "Enable scholar for report generation with citations"

dream_lab:
  enabled: false  # ORPHANED: Not imported. MEDIUM PRIORITY - chaos testing
  status: orphaned
  priority: medium
  integration_notes: "Enable dream lab for chaos/failure injection testing"

ace:
  enabled: false  # ORPHANED: Not imported. MEDIUM PRIORITY - context hints
  status: orphaned
  priority: medium
  integration_notes: "Enable ACE for self-improving context engineering"

stt:
  enabled: false  # ORPHANED: Not imported. MEDIUM PRIORITY - voice input
  status: orphaned
  priority: medium
  integration_notes: "Enable STT for speech-to-text processing (Vosk/Whisper)"

c2c:
  enabled: false  # ORPHANED: Not imported. MEDIUM PRIORITY - semantic communication
  status: orphaned
  priority: medium
  integration_notes: "Enable C2C for semantic context transfer between LLMs"

core:
  enabled: false  # ORPHANED: Not imported. MEDIUM PRIORITY - conversation flow
  status: orphaned
  priority: medium
  integration_notes: "Enable core conversation flow management. Check if already partially integrated."

# INVESTIGATE - Need deep dive before decision
toolforge:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - may overlap with tool_synthesis
  status: orphaned
  priority: investigate
  integration_notes: "Investigate overlap with tool_synthesis before integration"

tool_curation:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - may overlap with tool_synthesis
  status: orphaned
  priority: investigate
  integration_notes: "Investigate overlap with tool_synthesis before integration"

selfcoder:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - may overlap with dev_agent
  status: orphaned
  priority: investigate
  integration_notes: "Investigate overlap with dev_agent before integration"

ra3:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - unclear purpose
  status: orphaned
  priority: investigate
  integration_notes: "Investigate module purpose and value before integration"

tumix:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - unclear purpose
  status: orphaned
  priority: investigate
  integration_notes: "Investigate module purpose and value before integration"

cognition:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - may overlap with meta_cognition
  status: orphaned
  priority: investigate
  integration_notes: "Investigate overlap with meta_cognition before integration"

governance:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - policy layer
  status: orphaned
  priority: investigate
  integration_notes: "Investigate governance policy layer purpose"

speaker:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - TTS output
  status: orphaned
  priority: investigate
  integration_notes: "Check if superseded by existing TTS system"

voice:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - voice processing
  status: orphaned
  priority: investigate
  integration_notes: "Check overlap with stt/speaker modules"

logic:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - logic system
  status: orphaned
  priority: investigate
  integration_notes: "Investigate logic system component purpose"

common:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - utilities
  status: orphaned
  priority: investigate
  integration_notes: "Check if utilities are redundant with existing code"

routing:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - message routing
  status: orphaned
  priority: investigate
  integration_notes: "Investigate routing system purpose"

reporting:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - system reports
  status: orphaned
  priority: investigate
  integration_notes: "Check overlap with observability/logging"

observer:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - monitoring
  status: orphaned
  priority: investigate
  integration_notes: "Check overlap with observability system"

gpu_workers:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - GPU management
  status: orphaned
  priority: investigate
  integration_notes: "Investigate GPU worker management purpose"

scripts:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - utilities
  status: orphaned
  priority: investigate
  integration_notes: "May be utility scripts, check relevance"

style:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - code style
  status: orphaned
  priority: investigate
  integration_notes: "Code style/formatting module, check if needed"

ux:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - user experience
  status: orphaned
  priority: investigate
  integration_notes: "User experience layer, check purpose"

experiments:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - experimental code
  status: orphaned
  priority: investigate
  integration_notes: "Experimental/research code, may be WIP"

# DEPRECATED - Mark for removal
dream_legacy_domains:
  enabled: false  # DEPRECATED: Contains DEPRECATED_README.md
  status: deprecated
  priority: remove
  integration_notes: "Legacy D-REAM domains. DEPRECATED. Consider archiving or removing."

compat:
  enabled: false  # ORPHANED: Not imported. INVESTIGATE - compatibility layer
  status: orphaned
  priority: investigate
  integration_notes: "Compatibility layer, may be temporary. Investigate before removing."

# REMOVE - Empty directories
synthesized_tools:
  enabled: false  # EMPTY: 0 .py files
  status: empty
  priority: remove
  integration_notes: "Empty directory. DELETE."

vad:
  enabled: false  # EMPTY: 0 .py files (Voice Activity Detection likely moved)
  status: empty
  priority: remove
  integration_notes: "Empty directory. DELETE (VAD likely integrated elsewhere)."
```

---

## Implementation Steps

1. **Backup Current capabilities.yaml**:
   ```bash
   cp /home/kloros/src/registry/capabilities.yaml /home/kloros/src/registry/capabilities.yaml.backup-$(date +%Y%m%d)
   ```

2. **Update Each Orphaned Module Entry**:
   - Add `enabled: false` if currently `true`
   - Add `status: orphaned/deprecated/empty`
   - Add `priority: critical/high/medium/investigate/remove`
   - Add `integration_notes: "..."`

3. **Document in Capabilities.yaml Header**:
   ```yaml
   # KLoROS Capabilities Registry
   # Last updated: 2025-11-20
   # Orphan audit completed: 35 modules identified
   #
   # Status values:
   #   - active: Currently imported and functional
   #   - orphaned: Exists but not imported anywhere
   #   - deprecated: Marked for removal
   #   - empty: Directory with no Python files
   #
   # Priority values:
   #   - critical: Should be integrated immediately
   #   - high: Should be integrated soon
   #   - medium: Should be integrated eventually
   #   - investigate: Needs investigation before decision
   #   - remove: Should be deleted/archived
   ```

4. **Validate YAML Syntax**:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('/home/kloros/src/registry/capabilities.yaml'))"
   ```

---

## Auto-Generated Script

Create a script to mark all orphaned modules programmatically:

```python
#!/usr/bin/env python3
"""Update capabilities.yaml with orphan status."""
import yaml
from pathlib import Path

CAPABILITIES_PATH = Path("/home/kloros/src/registry/capabilities.yaml")

# Orphaned modules by category
INTEGRATE_CRITICAL = ["mcp", "self_heal", "petri"]
INTEGRATE_HIGH = ["tool_synthesis", "dev_agent", "meta_cognition"]
INTEGRATE_MEDIUM = ["scholar", "dream_lab", "ace", "stt", "c2c", "core"]
INVESTIGATE = [
    "toolforge", "tool_curation", "selfcoder", "ra3", "tumix", "cognition",
    "governance", "speaker", "voice", "logic", "common", "routing", "reporting",
    "observer", "gpu_workers", "scripts", "style", "ux", "experiments", "compat"
]
DEPRECATED = ["dream_legacy_domains"]
REMOVE = ["synthesized_tools", "vad"]

def update_capabilities():
    """Update capabilities.yaml with orphan status."""
    with open(CAPABILITIES_PATH) as f:
        caps = yaml.safe_load(f)

    # Mark modules by category
    for module in INTEGRATE_CRITICAL:
        if module in caps:
            caps[module]["enabled"] = False
            caps[module]["status"] = "orphaned"
            caps[module]["priority"] = "critical"

    for module in INTEGRATE_HIGH:
        if module in caps:
            caps[module]["enabled"] = False
            caps[module]["status"] = "orphaned"
            caps[module]["priority"] = "high"

    for module in INTEGRATE_MEDIUM:
        if module in caps:
            caps[module]["enabled"] = False
            caps[module]["status"] = "orphaned"
            caps[module]["priority"] = "medium"

    for module in INVESTIGATE:
        if module in caps:
            caps[module]["enabled"] = False
            caps[module]["status"] = "orphaned"
            caps[module]["priority"] = "investigate"

    for module in DEPRECATED:
        if module in caps:
            caps[module]["enabled"] = False
            caps[module]["status"] = "deprecated"
            caps[module]["priority"] = "remove"

    for module in REMOVE:
        if module in caps:
            caps[module]["enabled"] = False
            caps[module]["status"] = "empty"
            caps[module]["priority"] = "remove"

    # Write back
    with open(CAPABILITIES_PATH, 'w') as f:
        yaml.dump(caps, f, default_flow_style=False, sort_keys=False)

    print(f"✅ Updated {CAPABILITIES_PATH}")

if __name__ == "__main__":
    update_capabilities()
```

---

## Verification

After updating, verify:

1. **YAML is valid**:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('/home/kloros/src/registry/capabilities.yaml'))"
   ```

2. **Orphaned modules marked**:
   ```bash
   grep -c "status: orphaned" /home/kloros/src/registry/capabilities.yaml
   # Should be 33 (35 total - 2 empty)
   ```

3. **No active orphans**:
   ```bash
   # Should return no results (orphans should be enabled: false)
   grep -A1 "status: orphaned" /home/kloros/src/registry/capabilities.yaml | grep "enabled: true"
   ```
