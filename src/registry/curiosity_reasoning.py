#!/usr/bin/env python3
"""
Curiosity Reasoning - Wires brainmods into curiosity for intelligent question generation.

This module bridges CuriosityCore with brainmods (ToT, Debate, VOI, etc.) to:
- Generate better hypotheses using Tree of Thought
- Critique and refine questions using multi-agent debate
- Prioritize questions using Value of Information
- Pre-explore solution space before full investigation
- Route questions to appropriate reasoning strategies

Architectural Enhancement:
    Curiosity shouldn't just generate questions blindly. By applying
    advanced reasoning to the questions themselves, we get:
    - More focused hypotheses
    - Better prioritization
    - Pre-validated assumptions
    - Faster convergence to solutions
"""

import logging
from typing import Dict, Any, Optional, List, Tuple, Iterator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReasonedQuestion:
    """A curiosity question enriched with brainmod reasoning."""
    original_question: Any  # CuriosityQuestion
    hypotheses: List[Dict[str, Any]]  # Multiple competing hypotheses from ToT
    debate_verdict: Optional[Dict[str, Any]]  # Debate result on best hypothesis
    voi_score: float  # Value of Information score
    reasoning_mode: str  # Recommended reasoning mode (light/standard/thunderdome)
    pre_investigation_insights: List[str]  # Insights before full investigation
    confidence: float  # Confidence in hypothesis (0-1)
    follow_up_questions: List[Dict[str, Any]] = field(default_factory=list)  # Generated follow-ups for evidence gaps


class CuriosityReasoning:
    """
    Applies brainmods to curiosity questions for intelligent reasoning.

    Purpose:
        Make curiosity active and intelligent rather than reactive.
        Use existing reasoning infrastructure to think deeply about
        questions before committing resources to investigation.

    Flow:
        1. Receive curiosity question
        2. Use ToT to explore multiple hypotheses
        3. Use Debate to critique and refine top hypothesis
        4. Use VOI to calculate true investigation value
        5. Use ModeRouter to recommend reasoning strategy
        6. Return enriched question with pre-investigation insights
    """

    def __init__(self, llm_backend=None):
        """
        Initialize curiosity reasoning layer.

        Args:
            llm_backend: LLM backend for reasoning (optional, uses heuristics if None)
        """
        self.llm = llm_backend

        # Import brainmods
        try:
            from src.brainmods import (
                TreeOfThought,
                DebateRunner,
                VOIEstimator,
                ModeRouter
            )

            self.tot = TreeOfThought
            self.debate_runner = DebateRunner
            self.voi_estimator = VOIEstimator()
            self.mode_router = ModeRouter()
            self.enabled = True

            logger.info("[curiosity_reasoning] Brainmods successfully loaded")

        except Exception as e:
            logger.error(f"[curiosity_reasoning] Failed to load brainmods: {e}")
            self.enabled = False

    def reason_about_question(self, question: Any) -> ReasonedQuestion:
        """
        Apply brainmods reasoning to a curiosity question.

        Args:
            question: CuriosityQuestion object

        Returns:
            ReasonedQuestion with reasoning results
        """
        if not self.enabled:
            # Fallback: return question with minimal reasoning
            return self._minimal_reasoning(question)

        try:
            # 1. Generate multiple hypotheses using Tree of Thought
            hypotheses = self._explore_hypotheses(question)

            # 2. Debate top hypotheses to find best one
            debate_result = self._debate_hypotheses(question, hypotheses[:3])

            # 3. Calculate Value of Information
            voi_score = self._calculate_voi(question, hypotheses, debate_result)

            # 4. Route to appropriate reasoning mode
            reasoning_mode = self._route_reasoning_mode(question)

            # 5. Generate pre-investigation insights
            insights = self._generate_insights(question, hypotheses, debate_result)

            # 6. Estimate confidence
            confidence = self._estimate_confidence(hypotheses, debate_result)

            # 7. Generate follow-up questions if evidence gaps detected
            follow_ups = self._generate_follow_up_questions(question, hypotheses, debate_result)

            return ReasonedQuestion(
                original_question=question,
                hypotheses=hypotheses,
                debate_verdict=debate_result,
                voi_score=voi_score,
                reasoning_mode=reasoning_mode,
                pre_investigation_insights=insights,
                confidence=confidence,
                follow_up_questions=follow_ups
            )

        except Exception as e:
            logger.error(f"[curiosity_reasoning] Reasoning failed: {e}")
            return self._minimal_reasoning(question)

    def _explore_hypotheses(self, question: Any) -> List[Dict[str, Any]]:
        """
        Use Tree of Thought to explore multiple hypotheses.

        Args:
            question: CuriosityQuestion

        Returns:
            List of hypothesis dicts with scores
        """
        try:
            # Define expansion function: generate alternative hypotheses
            def expand_hypothesis(state):
                if isinstance(state, str):
                    # Initial state: generate root hypotheses from question
                    q_text = question.question if hasattr(question, 'question') else str(question)
                    hypothesis = question.hypothesis if hasattr(question, 'hypothesis') else "UNKNOWN"

                    # Generate alternative hypotheses
                    alternatives = []

                    # Root cause hypotheses
                    if "failure" in q_text.lower() or "error" in q_text.lower():
                        alternatives.extend([
                            ("root_cause", "Configuration issue causing failures"),
                            ("dependency", "Missing or outdated dependency"),
                            ("resource", "Resource exhaustion (memory/cpu/disk)"),
                            ("logic", "Logic error in implementation")
                        ])

                    # Performance hypotheses
                    elif "slow" in q_text.lower() or "performance" in q_text.lower():
                        alternatives.extend([
                            ("bottleneck", "Bottleneck in hot path"),
                            ("caching", "Missing or invalid cache"),
                            ("algorithm", "Suboptimal algorithm choice"),
                            ("io", "I/O bound operation")
                        ])

                    # Healing hypotheses (from chaos lab)
                    elif "healing" in q_text.lower() or "self-healing" in q_text.lower():
                        alternatives.extend([
                            ("detection", "Failure detection not working"),
                            ("recovery", "Recovery mechanism missing or broken"),
                            ("timeout", "Timeout too short for recovery"),
                            ("state", "State not properly restored after recovery")
                        ])

                    # Default: system analysis
                    else:
                        alternatives.extend([
                            ("investigate", "Need more data to determine cause"),
                            ("monitor", "Should monitor and gather patterns"),
                            ("experiment", "Run controlled experiment")
                        ])

                    return alternatives if alternatives else [("unknown", "Requires investigation")]

                else:
                    # Expand from current hypothesis
                    return [
                        ("verify", f"Verify {state} hypothesis with evidence"),
                        ("test", f"Test {state} hypothesis experimentally"),
                        ("implement", f"Implement fix for {state}")
                    ]

            # Define scoring function
            def score_hypothesis(state):
                """Score hypothesis based on keywords and structure."""
                if isinstance(state, str):
                    score = 0.5  # Baseline

                    # Prefer specific over generic
                    if any(kw in state.lower() for kw in ["missing", "broken", "exhausted", "bottleneck"]):
                        score += 0.3

                    # Prefer actionable hypotheses
                    if any(kw in state.lower() for kw in ["fix", "implement", "resolve", "restore"]):
                        score += 0.2

                    return min(score, 1.0)

                return 0.5

            # Run Tree of Thought search
            tot = self.tot(
                expand_fn=expand_hypothesis,
                score_fn=score_hypothesis,
                beam_width=4,
                max_depth=2,
                strategy="beam"
            )

            result = tot.search(question.hypothesis if hasattr(question, 'hypothesis') else "unknown")

            # Convert result to hypothesis list
            hypotheses = []

            # Add path hypotheses
            for i, step in enumerate(result['path']):
                hypotheses.append({
                    'rank': i + 1,
                    'hypothesis': step,
                    'score': result['score'],
                    'source': 'tot_path'
                })

            # Add final state
            hypotheses.append({
                'rank': len(hypotheses) + 1,
                'hypothesis': str(result['state']),
                'score': result['score'],
                'source': 'tot_final'
            })

            return hypotheses[:5]  # Top 5

        except Exception as e:
            logger.error(f"[curiosity_reasoning] Hypothesis exploration failed: {e}")
            # Fallback: use original hypothesis
            return [{
                'rank': 1,
                'hypothesis': question.hypothesis if hasattr(question, 'hypothesis') else 'UNKNOWN',
                'score': 0.5,
                'source': 'fallback'
            }]

    def _debate_hypotheses(
        self,
        question: Any,
        hypotheses: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Use multi-agent debate to critique and refine hypotheses.

        Args:
            question: CuriosityQuestion
            hypotheses: Top hypotheses from ToT

        Returns:
            Debate verdict dict
        """
        if not hypotheses:
            return None

        try:
            # Simple debate using heuristic agents
            top_hypothesis = hypotheses[0]['hypothesis']

            # Proposer: defends hypothesis
            def proposer(prompt, context):
                return f"Hypothesis: {top_hypothesis}. This explains the evidence because {context.get('evidence', 'it fits the pattern')}."

            # Critic: challenges hypothesis
            def critic(prompt, proposal, context):
                return f"Alternative explanation: Could also be caused by related factors not yet considered. Need to verify assumptions."

            # Judge: evaluates
            def judge(prompt, proposal, critique, context):
                # Simple heuristic judge
                requires_revision = len(hypotheses) > 1  # If multiple hypotheses, need more evidence

                return {
                    'verdict': 'plausible' if not requires_revision else 'needs_verification',
                    'requires_revision': requires_revision,
                    'confidence': 0.7 if not requires_revision else 0.5
                }

            debate = self.debate_runner(
                proposer=proposer,
                critic=critic,
                judge=judge,
                rounds=1
            )

            evidence_str = str(question.evidence) if hasattr(question, 'evidence') else ''

            result = debate.run(
                prompt=question.question if hasattr(question, 'question') else str(question),
                context={'evidence': evidence_str}
            )

            return {
                'verdict': result['verdict'],
                'proposal': result['final_proposal'],
                'confidence': result['verdict'].get('confidence', 0.5),
                'requires_verification': result['verdict'].get('requires_revision', True)
            }

        except Exception as e:
            logger.error(f"[curiosity_reasoning] Debate failed: {e}")
            return None

    def _calculate_voi(
        self,
        question: Any,
        hypotheses: List[Dict[str, Any]],
        debate_result: Optional[Dict[str, Any]]
    ) -> float:
        """
        Calculate Value of Information for investigating this question.

        Args:
            question: CuriosityQuestion
            hypotheses: Generated hypotheses
            debate_result: Debate verdict

        Returns:
            VOI score (0-1, higher is better)
        """
        try:
            # Build decision dict for VOI calculation
            decision = {
                'expected_gain': question.value_estimate if hasattr(question, 'value_estimate') else 0.5,
                'expected_cost': question.cost if hasattr(question, 'cost') else 0.3,
                'expected_risk': 0.1  # Low risk for curiosity investigations
            }

            # Adjust gain based on hypothesis quality
            if hypotheses and len(hypotheses) > 1:
                decision['expected_gain'] *= 1.2  # Bonus for multiple paths

            # Adjust cost based on debate verdict
            if debate_result and debate_result.get('confidence', 0) > 0.7:
                decision['expected_cost'] *= 0.8  # Lower cost if high confidence

            state = {'mode': 'curiosity'}

            voi = self.voi_estimator.estimate(decision, state)

            # Normalize to 0-1 range
            return max(0.0, min(1.0, voi))

        except Exception as e:
            logger.error(f"[curiosity_reasoning] VOI calculation failed: {e}")
            return question.value_estimate if hasattr(question, 'value_estimate') else 0.5

    def _route_reasoning_mode(self, question: Any) -> str:
        """
        Route question to appropriate reasoning mode.

        Args:
            question: CuriosityQuestion

        Returns:
            Mode name ('light', 'standard', 'thunderdome')
        """
        try:
            task_spec = {
                'query': question.question if hasattr(question, 'question') else str(question),
                'tags': []
            }

            # Add tags based on question attributes
            if hasattr(question, 'action_class'):
                action = question.action_class
                if 'fix' in str(action).lower() or 'improve' in str(action).lower():
                    task_spec['tags'].append('complex')

            if hasattr(question, 'value_estimate') and question.value_estimate > 0.8:
                task_spec['tags'].append('complex')  # High value = complex

            return self.mode_router.route(task_spec)

        except Exception as e:
            logger.error(f"[curiosity_reasoning] Mode routing failed: {e}")
            return 'standard'

    def _generate_insights(
        self,
        question: Any,
        hypotheses: List[Dict[str, Any]],
        debate_result: Optional[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate pre-investigation insights from reasoning.

        Args:
            question: CuriosityQuestion
            hypotheses: Generated hypotheses
            debate_result: Debate result

        Returns:
            List of insight strings
        """
        insights = []

        # Insight from hypothesis diversity
        if len(hypotheses) > 2:
            insights.append(f"Multiple competing hypotheses ({len(hypotheses)}) suggest complex root cause")

        # Insight from debate
        if debate_result:
            if debate_result.get('confidence', 0) > 0.7:
                insights.append("High confidence in primary hypothesis from multi-agent debate")
            else:
                insights.append("Debate suggests need for more evidence before conclusions")

        # Insight from question pattern
        q_text = question.question if hasattr(question, 'question') else str(question)
        if "repeatedly" in q_text.lower() or "always" in q_text.lower():
            insights.append("Systematic pattern detected - likely structural issue not random failure")

        # Insight from evidence
        if hasattr(question, 'evidence') and question.evidence:
            evidence_count = len(question.evidence) if isinstance(question.evidence, list) else 1
            if evidence_count > 5:
                insights.append(f"Rich evidence set ({evidence_count} items) enables data-driven investigation")

        return insights

    def _estimate_confidence(
        self,
        hypotheses: List[Dict[str, Any]],
        debate_result: Optional[Dict[str, Any]]
    ) -> float:
        """
        Estimate confidence in reasoning results.

        Args:
            hypotheses: Generated hypotheses
            debate_result: Debate result

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.5  # Baseline

        # Boost if top hypothesis has high score
        if hypotheses and hypotheses[0].get('score', 0) > 0.7:
            confidence += 0.2

        # Boost if debate reached high confidence
        if debate_result and debate_result.get('confidence', 0) > 0.7:
            confidence += 0.2

        # Reduce if too many competing hypotheses
        if len(hypotheses) > 4:
            confidence -= 0.1

        return max(0.0, min(1.0, confidence))

    def _generate_follow_up_questions(
        self,
        question: Any,
        hypotheses: List[Dict[str, Any]],
        debate_result: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate follow-up questions when debate indicates evidence gaps.

        Args:
            question: Original CuriosityQuestion
            hypotheses: Generated hypotheses
            debate_result: Debate verdict

        Returns:
            List of follow-up question dicts
        """
        follow_ups = []

        # Check if debate indicates need for more evidence
        if not debate_result:
            return follow_ups

        requires_verification = debate_result.get('requires_verification', False)
        confidence = debate_result.get('confidence', 1.0)
        verdict = debate_result.get('verdict', 'approved')

        # Generate follow-ups when evidence is insufficient
        if requires_verification or confidence < 0.6 or verdict in ['needs_verification', 'rejected']:
            logger.info(f"[curiosity_reasoning] Evidence gap detected - generating follow-up questions")

            # Extract what evidence is missing from critique
            critique = debate_result.get('critique', '')
            proposal = debate_result.get('proposal', '')

            # Generate targeted follow-ups based on hypothesis type
            q_text = question.question if hasattr(question, 'question') else str(question)
            hypothesis = question.hypothesis if hasattr(question, 'hypothesis') else 'UNKNOWN'

            # Follow-up 1: Request specific metrics/logs
            if 'failure' in q_text.lower() or 'error' in q_text.lower():
                follow_ups.append({
                    'question': f"What are the exact error messages and stack traces for {hypothesis}?",
                    'hypothesis': f"Detailed error logs will reveal root cause of {hypothesis}",
                    'action_class': 'investigate',
                    'parent_question_id': question.id if hasattr(question, 'id') else 'unknown',
                    'evidence_type': 'error_logs',
                    'reason': 'Debate requires more specific error evidence'
                })

            # Follow-up 2: Request timing/correlation data
            if 'performance' in q_text.lower() or 'slow' in q_text.lower():
                follow_ups.append({
                    'question': f"When did performance degradation for {hypothesis} start, and what changed around that time?",
                    'hypothesis': f"Timing correlation will identify trigger for {hypothesis}",
                    'action_class': 'investigate',
                    'parent_question_id': question.id if hasattr(question, 'id') else 'unknown',
                    'evidence_type': 'timing_correlation',
                    'reason': 'Debate requires temporal correlation evidence'
                })

            # Follow-up 3: Request resource metrics
            if 'resource' in hypothesis.lower() or 'memory' in hypothesis.lower() or 'cpu' in hypothesis.lower():
                follow_ups.append({
                    'question': f"What are the current resource utilization metrics related to {hypothesis}?",
                    'hypothesis': f"Resource metrics will validate or refute {hypothesis}",
                    'action_class': 'investigate',
                    'parent_question_id': question.id if hasattr(question, 'id') else 'unknown',
                    'evidence_type': 'resource_metrics',
                    'reason': 'Debate requires quantitative resource evidence'
                })

            # Follow-up 4: Request configuration/dependency verification
            if 'configuration' in hypothesis.lower() or 'dependency' in hypothesis.lower():
                follow_ups.append({
                    'question': f"What is the current configuration and dependency state for {hypothesis}?",
                    'hypothesis': f"Configuration audit will confirm or rule out {hypothesis}",
                    'action_class': 'investigate',
                    'parent_question_id': question.id if hasattr(question, 'id') else 'unknown',
                    'evidence_type': 'configuration_audit',
                    'reason': 'Debate requires configuration verification'
                })

            # Follow-up 5: Request comparative analysis (only if multiple hypotheses)
            if len(hypotheses) > 2:
                follow_ups.append({
                    'question': f"How do alternative explanations compare to {hypothesis} given current evidence?",
                    'hypothesis': f"Comparative analysis will identify most likely explanation",
                    'action_class': 'investigate',
                    'parent_question_id': question.id if hasattr(question, 'id') else 'unknown',
                    'evidence_type': 'comparative_analysis',
                    'reason': 'Multiple hypotheses require differentiation'
                })

            # Fallback: If debate says we need evidence but no specific patterns matched,
            # generate a follow-up question
            if len(follow_ups) == 0:
                if critique:
                    critique_summary = critique[:150] + '...' if len(critique) > 150 else critique
                    question_text = f"What additional evidence would help address: {critique_summary}"
                    reason_text = f"Debate critique: {critique}"
                else:
                    question_text = f"What additional evidence would help verify or refute: {hypothesis}"
                    reason_text = f"Debate requires verification (confidence={confidence:.2f})"

                follow_ups.append({
                    'question': question_text,
                    'hypothesis': f"Additional evidence will resolve uncertainty about {hypothesis}",
                    'action_class': 'investigate',
                    'parent_question_id': question.id if hasattr(question, 'id') else 'unknown',
                    'evidence_type': 'general_evidence',
                    'reason': reason_text
                })

            # Limit to top 3 most relevant follow-ups
            follow_ups = follow_ups[:3]

            if len(follow_ups) > 0:
                logger.info(f"[curiosity_reasoning] Generated {len(follow_ups)} follow-up questions for evidence gaps")

        return follow_ups

    def _minimal_reasoning(self, question: Any) -> ReasonedQuestion:
        """
        Fallback minimal reasoning when brainmods unavailable.

        Args:
            question: CuriosityQuestion

        Returns:
            ReasonedQuestion with minimal reasoning
        """
        return ReasonedQuestion(
            original_question=question,
            hypotheses=[{
                'rank': 1,
                'hypothesis': question.hypothesis if hasattr(question, 'hypothesis') else 'UNKNOWN',
                'score': 0.5,
                'source': 'minimal'
            }],
            debate_verdict=None,
            voi_score=question.value_estimate if hasattr(question, 'value_estimate') else 0.5,
            reasoning_mode='standard',
            pre_investigation_insights=['Brainmods unavailable - using minimal reasoning'],
            confidence=0.4
        )

    def batch_reason(self, questions: List[Any], top_n: int = 10) -> List[ReasonedQuestion]:
        """
        Apply reasoning to batch of questions and re-rank by VOI.

        Args:
            questions: List of CuriosityQuestion objects
            top_n: Return top N questions by VOI

        Returns:
            List of ReasonedQuestion objects sorted by VOI
        """
        reasoned = []

        for question in questions:
            reasoned_q = self.reason_about_question(question)
            reasoned.append(reasoned_q)

        # Sort by VOI score
        reasoned.sort(key=lambda x: x.voi_score, reverse=True)

        return reasoned[:top_n]

    def stream_reason(self, questions: List[Any]) -> Iterator[ReasonedQuestion]:
        """
        Stream reasoned questions one at a time with automatic memory cleanup.

        Yields ReasonedQuestion objects as they complete reasoning, allowing
        caller to process immediately. Memory-efficient: only one question's
        reasoning artifacts in memory at a time.

        Args:
            questions: List of CuriosityQuestion objects to process

        Yields:
            ReasonedQuestion objects in input order (unsorted)
        """
        for question in questions:
            reasoned = self.reason_about_question(question)
            yield reasoned


# Singleton instance
_curiosity_reasoning = None

def get_curiosity_reasoning(llm_backend=None):
    """Get singleton curiosity reasoning instance."""
    global _curiosity_reasoning
    if _curiosity_reasoning is None:
        _curiosity_reasoning = CuriosityReasoning(llm_backend)
    return _curiosity_reasoning
