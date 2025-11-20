"""Multi-agent debate for improved reasoning."""
from typing import Callable, Dict, Any, List, Optional


class DebateRunner:
    """Runs multi-agent debates for decision making."""

    def __init__(
        self,
        proposer: Callable,
        critic: Callable,
        judge: Callable,
        rounds: int = 1
    ):
        """Initialize debate runner.

        Args:
            proposer: Function that generates initial proposal
            critic: Function that critiques proposal
            judge: Function that judges between proposal and critique
            rounds: Number of debate rounds
        """
        self.proposer = proposer
        self.critic = critic
        self.judge = judge
        self.rounds = rounds

    def run(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run debate.

        Args:
            prompt: Initial prompt/question
            context: Optional context dict

        Returns:
            Debate result with proposal, critiques, and verdict
        """
        context = context or {}
        history = []

        # Initial proposal
        proposal = self.proposer(prompt, context)

        for round_num in range(self.rounds):
            # Critic responds
            critique = self.critic(prompt, proposal, context)

            # Judge evaluates
            verdict = self.judge(prompt, proposal, critique, context)

            history.append({
                "round": round_num + 1,
                "proposal": proposal,
                "critique": critique,
                "verdict": verdict
            })

            # If judge wants revision, proposer refines
            if verdict.get("requires_revision", False) and round_num < self.rounds - 1:
                proposal = self.proposer(prompt, {**context, "previous": proposal, "critique": critique})

        # Final verdict
        final_verdict = history[-1]["verdict"] if history else {}

        return {
            "final_proposal": proposal,
            "history": history,
            "verdict": final_verdict,
            "rounds_completed": len(history)
        }


class SimpleDebate:
    """Simple debate implementation with heuristic agents."""

    @staticmethod
    def proposer(prompt: str, context: Dict[str, Any]) -> str:
        """Generate proposal.

        Args:
            prompt: Question/prompt
            context: Context

        Returns:
            Proposal text
        """
        # Simple proposer just returns the prompt's implied answer
        # In practice, this would call an LLM
        return f"Proposal: {prompt}"

    @staticmethod
    def critic(prompt: str, proposal: str, context: Dict[str, Any]) -> str:
        """Generate critique.

        Args:
            prompt: Original prompt
            proposal: Proposal to critique
            context: Context

        Returns:
            Critique text
        """
        # Simple critic looks for obvious issues
        issues = []

        if len(proposal) < 10:
            issues.append("Proposal is too short")

        if "error" in proposal.lower():
            issues.append("Proposal contains error mentions")

        if not issues:
            issues.append("Proposal appears reasonable")

        return "Critique: " + "; ".join(issues)

    @staticmethod
    def judge(prompt: str, proposal: str, critique: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Judge between proposal and critique.

        Args:
            prompt: Original prompt
            proposal: Proposal
            critique: Critique
            context: Context

        Returns:
            Verdict dict
        """
        # Simple judge uses heuristics
        critique_lower = critique.lower()

        requires_revision = any(word in critique_lower for word in ["error", "wrong", "incorrect", "issue"])

        confidence = 0.7 if not requires_revision else 0.4

        return {
            "requires_revision": requires_revision,
            "confidence": confidence,
            "reasoning": critique,
            "final_answer": proposal if not requires_revision else "Needs revision"
        }


def run_debate(
    prompt: str,
    proposer: Optional[Callable] = None,
    critic: Optional[Callable] = None,
    judge: Optional[Callable] = None,
    rounds: int = 1,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convenience function to run debate.

    Args:
        prompt: Question/prompt
        proposer: Proposer function (defaults to SimpleDebate)
        critic: Critic function (defaults to SimpleDebate)
        judge: Judge function (defaults to SimpleDebate)
        rounds: Number of rounds
        context: Optional context

    Returns:
        Debate result
    """
    proposer = proposer or SimpleDebate.proposer
    critic = critic or SimpleDebate.critic
    judge = judge or SimpleDebate.judge

    runner = DebateRunner(proposer, critic, judge, rounds)
    return runner.run(prompt, context)


class ConsensusDebate:
    """Debate with multiple proposers seeking consensus."""

    def __init__(self, proposers: List[Callable], judge: Callable):
        """Initialize consensus debate.

        Args:
            proposers: List of proposer functions
            judge: Judge function to find consensus
        """
        self.proposers = proposers
        self.judge = judge

    def run(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run consensus debate.

        Args:
            prompt: Question
            context: Optional context

        Returns:
            Consensus result
        """
        context = context or {}

        # Get proposals from all proposers
        proposals = []
        for i, proposer in enumerate(self.proposers):
            try:
                proposal = proposer(prompt, context)
                proposals.append({
                    "proposer_id": i,
                    "proposal": proposal
                })
            except Exception as e:
                proposals.append({
                    "proposer_id": i,
                    "proposal": None,
                    "error": str(e)
                })

        # Judge finds consensus
        consensus = self.judge(prompt, proposals, context)

        return {
            "proposals": proposals,
            "consensus": consensus,
            "num_proposers": len(self.proposers)
        }
