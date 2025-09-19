#!/usr/bin/env python
import argparse, json
from pipeline.qa import answer as run_answer
import yaml

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='config/accuracy.yml')
    ap.add_argument('--limit', type=int, default=50)
    args = ap.parse_args()
    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    # Tiny mock eval: ask a few canned questions
    qs = [
        'What pipeline does KLoROS use?',
        'How does SLED help?',
        'What does CoVe do?',
    ][:args.limit]
    rows = []
    for q in qs:
        final, trace = run_answer(q, cfg)
        rows.append({'q': q, 'answer': final.get('answer'), 'abstained': final.get('abstained', False)})
    print(json.dumps(rows, indent=2))

if __name__ == '__main__':
    main()
