#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLOROS_HOME="/home/kloros"
VENV_DIR="${KLOROS_HOME}/.venv"
KLOROS_DATA_DIR="${KLOROS_HOME}/.kloros"
LOG_DIR="${KLOROS_DATA_DIR}/logs"
PID_DIR="${KLOROS_DATA_DIR}/pids"
KLOROS_SRC="${KLOROS_HOME}/src"

REFLECTION_DAEMON_PID_FILE="${PID_DIR}/reflection_consumer_daemon.pid"
HOUSEKEEPING_DAEMON_PID_FILE="${PID_DIR}/housekeeping_daemon.pid"

REFLECTION_DAEMON_LOG="${LOG_DIR}/reflection_daemon.log"
HOUSEKEEPING_DAEMON_LOG="${LOG_DIR}/housekeeping_daemon.log"

REFLECTION_DAEMON_MODULE="kloros.orchestration.reflection_consumer_daemon"
HOUSEKEEPING_DAEMON_MODULE="kloros.orchestration.housekeeping_daemon"

DAEMON_CHECK_INTERVAL=5
DAEMON_CHECK_MAX_RETRIES=10

usage() {
    cat << EOF
Usage: $(basename "$0") {start|stop|restart|status|force-stop}

Commands:
    start           Start both reflection and housekeeping daemons
    stop            Gracefully stop both daemons
    restart         Restart both daemons
    status          Check status of both daemons
    force-stop      Force-kill both daemons (use with caution)

Options:
    -h, --help      Show this help message

Examples:
    $(basename "$0") start
    $(basename "$0") status
    $(basename "$0") restart

EOF
    exit 0
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

info() {
    echo "[INFO] $*"
}

warn() {
    echo "[WARN] $*"
}

debug() {
    if [[ "${DEBUG:-0}" == "1" ]]; then
        echo "[DEBUG] $*"
    fi
}

verify_environment() {
    if [[ ! -d "$VENV_DIR" ]]; then
        error "Virtual environment not found at $VENV_DIR"
    fi

    if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
        error "Cannot find venv activation script at ${VENV_DIR}/bin/activate"
    fi

    if [[ ! -d "$KLOROS_DATA_DIR" ]]; then
        error "KLoROS data directory not found at $KLOROS_DATA_DIR"
    fi

    if [[ ! -d "$KLOROS_SRC" ]]; then
        error "KLoROS source directory not found at $KLOROS_SRC"
    fi

    info "Environment verified: venv=$VENV_DIR, src=$KLOROS_SRC"
}

ensure_directories() {
    mkdir -p "$LOG_DIR" || error "Cannot create log directory: $LOG_DIR"
    mkdir -p "$PID_DIR" || error "Cannot create pid directory: $PID_DIR"
    debug "Directories ensured: logs=$LOG_DIR, pids=$PID_DIR"
}

check_if_running() {
    local pid_file="$1"
    local daemon_name="$2"

    if [[ ! -f "$pid_file" ]]; then
        return 1
    fi

    local pid=$(<"$pid_file")

    if ! kill -0 "$pid" 2>/dev/null; then
        debug "Stale PID file detected for $daemon_name (PID: $pid not running)"
        rm -f "$pid_file"
        return 1
    fi

    return 0
}

get_daemon_status() {
    local pid_file="$1"
    local daemon_name="$2"

    if check_if_running "$pid_file" "$daemon_name"; then
        local pid=$(<"$pid_file")
        echo "RUNNING (PID: $pid)"
        return 0
    else
        echo "STOPPED"
        return 1
    fi
}

start_daemon() {
    local daemon_module="$1"
    local daemon_name="$2"
    local pid_file="$3"
    local log_file="$4"

    info "Starting $daemon_name..."

    if check_if_running "$pid_file" "$daemon_name"; then
        local pid=$(<"$pid_file")
        warn "$daemon_name is already running (PID: $pid)"
        return 0
    fi

    source "${VENV_DIR}/bin/activate"

    export PYTHONPATH="${KLOROS_SRC}:${PYTHONPATH:-}"

    local daemon_start_cmd="python -m ${daemon_module}"

    nohup $daemon_start_cmd >> "$log_file" 2>&1 &
    local daemon_pid=$!

    sleep 2

    if ! kill -0 "$daemon_pid" 2>/dev/null; then
        error "Failed to start $daemon_name (PID: $daemon_pid not found after 2s). Check logs: $log_file"
    fi

    echo "$daemon_pid" > "$pid_file"
    info "$daemon_name started successfully (PID: $daemon_pid)"
    info "Log file: $log_file"
}

stop_daemon() {
    local pid_file="$1"
    local daemon_name="$2"

    if ! check_if_running "$pid_file" "$daemon_name"; then
        warn "$daemon_name is not running"
        return 0
    fi

    local pid=$(<"$pid_file")
    info "Stopping $daemon_name (PID: $pid)..."

    kill "$pid" || warn "Failed to send SIGTERM to $daemon_name (PID: $pid)"

    local retry_count=0
    while [[ $retry_count -lt $DAEMON_CHECK_MAX_RETRIES ]]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            info "$daemon_name stopped successfully"
            rm -f "$pid_file"
            return 0
        fi

        sleep $DAEMON_CHECK_INTERVAL
        retry_count=$((retry_count + 1))
    done

    warn "Daemon did not stop gracefully after $((DAEMON_CHECK_MAX_RETRIES * DAEMON_CHECK_INTERVAL))s, force-killing..."
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    info "$daemon_name force-stopped"
}

force_stop_daemon() {
    local pid_file="$1"
    local daemon_name="$2"

    if [[ ! -f "$pid_file" ]]; then
        info "$daemon_name is not running"
        return 0
    fi

    local pid=$(<"$pid_file")

    if ! kill -0 "$pid" 2>/dev/null; then
        info "$daemon_name is not running (cleaning up stale PID file)"
        rm -f "$pid_file"
        return 0
    fi

    info "Force-stopping $daemon_name (PID: $pid)..."
    kill -9 "$pid" 2>/dev/null || warn "Failed to force-kill $daemon_name"
    rm -f "$pid_file"
    info "$daemon_name force-stopped"
}

start_daemons() {
    info "Starting KLoROS reflection and housekeeping daemons..."
    verify_environment
    ensure_directories

    start_daemon "$REFLECTION_DAEMON_MODULE" "ReflectionConsumerDaemon" \
        "$REFLECTION_DAEMON_PID_FILE" "$REFLECTION_DAEMON_LOG"

    start_daemon "$HOUSEKEEPING_DAEMON_MODULE" "HousekeepingDaemon" \
        "$HOUSEKEEPING_DAEMON_PID_FILE" "$HOUSEKEEPING_DAEMON_LOG"

    info "Both daemons started successfully"
    status_daemons
}

stop_daemons() {
    info "Stopping KLoROS reflection and housekeeping daemons..."

    stop_daemon "$REFLECTION_DAEMON_PID_FILE" "ReflectionConsumerDaemon"
    stop_daemon "$HOUSEKEEPING_DAEMON_PID_FILE" "HousekeepingDaemon"

    info "Both daemons stopped successfully"
}

force_stop_daemons() {
    info "Force-stopping KLoROS reflection and housekeeping daemons..."

    force_stop_daemon "$REFLECTION_DAEMON_PID_FILE" "ReflectionConsumerDaemon"
    force_stop_daemon "$HOUSEKEEPING_DAEMON_PID_FILE" "HousekeepingDaemon"

    info "Both daemons force-stopped"
}

restart_daemons() {
    info "Restarting KLoROS reflection and housekeeping daemons..."
    stop_daemons
    sleep 2
    start_daemons
}

status_daemons() {
    info "Daemon Status:"
    echo ""

    local reflection_status
    reflection_status=$(get_daemon_status "$REFLECTION_DAEMON_PID_FILE" "ReflectionConsumerDaemon" 2>/dev/null) || true

    local housekeeping_status
    housekeeping_status=$(get_daemon_status "$HOUSEKEEPING_DAEMON_PID_FILE" "HousekeepingDaemon" 2>/dev/null) || true

    printf "  ReflectionConsumerDaemon:  %s\n" "$reflection_status"
    printf "  HousekeepingDaemon:        %s\n" "$housekeeping_status"

    echo ""
    echo "Log Files:"
    printf "  Reflection:   %s\n" "$REFLECTION_DAEMON_LOG"
    printf "  Housekeeping: %s\n" "$HOUSEKEEPING_DAEMON_LOG"

    echo ""
    echo "PID Files:"
    printf "  Reflection:   %s\n" "$REFLECTION_DAEMON_PID_FILE"
    printf "  Housekeeping: %s\n" "$HOUSEKEEPING_DAEMON_PID_FILE"
}

main() {
    if [[ $# -eq 0 ]]; then
        usage
    fi

    case "$1" in
        start)
            start_daemons
            ;;
        stop)
            stop_daemons
            ;;
        restart)
            restart_daemons
            ;;
        status)
            status_daemons
            ;;
        force-stop)
            force_stop_daemons
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown command: $1"
            ;;
    esac
}

main "$@"
