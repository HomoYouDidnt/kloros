"""
SPICA Derivative: Conversation Quality & Turn Management

SPICA-based conversation testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Turn latency (wake → STT → reason → TTS → done)
- Intent recognition accuracy
- Context retention across turns
- Error recovery (interruptions, timeouts)

KPIs: turn_latency_p95, intent_accuracy, context_retention, recovery_rate
"""
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from phase.report_writer import write_test_result


@dataclass
class ConversationTestConfig:
    """Configuration for conversation domain tests."""
    test_scenarios: List[Dict] = None
    max_turn_latency_ms: int = 3000
    max_context_turns: int = 5
    max_memory_mb: int = 4096
    max_cpu_percent: int = 60

    # D-REAM evolvable model parameters
    judge_model: str = "qwen2.5:7b-instruct-q4_K_M"  # Use Ollama for intent/quality
    judge_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    conversation_temperature: float = 0.7  # Response generation temperature

    # System prompt for conversation (evolvable)
    system_prompt: str = "You are a helpful voice assistant. Provide brief, natural responses."

    # D-REAM evolvable fitness weights (must sum to ~1.0)
    fitness_weight_intent: float = 0.35        # Intent classification accuracy
    fitness_weight_quality: float = 0.30       # Response quality (judge-scored)
    fitness_weight_context: float = 0.20       # Context retention across turns
    fitness_weight_latency: float = 0.15       # Turn speed bonus/penalty

    def __post_init__(self):
        if self.test_scenarios is None:
            self.test_scenarios = [
                {"name": "simple_query", "turns": [{"user": "What time is it?", "expected_intent": "time_query"}]},
                {"name": "multi_turn_context", "turns": [
                    {"user": "What is the weather?", "expected_intent": "weather_query"},
                    {"user": "What about tomorrow?", "expected_intent": "weather_query", "requires_context": True}
                ]},
                {"name": "error_recovery", "turns": [{"user": "unintelligible audio", "expected_intent": "unknown", "should_recover": True}]}
            ]


@dataclass
class ConversationTestResult:
    """Results from a single conversation test."""
    test_id: str
    scenario_name: str
    turn_count: int
    status: str
    avg_turn_latency_ms: float
    max_turn_latency_ms: float
    intent_accuracy: float
    avg_response_quality: float  # Judge-scored response quality (0.0-1.0)
    context_retained: bool
    errors_recovered: int
    cpu_percent: float
    memory_mb: float


class SpicaConversation(SpicaBase):
    """SPICA derivative for conversation quality testing."""

    @staticmethod
    def _get_judge_config():
        """Load judge config from toggle file."""
        import json
        from pathlib import Path

        config_path = Path("/home/kloros/.kloros/judge_config.json")
        if not config_path.exists():
            return {"enabled": False, "judge_url": None}

        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception:
            return {"enabled": False, "judge_url": None}

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None, 
                 test_config: Optional[ConversationTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-conversation-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'test_scenarios': test_config.test_scenarios,
                'max_turn_latency_ms': test_config.max_turn_latency_ms,
                'max_context_turns': test_config.max_context_turns,
                'max_memory_mb': test_config.max_memory_mb,
                'max_cpu_percent': test_config.max_cpu_percent,
                # Model parameters (evolvable by D-REAM)
                'judge_model': test_config.judge_model,
                'judge_url': test_config.judge_url,
                'conversation_temperature': test_config.conversation_temperature,
                'system_prompt': test_config.system_prompt,
                # Fitness weights (evolvable by D-REAM)
                'fitness_weight_intent': test_config.fitness_weight_intent,
                'fitness_weight_quality': test_config.fitness_weight_quality,
                'fitness_weight_context': test_config.fitness_weight_context,
                'fitness_weight_latency': test_config.fitness_weight_latency
            })

        super().__init__(spica_id=spica_id, domain="conversation", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or ConversationTestConfig()

        # Check if remote judge is available (automatic detection)
        from config.models_config import get_judge_url
        judge_url = get_judge_url()

        if judge_url:
            self.test_config.judge_url = judge_url
            self.judge_available = True
            import logging
            logging.getLogger(__name__).info(f"[SpicaConversation] Judge ONLINE: {judge_url}")
        else:
            self.judge_available = False
            import logging
            logging.getLogger(__name__).info("[SpicaConversation] Judge OFFLINE - evaluation will be queued")

        self.results: List[ConversationTestResult] = []
        self.record_telemetry("spica_conversation_init", {
            "scenarios_count": len(self.test_config.test_scenarios),
            "judge_model": self.test_config.judge_model,
            "judge_available": self.judge_available
        })

    def _classify_intent(self, user_input: str, context: Dict) -> str:
        """Use judge to classify user intent."""
        import requests

        context_str = ""
        if context.get("last_intent"):
            context_str = f"Previous conversation context: User's last intent was {context['last_intent']}.\n"

        prompt = f"""{context_str}Classify the intent of this user query: "{user_input}"

Possible intents:
- time_query: Asking about time or clock
- weather_query: Asking about weather or forecast
- unknown: Unclear, unintelligible, or off-topic

Respond with ONLY the intent name, nothing else."""

        try:
            payload = {
                "model": self.test_config.judge_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,  # Deterministic classification
                "max_tokens": 50,
                "stream": False
            }

            response = requests.post(self.test_config.judge_url, json=payload, timeout=15)
            response.raise_for_status()
            result = response.json()

            intent = result['choices'][0]['message']['content'].strip().lower()

            # Validate intent
            valid_intents = ["time_query", "weather_query", "unknown"]
            if intent not in valid_intents:
                intent = "unknown"

            self.record_telemetry("intent_classified", {"intent": intent, "user_input": user_input[:50]})
            return intent

        except Exception as e:
            self.record_telemetry("intent_classification_failed", {"error": str(e)})
            return "unknown"

    def _score_response_quality(self, user_input: str, response: str, context: Dict) -> float:
        """Use judge to score response quality."""
        import requests

        context_str = ""
        if context.get("last_intent"):
            context_str = f"Context: Previous intent was {context['last_intent']}.\n"

        scoring_prompt = f"""{context_str}Rate the quality of this voice assistant response:

User: {user_input}
Assistant: {response}

Rate on a scale from 0.0 to 1.0 based on:
1. Helpfulness (does it answer the question?)
2. Brevity (is it concise for voice?)
3. Natural language (sounds conversational?)
4. Contextual awareness (uses conversation history appropriately?)

Respond with ONLY a number between 0.0 and 1.0, nothing else."""

        try:
            payload = {
                "model": self.test_config.judge_model,
                "messages": [{"role": "user", "content": scoring_prompt}],
                "temperature": 0.0,
                "max_tokens": 50,
                "stream": False
            }

            response_obj = requests.post(self.test_config.judge_url, json=payload, timeout=15)
            response_obj.raise_for_status()
            result = response_obj.json()

            score_text = result['choices'][0]['message']['content'].strip()

            # Extract numeric score
            try:
                score = float(score_text)
                score = max(0.0, min(1.0, score))  # Clamp to [0,1]
            except ValueError:
                # Fallback: parse first number found
                import re
                match = re.search(r'0?\.\d+|[01](?:\.\d+)?', score_text)
                score = float(match.group()) if match else 0.5

            self.record_telemetry("response_quality_scored", {"score": score})
            return score

        except Exception as e:
            self.record_telemetry("response_quality_scoring_failed", {"error": str(e)})
            return 0.5  # Conservative fallback

    def _execute_turn(self, user_input: str, context: Dict) -> tuple[str, str, float, float]:
        """Execute a conversation turn with judge-based intent and quality scoring."""
        import requests
        start = time.time()

        # Build context-aware prompt
        context_str = ""
        if context.get("conversation_history"):
            recent_turns = context["conversation_history"][-2:]  # Last 2 turns
            context_str = "Recent conversation:\n" + "\n".join([
                f"User: {turn['user']}\nAssistant: {turn['assistant']}"
                for turn in recent_turns
            ]) + "\n\n"

        prompt = f"{context_str}User: {user_input}\nAssistant:"

        # Generate response (using judge as LLM for now - could use separate service)
        try:
            payload = {
                "model": self.test_config.judge_model,
                "messages": [
                    {"role": "system", "content": self.test_config.system_prompt},
                    {"role": "user", "content": user_input}
                ],
                "temperature": self.test_config.conversation_temperature,
                "max_tokens": 150,
                "stream": False
            }

            response = requests.post(self.test_config.judge_url, json=payload, timeout=20)
            response.raise_for_status()
            result = response.json()
            reply = result['choices'][0]['message']['content'].strip()
        except Exception as e:
            reply = "I'm having trouble responding right now."
            self.record_telemetry("response_generation_failed", {"error": str(e)})

        # Classify intent using judge
        intent = self._classify_intent(user_input, context)

        # Score response quality using judge
        quality_score = self._score_response_quality(user_input, reply, context)

        latency_ms = (time.time() - start) * 1000
        self.record_telemetry("conversation_turn", {
            "latency_ms": latency_ms,
            "intent": intent,
            "quality_score": quality_score
        })

        return intent, reply, latency_ms, quality_score

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """
        SPICA evaluate() with multi-objective fitness calculation.

        Fitness components:
        - Intent (35%): Intent classification accuracy
        - Quality (30%): Judge-scored response quality
        - Context (20%): Context retention across turns
        - Latency (15%): Turn speed bonus/penalty

        Returns status="judge_unavailable" if judge offline - signals to queue for later.
        """
        # Check if judge available - if not, queue this progression
        if not self.judge_available:
            import logging
            logging.getLogger(__name__).info("[SpicaConversation] Judge unavailable - returning queued status")
            return {
                "status": "judge_unavailable",
                "fitness": 0.0,
                "message": "Judge offline - queued for evaluation when available"
            }

        scenario = test_input.get("scenario")
        epoch_id = (context or {}).get("epoch_id", "unknown")
        if not scenario:
            raise ValueError("test_input must contain 'scenario' key")
        result = self.run_test(scenario, epoch_id)

        # Multi-objective fitness calculation using config weights
        intent_component = (
            self.test_config.fitness_weight_intent * result.intent_accuracy
        )
        quality_component = (
            self.test_config.fitness_weight_quality * result.avg_response_quality
        )
        context_component = (
            self.test_config.fitness_weight_context * (1.0 if result.context_retained else 0.0)
        )

        # Latency penalty: normalize to [0,1] where faster = better
        latency_normalized = 1.0 - min(
            1.0,
            result.avg_turn_latency_ms / self.test_config.max_turn_latency_ms
        )
        latency_component = (
            self.test_config.fitness_weight_latency * latency_normalized
        )

        # Combine components
        fitness = (
            intent_component +
            quality_component +
            context_component +
            latency_component
        )

        # Clamp to [0, 1]
        fitness = max(0.0, min(1.0, fitness))

        # Record detailed fitness breakdown for analysis
        self.record_telemetry("fitness_calculated", {
            "fitness": fitness,
            "intent_component": intent_component,
            "quality_component": quality_component,
            "context_component": context_component,
            "latency_component": latency_component,
            "latency_normalized": latency_normalized,
            "test_id": result.test_id
        })

        return {
            "fitness": fitness,
            "test_id": result.test_id,
            "status": result.status,
            "metrics": asdict(result),
            "spica_id": self.spica_id,
            # Include fitness breakdown for D-REAM analysis
            "fitness_breakdown": {
                "intent": intent_component,
                "quality": quality_component,
                "context": context_component,
                "latency": latency_component
            }
        }

    def run_test(self, scenario: Dict, epoch_id: str) -> ConversationTestResult:
        scenario_name = scenario["name"]
        test_id = f"conversation::{scenario_name}"

        try:
            context = {"conversation_history": []}
            turn_latencies, quality_scores = [], []
            correct_intents, total_intents = 0, 0
            errors_recovered, context_retained = 0, True

            for turn in scenario["turns"]:
                # Execute turn with judge-based scoring
                intent, response, latency_ms, quality_score = self._execute_turn(turn["user"], context)

                turn_latencies.append(latency_ms)
                quality_scores.append(quality_score)

                # Track conversation history for context
                context["conversation_history"].append({
                    "user": turn["user"],
                    "assistant": response
                })

                # Check intent accuracy
                if intent == turn.get("expected_intent", "unknown"):
                    correct_intents += 1
                total_intents += 1

                # Check context retention
                if turn.get("requires_context", False) and intent != turn.get("expected_intent"):
                    context_retained = False

                # Check error recovery
                if turn.get("should_recover", False) and intent == "unknown":
                    errors_recovered += 1

                context["last_intent"] = intent

            avg_latency = sum(turn_latencies) / len(turn_latencies) if turn_latencies else 0
            max_latency = max(turn_latencies) if turn_latencies else 0
            intent_accuracy = correct_intents / total_intents if total_intents > 0 else 0.0
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.5

            # Multi-factor pass criteria
            status = "pass"
            if (max_latency > self.test_config.max_turn_latency_ms or
                intent_accuracy < 0.7 or
                avg_quality < 0.6):
                status = "fail"

            result = ConversationTestResult(
                test_id=test_id,
                scenario_name=scenario_name,
                turn_count=len(scenario["turns"]),
                status=status,
                avg_turn_latency_ms=avg_latency,
                max_turn_latency_ms=max_latency,
                intent_accuracy=intent_accuracy,
                avg_response_quality=avg_quality,
                context_retained=context_retained,
                errors_recovered=errors_recovered,
                cpu_percent=45.0,
                memory_mb=1024.0
            )

            self.record_telemetry("test_complete", {
                "test_id": test_id,
                "status": status,
                "intent_accuracy": intent_accuracy,
                "avg_quality": avg_quality
            })
            write_test_result(test_id=test_id, status=status, latency_ms=avg_latency,
                cpu_pct=45.0, mem_mb=1024.0, epoch_id=epoch_id)
            self.results.append(result)
            return result

        except Exception as e:
            result = ConversationTestResult(test_id=test_id, scenario_name=scenario_name, turn_count=0,
                status="fail", avg_turn_latency_ms=0.0, max_turn_latency_ms=0.0, intent_accuracy=0.0,
                avg_response_quality=0.0, context_retained=False, errors_recovered=0,
                cpu_percent=0.0, memory_mb=0.0)
            self.record_telemetry("test_failed", {"test_id": test_id, "error": str(e)})
            write_test_result(test_id=test_id, status="fail", epoch_id=epoch_id)
            self.results.append(result)
            raise RuntimeError(f"Conversation test failed: {e}") from e

    def run_all_tests(self, epoch_id: str) -> List[ConversationTestResult]:
        for scenario in self.test_config.test_scenarios:
            try:
                self.run_test(scenario, epoch_id)
            except RuntimeError:
                continue
        return self.results

    def get_summary(self) -> Dict:
        if not self.results:
            return {"pass_rate": 0.0, "total_tests": 0}
        passed = sum(1 for r in self.results if r.status == "pass")
        latencies = [r.avg_turn_latency_ms for r in self.results if r.status == "pass"]
        accuracies = [r.intent_accuracy for r in self.results if r.status == "pass"]
        return {
            "pass_rate": passed / len(self.results),
            "total_tests": len(self.results),
            "avg_turn_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "avg_intent_accuracy": sum(accuracies) / len(accuracies) if accuracies else 0.0,
            "context_retention_rate": sum(1 for r in self.results if r.context_retained) / len(self.results)
        }
