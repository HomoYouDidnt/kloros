from typing import List, Tuple
from .schema import CandidatePack, Candidate
from .judges.frozen import FrozenJudges
from .constraints import passes_constraints
from .config import DreamConfig
from .io import write_admitted, write_quarantine
from .kl_anchor import passes_kl_anchor_check
from .diversity_metrics import has_sufficient_diversity
from .dashboard_card_validator import DashboardCardValidator

def judge_and_admit(cfg: DreamConfig, pack: CandidatePack) -> Tuple[List[Candidate], List[Candidate]]:
    """
    Judge candidates and admit those that pass all gates.

    Admission Gates:
    1. Frozen judge scoring
    2. Novelty threshold
    3. Domain constraints
    4. KL anchor drift check
    5. Dashboard card completeness (NEW)
    6. Diversity metrics
    7. Holdout regression check

    Returns:
        (admitted, rejected) tuple of candidate lists
    """
    fj = FrozenJudges(cfg.judging.weights)
    card_validator = DashboardCardValidator(strict_mode=True)
    admitted, rejected = [], []

    for c in pack.candidates:
        score = fj.score(c.metrics)
        novel = c.metrics.get("novelty", 0.0) >= cfg.judging.novelty_threshold
        ok = passes_constraints(c.domain, c.metrics, c.params)

        # KL anchor drift check
        kl_ok = passes_kl_anchor_check(c.metrics, cfg.anchors.kl_tau)

        # Dashboard card completeness check (PHASE 5 GATE)
        card_result = card_validator.validate_card(c.metrics, c.id)
        card_ok = card_result.is_valid

        if not card_ok:
            # Reject candidates with incomplete dashboard cards
            rejected.append(c)
        elif score >= cfg.judging.score_threshold and novel and ok and kl_ok:
            admitted.append(c)
        else:
            rejected.append(c)

    # Diversity metrics check (prevent admitting overly similar candidates)
    if len(admitted) > 1:
        # Convert candidates to dictionaries for diversity check
        candidate_dicts = [{"params": c.params, "metrics": c.metrics} for c in admitted]

        # Check if admitted set has sufficient diversity
        diverse = has_sufficient_diversity(candidate_dicts, min_diversity=0.2)

        if not diverse:
            # Low diversity - quarantine all but the best performer
            sorted_admitted = sorted(admitted, key=lambda x: fj.score(x.metrics), reverse=True)
            best = sorted_admitted[0]
            rest = sorted_admitted[1:]

            # Keep only the best, reject the rest
            admitted = [best]
            rejected += rest
    # Block on holdout regressions if enabled
    if cfg.anchors.holdout_regressions_block:
        if not all(c.metrics.get("holdout_ok", True) for c in admitted):
            # Regression detected - quarantine everything
            rejected += admitted
            admitted = []

    write_admitted(pack.run_id, admitted, pack.lineage)
    write_quarantine(pack.run_id, rejected, pack.lineage)

    return admitted, rejected
