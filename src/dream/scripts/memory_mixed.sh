#!/usr/bin/env bash
# D-REAM Compliant Memory Bandwidth Test (Mixed)
set -euo pipefail
cd /home/kloros/src/dream
export PYTHONPATH=/home/kloros/src/dream:/home/kloros/src:$PYTHONPATH
python3 -c "from compliance_tools.memory_bw import memory_bandwidth_mb; import json; print(json.dumps(memory_bandwidth_mb(size_mb=768, iterations=7)))"
