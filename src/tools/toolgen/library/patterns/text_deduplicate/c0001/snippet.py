from typing import List, Tuple

def deduplicate_lines(text: str, threshold: float = 0.8) -> str:
    """Remove near-duplicate lines while preserving order.

    Rules:
    - threshold >= 0.9999: exact duplicate removal on the *raw* stripped line (case-sensitive).
    - threshold < 1.0: near-duplicate via Jaccard over lowercased token sets.
      When a near-duplicate is found, keep the "most informative" representative:
        * more tokens wins
        * tie-break by longer character length
        * if still tied, keep the earlier line
    """
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln != ""]

    if threshold >= 0.9999:
        seen_raw = set()
        out = []
        for ln in lines:
            if ln not in seen_raw:
                seen_raw.add(ln)
                out.append(ln)
        return "\n".join(out)

    def norm_tokens(s: str) -> List[str]:
        return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in s).split()).split()

    # Each entry: (raw_line, token_set, token_count, char_len, first_index)
    reps: List[Tuple[str, set, int, int, int]] = []

    for idx, ln in enumerate(lines):
        toks = set(norm_tokens(ln))
        tokc = len(toks)
        chlen = len(ln)

        # Try to match an existing representative by Jaccard
        match_i = -1
        best_sim = -1.0
        for i, (_r, stoks, _c, _L, _idx0) in enumerate(reps):
            inter = len(toks & stoks)
            union = len(toks | stoks) or 1
            sim = inter / union
            if sim > best_sim:
                best_sim = sim
                match_i = i

        if best_sim >= threshold:
            # candidate duplicate; decide if we should replace the representative
            r_line, r_stoks, r_tokc, r_len, r_idx0 = reps[match_i]
            replace = False
            if tokc > r_tokc:
                replace = True
            elif tokc == r_tokc and chlen > r_len:
                replace = True

            if replace:
                reps[match_i] = (ln, toks, tokc, chlen, r_idx0)
        else:
            reps.append((ln, toks, tokc, chlen, idx))

    # Reconstruct in the order representatives first appeared
    reps.sort(key=lambda t: t[4])
    return "\n".join([r[0] for r in reps])
