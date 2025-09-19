from typing import Any, Dict


def gatekeep(report: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    return (
        report.get('em_delta', 0) >= criteria.get('em_delta_min', 0) and
        report.get('faithfulness', 0) >= criteria.get('faithfulness_min', 0) and
        report.get('latency_ms', 9999) <= criteria.get('latency_delta_max_ms', 9999) and
        report.get('abstain_rate', 100) <= criteria.get('abstain_rate_max', 100) and
        report.get('passes_safety', False)
    )
