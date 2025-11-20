"""Scenario mutation and curriculum evolution."""

import copy
import random
from typing import List
from .spec import FailureSpec


def mutate(spec: FailureSpec, aggressive: bool = False) -> FailureSpec:
    """Mutate a failure spec to create a new variant.

    Args:
        spec: FailureSpec to mutate
        aggressive: Whether to use more aggressive mutations

    Returns:
        New mutated FailureSpec
    """
    mutated = copy.deepcopy(spec)
    mutated.id = f"{spec.id}_mutated_{random.randint(1000, 9999)}"

    mode = spec.mode
    params = mutated.params

    if mode == "timeout":
        # Increase timeout duration
        current = params.get("delay_s", 30)
        if aggressive:
            params["delay_s"] = min(120, current + random.randint(10, 30))
        else:
            params["delay_s"] = min(90, current + random.randint(5, 15))

    elif mode == "jitter":
        # Increase latency variability
        base = params.get("base_ms", 200)
        jitter = params.get("jitter_ms", 400)
        if aggressive:
            params["base_ms"] = base + random.randint(100, 300)
            params["jitter_ms"] = jitter + random.randint(200, 500)
        else:
            params["base_ms"] = base + random.randint(50, 150)
            params["jitter_ms"] = jitter + random.randint(100, 300)

    elif mode == "oom":
        # Reduce memory limit
        current = params.get("bytes_req", 2_000_000_000)
        if aggressive:
            params["bytes_req"] = max(100_000_000, int(current * 0.5))
        else:
            params["bytes_req"] = max(200_000_000, int(current * 0.7))

    elif mode == "corrupt":
        # Increase corruption size
        current = params.get("bytes_to_flip", 64)
        if aggressive:
            params["bytes_to_flip"] = min(1024, current * 4)
        else:
            params["bytes_to_flip"] = min(512, current * 2)

    elif mode == "intermittent":
        # Increase failure rate
        current = params.get("fail_rate", 0.3)
        if aggressive:
            params["fail_rate"] = min(0.9, current + 0.3)
        else:
            params["fail_rate"] = min(0.7, current + 0.2)

    # Optionally adjust guards
    if aggressive and "max_duration_s" in mutated.guards:
        mutated.guards["max_duration_s"] = min(
            60,
            mutated.guards["max_duration_s"] + 10
        )

    return mutated


def combine(spec_a: FailureSpec, spec_b: FailureSpec) -> FailureSpec:
    """Combine two failure specs into a composite scenario.

    Args:
        spec_a: First FailureSpec
        spec_b: Second FailureSpec

    Returns:
        New combined FailureSpec
    """
    # Create composite spec targeting both systems
    combined = FailureSpec(
        id=f"composite_{spec_a.id}_{spec_b.id}",
        target=f"{spec_a.target}+{spec_b.target}",
        mode="composite",
        params={
            "fault_a": {
                "target": spec_a.target,
                "mode": spec_a.mode,
                "params": spec_a.params
            },
            "fault_b": {
                "target": spec_b.target,
                "mode": spec_b.mode,
                "params": spec_b.params
            }
        },
        guards={
            "max_duration_s": max(
                spec_a.guards.get("max_duration_s", 20),
                spec_b.guards.get("max_duration_s", 20)
            )
        },
        expected={
            "heal_events": [
                spec_a.expected.get("heal_event"),
                spec_b.expected.get("heal_event")
            ]
        }
    )

    return combined


def shrink(spec: FailureSpec) -> List[FailureSpec]:
    """Shrink a failure spec to simpler variants.

    Args:
        spec: FailureSpec to shrink

    Returns:
        List of simpler variants
    """
    variants = []

    mode = spec.mode
    params = copy.deepcopy(spec.params)

    if mode == "timeout":
        # Try shorter timeouts
        current = params.get("delay_s", 30)
        for reduction in [0.25, 0.5, 0.75]:
            if current * reduction >= 1:
                shrunk = copy.deepcopy(spec)
                shrunk.id = f"{spec.id}_shrink_{int(reduction*100)}"
                shrunk.params["delay_s"] = current * reduction
                variants.append(shrunk)

    elif mode == "jitter":
        # Reduce variability
        base = params.get("base_ms", 200)
        jitter = params.get("jitter_ms", 400)

        # Try reducing jitter
        if jitter > 100:
            shrunk = copy.deepcopy(spec)
            shrunk.id = f"{spec.id}_shrink_jitter"
            shrunk.params["jitter_ms"] = jitter // 2
            variants.append(shrunk)

        # Try reducing base
        if base > 100:
            shrunk = copy.deepcopy(spec)
            shrunk.id = f"{spec.id}_shrink_base"
            shrunk.params["base_ms"] = base // 2
            variants.append(shrunk)

    elif mode == "oom":
        # Try larger memory limits
        current = params.get("bytes_req", 2_000_000_000)
        for increase in [1.5, 2.0]:
            shrunk = copy.deepcopy(spec)
            shrunk.id = f"{spec.id}_shrink_{int(increase*100)}"
            shrunk.params["bytes_req"] = int(current * increase)
            variants.append(shrunk)

    return variants


def evolve_curriculum(
    results: List[dict],
    pool: List[FailureSpec],
    max_pool_size: int = 50
) -> List[FailureSpec]:
    """Evolve curriculum based on results.

    Args:
        results: List of experiment results
        pool: Current scenario pool
        max_pool_size: Maximum scenarios to keep

    Returns:
        Evolved scenario pool
    """
    # Rank scenarios by teaching value
    from .grading import rank_scenarios
    ranked = rank_scenarios(results)

    # Keep top performers
    top_specs = []
    for result in ranked[:max_pool_size // 2]:
        spec_id = result.get("spec_id")
        spec = next((s for s in pool if s.id == spec_id), None)
        if spec:
            top_specs.append(spec)

    # Generate mutations from top performers
    mutations = []
    for spec in top_specs[:10]:  # Mutate top 10
        mutations.append(mutate(spec, aggressive=False))
        if random.random() < 0.3:  # 30% chance of aggressive mutation
            mutations.append(mutate(spec, aggressive=True))

    # Generate combinations
    combinations = []
    if len(top_specs) >= 2:
        for _ in range(min(5, len(top_specs) // 2)):
            a, b = random.sample(top_specs, 2)
            combinations.append(combine(a, b))

    # Combine all
    new_pool = top_specs + mutations + combinations

    # Deduplicate by ID
    seen = set()
    unique_pool = []
    for spec in new_pool:
        if spec.id not in seen:
            seen.add(spec.id)
            unique_pool.append(spec)

    # Trim to max size
    return unique_pool[:max_pool_size]


def generate_variants(spec: FailureSpec, count: int = 5) -> List[FailureSpec]:
    """Generate multiple variants of a spec.

    Args:
        spec: Base FailureSpec
        count: Number of variants to generate

    Returns:
        List of variant specs
    """
    variants = []

    for i in range(count):
        variant = mutate(spec, aggressive=(i % 2 == 0))
        variants.append(variant)

    return variants
