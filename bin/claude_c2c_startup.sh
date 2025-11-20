#!/bin/bash

RESTORE_OUTPUT=$(/usr/bin/python3 /home/kloros/src/c2c/auto_restore_claude.py restore 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$RESTORE_OUTPUT" ]; then
    RESTORE_FILE="/tmp/claude_c2c_restore_latest.txt"
    echo "$RESTORE_OUTPUT" > "$RESTORE_FILE"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "📋 Claude C2C: Previous session context available"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "View with: cat $RESTORE_FILE"
    echo "Or run: python3 /home/kloros/src/c2c/auto_restore_claude.py restore"
    echo ""
fi
