#!/usr/bin/env bash
# D-REAM Compliant Scheduler Metrics (Passive)
set -euo pipefail
cd /home/kloros/src/dream
export PYTHONPATH=/home/kloros/src/dream:/home/kloros/src:$PYTHONPATH
python3 -c "from compliance_tools.scheduler_metrics import collect; import json; print(json.dumps(collect()))"
