#!/bin/bash

RESTORE_OUTPUT=$(/usr/bin/python3 /home/kloros/src/c2c/auto_restore_claude.py restore 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$RESTORE_OUTPUT" ]; then
    RESTORE_FILE="/tmp/claude_c2c_restore_latest.txt"
    WELCOME_FILE="/tmp/claude_session_welcome.txt"

    echo "$RESTORE_OUTPUT" > "$RESTORE_FILE"

    cat > "$WELCOME_FILE" << 'EOFWELCOME'
═══════════════════════════════════════════════════════════════
🔄 CLAUDE SESSION CONTEXT AVAILABLE
═══════════════════════════════════════════════════════════════

A previous Claude Code session context has been automatically restored.
Please read the context file and provide it to Claude in your first message.

EOFWELCOME

    cat "$RESTORE_FILE" >> "$WELCOME_FILE"

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "📋 Claude C2C: Previous session context restored"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "Context saved to: $WELCOME_FILE"
    echo ""
    echo "⚠️  IMPORTANT: In your first message to Claude, include:"
    echo "   'Please read /tmp/claude_session_welcome.txt'"
    echo ""
fi
