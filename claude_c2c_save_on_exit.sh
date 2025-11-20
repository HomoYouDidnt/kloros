#!/bin/bash

if [ "$USER" = "claude_temp" ] || [ "$LOGNAME" = "claude_temp" ]; then
    /usr/bin/python3 /home/kloros/src/c2c/auto_restore_claude.py save 2>&1 | logger -t claude_c2c
fi
