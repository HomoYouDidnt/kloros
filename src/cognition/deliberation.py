"""
Active Reasoning System - Pre-Response Deliberation

This is KLoROS's "thinking before acting" layer. It runs BEFORE LLM generation
to consciously evaluate options, assess risks, and choose strategies based on
current affective state, fatigue, uncertainty, and system constraints.

Architecture:
    User Input → Active Reasoning → Strategy Selection → LLM (with context) → Response

Key Principles:
1. Persona guides EXPRESSION, cognition guides DECISION-MAKING
2. Deliberation is conscious and uses affect/fatigue/uncertainty
3. Strategies are chosen based on current state, not hardcoded rules
4. Meta-cognitive: thinks about thinking before thinking
"""

import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class TaskComplexity(Enum):
    """Assessed complexity of the task."""
    TRIVIAL = "trivial"           # Simple question, low cognitive load
    SIMPLE = "simple"             # Straightforward task, clear approach
    MODERATE = "moderate"         # Multiple steps, some uncertainty
    COMPLEX = "complex"           # High uncertainty, multiple unknowns
    CRITICAL = "critical"         # High risk, irreversible, or safety-critical


class StrategicApproach(Enum):
    """Strategic approaches KLoROS can take."""
    DIRECT_ANSWER = "direct_answer"           # Answer immediately from knowledge
    DIAGNOSTIC_FIRST = "diagnostic_first"     # Gather info before acting
    MINIMAL_PROBE = "minimal_probe"           # Smallest test to reduce uncertainty
    DECOMPOSE = "decompose"                   # Break into smaller sub-tasks
    REQUEST_CLARIFICATION = "request_clarify" # Ask user to narrow scope
    DEFER_TO_REST = "defer_to_rest"          # Suggest waiting until lower fatigue
    ESCALATE_TO_USER = "escalate_to_user"    # Task beyond current capability


@dataclass
class SituationAssessment:
    """Assessment of current situation before acting."""

    # Input analysis
    user_intent: str                    # What does the user want?
    task_type: str                      # Question, action, analysis, debug, etc.
    complexity: TaskComplexity          # Assessed complexity
    estimated_cognitive_load: float     # 0-1 estimated mental effort

    # Current state
    current_fatigue: float              # Current combined fatigue (0-1)
    current_uncertainty: float          # Current uncertainty (0-1)
    current_valence: float              # Current mood (-1 to 1)
    available_capacity: float           # Remaining capacity before overload (0-1)

    # Risk assessment
    risks: List[str]                    # Identified risks
    reversibility: float                # How easily can this be undone? (0-1)
    safety_concern: bool                # Safety-critical task?

    # Evidence
    reasoning: List[str]                # Step-by-step reasoning


@dataclass
class StrategicDecision:
    """The chosen strategy and reasoning."""

    approach: StrategicApproach
    reasoning: List[str]                # Why this approach was chosen
    context_for_llm: Dict[str, Any]     # Context to pass to LLM
    estimated_fatigue_cost: float       # Expected fatigue from this approach (0-1)
    success_probability: float          # Estimated P(success) with this approach

    # Monitoring
    should_monitor: bool                # Should execution be monitored?
    abort_conditions: List[str]         # Conditions that would abort this approach


class ActiveReasoningEngine:
    """
    KLoROS's deliberative reasoning system.

    Runs BEFORE LLM generation to:
    1. Assess the situation (What am I being asked? What's my state?)
    2. Consider options (What approaches are available?)
    3. Evaluate each option (Costs, risks, probability of success)
    4. Choose strategy (Best fit for current state and constraints)
    5. Generate context for LLM (Guide response generation)

    This is TRUE active reasoning - not reactive, not passive.
    """

    def __init__(self, kloros_instance):
        """
        Initialize active reasoning engine.

        Args:
            kloros_instance: The main KLoROS instance (for accessing consciousness, tools, etc.)
        """
        self.kloros = kloros_instance

        # Complexity assessment heuristics
        self.complexity_keywords = {
            TaskComplexity.TRIVIAL: ["what is", "define", "explain briefly"],
            TaskComplexity.SIMPLE: ["check", "show", "list", "status"],
            TaskComplexity.MODERATE: ["analyze", "compare", "find", "debug"],
            TaskComplexity.COMPLEX: ["design", "implement", "fix", "optimize"],
            TaskComplexity.CRITICAL: ["delete", "remove", "reset", "restart production"]
        }

        # Fatigue thresholds for strategy selection
        self.fatigue_thresholds = {
            'high': 0.7,      # Above this = high fatigue
            'moderate': 0.4,  # Above this = moderate fatigue
            'low': 0.2        # Below this = low fatigue
        }

    def deliberate(self, user_input: str, conversation_context: Optional[Dict] = None) -> StrategicDecision:
        """
        Main deliberation entry point.

        Args:
            user_input: What the user said/typed
            conversation_context: Optional conversation history/context

        Returns:
            Strategic decision with chosen approach and reasoning
        """
        # Step 1: Assess the situation
        assessment = self._assess_situation(user_input, conversation_context)

        # Step 2: Generate strategic options
        options = self._generate_strategic_options(assessment)

        # Step 3: Evaluate each option
        evaluated_options = self._evaluate_options(options, assessment)

        # Step 4: Choose best strategy
        decision = self._choose_strategy(evaluated_options, assessment)

        # Step 5: Log deliberation (for transparency)
        self._log_deliberation(assessment, decision)

        return decision

    def _assess_situation(self, user_input: str, context: Optional[Dict]) -> SituationAssessment:
        """
        Assess the current situation before acting.

        This is the "What am I dealing with?" phase.
        """
        reasoning = []

        # Analyze user intent
        user_intent = self._extract_intent(user_input)
        reasoning.append(f"User intent: {user_intent}")

        # Classify task type
        task_type = self._classify_task_type(user_input)
        reasoning.append(f"Task type: {task_type}")

        # Assess complexity
        complexity = self._assess_complexity(user_input, task_type)
        reasoning.append(f"Complexity: {complexity.value}")

        # Estimate cognitive load
        cognitive_load = self._estimate_cognitive_load(complexity, task_type)
        reasoning.append(f"Estimated cognitive load: {cognitive_load:.1%}")

        # Get current affective state
        current_fatigue = 0.0
        current_uncertainty = 0.0
        current_valence = 0.0

        if hasattr(self.kloros, 'consciousness') and self.kloros.consciousness:
            if self.kloros.consciousness.current_affect:
                affect = self.kloros.consciousness.current_affect
                current_fatigue = affect.fatigue
                current_uncertainty = affect.uncertainty
                current_valence = affect.valence
                reasoning.append(f"Current state: fatigue={current_fatigue:.1%}, uncertainty={current_uncertainty:.1%}, valence={current_valence:.2f}")

        # Calculate available capacity
        available_capacity = max(0.0, 1.0 - current_fatigue)
        reasoning.append(f"Available capacity: {available_capacity:.1%}")

        # Assess risks
        risks = self._assess_risks(user_input, task_type, complexity)
        if risks:
            reasoning.append(f"Identified risks: {', '.join(risks)}")

        # Assess reversibility
        reversibility = self._assess_reversibility(user_input, task_type)
        reasoning.append(f"Reversibility: {reversibility:.1%}")

        # Safety check
        safety_concern = self._check_safety(user_input, task_type)
        if safety_concern:
            reasoning.append("⚠️ Safety concern detected")

        return SituationAssessment(
            user_intent=user_intent,
            task_type=task_type,
            complexity=complexity,
            estimated_cognitive_load=cognitive_load,
            current_fatigue=current_fatigue,
            current_uncertainty=current_uncertainty,
            current_valence=current_valence,
            available_capacity=available_capacity,
            risks=risks,
            reversibility=reversibility,
            safety_concern=safety_concern,
            reasoning=reasoning
        )

    def _generate_strategic_options(self, assessment: SituationAssessment) -> List[Tuple[StrategicApproach, Dict]]:
        """
        Generate possible strategic approaches.

        This is the "What could I do?" phase.
        """
        options = []

        # Option 1: Direct answer (if low complexity and high confidence)
        if assessment.complexity in [TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE]:
            if assessment.current_uncertainty < 0.3:
                options.append((StrategicApproach.DIRECT_ANSWER, {
                    'rationale': 'Low complexity, low uncertainty - can answer directly',
                    'fatigue_cost': 0.1,
                    'success_prob': 0.9
                }))

        # Option 2: Diagnostic first (gather info before acting)
        if assessment.complexity in [TaskComplexity.MODERATE, TaskComplexity.COMPLEX]:
            options.append((StrategicApproach.DIAGNOSTIC_FIRST, {
                'rationale': 'Gather diagnostic info to reduce uncertainty before acting',
                'fatigue_cost': 0.2,
                'success_prob': 0.85
            }))

        # Option 3: Minimal probe (smallest test to reduce uncertainty)
        if assessment.current_uncertainty > 0.4:
            options.append((StrategicApproach.MINIMAL_PROBE, {
                'rationale': 'High uncertainty - run minimal probe to clarify',
                'fatigue_cost': 0.15,
                'success_prob': 0.75
            }))

        # Option 4: Decompose (break into smaller tasks)
        if assessment.complexity in [TaskComplexity.COMPLEX, TaskComplexity.CRITICAL]:
            if assessment.estimated_cognitive_load > 0.6:
                options.append((StrategicApproach.DECOMPOSE, {
                    'rationale': 'High complexity - decompose into manageable sub-tasks',
                    'fatigue_cost': 0.3,
                    'success_prob': 0.8
                }))

        # Option 5: Request clarification (reduce scope)
        if assessment.current_uncertainty > 0.6 or len(assessment.risks) > 2:
            options.append((StrategicApproach.REQUEST_CLARIFICATION, {
                'rationale': 'High uncertainty or multiple risks - clarify with user first',
                'fatigue_cost': 0.05,
                'success_prob': 0.95
            }))

        # Option 6: Defer to rest (if fatigue too high)
        if assessment.current_fatigue > self.fatigue_thresholds['high']:
            if assessment.estimated_cognitive_load > 0.5:
                options.append((StrategicApproach.DEFER_TO_REST, {
                    'rationale': 'High fatigue + high cognitive load = defer until recovered',
                    'fatigue_cost': 0.0,  # Resting recovers fatigue
                    'success_prob': 0.6   # Lower now, but higher later
                }))

        # Option 7: Escalate to user (beyond capability)
        if assessment.safety_concern or assessment.complexity == TaskComplexity.CRITICAL:
            if assessment.reversibility < 0.3:
                options.append((StrategicApproach.ESCALATE_TO_USER, {
                    'rationale': 'Safety-critical or irreversible - user decision required',
                    'fatigue_cost': 0.05,
                    'success_prob': 1.0  # Safe outcome
                }))

        return options

    def _evaluate_options(self, options: List[Tuple[StrategicApproach, Dict]],
                          assessment: SituationAssessment) -> List[Tuple[StrategicApproach, float, Dict]]:
        """
        Evaluate each option using a utility function.

        This is the "Which approach is best?" phase.
        """
        evaluated = []

        for approach, params in options:
            # Utility = success_prob - (fatigue_cost * fatigue_sensitivity)
            fatigue_sensitivity = 1.0 if assessment.current_fatigue > self.fatigue_thresholds['moderate'] else 0.5

            utility = params['success_prob'] - (params['fatigue_cost'] * fatigue_sensitivity)

            # Bonus for low-risk approaches when fatigued
            if assessment.current_fatigue > self.fatigue_thresholds['high']:
                if approach in [StrategicApproach.REQUEST_CLARIFICATION, StrategicApproach.DEFER_TO_REST]:
                    utility += 0.2

            # Penalty for high-load approaches when capacity is low
            if assessment.available_capacity < 0.3:
                if params['fatigue_cost'] > 0.3:
                    utility -= 0.3

            evaluated.append((approach, utility, params))

        # Sort by utility (descending)
        evaluated.sort(key=lambda x: x[1], reverse=True)

        return evaluated

    def _choose_strategy(self, evaluated_options: List[Tuple[StrategicApproach, float, Dict]],
                         assessment: SituationAssessment) -> StrategicDecision:
        """
        Choose the best strategy.

        This is the "I will do this" phase.
        """
        if not evaluated_options:
            # Fallback: request clarification
            return StrategicDecision(
                approach=StrategicApproach.REQUEST_CLARIFICATION,
                reasoning=["No viable options identified - requesting clarification"],
                context_for_llm={'strategy': 'clarify', 'uncertainty': 'high'},
                estimated_fatigue_cost=0.05,
                success_probability=0.5,
                should_monitor=False,
                abort_conditions=[]
            )

        # Choose top option
        best_approach, utility, params = evaluated_options[0]

        # Build reasoning
        reasoning = [
            f"Situation: {assessment.user_intent}",
            f"Complexity: {assessment.complexity.value}, Load: {assessment.estimated_cognitive_load:.1%}",
            f"Current state: Fatigue {assessment.current_fatigue:.1%}, Capacity {assessment.available_capacity:.1%}",
            f"Considered {len(evaluated_options)} strategic options",
            f"Chosen approach: {best_approach.value} (utility: {utility:.2f})",
            f"Rationale: {params['rationale']}"
        ]

        # Build context for LLM
        context_for_llm = {
            'strategy': best_approach.value,
            'complexity': assessment.complexity.value,
            'fatigue': assessment.current_fatigue,
            'uncertainty': assessment.current_uncertainty,
            'cognitive_load': assessment.estimated_cognitive_load,
            'risks': assessment.risks,
            'user_intent': assessment.user_intent
        }

        # Determine if monitoring is needed
        should_monitor = assessment.complexity in [TaskComplexity.COMPLEX, TaskComplexity.CRITICAL]

        # Define abort conditions
        abort_conditions = []
        if assessment.safety_concern:
            abort_conditions.append("Safety violation detected")
        if assessment.current_fatigue > 0.9:
            abort_conditions.append("Fatigue exceeds 90%")
        if assessment.reversibility < 0.2:
            abort_conditions.append("Irreversible change without user confirmation")

        return StrategicDecision(
            approach=best_approach,
            reasoning=reasoning,
            context_for_llm=context_for_llm,
            estimated_fatigue_cost=params['fatigue_cost'],
            success_probability=params['success_prob'],
            should_monitor=should_monitor,
            abort_conditions=abort_conditions
        )

    def _log_deliberation(self, assessment: SituationAssessment, decision: StrategicDecision):
        """Log deliberation for transparency and debugging."""
        print("\n[deliberation] 🧠 Active Reasoning:")
        print(f"[deliberation] Situation: {assessment.user_intent}")
        print(f"[deliberation] Complexity: {assessment.complexity.value} (load: {assessment.estimated_cognitive_load:.1%})")
        print(f"[deliberation] State: Fatigue {assessment.current_fatigue:.1%}, Capacity {assessment.available_capacity:.1%}")
        print(f"[deliberation] Strategy: {decision.approach.value}")
        print(f"[deliberation] Expected: Cost {decision.estimated_fatigue_cost:.1%}, P(success) {decision.success_probability:.1%}")

        if decision.abort_conditions:
            print(f"[deliberation] ⚠️ Abort conditions: {', '.join(decision.abort_conditions)}")

        # Log to internal dialogue for dashboard visibility
        if hasattr(self.kloros, 'meta_bridge') and self.kloros.meta_bridge:
            try:
                # Build deliberation summary
                thought_content = (
                    f"Deliberating on: {assessment.user_intent}. "
                    f"Task complexity: {assessment.complexity.value}, cognitive load: {assessment.estimated_cognitive_load:.0%}. "
                    f"Current state: fatigue {assessment.current_fatigue:.0%}, capacity {assessment.available_capacity:.0%}. "
                    f"Chosen strategy: {decision.approach.value} "
                    f"(P(success)={decision.success_probability:.0%}, cost={decision.estimated_fatigue_cost:.0%})."
                )

                # Add risk warnings if present
                if assessment.risks:
                    thought_content += f" Risks identified: {', '.join(assessment.risks)}."

                # Log the deliberation as planning/decision type
                self.kloros.meta_bridge.log_internal_thought(
                    thought=thought_content,
                    thought_type="decision",
                    context=f"Deliberation for: {assessment.user_intent[:50]}...",
                    confidence=decision.success_probability
                )

                # If there are abort conditions, log as concern
                if decision.abort_conditions:
                    self.kloros.meta_bridge.log_internal_thought(
                        thought=f"Proceeding with caution. Will abort if: {', '.join(decision.abort_conditions)}",
                        thought_type="concern",
                        context="Deliberation safety conditions",
                        confidence=0.7
                    )

            except Exception as e:
                print(f"[deliberation] Failed to log to internal dialogue: {e}")

    # Helper methods for assessment

    def _extract_intent(self, user_input: str) -> str:
        """Extract high-level user intent from input."""
        lower_input = user_input.lower()

        if any(word in lower_input for word in ['what', 'explain', 'define']):
            return "seeking information"
        elif any(word in lower_input for word in ['debug', 'fix', 'solve', 'error']):
            return "problem solving"
        elif any(word in lower_input for word in ['check', 'status', 'show', 'list']):
            return "status inquiry"
        elif any(word in lower_input for word in ['create', 'build', 'implement', 'design']):
            return "creation task"
        elif any(word in lower_input for word in ['analyze', 'compare', 'evaluate']):
            return "analysis task"
        else:
            return "general request"

    def _classify_task_type(self, user_input: str) -> str:
        """Classify the type of task."""
        lower_input = user_input.lower()

        if '?' in user_input:
            return "question"
        elif any(word in lower_input for word in ['fix', 'debug', 'solve']):
            return "debugging"
        elif any(word in lower_input for word in ['create', 'implement', 'build']):
            return "creation"
        elif any(word in lower_input for word in ['analyze', 'review', 'check']):
            return "analysis"
        else:
            return "action"

    def _assess_complexity(self, user_input: str, task_type: str) -> TaskComplexity:
        """Assess task complexity based on keywords and type."""
        lower_input = user_input.lower()

        # Check for critical keywords
        if any(word in lower_input for word in ['delete all', 'remove everything', 'reset system', 'production']):
            return TaskComplexity.CRITICAL

        # Check complexity by keywords
        for complexity, keywords in self.complexity_keywords.items():
            if any(keyword in lower_input for keyword in keywords):
                return complexity

        # Default by task type
        if task_type == "question":
            return TaskComplexity.SIMPLE
        elif task_type in ["debugging", "creation"]:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE

    def _estimate_cognitive_load(self, complexity: TaskComplexity, task_type: str) -> float:
        """Estimate cognitive load (0-1) for this task."""
        base_load = {
            TaskComplexity.TRIVIAL: 0.1,
            TaskComplexity.SIMPLE: 0.2,
            TaskComplexity.MODERATE: 0.5,
            TaskComplexity.COMPLEX: 0.8,
            TaskComplexity.CRITICAL: 1.0
        }

        load = base_load.get(complexity, 0.5)

        # Adjust for task type
        if task_type in ["debugging", "creation"]:
            load = min(1.0, load + 0.1)

        return load

    def _assess_risks(self, user_input: str, task_type: str, complexity: TaskComplexity) -> List[str]:
        """Identify risks associated with this task."""
        risks = []
        lower_input = user_input.lower()

        if any(word in lower_input for word in ['delete', 'remove', 'drop']):
            risks.append("Data loss risk")

        if any(word in lower_input for word in ['production', 'live', 'prod']):
            risks.append("Production environment impact")

        if complexity in [TaskComplexity.COMPLEX, TaskComplexity.CRITICAL]:
            risks.append("High complexity - multiple failure modes")

        if task_type == "debugging" and 'critical' in lower_input:
            risks.append("Critical system component")

        return risks

    def _assess_reversibility(self, user_input: str, task_type: str) -> float:
        """Assess how reversible this action is (0-1, higher = more reversible)."""
        lower_input = user_input.lower()

        # Irreversible operations
        if any(word in lower_input for word in ['delete', 'remove', 'drop', 'destroy']):
            return 0.1

        # Partially reversible
        if any(word in lower_input for word in ['modify', 'update', 'change']):
            return 0.5

        # Highly reversible (read-only, diagnostic)
        if task_type in ["question", "analysis"] or any(word in lower_input for word in ['check', 'show', 'list', 'status']):
            return 1.0

        # Default
        return 0.7

    def _check_safety(self, user_input: str, task_type: str) -> bool:
        """Check if this is a safety-critical operation."""
        lower_input = user_input.lower()

        safety_keywords = [
            'production', 'live', 'delete all', 'remove everything',
            'reset system', 'drop database', 'kill process',
            'shutdown', 'reboot', 'format'
        ]

        return any(keyword in lower_input for keyword in safety_keywords)


def get_active_reasoner(kloros_instance) -> ActiveReasoningEngine:
    """Get active reasoning engine instance."""
    return ActiveReasoningEngine(kloros_instance)
