#!/bin/bash
#
# SPICA Instance Cleanup
# Runs every 10 minutes via cron to prevent disk space issues
#

SPICA_DIR="/home/kloros/experiments/spica/instances"
MAX_AGE_MINUTES=15
MAX_INSTANCES=50

# Delete instances older than MAX_AGE_MINUTES
echo "[$(date)] Starting SPICA cleanup..."

deleted_count=0
for dir in "$SPICA_DIR"/spica-*; do
    if [ -d "$dir" ]; then
        # Check if directory is older than MAX_AGE_MINUTES
        if [ "$(find "$dir" -maxdepth 0 -mmin +$MAX_AGE_MINUTES)" ]; then
            # Fix permissions before deleting (pytest creates read-only cache files)
            chmod -R u+w "$dir" 2>/dev/null || true
            rm -rf "$dir" 2>/dev/null || true
            ((deleted_count++))
        fi
    fi
done

# Keep only the most recent MAX_INSTANCES
current_count=$(find "$SPICA_DIR" -maxdepth 1 -type d -name "spica-*" | wc -l)

if [ "$current_count" -gt "$MAX_INSTANCES" ]; then
    excess=$((current_count - MAX_INSTANCES))
    echo "Too many instances ($current_count), removing $excess oldest..."

    # Delete oldest instances
    find "$SPICA_DIR" -maxdepth 1 -type d -name "spica-*" -printf '%T@ %p\n' | \
        sort -n | \
        head -n "$excess" | \
        cut -d' ' -f2- | \
        xargs -r rm -rf

    ((deleted_count += excess))
fi

disk_usage=$(df -h / | awk 'NR==2 {print $5}')
echo "[$(date)] Cleanup complete: deleted $deleted_count instances, disk usage: $disk_usage"
