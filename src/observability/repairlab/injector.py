"""Bug injection utility with pluggable bug library."""
import random
from typing import List
from pathlib import Path
from .bugs import (
    BugSpec,
    InjectionResult,
    # String-based
    RemoveColon,
    MissingParen,
    MissingQuote,
    WrongOperator,
    TypoVariable,
    OffByOneString,
    # AST-based
    OffByOneRange,
    FloatTruncation,
    EarlyReturn,
)


def available_bugs() -> List[BugSpec]:
    """Return all available bug specifications."""
    return [
        # String-based mutations (easy/medium)
        RemoveColon(),
        MissingParen(),
        MissingQuote(),
        WrongOperator(),
        TypoVariable(),
        OffByOneString(),
        # AST-based mutations (hard)
        OffByOneRange(),
        FloatTruncation(),
        EarlyReturn(),
    ]


def choose_applicable_bug(source: str, rng: random.Random, difficulty: str = None) -> BugSpec:
    """Choose a random applicable bug for the given source.
    
    Args:
        source: Source code to inject bug into
        rng: Random number generator for deterministic selection
        difficulty: Optional difficulty filter ("easy", "medium", "hard")
    
    Returns:
        BugSpec that can be applied to the source
    
    Raises:
        RuntimeError: If no applicable bugs found
    """
    bugs = available_bugs()
    
    # Filter by difficulty if specified
    if difficulty:
        bugs = [b for b in bugs if b.difficulty == difficulty]
    
    # Filter by applicability
    candidates = [b for b in bugs if b.applies(source)]
    
    if not candidates:
        raise RuntimeError(f"No applicable bugs for this source (difficulty={difficulty})")
    
    return rng.choice(candidates)


def inject_bug(source: str, rng: random.Random, difficulty: str = None) -> InjectionResult:
    """Inject a random applicable bug into source code.
    
    Args:
        source: Source code to mutate
        rng: Random number generator for deterministic injection
        difficulty: Optional difficulty filter
    
    Returns:
        InjectionResult with mutated source and metadata
    """
    bug = choose_applicable_bug(source, rng, difficulty)
    return bug.inject(source)


def list_bugs() -> None:
    """Print all available bugs grouped by difficulty."""
    bugs = available_bugs()
    by_difficulty = {}
    
    for bug in bugs:
        if bug.difficulty not in by_difficulty:
            by_difficulty[bug.difficulty] = []
        by_difficulty[bug.difficulty].append(bug)
    
    for difficulty in ["easy", "medium", "hard"]:
        if difficulty in by_difficulty:
            print(f"\n{difficulty.upper()} Bugs:")
            for bug in by_difficulty[difficulty]:
                print(f"  - {bug.bug_id}: {bug.description}")
