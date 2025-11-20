# Discovery-to-Execution Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable autonomous curiosity system to discover modules, investigate them with LLM analysis, and automatically make them executable as introspection tools.

**Architecture:** Fix broken chain between intent creation → ZMQ signal publishing → investigation consumer → LLM analysis → capability registration → tool execution. Currently intents are created but never published as signals, so investigations never run. Even if they did, discovered capabilities wouldn't be executable.

**Tech Stack:** Python 3.10, ZeroMQ, Ollama (deepseek-r1:14b), YAML, introspection tools framework

---

## Background Context

**Current State:**
- `kloros-orchestrator.service` runs every 60 seconds
- Generates curiosity questions about undiscovered modules
- Creates intent JSON files in `/home/kloros/.kloros/intents/`
- **BROKEN**: Intents never get processed into ZMQ signals
- `klr-investigation-consumer.service` waits for `Q_CURIOSITY_INVESTIGATE` signals that never arrive
- Even if investigations ran, results wouldn't create executable tools

**Target State:**
- Orchestrator processes intent queue and publishes ZMQ signals
- Investigation consumer receives signals and runs deep LLM analysis
- LLM extracts callable interface (functions, parameters, purpose)
- New tool loader reads capabilities.yaml and creates IntrospectionTool instances
- Discovered modules become immediately usable via voice/reasoning

**Key Files:**
- `/home/kloros/src/kloros/orchestration/coordinator.py` - orchestrator main logic
- `/home/kloros/src/kloros/orchestration/intent_queue.py` - intent processing
- `/home/kloros/src/kloros/orchestration/signal_router_v2.py` - ZMQ signal publisher
- `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py` - signal consumer
- `/home/kloros/src/registry/module_investigator.py` - LLM analysis engine
- `/home/kloros/src/introspection_tools.py` - tool registry
- `/home/kloros/src/registry/capabilities.yaml` - capability registry

---

## Task 1: Add Intent Queue Processing to Orchestrator

**Goal:** Make orchestrator process pending intent files and route them to appropriate handlers

**Files:**
- Modify: `/home/kloros/src/kloros/orchestration/coordinator.py` (after line 50, in orchestrator_tick function)

**Step 1: Locate the orchestrator tick function**

```bash
grep -n "def orchestrator_tick" /home/kloros/src/kloros/orchestration/coordinator.py
```

Expected: Shows function around line 40-50

**Step 2: Add intent queue import at top of file**

Add after existing imports:
```python
from .intent_queue import get_next_intent, IntentQueue
```

**Step 3: Add intent processing loop after curiosity processor**

After the line that says `logger.info(f"Curiosity processor emitted {curiosity_result['intents_emitted']} new intents")`, add:

```python
        # Process pending intents from queue (new)
        intent_queue = IntentQueue()
        intents_processed = 0
        max_intents_per_tick = 10  # Rate limit

        while intents_processed < max_intents_per_tick:
            queue_result = get_next_intent()
            if queue_result["next_intent"] is None:
                break  # No more intents

            intent_file = queue_result["next_intent"]
            logger.info(f"[orchestrator] Processing intent: {intent_file.name}")

            try:
                action = _process_intent(intent_file)
                logger.info(f"[orchestrator] Intent processed: {intent_file.name} -> {action}")
                intents_processed += 1
            except Exception as e:
                logger.error(f"[orchestrator] Failed to process intent {intent_file.name}: {e}")
                break

        if intents_processed > 0:
            logger.info(f"[orchestrator] Processed {intents_processed} intents this tick")
```

**Step 4: Verify the _process_intent function exists**

```bash
grep -n "def _process_intent" /home/kloros/src/kloros/orchestration/coordinator.py
```

Expected: Should find function definition (if not, we'll add it in next task)

**Step 5: Test orchestrator runs without errors**

```bash
sudo systemctl restart kloros-orchestrator.service
sleep 65  # Wait for next tick
sudo journalctl -u kloros-orchestrator.service -n 50 --no-pager | grep "Processing intent"
```

Expected: Should see "Processing intent" messages

**Step 6: Commit**

```bash
git add src/kloros/orchestration/coordinator.py
git commit -m "feat(orchestrator): add intent queue processing to orchestrator tick"
```

---

## Task 2: Verify Chemical Signal Publishing for Curiosity Intents

**Goal:** Ensure _process_intent publishes Q_CURIOSITY_INVESTIGATE signals to ZMQ

**Files:**
- Read: `/home/kloros/src/kloros/orchestration/coordinator.py` (_process_intent function)
- Read: `/home/kloros/src/kloros/orchestration/signal_router_v2.py`

**Step 1: Find _process_intent function**

```bash
grep -A50 "def _process_intent" /home/kloros/src/kloros/orchestration/coordinator.py | head -60
```

**Step 2: Check if it calls _try_chemical_routing**

```bash
grep "_try_chemical_routing" /home/kloros/src/kloros/orchestration/coordinator.py
```

Expected: Should find function that routes intents to chemical signals

**Step 3: Verify curiosity_investigate intent type gets routed**

Look for this pattern in _try_chemical_routing:
```python
if intent_type == "curiosity_investigate":
    # Publish Q_CURIOSITY_INVESTIGATE signal
```

**Step 4: If routing is missing, add signal publishing**

In _try_chemical_routing function, add:

```python
    elif intent_type == "curiosity_investigate":
        from .signal_router_v2 import publish_signal

        question_data = intent.get("data", {})
        publish_signal(
            signal="Q_CURIOSITY_INVESTIGATE",
            facts=question_data,
            incident_id=question_data.get("question_id", "")
        )
        logger.info(f"[chemical_routing] Published Q_CURIOSITY_INVESTIGATE for {question_data.get('question_id')}")
        return True
```

**Step 5: Test signal publishing**

```bash
sudo systemctl restart kloros-orchestrator.service
sleep 65
sudo journalctl -u kloros-orchestrator.service -n 100 --no-pager | grep "Q_CURIOSITY_INVESTIGATE"
```

Expected: Should see "Published Q_CURIOSITY_INVESTIGATE" messages

**Step 6: Verify investigation consumer receives signals**

```bash
sudo journalctl -u klr-investigation-consumer.service -n 50 --no-pager | grep "Received Q_CURIOSITY_INVESTIGATE"
```

Expected: Should see consumer receiving signals

**Step 7: Commit**

```bash
git add src/kloros/orchestration/coordinator.py src/kloros/orchestration/signal_router_v2.py
git commit -m "feat(signals): add Q_CURIOSITY_INVESTIGATE signal publishing"
```

---

## Task 3: Verify Investigation Consumer Processes Signals

**Goal:** Confirm investigation consumer daemon receives signals and triggers LLM analysis

**Files:**
- Read: `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py`
- Monitor: `/home/kloros/.kloros/curiosity_investigations.jsonl`

**Step 1: Check investigation consumer is running**

```bash
sudo systemctl status klr-investigation-consumer.service --no-pager
```

Expected: active (running)

**Step 2: Monitor investigation consumer logs in real-time**

```bash
sudo journalctl -u klr-investigation-consumer.service -f
```

Let run for 2 minutes, watch for:
- "Received Q_CURIOSITY_INVESTIGATE"
- "Investigating module"
- "Investigation complete"

**Step 3: Check if investigations have LLM analysis**

```bash
tail -1 /home/kloros/.kloros/curiosity_investigations.jsonl | python3 -m json.tool | grep -A5 "llm_analysis"
```

Expected: Should have non-empty llm_analysis field

**Step 4: If llm_analysis is empty, check module_investigator**

```bash
grep -n "llm_analysis" /home/kloros/src/registry/module_investigator.py
```

Check that investigation result includes populated llm_analysis

**Step 5: Test with manual signal publish (optional debugging)**

```python
# In a Python shell
import zmq
import json

context = zmq.Context()
pub = context.socket(zmq.PUB)
pub.connect("tcp://127.0.0.1:5557")

msg = {
    "signal": "Q_CURIOSITY_INVESTIGATE",
    "facts": {
        "question_id": "test.manual.investigation",
        "question": "Test manual investigation trigger",
        "evidence": ["path:/home/kloros/src/registry"]
    },
    "incident_id": "test-001"
}

pub.send_multipart([b"Q_CURIOSITY_INVESTIGATE", json.dumps(msg).encode()])
```

**Step 6: No code changes needed if working**

If investigations are running and producing LLM analysis, proceed to next task.

---

## Task 4: Enhance LLM Analysis to Extract Callable Interface

**Goal:** Modify module_investigator to extract function signatures, parameters, and return types from analyzed modules

**Files:**
- Modify: `/home/kloros/src/registry/module_investigator.py` (investigate_module method)

**Step 1: Locate the LLM prompt construction**

```bash
grep -n "prompt.*=" /home/kloros/src/registry/module_investigator.py | grep -i "analyze\|understand"
```

**Step 2: Read current LLM analysis prompt**

```bash
grep -A20 "def.*_build_analysis_prompt" /home/kloros/src/registry/module_investigator.py
```

**Step 3: Enhance prompt to extract callable interface**

Find the prompt construction and modify to include:

```python
def _build_analysis_prompt(self, module_name: str, file_contents: List[Dict]) -> str:
    """Build prompt for LLM to analyze module."""

    prompt = f"""Analyze this Python module '{module_name}' and extract:

1. PRIMARY PURPOSE: What problem does this module solve? (1-2 sentences)

2. KEY CAPABILITIES: What can this module do? List 3-5 specific capabilities.

3. CALLABLE INTERFACE: For each major capability, identify:
   - Function/method name
   - Parameters (name and type)
   - Return type
   - One-sentence description

4. INTEGRATION POINTS: How does this integrate with other systems?

Module contents:
"""

    for file_info in file_contents:
        prompt += f"\n\n=== {file_info['filename']} ===\n"
        prompt += file_info['content'][:2000]  # Truncate long files

    prompt += """

Respond in JSON format:
{{
  "purpose": "...",
  "capabilities": ["...", "..."],
  "callable_interface": [
    {{
      "function": "function_name",
      "parameters": [{{"name": "param", "type": "str"}}],
      "returns": "return_type",
      "description": "..."
    }}
  ],
  "integration_points": ["...", "..."]
}}
"""
    return prompt
```

**Step 4: Update investigation result to store callable_interface**

In investigate_module method, after LLM call:

```python
        # Parse LLM response
        try:
            llm_result = response.json()
            analysis = json.loads(llm_result.get("response", "{}"))

            investigation["llm_analysis"] = analysis
            investigation["capabilities"] = analysis.get("capabilities", [])
            investigation["integration_points"] = analysis.get("integration_points", [])
            investigation["callable_interface"] = analysis.get("callable_interface", [])
            investigation["success"] = True

        except Exception as e:
            logger.error(f"[module_investigator] Failed to parse LLM response: {e}")
            investigation["error"] = f"LLM parse error: {e}"
```

**Step 5: Test with a known module**

```bash
# Trigger investigation manually for registry module
echo '{"question_id": "test.registry", "question": "What does registry module do?", "evidence": ["path:/home/kloros/src/registry"]}' > /tmp/test_intent.json
```

**Step 6: Verify callable_interface is extracted**

```bash
tail -1 /home/kloros/.kloros/curiosity_investigations.jsonl | python3 -m json.tool | grep -A10 "callable_interface"
```

Expected: Should show function signatures with parameters

**Step 7: Commit**

```bash
git add src/registry/module_investigator.py
git commit -m "feat(investigation): extract callable interface from LLM analysis"
```

---

## Task 5: Create Capability-to-Tool Loader

**Goal:** Add loader in IntrospectionToolRegistry that reads capabilities.yaml and creates executable tools

**Files:**
- Modify: `/home/kloros/src/introspection_tools.py` (add _load_capability_tools method)

**Step 1: Add capability registry import**

At top of introspection_tools.py, add:

```python
from registry.loader import get_registry
```

**Step 2: Add _load_capability_tools method to IntrospectionToolRegistry**

After _load_synthesized_tools method, add:

```python
    def _load_capability_tools(self):
        """Load auto-discovered capabilities as executable tools."""
        try:
            from registry.loader import get_registry

            registry = get_registry()
            capabilities = registry.get_enabled_capabilities()

            loaded_count = 0
            for cap in capabilities:
                # Only load auto-discovered capabilities
                if not cap.to_dict().get("auto_discovered", False):
                    continue

                # Check if we have investigation data for this module
                callable_interface = self._get_callable_interface(cap.module)

                if not callable_interface:
                    logger.debug(f"[tools] No callable interface for {cap.name}, skipping")
                    continue

                # Create tools from callable interface
                for interface in callable_interface:
                    tool = self._create_tool_from_interface(
                        cap_name=cap.name,
                        interface=interface,
                        module_path=cap.module
                    )

                    if tool:
                        self.register(tool)
                        loaded_count += 1
                        logger.info(f"[tools] Loaded capability tool: {tool.name}")

            if loaded_count > 0:
                logger.info(f"[tools] Loaded {loaded_count} capability tools")

        except Exception as e:
            logger.warning(f"[tools] Failed to load capability tools: {e}")
```

**Step 3: Add helper to get callable interface from investigations**

```python
    def _get_callable_interface(self, module_path: str) -> List[Dict]:
        """Get callable interface from investigation results."""
        try:
            investigations_file = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
            if not investigations_file.exists():
                return []

            # Find latest investigation for this module
            with open(investigations_file, 'r') as f:
                for line in reversed(list(f)):
                    if not line.strip():
                        continue

                    inv = json.loads(line)
                    if module_path in inv.get("module_path", ""):
                        return inv.get("callable_interface", [])

            return []
        except Exception as e:
            logger.error(f"[tools] Failed to read investigations: {e}")
            return []
```

**Step 4: Add tool creation from interface**

```python
    def _create_tool_from_interface(
        self,
        cap_name: str,
        interface: Dict,
        module_path: str
    ) -> Optional[IntrospectionTool]:
        """Create IntrospectionTool from callable interface."""
        try:
            function_name = interface.get("function")
            parameters = [p["name"] for p in interface.get("parameters", [])]
            description = interface.get("description", f"Auto-discovered: {function_name}")

            # Create wrapper function that dynamically imports and calls
            def tool_func(kloros_instance, **kwargs):
                try:
                    # Dynamic import of the module
                    import importlib
                    module = importlib.import_module(module_path)

                    # Get the function
                    func = getattr(module, function_name, None)
                    if func is None:
                        return f"Error: Function {function_name} not found in {module_path}"

                    # Call with provided kwargs
                    result = func(**kwargs)
                    return str(result)

                except Exception as e:
                    return f"Error executing {function_name}: {e}"

            tool_name = f"{cap_name}_{function_name}"

            return IntrospectionTool(
                name=tool_name,
                description=description,
                func=tool_func,
                parameters=parameters
            )

        except Exception as e:
            logger.error(f"[tools] Failed to create tool from interface: {e}")
            return None
```

**Step 5: Call _load_capability_tools in __init__**

In IntrospectionToolRegistry.__init__, after _load_synthesized_tools():

```python
        self._load_synthesized_tools()
        self._load_capability_tools()  # Add this line
```

**Step 6: Test tool loading**

```bash
# Restart kloros to reload tools
sudo systemctl restart kloros.service

# Check logs for loaded capability tools
sudo journalctl -u kloros.service -n 100 --no-pager | grep "Loaded capability tool"
```

Expected: Should see tools loaded from capabilities.yaml

**Step 7: Commit**

```bash
git add src/introspection_tools.py
git commit -m "feat(tools): add capability-to-tool loader for auto-discovered modules"
```

---

## Task 6: Integration Test - End-to-End Discovery to Execution

**Goal:** Verify complete pipeline works: discover → investigate → register → execute

**Step 1: Create test module to discover**

```bash
mkdir -p /home/kloros/src/test_discovery_module
cat > /home/kloros/src/test_discovery_module/__init__.py << 'EOF'
"""Test module for discovery pipeline validation."""

def get_test_info(test_id: str) -> str:
    """Get information about a test.

    Args:
        test_id: The test identifier

    Returns:
        Test information string
    """
    return f"Test info for: {test_id}"

def calculate_test_score(value: int) -> float:
    """Calculate a test score.

    Args:
        value: Input value

    Returns:
        Calculated score
    """
    return value * 0.85
EOF
```

**Step 2: Wait for orchestrator to discover it**

```bash
# Watch orchestrator logs
sudo journalctl -u kloros-orchestrator.service -f | grep -i "test_discovery"
```

Wait up to 5 minutes. Should see:
- "Emitted intent for question discover.module.test_discovery_module"

**Step 3: Verify investigation runs**

```bash
# Wait for investigation consumer
sudo journalctl -u klr-investigation-consumer.service -f | grep -i "test_discovery"
```

Should see:
- "Investigating module: test_discovery_module"
- "Investigation complete"

**Step 4: Check investigation has callable interface**

```bash
grep "test_discovery_module" /home/kloros/.kloros/curiosity_investigations.jsonl | tail -1 | python3 -m json.tool | grep -A20 "callable_interface"
```

Expected: Should show get_test_info and calculate_test_score functions

**Step 5: Verify added to capabilities.yaml**

```bash
grep -A5 "test_discovery_module" /home/kloros/src/registry/capabilities.yaml
```

Expected:
```yaml
test_discovery_module:
  module: test_discovery_module
  enabled: true
  description: Test module for discovery pipeline validation
  auto_discovered: true
```

**Step 6: Verify tools were loaded**

```bash
sudo journalctl -u kloros.service --since "5 minutes ago" | grep "test_discovery_module"
```

Expected: "Loaded capability tool: test_discovery_module_get_test_info"

**Step 7: Test tool execution via voice/reasoning**

Manually trigger kloros and ask: "Use the test_discovery_module_get_test_info tool with test_id=demo123"

Expected: Should execute and return "Test info for: demo123"

**Step 8: Clean up test module**

```bash
rm -rf /home/kloros/src/test_discovery_module
```

**Step 9: Document test results**

If all steps pass, the pipeline is working end-to-end.

---

## Task 7: Add Monitoring and Metrics

**Goal:** Add observability for discovery-to-execution pipeline health

**Files:**
- Create: `/home/kloros/src/monitoring/discovery_metrics.py`

**Step 1: Create metrics module**

```python
"""Discovery-to-Execution Pipeline Metrics."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
from pathlib import Path
import json

@dataclass
class DiscoveryMetrics:
    """Metrics for discovery pipeline health."""
    timestamp: str
    intents_created: int
    intents_processed: int
    signals_published: int
    investigations_started: int
    investigations_completed: int
    capabilities_registered: int
    tools_loaded: int

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "intents_created": self.intents_created,
            "intents_processed": self.intents_processed,
            "signals_published": self.signals_published,
            "investigations_started": self.investigations_started,
            "investigations_completed": self.investigations_completed,
            "capabilities_registered": self.capabilities_registered,
            "tools_loaded": self.tools_loaded,
            "pipeline_health": self._calculate_health()
        }

    def _calculate_health(self) -> str:
        """Calculate pipeline health status."""
        # Check each stage
        if self.intents_created == 0:
            return "IDLE"

        if self.intents_processed < self.intents_created * 0.5:
            return "DEGRADED: Intent processing backlog"

        if self.signals_published < self.intents_processed * 0.9:
            return "DEGRADED: Signal publishing failing"

        if self.investigations_completed < self.investigations_started * 0.8:
            return "DEGRADED: Investigations failing"

        if self.tools_loaded < self.capabilities_registered * 0.9:
            return "DEGRADED: Tool loading failing"

        return "HEALTHY"


def record_discovery_metrics() -> DiscoveryMetrics:
    """Record current discovery pipeline metrics."""
    metrics_file = Path("/home/kloros/.kloros/discovery_metrics.jsonl")

    # Collect metrics from various sources
    metrics = DiscoveryMetrics(
        timestamp=datetime.now().isoformat(),
        intents_created=_count_intent_files(),
        intents_processed=_count_processed_intents(),
        signals_published=_count_signals_published(),
        investigations_started=_count_investigations_started(),
        investigations_completed=_count_investigations_completed(),
        capabilities_registered=_count_registered_capabilities(),
        tools_loaded=_count_loaded_tools()
    )

    # Append to metrics log
    with open(metrics_file, 'a') as f:
        f.write(json.dumps(metrics.to_dict()) + '\n')

    return metrics


def _count_intent_files() -> int:
    """Count pending intent files."""
    intents_dir = Path("/home/kloros/.kloros/intents")
    return len(list(intents_dir.glob("*.json")))


def _count_processed_intents() -> int:
    """Count processed intents from last hour."""
    # Read from orchestrator logs or processed directory
    processed_dir = Path("/home/kloros/.kloros/intents/processed")
    if not processed_dir.exists():
        return 0

    # Count recent processed intents
    import time
    one_hour_ago = time.time() - 3600
    count = 0

    for file in processed_dir.rglob("*.json"):
        if file.stat().st_mtime > one_hour_ago:
            count += 1

    return count


def _count_signals_published() -> int:
    """Count Q_CURIOSITY_INVESTIGATE signals from logs."""
    # Parse orchestrator logs
    import subprocess
    result = subprocess.run(
        ["journalctl", "-u", "kloros-orchestrator.service", "--since", "1 hour ago", "-q"],
        capture_output=True,
        text=True
    )

    return result.stdout.count("Published Q_CURIOSITY_INVESTIGATE")


def _count_investigations_started() -> int:
    """Count investigations started."""
    result = subprocess.run(
        ["journalctl", "-u", "klr-investigation-consumer.service", "--since", "1 hour ago", "-q"],
        capture_output=True,
        text=True
    )

    return result.stdout.count("Investigating module")


def _count_investigations_completed() -> int:
    """Count completed investigations from last hour."""
    investigations_file = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
    if not investigations_file.exists():
        return 0

    import time
    one_hour_ago = time.time() - 3600
    count = 0

    with open(investigations_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                inv = json.loads(line)
                timestamp_str = inv.get("timestamp", "")
                inv_time = datetime.fromisoformat(timestamp_str).timestamp()

                if inv_time > one_hour_ago and inv.get("success", False):
                    count += 1
            except:
                continue

    return count


def _count_registered_capabilities() -> int:
    """Count auto-discovered capabilities."""
    import yaml
    capabilities_file = Path("/home/kloros/src/registry/capabilities.yaml")

    with open(capabilities_file, 'r') as f:
        caps = yaml.safe_load(f) or {}

    count = 0
    for name, config in caps.items():
        if isinstance(config, dict) and config.get("auto_discovered", False):
            count += 1

    return count


def _count_loaded_tools() -> int:
    """Count loaded capability tools."""
    result = subprocess.run(
        ["journalctl", "-u", "kloros.service", "--since", "1 hour ago", "-q"],
        capture_output=True,
        text=True
    )

    return result.stdout.count("Loaded capability tool")


if __name__ == "__main__":
    metrics = record_discovery_metrics()
    print(json.dumps(metrics.to_dict(), indent=2))
```

**Step 2: Add metrics collection to orchestrator**

In coordinator.py orchestrator_tick, at the end:

```python
        # Record discovery pipeline metrics
        try:
            from monitoring.discovery_metrics import record_discovery_metrics
            metrics = record_discovery_metrics()
            logger.info(f"[metrics] Discovery pipeline: {metrics._calculate_health()}")
        except Exception as e:
            logger.warning(f"[metrics] Failed to record discovery metrics: {e}")
```

**Step 3: Create monitoring script**

```bash
cat > /home/kloros/bin/check_discovery_health.sh << 'EOF'
#!/bin/bash
# Check discovery-to-execution pipeline health

echo "=== Discovery Pipeline Health Check ==="
python3 -m src.monitoring.discovery_metrics
EOF

chmod +x /home/kloros/bin/check_discovery_health.sh
```

**Step 4: Test metrics collection**

```bash
/home/kloros/bin/check_discovery_health.sh
```

Expected: JSON output with all metrics and health status

**Step 5: Commit**

```bash
git add src/monitoring/discovery_metrics.py src/kloros/orchestration/coordinator.py bin/check_discovery_health.sh
git commit -m "feat(monitoring): add discovery pipeline health metrics"
```

---

## Task 8: Documentation and Cleanup

**Goal:** Document the discovery-to-execution pipeline for future maintenance

**Files:**
- Create: `/home/kloros/docs/architecture/discovery-to-execution.md`

**Step 1: Create architecture document**

```markdown
# Discovery-to-Execution Pipeline

## Overview

Autonomous system that discovers undiscovered Python modules, investigates them with LLM analysis, registers them in the capability registry, and makes them immediately executable as introspection tools.

## Pipeline Stages

### Stage 1: Discovery
**Component:** `curiosity_core.py`
- Scans `/home/kloros/src/` for Python modules
- Generates curiosity questions for undiscovered modules
- Outputs: Questions to `curiosity_feed.json`

### Stage 2: Intent Creation
**Component:** `curiosity_processor.py`
- Processes curiosity questions
- Creates intent JSON files in `/home/kloros/.kloros/intents/`
- Each intent contains question_id, evidence, hypothesis

### Stage 3: Intent Processing
**Component:** `coordinator.py` (orchestrator_tick)
- Runs every 60 seconds via `kloros-orchestrator.timer`
- Processes intent queue (max 10 intents per tick)
- Routes intents to chemical signal publisher

### Stage 4: Signal Publishing
**Component:** `signal_router_v2.py`
- Publishes `Q_CURIOSITY_INVESTIGATE` ZMQ signals
- Signals contain question_id, module_path, evidence
- Published on `tcp://127.0.0.1:5557`

### Stage 5: Investigation
**Component:** `investigation_consumer_daemon.py`
- Subscribes to `Q_CURIOSITY_INVESTIGATE` signals
- Triggers deep code analysis via `module_investigator.py`
- Uses Ollama LLM (deepseek-r1:14b) for understanding

### Stage 6: LLM Analysis
**Component:** `module_investigator.py`
- Reads all Python files in module directory
- Extracts structure (classes, functions, imports)
- Prompts LLM to extract:
  - Purpose and capabilities
  - Callable interface (functions, parameters, return types)
  - Integration points
- Writes results to `curiosity_investigations.jsonl`

### Stage 7: Capability Registration
**Component:** `capability_integrator.py`
- Processes investigation results
- Validates modules have proper structure (__init__.py, etc.)
- Adds to `/home/kloros/src/registry/capabilities.yaml`
- Marks as `auto_discovered: true`

### Stage 8: Tool Loading
**Component:** `introspection_tools.py` (_load_capability_tools)
- Reads capabilities.yaml for auto-discovered modules
- Looks up callable interface from investigations
- Creates `IntrospectionTool` instances with dynamic import wrappers
- Registers tools in global tool registry

### Stage 9: Tool Execution
**Component:** Voice/reasoning systems
- LLM can now invoke tools via natural language
- Tools execute by dynamically importing module and calling functions
- Results returned to user

## Data Flow

```
Modules → Discovery → Questions → Intents → ZMQ Signals → Investigations
    ↓                                                            ↓
    └────────────── Tools ← Registry ← Capabilities ←───────────┘
```

## Key Files

- `/home/kloros/.kloros/curiosity_feed.json` - Active curiosity questions
- `/home/kloros/.kloros/intents/*.json` - Pending investigation intents
- `/home/kloros/.kloros/curiosity_investigations.jsonl` - Investigation results
- `/home/kloros/.kloros/integrated_capabilities.jsonl` - Integration log
- `/home/kloros/src/registry/capabilities.yaml` - Registered capabilities

## Monitoring

Check pipeline health:
```bash
/home/kloros/bin/check_discovery_health.sh
```

View recent investigations:
```bash
tail -5 /home/kloros/.kloros/curiosity_investigations.jsonl | python3 -m json.tool
```

Monitor orchestrator:
```bash
sudo journalctl -u kloros-orchestrator.service -f
```

Monitor investigation consumer:
```bash
sudo journalctl -u klr-investigation-consumer.service -f
```

## Troubleshooting

**Intents not being processed:**
- Check orchestrator is running: `systemctl status kloros-orchestrator.timer`
- Check intent queue: `ls /home/kloros/.kloros/intents/*.json | wc -l`

**Signals not being published:**
- Check ZMQ publisher in orchestrator logs
- Verify _try_chemical_routing handles curiosity_investigate

**Investigations not running:**
- Check consumer daemon: `systemctl status klr-investigation-consumer.service`
- Verify LLM is accessible: `curl http://localhost:11434/api/tags`

**Tools not loading:**
- Check investigations have callable_interface
- Verify capabilities.yaml has auto_discovered modules
- Check introspection_tools.py logs for load errors

## Performance

- **Discovery cycle:** Every 5 minutes (reflection interval)
- **Orchestrator tick:** Every 60 seconds
- **Intent processing:** Max 10 intents per tick
- **Investigation rate:** Max 4 concurrent (semaphore limit)
- **LLM model:** deepseek-r1:14b (reasoning model)

## Future Improvements

1. Add capability versioning for updates
2. Implement capability deprecation/removal
3. Add tool usage analytics
4. Create capability dependency graph
5. Add safety checks for auto-loaded tools
```

**Step 2: Commit documentation**

```bash
git add docs/architecture/discovery-to-execution.md
git commit -m "docs: add discovery-to-execution pipeline architecture"
```

**Step 3: Update main README if exists**

Add link to new architecture doc in project README.

---

## Completion Checklist

After implementing all tasks:

- [ ] Orchestrator processes intent queue
- [ ] Intents route to ZMQ signal publisher
- [ ] Investigation consumer receives signals
- [ ] LLM analysis extracts callable interface
- [ ] Capabilities auto-register in YAML
- [ ] Tools auto-load from capabilities
- [ ] End-to-end test passes
- [ ] Metrics collection works
- [ ] Documentation complete

## Testing Strategy

**Unit Tests:**
- Test intent queue processing
- Test signal publishing
- Test callable interface extraction
- Test tool creation from interface

**Integration Tests:**
- End-to-end discovery test (Task 6)
- Test with real modules

**Monitoring:**
- Dashboard showing pipeline health
- Alerts for degraded stages

---

## Notes for Engineer

**Why this architecture:**
- Separation of concerns: discovery, investigation, registration, execution
- Async via ZMQ prevents blocking
- LLM provides semantic understanding, not just static analysis
- Dynamic tool loading enables runtime capability expansion

**Common gotchas:**
- ZMQ publish-subscribe needs small delay after connect
- YAML formatting must be preserved when updating capabilities
- Dynamic imports need proper error handling
- Investigation results can be large (35MB file)

**When to ask for help:**
- If ZMQ signals aren't being received
- If LLM analysis is consistently empty
- If dynamic tool execution fails
- If you need to understand the chemical signals architecture

**Related systems:**
- D-REAM evolution (disabled, but shares intent framework)
- SPICA tournaments (uses similar ZMQ signals)
- MCP capability graph (different registry, but related concept)
