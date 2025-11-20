#!/usr/bin/env bash
# D-REAM Compliant CPU Bounded Load
set -euo pipefail
cd /home/kloros/src/dream
export PYTHONPATH=/home/kloros/src/dream:/home/kloros/src:$PYTHONPATH
python3 -c "from compliance_tools.cpu_bounded import bounded_cpu_load; import json; print(json.dumps(bounded_cpu_load(seconds=5.0)))"
