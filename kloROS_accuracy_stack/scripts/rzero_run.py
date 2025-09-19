#!/usr/bin/env python
import argparse
import json

from rzero.evaluator import evaluate_candidate
from rzero.gatekeeper import gatekeep
from rzero.proposer import propose_candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['propose','evaluate','gatekeep'])
    ap.add_argument('--n', type=int, default=4)
    ap.add_argument('--out', default='out/rzero')
    args = ap.parse_args()

    if args.cmd == 'propose':
        knobs = {
            'sled_alpha': [0.1,0.2,0.3],
            'cisc_k': [3,5,7],
        }
        cands = propose_candidates({}, knobs, n=args.n)
        print(json.dumps(cands, indent=2))
    elif args.cmd == 'evaluate':
        profile = {'id':'demo-profile'}
        path = evaluate_candidate(profile, args.out)
        print(path)
    else:
        # gatekeep demo
        report = {'em_delta': 2.2, 'faithfulness': 0.95, 'latency_ms': 50, 'abstain_rate': 7.5, 'passes_safety': True}
        crit = {'em_delta_min': 2.0, 'faithfulness_min': 0.93, 'latency_delta_max_ms': 60, 'abstain_rate_max': 8.0}
        print(gatekeep(report, crit))

if __name__ == '__main__':
    main()
