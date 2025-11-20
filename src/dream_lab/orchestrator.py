"""Chaos experiment orchestration and execution."""

import time
from typing import Dict, Any, Optional
from datetime import datetime

from .spec import FailureSpec
from .observers import TraceObserver
from .grading import grade_outcome
from .sandbox import Sandbox


class ChaosOrchestrator:
    """Orchestrates chaos experiments with safety and observability."""

    def __init__(
        self,
        heal_bus,
        tool_registry=None,
        dream_runtime=None,
        metrics=None,
        logger=None,
        safe_mode: bool = True,
        kloros_instance=None
    ):
        """Initialize orchestrator.

        Args:
            heal_bus: HealBus instance for event monitoring
            tool_registry: Tool registry (optional)
            dream_runtime: D-REAM runtime (optional)
            metrics: Metrics system (optional)
            logger: Logger (optional)
            safe_mode: Run in sandbox (default True)
            kloros_instance: KLoROS instance for accessing backends (optional)
        """
        self.heal_bus = heal_bus
        self.tool_registry = tool_registry
        self.dream = dream_runtime
        self.metrics = metrics
        self.logger = logger
        self.safe_mode = safe_mode
        self.kloros_instance = kloros_instance
        self.obs = TraceObserver(metrics, logger)

        # Subscribe observer to heal bus
        if self.heal_bus:
            self.heal_bus.subscribe(self.obs.on_event)

        # Cache for component references
        self._component_cache = {}

    def run(self, spec: FailureSpec) -> Dict[str, Any]:
        """Run a chaos experiment.

        Args:
            spec: FailureSpec defining the experiment

        Returns:
            Result dict with outcome and score
        """
        if self.logger:
            self.logger.info(f"[CHAOS] Starting: {spec.id} → {spec.target}/{spec.mode}")

        with Sandbox(enabled=self.safe_mode, metrics=self.metrics, logger=self.logger) as sbx:
            # Reset observer for new experiment
            self.obs.reset()

            start_time = datetime.now()

            # 1) Capture baseline metrics
            start_metrics = self.obs.snapshot()

            # 2) Apply fault injection
            try:
                self._apply(spec)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"[CHAOS] Injection failed: {e}")
                return {
                    "spec_id": spec.id,
                    "outcome": {"healed": False, "reason": f"injection_error: {e}"},
                    "score": 0
                }

            # 3) Exercise the system (poke the failure)
            try:
                self._poke(spec)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[CHAOS] Poke failed (expected): {e}")

            # 4) Wait for healing or timeout
            outcome = self._await(spec, start_time)

            # 5) Capture final metrics
            end_metrics = self.obs.snapshot()

            # 6) Grade the outcome
            score = grade_outcome(spec, start_metrics, end_metrics, outcome)

            result = {
                "spec_id": spec.id,
                "target": spec.target,
                "mode": spec.mode,
                "outcome": outcome,
                "score": score,
                "start_metrics": start_metrics,
                "end_metrics": end_metrics,
                "events": self.obs.get_events(),
                "summary": self.obs.get_summary(),
                "timestamp": datetime.now().isoformat()
            }

            if self.logger:
                self.logger.info(
                    f"[CHAOS] Completed: {spec.id} "
                    f"healed={outcome.get('healed')} score={score}"
                )

            return result

    def _apply(self, spec: FailureSpec):
        """Apply fault injection based on spec.

        Args:
            spec: FailureSpec to apply
        """
        from . import injectors as inj

        target = spec.target
        mode = spec.mode
        params = spec.params

        if self.logger:
            self.logger.info(f"[CHAOS] Applying {mode} to {target}")

        # Map target to injection
        if target.startswith("rag.synthesis"):
            backend = self._get_rag_backend()
            if backend and hasattr(backend, 'tool_synthesizer'):
                if mode == "timeout":
                    delay = params.get("delay_s", 35)
                    inj.inject_timeout(backend.tool_synthesizer, "synthesize_tool", delay,
                                      heal_bus=self.heal_bus, event_source="rag", event_kind="synthesis_timeout")
                elif mode == "intermittent":
                    rate = params.get("fail_rate", 0.3)
                    inj.inject_intermittent_failure(backend.tool_synthesizer, "synthesize_tool", rate,
                                                   heal_bus=self.heal_bus, event_source="rag", event_kind="synthesis_timeout")

        elif target.startswith("tts"):
            tts = self._get_tts_backend()
            if tts:
                if mode == "jitter":
                    base = params.get("base_ms", 400)
                    jitter = params.get("jitter_ms", 600)
                    inj.inject_latency_jitter(tts, "synthesize", base, jitter)
                elif mode == "timeout":
                    delay = params.get("delay_s", 2)
                    inj.inject_timeout(tts, "synthesize", delay,
                                      heal_bus=self.heal_bus, event_source="audio", event_kind="beep_echo")

        elif target.startswith("validator"):
            # Validator injection handled via environment flags
            if mode == "threshold":
                import os
                threshold = params.get("threshold", 0.15)
                os.environ["KLR_VALIDATOR_THRESHOLD"] = str(threshold)

        elif mode == "oom":
            device = params.get("device", "gpu")
            bytes_req = params.get("bytes_req", 2_000_000_000)
            inj.inject_oom(device, bytes_req)

        elif mode == "corrupt":
            path = params.get("path")
            if path:
                bytes_to_flip = params.get("bytes_to_flip", 64)
                inj.inject_corrupt_file(path, bytes_to_flip)

        elif mode == "quota":
            service = params.get("service", "tool_synth")
            inj.inject_quota_exceeded(service)

        else:
            if self.logger:
                self.logger.warning(f"[CHAOS] Unknown injection: {target}/{mode}")

    def _poke(self, spec: FailureSpec):
        """Exercise the system to trigger the injected failure.

        Args:
            spec: FailureSpec being tested
        """
        target = spec.target

        if self.logger:
            self.logger.info(f"[CHAOS] Poking {target}")

        # Minimal action to trigger the failure path
        if target.startswith("rag.synthesis"):
            backend = self._get_rag_backend()
            if backend and hasattr(backend, 'tool_synthesizer'):
                # Check for quota exceeded before attempting synthesis
                import os
                if os.getenv("KLR_FORCE_QUOTA_EXCEEDED") == "1":
                    if self.logger:
                        self.logger.info(f"[CHAOS] Quota exceeded detected, emitting event")
                    try:
                        from src.self_heal.adapters.kloros_rag import emit_quota_exceeded
                        if backend.heal_bus:
                            emit_quota_exceeded(backend.heal_bus, "chaos_probe_tool")
                    except (ImportError, AttributeError) as e:
                        if self.logger:
                            self.logger.warning(f"[CHAOS] Could not emit quota event: {e}")
                    return  # Don't proceed with synthesis

                try:
                    backend.tool_synthesizer.synthesize_tool(
                        "chaos_probe_tool",
                        context="test probe",
                        timeout=spec.guards.get("max_duration_s", 10)
                    )
                except Exception as e:
                    if self.logger:
                        self.logger.info(f"[CHAOS] Poke triggered failure: {e}")

        elif target.startswith("tts"):
            tts = self._get_tts_backend()
            if tts and hasattr(tts, 'synthesize'):
                try:
                    tts.synthesize("test", sample_rate=22050)
                except Exception as e:
                    if self.logger:
                        self.logger.info(f"[CHAOS] Poke triggered failure: {e}")

        elif target.startswith("dream.domain"):
            if self.dream and hasattr(self.dream, 'request_eval'):
                domain = target.split(":")[1] if ":" in target else "cpu"
                self.dream.request_eval(domain=domain, goal="smoke_test")

        elif target.startswith("validator"):
            validator = self._get_validator()
            if validator:
                try:
                    # Trigger validation with low-overlap context to emit heal event
                    # Use context that won't match "chaos_probe_tool" purpose
                    result = validator.validate_tool_request(
                        tool_name="chaos_probe_tool",
                        tool_args={},
                        context="unrelated user query with no keyword overlap whatsoever"
                    )
                    if not result.is_valid:
                        if self.logger:
                            self.logger.info(f"[CHAOS] Poke triggered validation rejection: {result.error_message}")
                except Exception as e:
                    if self.logger:
                        self.logger.info(f"[CHAOS] Poke triggered validation error: {e}")

    def _await(self, spec: FailureSpec, start_time: datetime) -> Dict[str, Any]:
        """Wait for healing or timeout.

        Args:
            spec: FailureSpec being tested
            start_time: When experiment started

        Returns:
            Outcome dict
        """
        max_duration = spec.guards.get("max_duration_s", 20)
        deadline = time.time() + max_duration

        expected_event = spec.expected.get("heal_event", {})
        expected_source = expected_event.get("source")
        expected_kind = expected_event.get("kind")

        while time.time() < deadline:
            # Check if expected healing event occurred
            if expected_source and self.obs.seen_event(source=expected_source, kind=expected_kind):
                duration = (datetime.now() - start_time).total_seconds()
                return {
                    "healed": True,
                    "event": expected_event,
                    "duration_s": duration,
                    "clean_recovery": True
                }

            # Check abort conditions
            abort_event = spec.guards.get("abort_on_event", {})
            if abort_event:
                abort_source = abort_event.get("source")
                abort_kind = abort_event.get("kind")
                if self.obs.seen_event(source=abort_source, kind=abort_kind):
                    duration = (datetime.now() - start_time).total_seconds()
                    return {
                        "healed": False,
                        "reason": "abort_condition_met",
                        "duration_s": duration,
                        "guard_triggered": True
                    }

            time.sleep(0.2)

        # Timeout
        duration = (datetime.now() - start_time).total_seconds()
        return {
            "healed": False,
            "reason": "timeout",
            "duration_s": duration
        }

    def _get_rag_backend(self):
        """Get RAG backend instance."""
        if "rag_backend" not in self._component_cache:
            backend = None

            # First try: get from KLoROS instance if provided
            if self.kloros_instance and hasattr(self.kloros_instance, 'reason_backend'):
                backend = self.kloros_instance.reason_backend
                print(f"[chaos] Found RAG backend from KLoROS instance")

            # Fallback: try singleton pattern
            if not backend:
                try:
                    import src.reasoning.local_rag_backend as rag_mod
                    if hasattr(rag_mod, 'LocalRagBackend'):
                        if hasattr(rag_mod.LocalRagBackend, '_instance'):
                            backend = rag_mod.LocalRagBackend._instance
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"[CHAOS] Could not get RAG backend: {e}")

            self._component_cache["rag_backend"] = backend

        return self._component_cache.get("rag_backend")

    def _get_tts_backend(self):
        """Get TTS backend instance."""
        if "tts_backend" not in self._component_cache:
            try:
                # This is a placeholder - adjust based on your architecture
                import src.tts.base as tts_mod
                if hasattr(tts_mod, 'TtsBackend') and hasattr(tts_mod.TtsBackend, '_instance'):
                    self._component_cache["tts_backend"] = tts_mod.TtsBackend._instance
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[CHAOS] Could not get TTS backend: {e}")
                self._component_cache["tts_backend"] = None

        return self._component_cache.get("tts_backend")

    def _get_validator(self):
        """Get PreExecutionValidator instance."""
        if "validator" not in self._component_cache:
            try:
                from src.tool_synthesis.pre_execution_validator import PreExecutionValidator

                # Create a minimal mock tool registry for chaos testing
                class MockToolRegistry:
                    def __init__(self):
                        # Create a mock tool with description that won't match test context
                        class MockTool:
                            def __init__(self):
                                self.name = "chaos_probe_tool"
                                self.description = "probe tool for chaos testing"
                                self.parameters = []

                        self.tools = {"chaos_probe_tool": MockTool()}

                mock_registry = MockToolRegistry()

                # Create validator with orchestrator's heal bus and mock registry
                validator = PreExecutionValidator(
                    tool_registry=mock_registry,
                    heal_bus=self.heal_bus
                )
                self._component_cache["validator"] = validator
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[CHAOS] Could not get validator: {e}")
                self._component_cache["validator"] = None

        return self._component_cache.get("validator")
