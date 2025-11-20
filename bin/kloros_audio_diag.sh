#!/usr/bin/env bash
# KLoROS Audio Diagnostic Script
# READ-ONLY diagnostic mode - safe to run anytime

set -euo pipefail

echo "=================================================================="
echo "KLoROS Audio Binding Diagnostic Report"
echo "=================================================================="
echo "Timestamp: $(date)"
echo "Host: $(hostname)"
echo

echo "=== User Environment ==="
echo "Current UID: $(id -u)"
echo "Current USER: $USER"
echo "XDG_RUNTIME_DIR: ${XDG_RUNTIME_DIR:-<not set>}"

# Check runtime directory ownership
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    if [ -d "$XDG_RUNTIME_DIR" ]; then
        echo "Runtime dir owner: $(stat -c '%u' "$XDG_RUNTIME_DIR") (should be $(id -u))"
        echo "Runtime dir writable: $(test -w "$XDG_RUNTIME_DIR" && echo "YES" || echo "NO")"
    else
        echo "❌ Runtime directory does not exist: $XDG_RUNTIME_DIR"
    fi
else
    echo "❌ XDG_RUNTIME_DIR not set"
fi
echo

echo "=== Audio Device Status ==="
echo "Sound cards:"
cat /proc/asound/cards 2>/dev/null || echo "No sound cards found"
echo

echo "Audio devices:"
cat /proc/asound/devices 2>/dev/null || echo "No audio devices found"
echo

echo "ALSA playback devices:"
aplay -l 2>/dev/null || echo "No playback devices"
echo

echo "ALSA capture devices:"
arecord -l 2>/dev/null || echo "No capture devices"
echo

echo "=== Audio Process Status ==="
echo "Processes using /dev/snd/*:"
if lsof -nP /dev/snd/* 2>/dev/null; then
    echo "❌ Audio devices are busy"
else
    echo "✅ Audio devices are idle"
fi
echo

echo "KLoROS-related processes:"
ps aux | egrep "(kloros|pipewire|vosk|tts)" | grep -v grep || echo "No KLoROS processes found"
echo

echo "=== PipeWire/PulseAudio Status ==="
if command -v pactl >/dev/null; then
    if pactl info >/dev/null 2>&1; then
        echo "✅ PulseAudio/PipeWire connection successful"
        echo "Server info:"
        pactl info | head -8
        echo
        echo "Available sinks:"
        pactl list short sinks || echo "No sinks"
        echo
        echo "Available sources:"
        pactl list short sources || echo "No sources"
    else
        echo "❌ PulseAudio/PipeWire connection failed"
        echo "Error: Connection refused (likely XDG_RUNTIME_DIR mismatch)"
    fi
else
    echo "❌ pactl not available"
fi
echo

echo "=== GPU Status ==="
if command -v nvidia-smi >/dev/null; then
    echo "GPU memory usage:"
    nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader,nounits
    echo
    echo "CUDA compute processes:"
    if nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader | grep -q .; then
        nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
    else
        echo "✅ No CUDA compute processes"
    fi
else
    echo "❌ nvidia-smi not available"
fi
echo

echo "=== SystemD User Services ==="
if command -v systemctl >/dev/null && [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    echo "KLoROS services status:"
    systemctl --user list-units 'kloros*' --no-pager || echo "No KLoROS user services"
    echo
    echo "Audio services status:"
    systemctl --user list-units 'pipewire*' 'wireplumber*' --no-pager || echo "No audio user services"
else
    echo "❌ Cannot check user services (systemctl or XDG_RUNTIME_DIR unavailable)"
fi
echo

echo "=== Recent Audio Logs ==="
if command -v journalctl >/dev/null && [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    echo "Last 20 PipeWire/WirePlumber log entries:"
    journalctl --user -u pipewire -u wireplumber -n 20 --no-pager --since "10 minutes ago" || echo "No recent audio logs"
else
    echo "❌ Cannot check logs (journalctl or XDG_RUNTIME_DIR unavailable)"
fi

echo
echo "=================================================================="
echo "Diagnostic Complete"
echo "=================================================================="

# Quick summary
echo
echo "=== SUMMARY ==="
if [ "$(id -u)" = "1001" ] && [ "${XDG_RUNTIME_DIR:-}" = "/run/user/1001" ]; then
    echo "✅ User environment correct (kloros user with proper runtime dir)"
else
    echo "❌ User environment mismatch"
fi

if command -v pactl >/dev/null && pactl info >/dev/null 2>&1; then
    echo "✅ Audio connection working"
else
    echo "❌ Audio connection failed"
fi

if ! lsof -nP /dev/snd/* 2>/dev/null | grep -q .; then
    echo "✅ Audio devices available"
else
    echo "⚠️  Audio devices busy"
fi

echo
