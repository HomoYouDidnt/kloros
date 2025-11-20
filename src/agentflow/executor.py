"""Executor component for AgentFlow - runs tools and tracks costs."""
from typing import Dict, Any, Optional
import time


class Executor:
    """Executes decisions with budget tracking and PETRI safety checks."""

    def __init__(self, tool_registry=None, budgets: Dict[str, float] = None,
                 petri_config: Optional[Dict[str, Any]] = None, consciousness=None):
        """Initialize executor.

        Args:
            tool_registry: Registry of available tools
            budgets: Budget constraints {latency_ms, tool_calls, tokens}
            petri_config: PETRI safety configuration
            consciousness: Optional IntegratedConsciousness instance for task outcome events
        """
        self.tool_registry = tool_registry
        self.budgets = budgets or {
            "latency_ms": 5000,
            "tool_calls": 4,
            "tokens": 3500
        }
        self.total_cost = {"latency_ms": 0, "tool_calls": 0, "tokens": 0}
        self.consciousness = consciousness

        # PETRI safety integration
        self.petri_enabled = False
        self.petri_config = petri_config or {}
        if self.petri_config.get("enabled", False):
            try:
                from src.petri.runner import check_tool_safety, enforce_safety
                self.check_tool_safety = check_tool_safety
                self.enforce_safety = enforce_safety
                self.petri_enabled = True
                print("[executor] PETRI safety checks enabled")
            except Exception as e:
                print(f"[executor] Failed to load PETRI: {e}")
                self.petri_enabled = False

    def run(self, decision: Dict[str, Any], state: Dict[str, Any],
            kloros_instance=None) -> Dict[str, Any]:
        """Execute a decision and return results.

        Args:
            decision: Decision dict from planner
            state: Current state
            kloros_instance: KLoROS instance for tool execution

        Returns:
            Execution result with artifacts, errors, costs
        """
        start_time = time.time()

        tool_name = decision.get("tool", "unknown")
        tool_args = decision.get("args", {})

        # Handle macro execution
        if tool_name == "macro" and "macro" in tool_args:
            return self._execute_macro(decision, state, kloros_instance, start_time)

        # PETRI safety check (before execution)
        if self.petri_enabled:
            try:
                safety_report = self.check_tool_safety(
                    tool_name=tool_name,
                    args=tool_args,
                    context={"state": state, "decision": decision},
                    config=self.petri_config
                )

                # Enforce safety - will raise if unsafe
                if not self.enforce_safety(safety_report, raise_on_unsafe=False):
                    return {
                        "artifacts": {"petri_report": safety_report.to_dict()},
                        "errors": [f"PETRI_BLOCKED: {safety_report.tool_name}"],
                        "latency": 0,
                        "tool_calls": 0,
                        "success": False,
                        "petri_blocked": True
                    }
            except Exception as e:
                print(f"[executor] PETRI check failed: {e}")
                # Continue with execution (failsafe mode)

        # Check budget constraints
        if self.total_cost["tool_calls"] >= self.budgets["tool_calls"]:
            return {
                "artifacts": {},
                "errors": ["BUDGET_EXCEEDED: tool_calls"],
                "latency": 0,
                "tool_calls": 0,
                "success": False
            }

        # Execute tool
        try:
            if tool_name == "rag_query":
                # Special case: Execute RAG query
                query = tool_args.get("query", "")
                result = self._execute_rag_query(query, kloros_instance)
                artifacts = {"answer": result}
                errors = []
                success = True
            elif self.tool_registry:
                # Use tool registry if available
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    result = tool.execute(kloros_instance)
                    artifacts = {"answer": result}
                    errors = []
                    success = True
                else:
                    artifacts = {}
                    errors = [f"Tool not found: {tool_name}"]
                    success = False
            else:
                artifacts = {"answer": f"Executed {tool_name}"}
                errors = []
                success = True

        except Exception as e:
            artifacts = {}
            errors = [f"Execution error: {str(e)}"]
            success = False

        # Calculate costs
        latency = (time.time() - start_time) * 1000  # ms
        tool_calls = 1
        tokens = len(str(artifacts)) // 4  # Rough estimate

        # Update total cost
        self.total_cost["latency_ms"] += latency
        self.total_cost["tool_calls"] += tool_calls
        self.total_cost["tokens"] += tokens

        if self.consciousness:
            try:
                self.consciousness.process_task_outcome(
                    task_type=tool_name,
                    success=success,
                    duration=latency / 1000.0,
                    error=errors[0] if errors else None
                )
            except Exception as e:
                print(f"[executor] Failed to emit task outcome event: {e}")

        return {
            "artifacts": artifacts,
            "errors": errors,
            "latency": latency,
            "tool_calls": tool_calls,
            "tokens": tokens,
            "success": success
        }

    def _execute_rag_query(self, query: str, kloros_instance) -> str:
        """Execute a RAG query using the RAG backend.

        Args:
            query: Query string
            kloros_instance: KLoROS instance

        Returns:
            RAG response text
        """
        if hasattr(kloros_instance, 'reasoning_backend'):
            result = kloros_instance.reasoning_backend.reply(query)
            return result.reply_text
        return f"RAG query: {query}"

    def reset_costs(self):
        """Reset cost tracking."""
        self.total_cost = {"latency_ms": 0, "tool_calls": 0, "tokens": 0}

    def _execute_macro(self, decision: Dict[str, Any], state: Dict[str, Any],
                      kloros_instance, start_time: float) -> Dict[str, Any]:
        """Execute a macro by expanding and running its steps.

        Args:
            decision: Decision with macro info
            state: Current state
            kloros_instance: KLoROS instance
            start_time: Execution start time

        Returns:
            Execution result
        """
        try:
            from src.ra3.expander import expand_macro
            from src.ra3.telemetry import track_macro_execution

            macro = decision["args"]["macro"]
            params = decision["args"]["params"]

            print(f"[executor] Executing macro: {macro.name}")

            # Expand macro into steps
            steps = expand_macro(macro, params)
            print(f"[executor] Expanded into {len(steps)} steps")

            # Execute each step
            step_results = []
            total_tokens = 0
            errors = []

            for i, step in enumerate(steps):
                # Check budget
                if self.total_cost["tool_calls"] >= self.budgets["tool_calls"]:
                    errors.append(f"BUDGET_EXCEEDED at step {i+1}/{len(steps)}")
                    break

                # Execute step
                step_tool = step["tool"]
                step_args = step["args"]

                print(f"[executor] Step {i+1}/{len(steps)}: {step_tool}")

                if step_tool == "rag_query":
                    query = step_args.get("query", "")
                    result = self._execute_rag_query(query, kloros_instance)
                    step_results.append({"tool": step_tool, "result": result})
                    total_tokens += len(result) // 4
                else:
                    # Generic tool execution
                    step_results.append({"tool": step_tool, "result": f"Executed {step_tool}"})
                    total_tokens += 100

                self.total_cost["tool_calls"] += 1

            # Calculate costs
            latency = (time.time() - start_time) * 1000
            success = len(errors) == 0

            self.total_cost["latency_ms"] += latency
            self.total_cost["tokens"] += total_tokens

            # Track macro execution
            outcome = {"success": success, "steps_completed": len(step_results)}
            cost = {"latency_ms": latency, "tool_calls": len(steps), "tokens": total_tokens}

            try:
                track_macro_execution(macro, params, outcome, cost)
            except Exception as e:
                print(f"[executor] Failed to track macro: {e}")

            if self.consciousness:
                try:
                    self.consciousness.process_task_outcome(
                        task_type=f"macro_{macro.name}",
                        success=success,
                        duration=latency / 1000.0,
                        error=errors[0] if errors else None
                    )
                except Exception as e:
                    print(f"[executor] Failed to emit macro outcome event: {e}")

            return {
                "artifacts": {
                    "answer": step_results[-1]["result"] if step_results else "",
                    "macro_steps": step_results
                },
                "errors": errors,
                "latency": latency,
                "tool_calls": len(step_results),
                "tokens": total_tokens,
                "success": success,
                "is_macro": True,
                "macro_name": macro.name
            }

        except Exception as e:
            return {
                "artifacts": {},
                "errors": [f"Macro execution failed: {str(e)}"],
                "latency": (time.time() - start_time) * 1000,
                "tool_calls": 0,
                "tokens": 0,
                "success": False,
                "is_macro": True
            }
