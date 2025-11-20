def assemble_training_mix(cfg, fresh_env: list, replay: list, synthetic: list, lineage):
    """
    Assemble training mix with ratio enforcement.

    Args:
        cfg: DreamConfig with mix ratios
        fresh_env: Fresh environment data
        replay: Replay buffer data
        synthetic: Synthetic/generated data
        lineage: Lineage object for tracking

    Returns:
        Dictionary containing the assembled mix
    """
    total = max(1, len(fresh_env) + len(replay) + len(synthetic))

    # Enforce ratio caps
    syn = synthetic[:int(cfg.mix.max_synthetic_ratio * total)]
    rep = replay[:int(cfg.mix.replay_ratio * total)]
    env = fresh_env

    return {
        "synthetic": [c.__dict__ for c in syn],
        "replay": rep,
        "fresh_env": env,
        "lineage": lineage.__dict__
    }
