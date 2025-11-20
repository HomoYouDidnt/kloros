#!/usr/bin/env python3
"""
LLM-Guided Mutation Engine for D-REAM Tool Evolution

Uses KLoROS's own LLM to analyze tool failures and propose intelligent code improvements.
This is the key to moving from blind genetic programming to AI-guided evolution.
"""

import json
import sys
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Add src path for LLM backend
sys.path.insert(0, '/home/kloros/src')


class LLMMutationEngine:
    """Generates intelligent code mutations using LLM analysis."""

    def __init__(self, llm_backend=None):
        """
        Initialize mutation engine.

        Args:
            llm_backend: Optional LLM backend (defaults to KLoROS's Ollama)
        """
        self.llm_backend = llm_backend
        if not self.llm_backend:
            # Use KLoROS's LLM backend
            try:
                from llm_interface import OllamaInterface
                self.llm_backend = OllamaInterface()
            except Exception as e:
                print(f"[mutation] Warning: Could not load LLM backend: {e}")
                self.llm_backend = None

        self.mutation_history_dir = Path("/home/kloros/artifacts/dream/mutations")
        self.mutation_history_dir.mkdir(parents=True, exist_ok=True)

    def should_trigger_llm_mutation(
        self,
        tool_name: str,
        fitness_history: List[float],
        failure_info: Optional[Dict] = None
    ) -> bool:
        """
        Determine if LLM mutation should be triggered.

        Triggers when:
        - Tool crashes (failure_info present)
        - Fitness plateaus for N generations
        - Fitness drops suddenly
        """
        # Always trigger on crash
        if failure_info and failure_info.get("crashed"):
            return True

        # Trigger on plateau (last 3 generations same fitness)
        if len(fitness_history) >= 3:
            recent = fitness_history[-3:]
            if max(recent) - min(recent) < 0.01:  # Plateau threshold
                return True

        # Trigger on fitness drop
        if len(fitness_history) >= 2:
            if fitness_history[-1] < fitness_history[-2] - 0.05:
                return True

        return False

    def generate_mutation(
        self,
        tool_name: str,
        tool_code: str,
        metrics_current: Dict[str, float],
        metrics_target: Dict[str, float],
        failure_info: Optional[Dict] = None,
        diff_history: Optional[List[Dict]] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Generate intelligent code mutation using LLM.

        Args:
            tool_name: Name of tool to mutate
            tool_code: Current tool source code
            metrics_current: Current performance metrics
            metrics_target: Target performance metrics
            failure_info: Crash/error information if available
            diff_history: Previous mutations and their metric deltas

        Returns:
            (mutation_id, unified_diff_patch) or None if failed
        """
        if not self.llm_backend:
            print("[mutation] No LLM backend available")
            return None

        # Build context for LLM
        context = self._build_mutation_context(
            tool_name, tool_code, metrics_current, metrics_target,
            failure_info, diff_history
        )

        # Generate mutation via LLM
        prompt = self._build_mutation_prompt(context)

        try:
            response = self.llm_backend.generate(
                prompt=prompt,
                temperature=0.3,  # Low temp for precise code edits
                max_tokens=2000
            )

            # Parse diff from response
            diff_patch = self._extract_diff_from_response(response)

            if not diff_patch:
                print("[mutation] LLM did not return valid diff")
                return None

            # Validate diff
            if not self._validate_diff(diff_patch, tool_code):
                print("[mutation] Generated diff failed validation")
                return None

            # Create mutation ID
            mutation_id = f"{tool_name}:{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Log mutation
            self._log_mutation(mutation_id, context, diff_patch, response)

            return mutation_id, diff_patch

        except Exception as e:
            print(f"[mutation] Failed to generate mutation: {e}")
            return None

    def _build_mutation_context(
        self,
        tool_name: str,
        tool_code: str,
        metrics_current: Dict,
        metrics_target: Dict,
        failure_info: Optional[Dict],
        diff_history: Optional[List[Dict]]
    ) -> Dict:
        """Build context dictionary for LLM prompt."""
        context = {
            "tool_name": tool_name,
            "tool_code": tool_code,
            "metrics": {
                "current": metrics_current,
                "target": metrics_target,
                "deltas": {
                    k: metrics_target.get(k, 0) - metrics_current.get(k, 0)
                    for k in set(list(metrics_current.keys()) + list(metrics_target.keys()))
                }
            },
            "failure_info": failure_info or {},
            "diff_history": diff_history or []
        }
        return context

    def _build_mutation_prompt(self, context: Dict) -> str:
        """Build LLM prompt for mutation generation."""
        tool_name = context["tool_name"]
        tool_code = context["tool_code"]
        metrics = context["metrics"]
        failure = context["failure_info"]
        history = context["diff_history"]

        prompt = f"""You are KLoROS' code evolution assistant. Produce minimal, safe patches to improve tool performance.

CONSTRAINTS:
- Keep output schema: {{latency_ms_p95, jitter_ms_p95, f1_score, processed_ms}}
- Max changed lines: 30
- No external network calls or new system calls
- No eval() or exec()
- Total runtime must not increase >10%
- Preserve CLI interface

TOOL: {tool_name}

CURRENT METRICS:
{json.dumps(metrics['current'], indent=2)}

TARGET METRICS:
{json.dumps(metrics['target'], indent=2)}

METRIC DELTAS NEEDED:
{json.dumps(metrics['deltas'], indent=2)}
"""

        if failure:
            prompt += f"""
FAILURE INFORMATION:
- Crashed: {failure.get('crashed', False)}
- Error: {failure.get('stderr', 'N/A')[:500]}
- Return code: {failure.get('rc', 'N/A')}
"""

        if history:
            prompt += f"""
PREVIOUS MUTATIONS (last 3):
"""
            for i, h in enumerate(history[-3:]):
                prompt += f"""
{i+1}. Mutation: {h.get('mutation_id', 'unknown')}
   Metric deltas: {h.get('metric_deltas', {})}
   Result: {h.get('result', 'unknown')}
"""

        prompt += f"""
CURRENT TOOL CODE:
```python
{tool_code}
```

TASK:
1) Analyze the code and identify the specific changes needed to achieve the target metrics
2) Provide a UNIFIED DIFF patch in this exact format:

```diff
--- a/{tool_name}.py
+++ b/{tool_name}.py
@@ -LINE,COUNT +LINE,COUNT @@
 context line
-removed line
+added line
 context line
```

3) Keep changes minimal and focused on the metrics that need improvement

RESPONSE FORMAT:
First, provide your analysis in 3 bullets:
- Issue:
- Root cause:
- Proposed fix:

Then provide ONLY the unified diff patch, nothing else after it.
"""

        return prompt

    def _extract_diff_from_response(self, response: str) -> Optional[str]:
        """Extract unified diff from LLM response."""
        # Find diff block between ```diff markers
        if "```diff" in response:
            parts = response.split("```diff")
            if len(parts) > 1:
                diff_part = parts[1].split("```")[0]
                return diff_part.strip()

        # Fallback: look for diff header
        lines = response.split('\n')
        diff_lines = []
        in_diff = False

        for line in lines:
            if line.startswith('---') or line.startswith('+++'):
                in_diff = True

            if in_diff:
                diff_lines.append(line)

            # Stop at next markdown block or end
            if in_diff and line.strip() and not any(
                line.startswith(p) for p in ['---', '+++', '@@', ' ', '-', '+']
            ):
                break

        if diff_lines:
            return '\n'.join(diff_lines)

        return None

    def _validate_diff(self, diff: str, original_code: str) -> bool:
        """
        Validate diff patch.

        Checks:
        - Has proper unified diff format
        - Changes don't exceed line limit
        - No forbidden patterns (eval, exec, etc.)
        """
        # Check format
        if not ('---' in diff and '+++' in diff and '@@' in diff):
            return False

        # Count changed lines
        changed_lines = len([l for l in diff.split('\n') if l.startswith('+') or l.startswith('-')])
        if changed_lines > 60:  # Max 30 line pairs
            return False

        # Check for forbidden patterns
        forbidden = ['eval(', 'exec(', '__import__(', 'os.system']
        for pattern in forbidden:
            if pattern in diff:
                return False

        return True

    def _log_mutation(
        self,
        mutation_id: str,
        context: Dict,
        diff_patch: str,
        llm_response: str
    ):
        """Log mutation for audit trail."""
        log_file = self.mutation_history_dir / f"{mutation_id.replace(':', '_')}.json"

        log_entry = {
            "mutation_id": mutation_id,
            "timestamp": datetime.now().isoformat(),
            "tool_name": context["tool_name"],
            "metrics_current": context["metrics"]["current"],
            "metrics_target": context["metrics"]["target"],
            "failure_info": context["failure_info"],
            "diff_patch": diff_patch,
            "llm_response": llm_response,
            "diff_hash": hashlib.sha256(diff_patch.encode()).hexdigest()[:16]
        }

        log_file.write_text(json.dumps(log_entry, indent=2))
        print(f"[mutation] Logged mutation: {mutation_id}")


# Test function
def test_mutation_engine():
    """Test the LLM mutation engine."""
    engine = LLMMutationEngine()

    # Mock tool code
    tool_code = """#!/usr/bin/env python3
def analyze_noise(audio_data, threshold=0.02):
    # Simple noise detection
    peaks = find_peaks(audio_data)
    return len([p for p in peaks if p > threshold])
"""

    # Mock metrics
    metrics_current = {
        "fail_rate": 0.1,
        "latency_ms_p95": 150,
        "f1_score": 0.65
    }

    metrics_target = {
        "fail_rate": 0.0,
        "latency_ms_p95": 100,
        "f1_score": 0.80
    }

    # Test trigger logic
    fitness_history = [0.6, 0.61, 0.61, 0.61]  # Plateau
    should_trigger = engine.should_trigger_llm_mutation(
        "noise_floor",
        fitness_history
    )

    print(f"Should trigger LLM mutation: {should_trigger}")

    if should_trigger and engine.llm_backend:
        print("\nGenerating mutation...")
        result = engine.generate_mutation(
            tool_name="noise_floor",
            tool_code=tool_code,
            metrics_current=metrics_current,
            metrics_target=metrics_target,
            failure_info=None,
            diff_history=[]
        )

        if result:
            mutation_id, diff = result
            print(f"\nMutation ID: {mutation_id}")
            print(f"Diff:\n{diff}")
        else:
            print("\nMutation generation failed")


if __name__ == '__main__':
    test_mutation_engine()
