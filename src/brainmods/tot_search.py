"""Tree of Thought search with beam search and MCTS."""
from typing import List, Tuple, Callable, Dict, Any, Optional
import math


class TreeOfThought:
    """Tree of Thought reasoning with configurable search strategy."""

    def __init__(
        self,
        expand_fn: Callable,
        score_fn: Callable,
        beam_width: int = 3,
        max_depth: int = 3,
        strategy: str = "beam"
    ):
        """Initialize ToT search.

        Args:
            expand_fn: Function to expand state → [(action, next_state)]
            score_fn: Function to score states → float
            beam_width: Width of beam for beam search
            max_depth: Maximum search depth
            strategy: Search strategy ('beam' or 'mcts')
        """
        self.expand_fn = expand_fn
        self.score_fn = score_fn
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.strategy = strategy

    def search(self, root_state: Any) -> Dict[str, Any]:
        """Perform tree search.

        Args:
            root_state: Initial state

        Returns:
            Dict with best state, score, and path
        """
        if self.strategy == "beam":
            return self._beam_search(root_state)
        elif self.strategy == "mcts":
            return self._mcts_search(root_state)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def _beam_search(self, root_state: Any) -> Dict[str, Any]:
        """Beam search implementation.

        Args:
            root_state: Initial state

        Returns:
            Search result
        """
        # Initial frontier: (state, score, path)
        frontier = [(root_state, 0.0, [])]
        best = frontier[0]

        for depth in range(self.max_depth):
            candidates = []

            # Expand each state in frontier
            for state, score, path in frontier:
                try:
                    expansions = self.expand_fn(state)

                    for action, next_state in expansions:
                        # Score next state
                        next_score = self.score_fn(next_state)
                        candidates.append((next_state, next_score, path + [action]))

                except Exception as e:
                    # If expansion fails, keep current state
                    candidates.append((state, score, path))

            if not candidates:
                break

            # Select top beam_width candidates
            candidates.sort(key=lambda x: x[1], reverse=True)
            frontier = candidates[:self.beam_width]

            # Track best
            if frontier and frontier[0][1] > best[1]:
                best = frontier[0]

        return {
            "state": best[0],
            "score": best[1],
            "path": best[2],
            "depth": len(best[2])
        }

    def _mcts_search(self, root_state: Any) -> Dict[str, Any]:
        """Monte Carlo Tree Search (simplified).

        Args:
            root_state: Initial state

        Returns:
            Search result
        """
        # Simple MCTS with UCB1
        root = MCTSNode(root_state)
        iterations = self.beam_width * self.max_depth

        for _ in range(iterations):
            # Selection
            node = root
            while node.children and not node.is_terminal:
                node = node.select_child()

            # Expansion
            if not node.is_terminal and node.visits > 0:
                try:
                    expansions = self.expand_fn(node.state)
                    for action, next_state in expansions[:self.beam_width]:
                        child = MCTSNode(next_state, parent=node, action=action)
                        node.children.append(child)

                    if node.children:
                        node = node.children[0]
                except:
                    node.is_terminal = True

            # Simulation (just score the node)
            try:
                score = self.score_fn(node.state)
            except:
                score = 0.0

            # Backpropagation
            while node:
                node.visits += 1
                node.total_score += score
                node = node.parent

        # Find best path
        path = []
        node = root
        while node.children:
            node = max(node.children, key=lambda c: c.avg_score)
            if node.action:
                path.append(node.action)

        return {
            "state": node.state,
            "score": node.avg_score,
            "path": path,
            "visits": root.visits
        }


class MCTSNode:
    """Node for MCTS tree."""

    def __init__(self, state: Any, parent: Optional['MCTSNode'] = None, action: Optional[Any] = None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: List['MCTSNode'] = []
        self.visits = 0
        self.total_score = 0.0
        self.is_terminal = False

    @property
    def avg_score(self) -> float:
        """Average score."""
        return self.total_score / self.visits if self.visits > 0 else 0.0

    def select_child(self) -> 'MCTSNode':
        """Select child using UCB1.

        Returns:
            Selected child node
        """
        if not self.children:
            return self

        # UCB1 formula
        c = math.sqrt(2)  # Exploration constant
        log_parent = math.log(self.visits + 1)

        best_score = float('-inf')
        best_child = self.children[0]

        for child in self.children:
            if child.visits == 0:
                return child  # Prefer unvisited

            exploitation = child.avg_score
            exploration = c * math.sqrt(log_parent / child.visits)
            ucb_score = exploitation + exploration

            if ucb_score > best_score:
                best_score = ucb_score
                best_child = child

        return best_child


def beam_search(
    expand_fn: Callable,
    score_fn: Callable,
    root_state: Any,
    beam: int = 3,
    depth: int = 3
) -> Dict[str, Any]:
    """Convenience function for beam search.

    Args:
        expand_fn: Expansion function
        score_fn: Scoring function
        root_state: Initial state
        beam: Beam width
        depth: Maximum depth

    Returns:
        Search result
    """
    tot = TreeOfThought(
        expand_fn=expand_fn,
        score_fn=score_fn,
        beam_width=beam,
        max_depth=depth,
        strategy="beam"
    )
    return tot.search(root_state)
