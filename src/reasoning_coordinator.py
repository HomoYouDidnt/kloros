#!/usr/bin/env python3
"""
Reasoning Coordinator - System-wide access to brainmods reasoning.

Making KLoROS's name real: Knowledge & Logic-based Reasoning Operating System

This module embeds reasoning (ToT, Debate, VOI) into EVERY decision-making system:
    - Introspection & Self-Reflection
    - Curiosity & Investigation
    - Improvement Proposals
    - Alert Prioritization
    - Auto-Approval Safety
    - D-REAM Experiments
    - Tool Synthesis
    - Component Analysis

Architecture: Instead of hardcoded heuristics, REASON about decisions.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ReasoningMode(Enum):
    """Reasoning depth for different decision types."""
    LIGHT = "light"        # Quick: 2-3 alternatives
    STANDARD = "standard"  # Normal: 4-5 alternatives
    DEEP = "deep"          # Complex: 6+ alternatives + debate
    CRITICAL = "critical"  # Safety: full ToT + multi-round debate


@dataclass
class ReasoningResult:
    """Result from reasoning about a decision."""
    decision: str                      # Final recommendation
    alternatives_explored: List[Dict]  # All options considered
    best_alternative: Dict             # Top choice
    confidence: float                  # Confidence (0-1)
    voi_score: float                   # Value of Information
    reasoning_trace: List[str]         # Step-by-step logic
    debate_verdict: Optional[Dict]     # Debate results
    recommended_action: str            # What to do


class ReasoningCoordinator:
    """
    Central reasoning coordinator using brainmods.

    Simple API for any subsystem:
        - reason_about_alternatives(): Pick best from N options
        - debate_decision(): Critique a proposed decision
        - calculate_voi(): Estimate action value
        - explore_solutions(): Find solution paths via ToT
    """

    def __init__(self, llm_backend=None):
        self.llm = llm_backend

        try:
            from src.brainmods import (
                TreeOfThought,
                DebateRunner,
                VOIEstimator,
                ModeRouter
            )

            self.TreeOfThought = TreeOfThought
            self.DebateRunner = DebateRunner
            self.voi_estimator = VOIEstimator()
            self.mode_router = ModeRouter()
            self.enabled = True

            logger.info("[reasoning_coordinator] Brainmods loaded - reasoning enabled system-wide")

        except Exception as e:
            logger.error(f"[reasoning_coordinator] Brainmods unavailable: {e}")
            self.enabled = False

    def reason_about_alternatives(
        self,
        context: str,
        alternatives: List[Dict[str, Any]],
        mode: ReasoningMode = ReasoningMode.STANDARD,
        criteria: Optional[List[str]] = None
    ) -> ReasoningResult:
        """
        Reason about alternatives and pick best.

        Args:
            context: What are we deciding?
            alternatives: List with 'name', 'value', 'cost', 'risk'
            mode: Reasoning depth
            criteria: Optional evaluation criteria

        Returns:
            ReasoningResult with decision + trace
        """
        if not self.enabled:
            return self._fallback_reasoning(context, alternatives)

        trace = [f"Reasoning: {context}", f"Mode: {mode.value}, Options: {len(alternatives)}"]

        try:
            # Step 1: Calculate VOI for each
            trace.append("Step 1: Calculating VOI")
            for alt in alternatives:
                decision = {
                    'expected_gain': alt.get('value', 0.5),
                    'expected_cost': alt.get('cost', 0.3),
                    'expected_risk': alt.get('risk', 0.1)
                }
                alt['voi'] = self.voi_estimator.estimate(decision, {'context': context})
                trace.append(f"  {alt.get('name')}: VOI={alt['voi']:.3f}")

            # Step 2: ToT exploration if DEEP/CRITICAL
            if mode in [ReasoningMode.DEEP, ReasoningMode.CRITICAL]:
                trace.append("Step 2: Tree of Thought exploration")

                def expand_decision(state):
                    if isinstance(state, str):
                        return [(alt['name'], alt) for alt in alternatives]
                    return [('implement', f"Implement {state.get('name')}")]

                def score_decision(state):
                    return state.get('voi', 0.5) if isinstance(state, dict) else 0.5

                tot = self.TreeOfThought(
                    expand_fn=expand_decision,
                    score_fn=score_decision,
                    beam_width=min(len(alternatives), 4),
                    max_depth=2,
                    strategy="beam"
                )

                tot_result = tot.search(context)
                trace.append(f"  ToT score: {tot_result['score']:.3f}")

            # Step 3: Rank by VOI
            alternatives.sort(key=lambda x: x.get('voi', 0), reverse=True)
            best = alternatives[0]
            trace.append(f"Step 3: Best option: {best.get('name')} (VOI: {best.get('voi'):.3f})")

            # Step 4: Debate if CRITICAL
            debate_result = None
            if mode == ReasoningMode.CRITICAL and len(alternatives) > 1:
                trace.append("Step 4: Multi-agent debate")
                debate_result = self._debate_alternatives(context, alternatives[:2])
                trace.append(f"  Verdict: {debate_result.get('verdict', {}).get('verdict')}")

            # Step 5: Calculate confidence
            confidence = self._calculate_confidence(alternatives, debate_result)
            trace.append(f"Step 5: Confidence: {confidence:.3f}")

            # Step 6: Recommend action
            if confidence > 0.75:
                action = f"Proceed with {best.get('name')} (high confidence)"
            elif confidence > 0.5:
                action = f"Proceed with {best.get('name')}, monitor closely"
            else:
                action = f"Gather more data (low confidence: {confidence:.3f})"

            return ReasoningResult(
                decision=best.get('name', 'unknown'),
                alternatives_explored=alternatives,
                best_alternative=best,
                confidence=confidence,
                voi_score=best.get('voi', 0),
                reasoning_trace=trace,
                debate_verdict=debate_result,
                recommended_action=action
            )

        except Exception as e:
            logger.error(f"[reasoning_coordinator] Error: {e}")
            return self._fallback_reasoning(context, alternatives)

    def debate_decision(
        self,
        context: str,
        proposed_decision: Dict[str, Any],
        rounds: int = 1
    ) -> Dict[str, Any]:
        """Multi-agent debate to critique a decision."""
        if not self.enabled:
            return {'verdict': {'verdict': 'uncertain'}, 'confidence': 0.5}

        try:
            def proposer(prompt, ctx):
                return f"Propose: {proposed_decision.get('action')}. {proposed_decision.get('rationale')}"

            def critic(prompt, proposal, ctx):
                risks = proposed_decision.get('risks', [])
                return f"Concerns: {', '.join(risks) if risks else 'None identified'}"

            def judge(prompt, proposal, critique, ctx):
                conf = proposed_decision.get('confidence', 0.5)
                risk = proposed_decision.get('risk', 0.1)

                if conf > 0.7 and risk < 0.3:
                    return {'verdict': 'approved', 'confidence': conf, 'requires_revision': False}
                elif conf > 0.5:
                    return {'verdict': 'conditional', 'confidence': conf, 'requires_revision': False}
                else:
                    return {'verdict': 'needs_revision', 'confidence': conf, 'requires_revision': True}

            debate = self.DebateRunner(proposer, critic, judge, rounds)
            return debate.run(context, {'decision': proposed_decision})

        except Exception as e:
            logger.error(f"[reasoning_coordinator] Debate failed: {e}")
            return {'verdict': {'verdict': 'error'}, 'error': str(e)}

    def explore_solutions(self, problem: str, max_depth: int = 3) -> Dict[str, Any]:
        """Use ToT to explore solution space."""
        if not self.enabled:
            return {'solution': 'Standard fix', 'confidence': 0.5}

        try:
            def expand_solution(state):
                if isinstance(state, str):
                    return [
                        ('analyze', 'Analyze root cause'),
                        ('isolate', 'Isolate failure'),
                        ('patch', 'Apply patch'),
                        ('refactor', 'Refactor component')
                    ]
                return [('implement', f'Implement: {state}')]

            def score_solution(state):
                if isinstance(state, str):
                    keywords = ['implement', 'fix', 'patch']
                    return sum(1 for kw in keywords if kw in state.lower()) / len(keywords)
                return 0.5

            tot = self.TreeOfThought(expand_solution, score_solution, 4, max_depth, "beam")
            result = tot.search(problem)

            return {
                'solution': result['state'],
                'path': result['path'],
                'score': result['score'],
                'confidence': result['score']
            }

        except Exception as e:
            logger.error(f"[reasoning_coordinator] Solution exploration failed: {e}")
            return {'solution': 'Standard investigation', 'error': str(e)}

    def calculate_voi(self, action: Dict[str, Any], context: Optional[Dict] = None) -> float:
        """Calculate Value of Information."""
        if not self.enabled:
            return action.get('value', 0.5) - action.get('cost', 0.3)

        decision = {
            'expected_gain': action.get('value', 0.5),
            'expected_cost': action.get('cost', 0.3),
            'expected_risk': action.get('risk', 0.1)
        }
        return self.voi_estimator.estimate(decision, context or {})

    def route_reasoning_mode(self, task_spec: Dict[str, Any]) -> str:
        """Determine reasoning mode for task."""
        if not self.enabled:
            return 'standard'
        return self.mode_router.route(task_spec)

    def _debate_alternatives(self, context: str, alts: List[Dict]) -> Dict:
        """Debate top 2 alternatives."""
        try:
            def proposer(p, c): return f"Best: {alts[0].get('name')}"
            def critic(p, prop, c): return f"Consider: {alts[1].get('name')}" if len(alts) > 1 else "Unopposed"
            def judge(p, prop, crit, c):
                gap = alts[0].get('voi', 0) - (alts[1].get('voi', 0) if len(alts) > 1 else 0)
                return {'verdict': 'clear' if gap > 0.2 else 'marginal', 'confidence': 0.9 if gap > 0.2 else 0.7}

            debate = self.DebateRunner(proposer, critic, judge, 1)
            return debate.run(context, {})
        except:
            return {'verdict': {'verdict': 'error'}}

    def _calculate_confidence(self, alts: List[Dict], debate: Optional[Dict]) -> float:
        """Calculate decision confidence."""
        conf = 0.5
        if alts and alts[0].get('voi', 0) > 0.6:
            conf += 0.2
        if len(alts) > 1:
            gap = alts[0].get('voi', 0) - alts[1].get('voi', 0)
            conf += 0.2 if gap > 0.2 else (-0.1 if gap < 0.05 else 0)
        if debate:
            conf = (conf + debate.get('verdict', {}).get('confidence', 0.5)) / 2
        return max(0.0, min(1.0, conf))

    def _fallback_reasoning(self, context: str, alts: List[Dict], trace=None) -> ReasoningResult:
        """Fallback when brainmods unavailable."""
        trace = trace or [f"Fallback: {context}"]
        for alt in alts:
            alt['voi'] = alt.get('value', 0.5) - alt.get('cost', 0.3)
        alts.sort(key=lambda x: x.get('voi', 0), reverse=True)
        best = alts[0] if alts else {'name': 'none', 'voi': 0}

        return ReasoningResult(
            decision=best.get('name'),
            alternatives_explored=alts,
            best_alternative=best,
            confidence=0.5,
            voi_score=best.get('voi', 0),
            reasoning_trace=trace,
            debate_verdict=None,
            recommended_action=f"Proceed with {best.get('name')} (heuristic)"
        )


# Singleton
_coordinator = None

def get_reasoning_coordinator(llm_backend=None):
    """Get singleton."""
    global _coordinator
    if _coordinator is None:
        _coordinator = ReasoningCoordinator(llm_backend)
    return _coordinator
