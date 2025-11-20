#!/usr/bin/env bash
# Safe shell wrapper for AI assistants
# Blocks dangerous commands that could crash KLoROS or GPU workers

set -euo pipefail

echo "=== KLoROS Assistant Shell (Safe Mode) ==="
echo "Commands are filtered to prevent system damage"
echo "Type 'exit' to quit, 'help' for safe commands"
echo

# List of safe diagnostic commands
safe_commands=(
    "id -u" "echo \$XDG_RUNTIME_DIR" "pactl info" "pactl list short"
    "lsof -nP /dev/snd/*" "aplay -l" "arecord -l" "nvidia-smi"
    "nvidia-smi --query-compute-apps" "ps aux" "systemctl --user status"
    "journalctl --user" "cat /proc/asound" "ls" "pwd" "which"
    "stat" "test" "grep" "head" "tail" "wc"
)

show_help() {
    echo "=== Safe Commands Available ==="
    printf '%s\n' "${safe_commands[@]}" | sort
    echo
    echo "=== Blocked (Dangerous) Patterns ==="
    echo "- kill/pkill commands"
    echo "- systemctl restart/stop"
    echo "- nvidia-smi --gpu-reset"
    echo "- Direct GPU resets"
    echo
}

while IFS= read -r line; do
    # Handle special commands
    case "$line" in
        "exit"|"quit") 
            echo "👋 Exiting safe shell"
            exit 0 ;;
        "help"|"?")
            show_help
            continue ;;
        "")
            continue ;;
    esac
    
    # Check for dangerous patterns
    case "$line" in
        *" kill "*|kill\ *|pkill\ *)
            echo "🚫 [BLOCKED] Kill commands not allowed in safe mode"
            echo "   Use: ~/bin/safe_kill.sh <pid> for CUDA processes"
            continue ;;
        *systemctl*restart*|*systemctl*stop*)
            echo "🚫 [BLOCKED] Service restart/stop not allowed in safe mode"
            echo "   Use: ~/bin/audio_reset_safe.sh for audio restart"
            continue ;;
        *nvidia-smi*-r*|*nvidia-smi*reset*|*gpu-reset*)
            echo "🚫 [BLOCKED] GPU reset commands not allowed in safe mode"
            continue ;;
        *rm\ -rf*|*rm\ -r\ /*|*rm\ /*|*rmdir\ /*)
            echo "🚫 [BLOCKED] Dangerous file deletion not allowed"
            continue ;;
        *chmod\ 777*|*chown\ root*)
            echo "🚫 [BLOCKED] Dangerous permission changes not allowed"
            continue ;;
    esac
    
    # Execute safe command
    echo "🔍 Executing: $line"
    eval "$line" || echo "❌ Command failed with exit code $?"
    echo
    
done
