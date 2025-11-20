from .io import write_report_files

def emit_report(pack, admitted_n: int, rejected_n: int, anchors: dict):
    """
    Emit D-REAM evaluation report.

    Args:
        pack: CandidatePack being reported on
        admitted_n: Number of admitted candidates
        rejected_n: Number of rejected candidates
        anchors: Anchor evaluation results (KL divergence, etc.)
    """
    report = {
        "run_id": pack.run_id,
        "mix": {},
        "scores": {
            "admitted": admitted_n,
            "rejected": rejected_n
        },
        "diversity": {},  # TODO: Add MinHash/self-BLEU metrics
        "anchor_eval": anchors,
        "notes": ""
    }

    write_report_files(pack, report)
