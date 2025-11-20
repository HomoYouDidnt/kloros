#!/bin/bash
#
# ToolGen Challenger Queue TTL Pruning
# Removes challenger files older than 7 days from /tmp/toolgen_challengers/
#

QUEUE_DIR="/tmp/toolgen_challengers"
PROCESSED_DIR="$QUEUE_DIR/processed"
TTL_DAYS=7
LOGFILE="/home/kloros/logs/toolgen_challenger_cleanup.log"

# Create log directory if needed
mkdir -p "$(dirname "$LOGFILE")"

echo "[$(date)] Starting TTL pruning for challenger queue" >> "$LOGFILE"

# Clean main queue (active challengers older than 7 days)
if [ -d "$QUEUE_DIR" ]; then
    FOUND=$(find "$QUEUE_DIR" -maxdepth 1 -name "challenger_*.json" -type f -mtime +$TTL_DAYS 2>/dev/null)
    COUNT=$(echo "$FOUND" | grep -c "challenger_" || echo 0)

    if [ "$COUNT" -gt 0 ]; then
        echo "[$(date)] Removing $COUNT active challengers older than $TTL_DAYS days" >> "$LOGFILE"
        find "$QUEUE_DIR" -maxdepth 1 -name "challenger_*.json" -type f -mtime +$TTL_DAYS -delete
    else
        echo "[$(date)] No active challengers to prune" >> "$LOGFILE"
    fi
else
    echo "[$(date)] Queue directory not found: $QUEUE_DIR" >> "$LOGFILE"
fi

# Clean processed directory
if [ -d "$PROCESSED_DIR" ]; then
    FOUND_PROCESSED=$(find "$PROCESSED_DIR" -name "challenger_*" -type f -mtime +$TTL_DAYS 2>/dev/null)
    COUNT_PROCESSED=$(echo "$FOUND_PROCESSED" | grep -c "challenger_" || echo 0)

    if [ "$COUNT_PROCESSED" -gt 0 ]; then
        echo "[$(date)] Removing $COUNT_PROCESSED processed challengers older than $TTL_DAYS days" >> "$LOGFILE"
        find "$PROCESSED_DIR" -name "challenger_*" -type f -mtime +$TTL_DAYS -delete
    else
        echo "[$(date)] No processed challengers to prune" >> "$LOGFILE"
    fi
fi

echo "[$(date)] TTL pruning completed" >> "$LOGFILE"
