"""
Lightweight runtime wrapper for skills.

Provides retry with exponential backoff, fallback handling, telemetry, cost tracking,
and circuit breaker protection.

Governance:
- Self-contained with graceful error handling
- Logs to /var/log/kloros/structured.jsonl
- Circuit breaker prevents cascading failures
- Telemetry tracks cost and performance
"""

import time
import functools
import random
from typing import Optional, Dict, Any
from .logging import log
from .telemetry import get_telemetry_collector
from .error_taxonomy import ErrorTaxonomy, ErrorCode
from .circuit_breaker import get_circuit_breaker

# XAI integration for explainable execution
try:
    from .xai import log_execution_trace, sanitize_params, build_execution_steps
    XAI_AVAILABLE = True
except ImportError:
    XAI_AVAILABLE = False


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open for a tool."""
    pass


def _backoff(a, base=300, jitter=150):
    """
    Calculate exponential backoff delay with jitter.

    Args:
        a: Attempt number (1-indexed)
        base: Base delay in milliseconds
        jitter: Random jitter range in milliseconds

    Returns:
        Delay in milliseconds
    """
    return (2**(a-1)) * base + random.randint(0, jitter)


class FallbackDispatcher:
    """Dispatcher for fallback skill execution."""

    def __init__(self, tool_registry=None):
        """
        Initialize dispatcher.

        Args:
            tool_registry: Optional tool registry for skill lookup
        """
        self.tool_registry = tool_registry

    def dispatch(self, fallback_config: dict, original_input: Any, context: dict) -> Any:
        """
        Dispatch to fallback skill with visibility checking.

        Args:
            fallback_config: Fallback configuration from manifest
            original_input: Input that caused the original skill to fail
            context: Context dict with intent, error, etc.

        Returns:
            Output from fallback skill

        Raises:
            PermissionError: If fallback skill is not visible
            LookupError: If fallback skill not found
            Exception: If fallback execution fails
        """
        fallback_skill_name = fallback_config.get("skill")
        if not fallback_skill_name:
            raise ValueError("Fallback config missing 'skill' field")

        # Check visibility
        from .registry import visible_to

        if self.tool_registry and fallback_skill_name in self.tool_registry.tools:
            tool_obj = self.tool_registry.tools[fallback_skill_name]

            # Check if fallback skill has manifest with visibility rules
            if hasattr(tool_obj, 'manifest'):
                intent = context.get("intent", "")
                if not visible_to(intent, context, tool_obj.manifest):
                    raise PermissionError(
                        f"Fallback skill '{fallback_skill_name}' not visible for intent '{intent}'"
                    )

        # Map arguments if args_map is provided
        args_map = fallback_config.get("args_map", {})
        fallback_input = self._map_args(original_input, args_map)

        log("skill.fallback_start",
            from_skill=context.get("skill"),
            to_skill=fallback_skill_name,
            error=context.get("error"))

        # Execute fallback skill
        t0 = time.time()
        try:
            if self.tool_registry and fallback_skill_name in self.tool_registry.tools:
                tool_func = self.tool_registry.tools[fallback_skill_name].func
                result = tool_func(fallback_input)
            else:
                raise LookupError(f"Fallback skill '{fallback_skill_name}' not found in registry")

            log("skill.fallback_complete",
                from_skill=context.get("skill"),
                to_skill=fallback_skill_name,
                latency_ms=int((time.time() - t0) * 1000),
                success=True)

            return result

        except Exception as e:
            log("skill.fallback_complete",
                from_skill=context.get("skill"),
                to_skill=fallback_skill_name,
                latency_ms=int((time.time() - t0) * 1000),
                success=False,
                error=str(e))
            raise

    def _map_args(self, original_input: Any, args_map: dict) -> Any:
        """
        Map arguments from original input to fallback input.

        Args:
            original_input: Original input (can be dict or Pydantic model)
            args_map: Mapping dict like {"query": "search_term"}

        Returns:
            Mapped input for fallback skill
        """
        if not args_map:
            return original_input  # No mapping, pass through

        # Handle Pydantic models
        if hasattr(original_input, 'model_dump'):
            input_dict = original_input.model_dump()
        elif isinstance(original_input, dict):
            input_dict = original_input
        else:
            # Unknown type, pass through
            return original_input

        # Apply mapping
        mapped = {}
        for fallback_key, original_key in args_map.items():
            if original_key in input_dict:
                mapped[fallback_key] = input_dict[original_key]

        return mapped


# Global dispatcher instance
_dispatcher: Optional[FallbackDispatcher] = None


def set_fallback_dispatcher(tool_registry=None):
    """
    Set global fallback dispatcher.

    Args:
        tool_registry: Tool registry for skill lookup
    """
    global _dispatcher
    _dispatcher = FallbackDispatcher(tool_registry)


def skill_wrapper(manifest: dict, intent: str = ""):
    """
    Decorator to wrap skill execution with runtime features.

    Features:
    - Circuit breaker protection (auto-mask on high error rate)
    - Retry with exponential backoff
    - Error-typed fallback routing
    - Telemetry with cost tracking
    - Structured logging
    - XAI execution tracing

    Args:
        manifest: Skill manifest dictionary with name, version, retries, fallbacks, etc.
        intent: User intent/query for visibility checking

    Returns:
        Decorated function with runtime features

    Raises:
        CircuitOpenError: If circuit breaker is open for this skill
        Exception: If skill and all fallbacks fail
    """
    def deco(fn):
        @functools.wraps(fn)
        def run(inp):
            skill_name = manifest["name"]
            skill_version = manifest["version"]
            tool_selected = f"{skill_name}@{skill_version}"

            # XAI: Track execution steps
            xai_steps = []

            # Check circuit breaker (kill-switch)
            breaker = get_circuit_breaker()
            if breaker.is_open(skill_name):
                status = breaker.get_status(skill_name)
                error_msg = (
                    f"Circuit breaker open for {skill_name} "
                    f"(error_rate={status['error_rate']*100:.1f}%, "
                    f"cooldown_remaining={status['cooldown_remaining']:.0f}s)"
                )

                # XAI: Log circuit breaker denial
                xai_steps.append({
                    "step": "circuit_breaker",
                    "why": f"error_rate={status['error_rate']*100:.1f}% > threshold",
                    "result": "denied"
                })

                if XAI_AVAILABLE:
                    log_execution_trace(
                        intent or "unknown",
                        tool_selected,
                        xai_steps,
                        sanitize_params(inp),
                        outcome="failure",
                        error=error_msg
                    )

                log("skill.circuit_open",
                    skill=skill_name,
                    version=skill_version,
                    error_rate=status['error_rate'],
                    cooldown_remaining=status['cooldown_remaining'])
                raise CircuitOpenError(error_msg)

            # XAI: Circuit breaker passed
            xai_steps.append({
                "step": "circuit_breaker",
                "why": "error rate within threshold",
                "result": "ok"
            })

            attempts = 0
            last_err = None
            t0 = time.time()
            retry_info = []

            while True:
                attempts += 1
                try:
                    out = fn(inp)
                    latency_ms = int((time.time() - t0) * 1000)

                    # Extract model name from manifest for cost tracking
                    model = None
                    if "llm" in manifest and isinstance(manifest["llm"], dict):
                        model = manifest["llm"].get("model")
                    elif "model" in manifest:
                        model = manifest.get("model")

                    # Extract token counts from output
                    tokens_in = 0
                    tokens_out = 0
                    if hasattr(out, '__dict__'):
                        tokens_in = getattr(out, 'tokens_in', 0)
                        tokens_out = getattr(out, 'tokens_out', 0)
                    elif isinstance(out, dict):
                        tokens_in = out.get('tokens_in', 0)
                        tokens_out = out.get('tokens_out', 0)

                    # Record telemetry with cost tracking
                    collector = get_telemetry_collector()
                    collector.record_execution(
                        skill=skill_name,
                        version=skill_version,
                        latency_ms=latency_ms,
                        success=True,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        model=model
                    )

                    # Record to circuit breaker (success)
                    breaker.record_execution(skill_name, success=True)

                    # XAI: Execution completed successfully
                    xai_steps.append({
                        "step": "complete",
                        "why": "execution finished",
                        "result": f"success (latency={latency_ms}ms)"
                    })

                    if XAI_AVAILABLE:
                        log_execution_trace(
                            intent or manifest.get("intent_tags", ["unknown"])[0] if "intent_tags" in manifest else "unknown",
                            tool_selected,
                            xai_steps,
                            sanitize_params(inp),
                            outcome="success"
                        )

                    log("skill.completed",
                        skill=skill_name,
                        v=skill_version,
                        latency_ms=latency_ms,
                        attempts=attempts,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        model=model)
                    return out

                except Exception as e:
                    last_err = str(e)
                    max_attempts = manifest.get("retries", {}).get("attempts", 1)

                    if attempts < max_attempts:
                        delay_ms = _backoff(attempts)

                        # XAI: Log retry
                        xai_steps.append({
                            "step": "retry",
                            "why": f"attempt {attempts} failed: {last_err[:80]}",
                            "result": f"attempt={attempts+1}, backoff={delay_ms}ms"
                        })

                        time.sleep(delay_ms / 1000)
                        continue

                    # Classify error and try appropriate fallback
                    error_code = ErrorTaxonomy.classify(e)
                    log("skill.error_classified",
                        skill=skill_name,
                        error_code=error_code.value,
                        error=last_err)

                    # Get remediation strategy
                    remediation = ErrorTaxonomy.get_remediation(error_code, manifest)

                    if remediation and remediation.get("retry") and attempts == 1:
                        # Retry once if remediation says so
                        max_attempts = 2
                        delay_ms = _backoff(1)

                        # XAI: Log remediation retry
                        xai_steps.append({
                            "step": "retry",
                            "why": f"remediation strategy for {error_code.value}",
                            "result": f"attempt=2, backoff={delay_ms}ms"
                        })

                        time.sleep(delay_ms / 1000)
                        continue

                    # Try targeted fallback based on error type
                    fallback_skill = ErrorTaxonomy.find_fallback_for_error(error_code, manifest)

                    if fallback_skill and _dispatcher:
                        # Find fallback config
                        fallbacks = manifest.get("fallbacks", [])
                        fb_config = None
                        for fb in fallbacks:
                            if fb.get("skill") == fallback_skill:
                                fb_config = fb
                                break

                        if not fb_config:
                            fb_config = {"skill": fallback_skill}

                        try:
                            context = {
                                "skill": skill_name,
                                "intent": intent,
                                "error": last_err,
                                "error_code": error_code.value
                            }
                            result = _dispatcher.dispatch(fb_config, inp, context)

                            # XAI: Log successful fallback
                            xai_steps.append({
                                "step": "fallback",
                                "why": f"{error_code.value} → taxonomy rule",
                                "result": fallback_skill
                            })

                            if XAI_AVAILABLE:
                                log_execution_trace(
                                    intent or "unknown",
                                    tool_selected,
                                    xai_steps,
                                    sanitize_params(inp),
                                    outcome="fallback",
                                    error=last_err[:160]
                                )

                            # Fallback succeeded - record partial success to circuit breaker
                            breaker.record_execution(skill_name, success=True)

                            return result
                        except Exception as fb_err:
                            log("skill.fallback_failed",
                                skill=skill_name,
                                fallback=fallback_skill,
                                error_code=error_code.value,
                                error=str(fb_err))

                    # Try all fallbacks if targeted routing didn't work
                    fallbacks = manifest.get("fallbacks", [])
                    if fallbacks and _dispatcher:
                        for fb in fallbacks:
                            if fb.get("skill") == fallback_skill:
                                continue  # Already tried this one
                            try:
                                context = {
                                    "skill": skill_name,
                                    "intent": intent,
                                    "error": last_err,
                                    "error_code": error_code.value
                                }
                                result = _dispatcher.dispatch(fb, inp, context)

                                # XAI: Log fallback
                                xai_steps.append({
                                    "step": "fallback",
                                    "why": f"generic fallback after {error_code.value}",
                                    "result": fb.get("skill")
                                })

                                if XAI_AVAILABLE:
                                    log_execution_trace(
                                        intent or "unknown",
                                        tool_selected,
                                        xai_steps,
                                        sanitize_params(inp),
                                        outcome="fallback",
                                        error=last_err[:160]
                                    )

                                # Fallback succeeded
                                breaker.record_execution(skill_name, success=True)

                                return result
                            except Exception as fb_err:
                                log("skill.fallback_failed",
                                    skill=skill_name,
                                    fallback=fb.get("skill"),
                                    error=str(fb_err))
                                continue  # Try next fallback

                    # No fallbacks worked or none available
                    latency_ms = int((time.time() - t0) * 1000)

                    # Extract model for failure telemetry
                    model = None
                    if "llm" in manifest and isinstance(manifest["llm"], dict):
                        model = manifest["llm"].get("model")
                    elif "model" in manifest:
                        model = manifest.get("model")

                    # Record telemetry for failure
                    collector = get_telemetry_collector()
                    collector.record_execution(
                        skill=skill_name,
                        version=skill_version,
                        latency_ms=latency_ms,
                        success=False,
                        model=model
                    )

                    # Record to circuit breaker (failure)
                    breaker.record_execution(skill_name, success=False)

                    # XAI: Log final failure
                    xai_steps.append({
                        "step": "error",
                        "why": last_err[:160],
                        "result": "exception"
                    })

                    if XAI_AVAILABLE:
                        log_execution_trace(
                            intent or "unknown",
                            tool_selected,
                            xai_steps,
                            sanitize_params(inp),
                            outcome="failure",
                            error=last_err[:160]
                        )

                    log("skill.error",
                        skill=skill_name,
                        err=last_err,
                        fallbacks_attempted=len(fallbacks),
                        error_code=error_code.value)
                    raise

        return run
    return deco
