#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '%s\n' "$@"
}

check_cmd() {
  local label="$1"; shift
  if command -v "$label" >/dev/null 2>&1; then
    "$@"
  else
    log "WARN: $label not found"
    return 1
  fi
}

log "== KLoROS Doctor =="

log "-- OS & kernel --"
if [ -r /etc/os-release ]; then
  # shellcheck source=/etc/os-release
  . /etc/os-release
  log "OS: ${NAME:-unknown} ${VERSION_ID:-}" || true
else
  log "WARN: /etc/os-release missing"
fi
uname -a || log "WARN: uname failed"

log "-- CPU --"
if command -v lscpu >/dev/null 2>&1; then
  lscpu | head -20
else
  log "INFO: lscpu unavailable"
fi

log "-- GPU --"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -q | head -40
else
  log "WARN: nvidia-smi not found"
fi

log "-- Python toolchain --"
if command -v python3 >/dev/null 2>&1; then
  pyver=$(python3 --version | awk '{print $2}')
  log "python3: ${pyver}"
  python3 -m pip --version || log "WARN: pip missing"
  if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
    :
  else
    log "FAIL: python>=3.10 required"
    exit 1
  fi
else
  log "FAIL: python3 not found"
  exit 1
fi

log "-- Node toolchain --"
if command -v node >/dev/null 2>&1; then
  node --version
else
  log "WARN: node not installed (expected for media helpers)"
fi

log "-- Media --"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -1
else
  log "WARN: ffmpeg missing"
fi

log "-- Services --"
for svc in ollama tailscaled obs-studio docker; do
  if systemctl list-unit-files "$svc.service" >/dev/null 2>&1; then
    state=$(systemctl is-active "$svc" 2>/dev/null || true)
    log "$svc: ${state:-inactive}"
  fi
done

log "-- Ports --"
if command -v ss >/dev/null 2>&1; then
  ss -tulpn | head -40
else
  log "INFO: ss unavailable"
fi

log "Doctor checks complete"
