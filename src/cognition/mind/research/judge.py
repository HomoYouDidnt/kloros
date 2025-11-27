"""Judge LLM for TUMIX committee aggregation."""
from typing import Dict, Any, List, Tuple, Optional
import requests
import os
import json
import re

from src.core.config.models_config import get_ollama_context_size


class JudgeLLM:
    """Judge LLM for evaluating and selecting committee outputs."""

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        timeout: int = 30
    ):
        """Initialize judge LLM.

        Args:
            ollama_url: Ollama API URL (default: from env or SSOT config)
            model: Model name (default: from env or SSOT config)
            temperature: Sampling temperature
            timeout: Request timeout in seconds
        """
        # Get defaults from SSOT config
        from src.core.config.models_config import get_ollama_url, get_ollama_model
        default_url = get_ollama_url() + "/api/generate"
        default_model = get_ollama_model()

        self.ollama_url = ollama_url or os.getenv('KLR_OLLAMA_URL', default_url)
        self.model = model or os.getenv('KLR_OLLAMA_MODEL', default_model)
        self.temperature = temperature
        self.timeout = timeout

    def judge(
        self,
        task: str,
        outputs_by_agent: Dict[str, Dict[str, Any]]
    ) -> Tuple[str, Dict[str, float]]:
        """Judge committee outputs and select the best.

        Args:
            task: Task description
            outputs_by_agent: Outputs from each agent

        Returns:
            (selected_answer, confidence_scores) tuple
        """
        # Build prompt
        prompt = self._build_judge_prompt(task, outputs_by_agent)

        # Call LLM
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": self.temperature,
                    "num_ctx": get_ollama_context_size(check_vram=False)
                }
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                llm_response = response.json().get("response", "").strip()

                # Parse response
                return self._parse_judge_response(llm_response, outputs_by_agent)
            else:
                # Fallback to heuristic
                return self._fallback_heuristic(outputs_by_agent)

        except Exception as e:
            print(f"[judge] Error calling LLM: {e}")
            return self._fallback_heuristic(outputs_by_agent)

    def _build_judge_prompt(
        self,
        task: str,
        outputs_by_agent: Dict[str, Dict[str, Any]]
    ) -> str:
        """Build judge prompt.

        Args:
            task: Task description
            outputs_by_agent: Outputs from each agent

        Returns:
            Prompt string
        """
        prompt = f"""You are a judge evaluating multiple answers to a task. Your job is to select the best answer.

Task: {task}

Agent Answers:
"""

        for agent_id, output in outputs_by_agent.items():
            answer = output.get("answer", output.get("output", ""))
            confidence = output.get("confidence", 0.5)
            trace = output.get("trace", "")

            prompt += f"""
--- {agent_id} (confidence: {confidence:.2f}) ---
Answer: {answer}
Reasoning: {trace[:200]}...
"""

        prompt += """
Evaluate each answer on:
1. Correctness - Is the answer accurate?
2. Completeness - Does it fully address the task?
3. Clarity - Is it well-explained?
4. Evidence - Is the reasoning sound?

Respond in JSON format:
{
  "best_agent": "agent_id",
  "reason": "brief explanation",
  "confidence_scores": {
    "agent_1": 0.9,
    "agent_2": 0.7,
    ...
  }
}
"""

        return prompt

    def _parse_judge_response(
        self,
        llm_response: str,
        outputs_by_agent: Dict[str, Dict[str, Any]]
    ) -> Tuple[str, Dict[str, float]]:
        """Parse judge LLM response.

        Args:
            llm_response: Raw LLM response
            outputs_by_agent: Original outputs

        Returns:
            (selected_answer, confidence_scores) tuple
        """
        try:
            # Extract JSON
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                best_agent = result.get("best_agent")
                confidence_scores = result.get("confidence_scores", {})

                if best_agent and best_agent in outputs_by_agent:
                    best_output = outputs_by_agent[best_agent]
                    answer = best_output.get("answer", best_output.get("output", ""))
                    return answer, confidence_scores

        except Exception as e:
            print(f"[judge] Error parsing response: {e}")

        # Fallback
        return self._fallback_heuristic(outputs_by_agent)

    def _fallback_heuristic(
        self,
        outputs_by_agent: Dict[str, Dict[str, Any]]
    ) -> Tuple[str, Dict[str, float]]:
        """Fallback heuristic judge.

        Args:
            outputs_by_agent: Outputs from each agent

        Returns:
            (selected_answer, confidence_scores) tuple
        """
        best_agent = None
        best_score = float('-inf')
        confidence_scores = {}

        for agent_id, output in outputs_by_agent.items():
            conf = output.get("confidence", 0.5)
            trace = output.get("trace", "")

            # Score = confidence * (1 + trace_length_bonus)
            score = conf * (1 + len(trace) / 1000)
            confidence_scores[agent_id] = conf

            if score > best_score:
                best_score = score
                best_agent = agent_id

        if best_agent:
            best_output = outputs_by_agent[best_agent]
            answer = best_output.get("answer", best_output.get("output", ""))
            return answer, confidence_scores

        # Last resort: return first agent's answer
        first_agent = list(outputs_by_agent.keys())[0]
        first_output = outputs_by_agent[first_agent]
        return first_output.get("answer", first_output.get("output", "")), confidence_scores


def judge_llm_aggregate_real(
    committee_genome: Any,
    outputs_by_agent: Dict[str, Any],
    comm_state: Dict[str, Any],
    judge_pool: Optional[JudgeLLM] = None
) -> Tuple[Any, List[Tuple[str, float]]]:
    """Judge LLM aggregation with real LLM calls.

    Args:
        committee_genome: CommitteeGenome configuration
        outputs_by_agent: Outputs from each agent
        comm_state: Communication state
        judge_pool: Optional JudgeLLM instance

    Returns:
        (aggregated_output, votes)
    """
    # Create or use existing judge
    judge = judge_pool or JudgeLLM()

    # Extract task from committee or use generic
    task = "Evaluate the committee outputs and select the best answer"

    # Get judge decision
    selected_answer, confidence_scores = judge.judge(task, outputs_by_agent)

    # Build votes list
    votes = [
        (agent_id, confidence_scores.get(agent_id, 0.5))
        for agent_id in outputs_by_agent.keys()
    ]

    return selected_answer, votes
