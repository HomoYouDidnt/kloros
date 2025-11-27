# Heuristic reviewer committee producing notes and score deltas.
from typing import List, Dict

def _review_section(sec: Dict) -> Dict:
    text = sec.get("body_md","")
    notes = []
    delta = 0.0
    if len(text) < 200:
        notes.append("Section is brief; add experimental details or ablations.")
        delta -= 0.1
    if "limitations" not in text.lower() and "threats to validity" not in text.lower():
        notes.append("Add a 'Limitations / Threats to Validity' paragraph.")
        delta -= 0.05
    return {"section": sec.get("title",""), "notes": notes, "score_delta": round(delta,3)}

def run_committee(sections: List[Dict], rounds: int = 1) -> List[Dict]:
    # Multi-round could vary heuristics; here we keep it simple.
    out = []
    for s in sections:
        out.append(_review_section(s))
    return out
