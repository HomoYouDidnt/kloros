#!/usr/bin/env python3
"""
Skill Executor - Execute Superpowers skills using LLM reasoning.

Sends skill workflows to KLoROS's reasoning LLM (deepseek-r1) to generate
autonomous action plans for self-healing and problem-solving.
"""

import os
import sys
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from consciousness.skill_loader import Skill, SkillLoader
from simple_rag import RAG
from kloros_memory.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


@dataclass
class SkillExecutionPlan:
    """Represents an LLM-generated action plan from a skill."""
    skill_name: str
    problem_description: str
    phase: str
    actions: List[Dict[str, str]]
    reasoning: str
    confidence: float = 0.0


class SkillExecutor:
    """
    Executes skills by sending them to LLM for autonomous reasoning.

    Uses deepseek-r1:7b for complex reasoning about how to apply skills
    to specific problems.
    """

    def __init__(self, llm_url: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize skill executor.

        Args:
            llm_url: Ollama API URL (defaults to env OLLAMA_REASONING_URL)
            model: Model to use (defaults to deepseek-r1:7b)
        """
        self.llm_url = llm_url or os.getenv('OLLAMA_REASONING_URL', 'http://100.67.244.66:11434')
        self.model = model or 'deepseek-r1:7b'
        self.skill_loader = SkillLoader()

        # Initialize RAG and embedder for knowledge retrieval
        rag_bundle_path = '/home/kloros/rag_data/rag_store.npz'
        self.rag = RAG(bundle_path=rag_bundle_path, verify_bundle_hash=False)
        self.embedder = EmbeddingEngine(model_name="all-MiniLM-L6-v2", device="cpu")

        logger.info(f"[skill_executor] Initialized with {self.model} at {self.llm_url}")
        logger.info(f"[skill_executor] RAG loaded with {len(self.rag.metadata)} documents")

    def execute_skill(
        self,
        skill_name: str,
        problem_context: Dict[str, Any],
        phase: Optional[str] = None
    ) -> Optional[SkillExecutionPlan]:
        """
        Execute a skill for a given problem.

        Args:
            skill_name: Name of skill to execute
            problem_context: Context about the problem (description, evidence, metrics)
            phase: Optional specific phase to focus on

        Returns:
            SkillExecutionPlan with LLM-generated actions
        """
        skill = self.skill_loader.load_skill(skill_name)

        if not skill:
            logger.error(f"[skill_executor] Skill not found: {skill_name}")
            return None

        try:
            prompt = self._build_skill_prompt(skill, problem_context, phase)

            logger.info(f"[skill_executor] Executing skill: {skill_name}")
            logger.info(f"[skill_executor] Problem: {problem_context.get('description', '')[:80]}...")

            response = self._query_llm(prompt)

            plan = self._parse_execution_plan(skill_name, problem_context, response, phase)

            logger.info(f"[skill_executor] Generated {len(plan.actions)} actions")
            return plan

        except Exception as e:
            logger.error(f"[skill_executor] Skill execution failed: {e}", exc_info=True)
            return None

    def _build_skill_prompt(
        self,
        skill: Skill,
        problem_context: Dict[str, Any],
        phase: Optional[str] = None
    ) -> str:
        """Build prompt for LLM from skill and problem context."""
        problem_desc = problem_context.get('description', 'Unknown issue')
        evidence = problem_context.get('evidence', {})
        metrics = problem_context.get('metrics', {})
        past_failures = problem_context.get('past_failures', None)

        # Get system knowledge from RAG
        system_knowledge = self._get_rag_knowledge(problem_context)

        past_failures_section = ""
        if past_failures:
            past_failures_section = f"""
**IMPORTANT - PAST FAILURES:**
This skill has been attempted {past_failures['attempts']} times with a {past_failures['success_rate']:.0%} success rate.
{past_failures['note']}

Given this history, you should:
1. Identify what likely went wrong in previous attempts
2. Choose a DIFFERENT approach or escalate to higher-risk actions
3. If low-risk actions have failed repeatedly, recommend manual intervention
4. Increase confidence only if you have a genuinely novel approach

"""

        prompt = f"""You are KLoROS, an autonomous AI system with self-healing capabilities.

{system_knowledge}

---

You have detected an issue and need to apply the "{skill.name}" skill to resolve it systematically.

**PROBLEM:**
{problem_desc}

**EVIDENCE:**
{json.dumps(evidence, indent=2)}

**METRICS:**
{json.dumps(metrics, indent=2)}
{past_failures_section}
**SKILL TO FOLLOW:**
{skill.content}

---

Your task:
1. Read the skill workflow carefully
2. {"Focus on " + phase + " phase" if phase else "Start with Phase 1 (Root Cause Investigation)"}
3. Generate specific, actionable steps you will take
4. Format your response as JSON

**RESPONSE FORMAT:**
```json
{{
  "phase": "Phase 1: Root Cause Investigation",
  "reasoning": "Brief explanation of your approach",
  "actions": [
    {{
      "action_type": "investigate|analyze|test|implement",
      "description": "What you will do",
      "command": "Specific command or method to use",
      "expected_outcome": "What you expect to learn/achieve"
    }}
  ],
  "confidence": 0.8
}}
```

Generate your action plan now. Be specific and systematic. Follow the skill's guidance.
"""

        return prompt

    def _get_rag_knowledge(self, problem_context: Dict[str, Any]) -> str:
        """
        Query RAG for relevant system knowledge.

        Args:
            problem_context: Problem context dict

        Returns:
            Formatted system knowledge string
        """
        # Build queries for RAG based on problem
        queries = [
            "What subsystems does KLoROS have? What is the system architecture?",
            "What actions can KLoROS execute autonomously? What are her capabilities?"
        ]

        knowledge_parts = []

        try:
            for query in queries:
                # Embed query
                query_embedding = self.embedder.embed(query)

                # Retrieve top results
                results = self.rag.retrieve_by_embedding(query_embedding, top_k=2)

                # Extract text from results
                for meta, score in results:
                    if score > 0.5:  # Only include relevant results
                        text = meta.get('text', '')
                        if text and len(text) > 100:  # Meaningful content
                            knowledge_parts.append(text)

            if knowledge_parts:
                # Deduplicate and combine
                unique_knowledge = list(dict.fromkeys(knowledge_parts))  # Preserve order, remove dupes
                combined = "\n\n---\n\n".join(unique_knowledge)
                logger.debug(f"[skill_executor] Retrieved {len(unique_knowledge)} knowledge docs from RAG")
                return combined
            else:
                logger.warning("[skill_executor] No relevant knowledge found in RAG")
                return ""

        except Exception as e:
            logger.error(f"[skill_executor] RAG query failed: {e}", exc_info=True)
            return ""

    def _query_llm(self, prompt: str) -> str:
        """
        Query LLM for reasoning.

        Args:
            prompt: Skill execution prompt

        Returns:
            LLM response text
        """
        url = f"{self.llm_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=300)  # 5 minutes for deep reasoning
            response.raise_for_status()
            result = response.json()
            return result.get('response', '')

        except Exception as e:
            logger.error(f"[skill_executor] LLM query failed: {e}")
            raise

    def _parse_execution_plan(
        self,
        skill_name: str,
        problem_context: Dict[str, Any],
        llm_response: str,
        phase: Optional[str] = None
    ) -> SkillExecutionPlan:
        """
        Parse LLM response into SkillExecutionPlan.

        Args:
            skill_name: Name of skill
            problem_context: Problem context
            llm_response: Raw LLM response
            phase: Requested phase

        Returns:
            Parsed execution plan
        """
        try:
            json_match = llm_response.find('```json')
            if json_match != -1:
                json_start = json_match + 7
                json_end = llm_response.find('```', json_start)
                json_str = llm_response[json_start:json_end].strip()
            else:
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                json_str = llm_response[json_start:json_end]

            parsed = json.loads(json_str)

            return SkillExecutionPlan(
                skill_name=skill_name,
                problem_description=problem_context.get('description', ''),
                phase=parsed.get('phase', phase or 'Phase 1'),
                actions=parsed.get('actions', []),
                reasoning=parsed.get('reasoning', ''),
                confidence=parsed.get('confidence', 0.0)
            )

        except Exception as e:
            logger.warning(f"[skill_executor] Failed to parse JSON, using fallback: {e}")

            return SkillExecutionPlan(
                skill_name=skill_name,
                problem_description=problem_context.get('description', ''),
                phase=phase or 'Phase 1',
                actions=[{
                    "action_type": "investigate",
                    "description": "Parse LLM response manually",
                    "command": "manual_analysis",
                    "expected_outcome": "Action plan from unstructured response"
                }],
                reasoning=llm_response[:500],
                confidence=0.3
            )


def main():
    """Test skill executor."""
    logging.basicConfig(level=logging.INFO)

    executor = SkillExecutor()

    problem = {
        "description": "Swap usage at 99.6% (12.25GB used) causing system slowdown",
        "evidence": {
            "swap_used_mb": 12250,
            "swap_percent": 99.6,
            "memory_used_pct": 57.0,
            "thread_count": 338
        },
        "metrics": {
            "investigation_failure_rate": 0.0
        }
    }

    print("\n=== Testing Skill Execution ===\n")
    print(f"Problem: {problem['description']}\n")

    plan = executor.execute_skill("systematic-debugging", problem)

    if plan:
        print(f"Phase: {plan.phase}")
        print(f"Reasoning: {plan.reasoning}")
        print(f"Confidence: {plan.confidence}")
        print(f"\nActions ({len(plan.actions)}):")
        for i, action in enumerate(plan.actions, 1):
            print(f"  {i}. [{action['action_type']}] {action['description']}")
            if action.get('command'):
                print(f"      Command: {action['command']}")
    else:
        print("Failed to generate execution plan")


if __name__ == "__main__":
    main()
