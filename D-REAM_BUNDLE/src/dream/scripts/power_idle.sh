#!/usr/bin/env bash
# D-REAM Compliant Power Monitor (Passive)
set -euo pipefail
cd /home/kloros/src/dream
export PYTHONPATH=/home/kloros/src/dream:/home/kloros/src:$PYTHONPATH
python3 -c "from compliance_tools.power_monitor import collect; import json; print(json.dumps(collect(duration_s=10, interval_s=1.0)))"
