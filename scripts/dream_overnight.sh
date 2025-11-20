#!/usr/bin/env bash
# PHASE - Phased Heuristic Adaptive Scheduling Engine
# Production-grade D-REAM test orchestration with full traceability
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---- METADATA & SCHEMA ----
export PHASE="${PHASE:-overnight}"
export RUN_ID="${PHASE}-$(date -u +%Y%m%dT%H%M%SZ)"
export SCHEMA_VERSION=4
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

# Create run artifacts directory
RUN_DIR="${ROOT}/out/test_runs/${RUN_ID}"
mkdir -p "$RUN_DIR"

# ---- SYSTEM HELPERS ----
cores=$(python3 -c 'import os; print(os.cpu_count() or 16)')

is_daytime() {
    [[ "${PHASE:-}" == "midday" ]] && return 0 || return 1
}

calc_workers() {
    local mode="${1:-DEEP}"
    if is_daytime; then
        case "$mode" in
            LIGHT) echo "4" ;;
            *)     echo "$(( (cores+1)/2 ))" ;;  # 50% of cores for midday
        esac
    else
        case "$mode" in
            LIGHT) echo "4" ;;
            *)     echo "auto" ;;  # Overnight can use full auto
        esac
    fi
}

# Dynamic RAM-based worker calculation (replaces hardcoded auto)
calc_safe_workers() {
    local mem_per_worker_gb=17  # Observed from OOM logs
    local safety_margin_gb=8    # Headroom for OS + services + swap overhead
    local avail_gb=$(awk '/MemAvailable:/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
    local max_workers=$(( (avail_gb - safety_margin_gb) / mem_per_worker_gb ))

    # Clamp: minimum 1, maximum 3 (conservative cap)
    [[ $max_workers -lt 1 ]] && max_workers=1
    [[ $max_workers -gt 3 ]] && max_workers=3

    echo "$max_workers"
}

preflight_resources() {
    local la1 free_kb swap_used_kb swap_total_kb swap_pct
    la1=$(awk '{print $1}' /proc/loadavg)
    free_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 4000000)
    read swap_used_kb swap_total_kb < <(awk '/SwapTotal:/ {t=$2} /SwapFree:/ {f=$2} END{print t-f, t}' /proc/meminfo 2>/dev/null || echo "0 1")
    swap_pct=$(( swap_total_kb>0 ? (100*swap_used_kb)/swap_total_kb : 0 ))

    # Check thresholds: load > 3x cores (true thrashing), free < 512MB (OOM imminent), swap > 99%
    awk -v la="$la1" -v cores="$cores" -v free="$free_kb" -v swap="$swap_pct" '
        BEGIN {
            bad = (la > cores*3) || (free < 512*1024) || (swap > 99);
            exit(bad ? 1 : 0);
        }'
}

run_safely() {
    local desc="$1"; shift
    if preflight_resources; then
        # Resources are good, run the command
        "$@"
    else
        # Resources are under pressure, skip
        echo "[PHASE_SKIPPED_RESOURCE_PRESSURE] $desc - load=$(awk '{print $1}' /proc/loadavg), free=$(awk '/MemAvailable:/ {printf "%.1fG", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo '?')"
        return 0
    fi
}

write_manifest_partial() {
    local status="$1"
    jq -n --arg run_id "$RUN_ID" --arg phase "${PHASE_TYPE:-DEEP}" \
          --arg status "$status" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
          '{run_id:$run_id, phase:$phase, status:$status, updated_at_utc:$ts}' \
          > "$RUN_DIR/manifest.partial.json" 2>/dev/null || true
}

# ---- CONFIG ----
START_ET="${START_ET:-03:00}"
END_ET="${END_ET:-07:00}"
EPOCH_MIN="${EPOCH_MIN:-12}"
SEEDS="${SEEDS:-1337 2025 42}"
export DREAM_GLOBAL_SEED="${DREAM_GLOBAL_SEED:-1337}"

# Parallelism will be set after reading hints
XDIST=""
FAST_FILTER=${FAST_FILTER:-"not slow and not e2e"}
E2E_FILTER=${E2E_FILTER:-"not slow"}

LOGDIR="${ROOT}/logs"
mkdir -p "$LOGDIR"

VENV="${ROOT}/.venv/bin"
PYTEST="${VENV}/pytest"

# Check for pytest-xdist
if ! ${VENV}/python -c "import xdist" 2>/dev/null; then
    echo "WARNING: pytest-xdist not found, falling back to sequential execution"
    XDIST=""
fi

# ---- UTC WINDOW CONVERSION ----
# Convert EDT to UTC (EDT = UTC-4, EST = UTC-5)
START_UTC=$(TZ=America/New_York date -d "today ${START_ET}" -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "UNKNOWN")
END_UTC=$(TZ=America/New_York date -d "today ${END_ET}" -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "UNKNOWN")

# ---- TIME UTILS ----
now_s() { date +%s; }
now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Anchor to today's time window
start_ts=$(date -d "today ${START_ET}" +%s 2>/dev/null || date -j -f "%H:%M" "${START_ET}" +%s)
end_ts=$(date -d "today ${END_ET}" +%s 2>/dev/null || date -j -f "%H:%M" "${END_ET}" +%s)

# If started early/late, clamp window
cur=$(now_s)
if [[ $cur -lt $start_ts ]]; then
  echo "Waiting until ${START_ET} to begin..."
  sleep $((start_ts - cur))
fi

finish_at=$end_ts

# ---- HEADER ----
echo "==============================================="
echo "PHASE - Phased Heuristic Adaptive Scheduling Engine"
echo "D-REAM Test Orchestration (Production Grade)"
echo "==============================================="
echo "RUN_ID: ${RUN_ID}"
echo "Schema: v${SCHEMA_VERSION}"
echo "Phase: ${PHASE}"
echo "Window (ET): ${START_ET}–${END_ET}"
echo "Window (UTC): ${START_UTC}–${END_UTC}"
echo "Epoch duration: ${EPOCH_MIN} minutes"
echo "Seeds: ${SEEDS}"
echo "Artifacts: ${RUN_DIR}/"
echo "Logs: ${LOGDIR}/"
echo "==============================================="

# Memory logging for observability
log_mem() {
    echo "=== Memory State at $(date) ==="
    free -h
    echo "Swap detail:"
    cat /proc/swaps
    echo "Top 5 memory consumers:"
    ps aux --sort=-%mem | head -6
    echo "================================"
}

# Initialize result tracking
RESULTS_FILE="${RUN_DIR}/results.jsonl"
METRICS_FILE="${RUN_DIR}/metrics.jsonl"
touch "$RESULTS_FILE" "$METRICS_FILE"

# ---- ADAPTIVE HINTS ----
# Read hints.json from heuristic controller (read-only, zero-risk integration)
HINTS_FILE="${ROOT}/out/hints.json"

read_hints() {
    if [[ ! -f "$HINTS_FILE" ]]; then
        echo "No hints.json found, using defaults"
        PHASE_TYPE="DEEP"
        WORKERS_HINT="auto"
        FIDELITY_HINT="standard"
        return
    fi

    if ! command -v jq &> /dev/null; then
        echo "WARNING: jq not found, cannot parse hints.json"
        PHASE_TYPE="DEEP"
        WORKERS_HINT="auto"
        FIDELITY_HINT="standard"
        return
    fi

    # Check hints age (expire after 2 hours)
    HINTS_AGE=$(stat -c %Y "$HINTS_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    AGE_SECONDS=$((NOW - HINTS_AGE))

    if [[ $AGE_SECONDS -gt 7200 ]]; then
        echo "HINTS_EXPIRED_FALLBACK: Hints older than 2h (${AGE_SECONDS}s), using defaults"
        PHASE_TYPE="DEEP"
        WORKERS_HINT="auto"
        FIDELITY_HINT="standard"
        return
    fi

    PHASE_TYPE=$(jq -r '.phase_type // "DEEP"' "$HINTS_FILE" 2>/dev/null || echo "DEEP")
    WORKERS_HINT=$(jq -r '.workers_hint // 0' "$HINTS_FILE" 2>/dev/null || echo "0")
    FIDELITY_HINT=$(jq -r '.fidelity_hint // "standard"' "$HINTS_FILE" 2>/dev/null || echo "standard")

    echo "Hints: phase_type=${PHASE_TYPE}, workers=${WORKERS_HINT}, fidelity=${FIDELITY_HINT} (age=${AGE_SECONDS}s)"

    # Calculate safe workers based on phase and time of day
    if [[ "$WORKERS_HINT" -gt 0 ]]; then
        WORKERS="$WORKERS_HINT"
    else
        # Use dynamic RAM-based calculation instead of hardcoded "auto"
        WORKERS="$(calc_safe_workers)"
    fi
    XDIST="-n ${WORKERS}"
    echo "Workers: ${WORKERS} (daytime=$(is_daytime && echo yes || echo no), cores=${cores})"
}

# Read initial hints
read_hints

# ---- PHASE TYPE STRATEGIES ----
# Adaptive pass selection based on phase type
apply_phase_strategy() {
    case "$PHASE_TYPE" in
        LIGHT)
            echo "PHASE_TYPE=LIGHT: Quick diagnostics mode"
            RUN_LAST_FAILED=1
            RUN_NEW_FIRST=0
            RUN_SEED_SWEEP=0
            RUN_E2E=0
            RUN_PROMOTION=1
            FAST_FILTER="not slow and not e2e and not integration"
            ;;
        REM)
            echo "PHASE_TYPE=REM: D-REAM meta-learning mode"
            RUN_LAST_FAILED=1
            RUN_NEW_FIRST=1
            RUN_SEED_SWEEP=1
            RUN_E2E=1
            RUN_PROMOTION=1
            FAST_FILTER="not slow"  # More comprehensive
            ;;
        DEEP|*)
            echo "PHASE_TYPE=DEEP: Full integration mode"
            RUN_LAST_FAILED=1
            RUN_NEW_FIRST=1
            RUN_SEED_SWEEP=1
            RUN_E2E=1
            RUN_PROMOTION=1
            FAST_FILTER="${FAST_FILTER:-not slow and not e2e}"
            ;;
    esac
}

apply_phase_strategy

# ---- PHASE 0: warm cache (short & parallel) ----
echo ""
log_mem | tee -a "$LOGDIR/memory_phase0.log"
echo "==[00] Fast triage (unit+acceptance, filtered)==" | tee "$LOGDIR/00_fast_triage.log"
run_safely "phase0" ${PYTEST} -q tests src/dream/tests -k "${FAST_FILTER}" ${XDIST} --durations=25 --maxfail=1 \
    --json-report --json-report-file="${RUN_DIR}/phase0_report.json" 2>&1 | tee -a "$LOGDIR/00_fast_triage.log" || true
write_manifest_partial "phase0_done"

# Try promotion if available
if command -v make &> /dev/null && grep -q "^promotion:" Makefile 2>/dev/null; then
    echo "-- promotion policy warm-up --" | tee -a "$LOGDIR/00_fast_triage.log"
    run_safely "phase0-promotion" make promotion 2>&1 | tee -a "$LOGDIR/00_fast_triage.log" || true
fi

# ---- EPOCH LOOP ----
epoch=1
total_tests_run=0
total_passed=0
total_failed=0

while [[ $(now_s) -lt $((finish_at - 300)) ]]; do  # leave ~5 min for wrap-up
  echo ""
  echo "==[Epoch ${epoch}] Quantum sweep ($(date '+%H:%M:%S'))=="
  epoch_log="$LOGDIR/epoch_${epoch}.log"
  log_mem | tee -a "$epoch_log"

  epoch_start=$(now_s)
  epoch_end=$(( epoch_start + EPOCH_MIN*60 ))

  # 1) Re-run last failed/new first (super high signal)
  if [[ $RUN_LAST_FAILED -eq 1 ]]; then
    echo "-- last-failed pass --" | tee -a "$epoch_log"
    run_safely "last-failed" ${PYTEST} --lf ${XDIST} --maxfail=1 \
        --json-report --json-report-file="${RUN_DIR}/epoch${epoch}_lf.json" 2>&1 | tee -a "$epoch_log" || true
    write_manifest_partial "epoch${epoch}_lf_done"
  fi

  if [[ $(now_s) -ge $epoch_end ]]; then goto_next=1; else goto_next=0; fi

  # 2) New-first on core suites (catches fresh regressions quickly)
  if [[ $goto_next -eq 0 && $RUN_NEW_FIRST -eq 1 ]]; then
    echo "-- new-first unit/integration --" | tee -a "$epoch_log"
    run_safely "new-first" ${PYTEST} --nf tests src/dream/tests ${XDIST} -k "${FAST_FILTER}" \
        --json-report --json-report-file="${RUN_DIR}/epoch${epoch}_nf.json" 2>&1 | tee -a "$epoch_log" || true
    write_manifest_partial "epoch${epoch}_nf_done"
  fi

  # 3) Seed sweep (repro/stability) — SEQUENTIAL for daytime, short filter, different RNGs
  if [[ $RUN_SEED_SWEEP -eq 1 ]]; then
    if is_daytime; then
      # Daytime: sequential seeds to avoid workers × seeds explosion
      for s in ${SEEDS}; do
        if [[ $(now_s) -ge $epoch_end ]]; then break; fi
        echo "-- seed ${s} fast sweep (sequential) --" | tee -a "$epoch_log"
        run_safely "seed-${s}" env DREAM_GLOBAL_SEED="$s" ${PYTEST} -q tests src/dream/tests -k "${FAST_FILTER}" ${XDIST} --maxfail=1 \
            --json-report --json-report-file="${RUN_DIR}/epoch${epoch}_seed${s}.json" 2>&1 | tee -a "$epoch_log" || true
        write_manifest_partial "epoch${epoch}_seed${s}_done"
      done
    else
      # Overnight: can run seeds (still sequential to avoid overwhelming, but could be parallelized if needed)
      for s in ${SEEDS}; do
        if [[ $(now_s) -ge $epoch_end ]]; then break; fi
        echo "-- seed ${s} fast sweep --" | tee -a "$epoch_log"
        run_safely "seed-${s}" env DREAM_GLOBAL_SEED="$s" ${PYTEST} -q tests src/dream/tests -k "${FAST_FILTER}" ${XDIST} --maxfail=1 \
            --json-report --json-report-file="${RUN_DIR}/epoch${epoch}_seed${s}.json" 2>&1 | tee -a "$epoch_log" || true
        write_manifest_partial "epoch${epoch}_seed${s}_done"
      done
    fi
  fi

  # 4) E2E smoke (non-slow) — usually sequential via your runner
  if [[ $(now_s) -lt $epoch_end && $RUN_E2E -eq 1 ]]; then
    echo "-- e2e smoke (non-slow) --" | tee -a "$epoch_log"
    if [ -f "${ROOT}/scripts/run-e2e.sh" ]; then
        run_safely "e2e" bash "${ROOT}/scripts/run-e2e.sh" 2>&1 | tee -a "$epoch_log" || true
    else
        run_safely "e2e" ${PYTEST} -v kloros-e2e/tests/e2e --tb=line -k "not browser and not slow" \
            --json-report --json-report-file="${RUN_DIR}/epoch${epoch}_e2e.json" 2>&1 | tee -a "$epoch_log" || true
    fi
    write_manifest_partial "epoch${epoch}_e2e_done"
  fi

  # 4.5) PHASE Domain Tests (TTS, Conversation, RAG, CodeRepair, SystemHealth) - Feed D-REAM evolution
  if [[ $(now_s) -lt $epoch_end ]]; then
    echo "-- PHASE domain tests (TTS, Conversation, RAG, CodeRepair, SystemHealth) --" | tee -a "$epoch_log"
    run_safely "phase-domains" ${VENV}/python3 /home/kloros/src/phase/run_all_domains.py 2>&1 | tee -a "$epoch_log" || true
    # Update dashboard CSVs with PHASE metrics
    ${VENV}/python3 /home/kloros/src/phase/bridge_phase_to_dashboard.py 2>&1 | tee -a "$epoch_log" || true
    write_manifest_partial "epoch${epoch}_phase_domains_done"
  fi

  # 5) One quick promotion-policy pass to keep policy honest
  if [[ $(now_s) -lt $epoch_end && $RUN_PROMOTION -eq 1 ]]; then
    if command -v make &> /dev/null && grep -q "^promotion:" Makefile 2>/dev/null; then
        echo "-- promotion policy ping --" | tee -a "$epoch_log"
        run_safely "promotion" make promotion 2>&1 | tee -a "$epoch_log" || true
        write_manifest_partial "epoch${epoch}_promotion_done"
    fi
  fi

  # Small breather if we ran hot
  sleep 3
  ((epoch++))
done

# ---- WRAP-UP: concentrate remaining budget on any failures ----
echo ""
echo "==[Wrap-up] Failed-first blitz ==" | tee "$LOGDIR/wrap_up.log"
run_safely "wrap-up" ${PYTEST} --lf ${XDIST} --maxfail=1 \
    --json-report --json-report-file="${RUN_DIR}/wrap_up.json" 2>&1 | tee -a "$LOGDIR/wrap_up.log" || true
write_manifest_partial "wrap_up_done"

# ---- AGGREGATE METRICS ----
# Collect test counts from JSON reports
if command -v jq &> /dev/null; then
    for report in "$RUN_DIR"/*.json; do
        if [[ -f "$report" ]]; then
            passed=$(jq -r '.summary.passed // 0' "$report" 2>/dev/null || echo 0)
            failed=$(jq -r '.summary.failed // 0' "$report" 2>/dev/null || echo 0)
            total=$(jq -r '.summary.total // 0' "$report" 2>/dev/null || echo 0)
            total_tests_run=$((total_tests_run + total))
            total_passed=$((total_passed + passed))
            total_failed=$((total_failed + failed))
        fi
    done
fi

# Write aggregate metrics
cat > "$METRICS_FILE" << EOF
{"metric": "total_tests_run", "value": ${total_tests_run}, "timestamp_utc": "$(now_utc)"}
{"metric": "total_passed", "value": ${total_passed}, "timestamp_utc": "$(now_utc)"}
{"metric": "total_failed", "value": ${total_failed}, "timestamp_utc": "$(now_utc)"}
{"metric": "epochs_completed", "value": $((epoch-1)), "timestamp_utc": "$(now_utc)"}
{"metric": "pass_rate", "value": $(awk "BEGIN {printf \"%.4f\", $total_passed / $total_tests_run}" 2>/dev/null || echo "0.0"), "timestamp_utc": "$(now_utc)"}
EOF

# ---- OBSERVABILITY SUMMARY ----
# Write summary.json for dashboard visibility
if command -v jq &> /dev/null && [[ -f "$HINTS_FILE" ]]; then
    # Read hints for observability
    phase_type_used=$(jq -r '.phase_type // "UNKNOWN"' "$HINTS_FILE" 2>/dev/null || echo "UNKNOWN")
    pass_weights=$(jq -c '.pass_weights // {}' "$HINTS_FILE" 2>/dev/null || echo "{}")
    signals=$(jq -c '.signals // {}' "$HINTS_FILE" 2>/dev/null || echo "{}")
    rationale=$(jq -r '.rationale // ""' "$HINTS_FILE" 2>/dev/null || echo "")

    cat > "$RUN_DIR/summary.json" << SUMMARY_EOF
{
  "run_id": "${RUN_ID}",
  "completed_at_utc": "$(now_utc)",
  "adaptive_hints": {
    "phase_type": "${phase_type_used}",
    "pass_weights": ${pass_weights},
    "signals": ${signals},
    "rationale": "${rationale}"
  },
  "execution": {
    "epochs_completed": $((epoch-1)),
    "passes_run": {
      "last_failed": ${RUN_LAST_FAILED},
      "new_first": ${RUN_NEW_FIRST},
      "seed_sweep": ${RUN_SEED_SWEEP},
      "e2e": ${RUN_E2E},
      "promotion": ${RUN_PROMOTION}
    }
  },
  "results": {
    "total_tests": ${total_tests_run},
    "passed": ${total_passed},
    "failed": ${total_failed},
    "pass_rate": $(awk "BEGIN {printf \"%.4f\", $total_passed / $total_tests_run}" 2>/dev/null || echo "0.0")
  }
}
SUMMARY_EOF
    echo "Observability summary written to: ${RUN_DIR}/summary.json"
fi

# ---- WRITE FINAL MANIFEST ----
COMPLETED_UTC=$(now_utc)

# Promote partial manifest to final if it exists
if [[ -f "$RUN_DIR/manifest.partial.json" ]]; then
    cp "$RUN_DIR/manifest.partial.json" "$RUN_DIR/manifest.json.bak" 2>/dev/null || true
fi

cat > "$RUN_DIR/manifest.json" << EOF
{
  "run_id": "${RUN_ID}",
  "schema_version": ${SCHEMA_VERSION},
  "phase": "${PHASE}",
  "window_utc": {
    "start": "${START_UTC}",
    "end": "${END_UTC}"
  },
  "window_et": {
    "start": "${START_ET}",
    "end": "${END_ET}"
  },
  "completed_at_utc": "${COMPLETED_UTC}",
  "epochs": $((epoch-1)),
  "seeds": [$(echo ${SEEDS} | tr ' ' ',')],
  "test_summary": {
    "total_run": ${total_tests_run},
    "passed": ${total_passed},
    "failed": ${total_failed},
    "pass_rate": $(awk "BEGIN {printf \"%.4f\", $total_passed / $total_tests_run}" 2>/dev/null || echo "0.0")
  },
  "artifacts": {
    "results": "results.jsonl",
    "metrics": "metrics.jsonl",
    "reports": "*.json"
  }
}
EOF

# ---- SUMMARY ----
echo ""
echo "================ Run Summary ================"
echo "RUN_ID: ${RUN_ID}"
echo "Window (ET): ${START_ET}–${END_ET}"
echo "Window (UTC): ${START_UTC}–${END_UTC}"
echo "Completed: ${COMPLETED_UTC}"
echo "Epochs: $((epoch-1))"
echo "Tests run: ${total_tests_run}"
echo "Passed: ${total_passed}"
echo "Failed: ${total_failed}"
echo "Artifacts: ${RUN_DIR}/"
echo ""
echo "Last-failed status:"
${PYTEST} --lf --collect-only 2>&1 | head -20 || true
echo ""
echo "Manifest written to: ${RUN_DIR}/manifest.json"
echo "==================================================="
