#!/bin/bash
# Generate clean environment file for systemd (strip inline comments)

INPUT="/home/kloros/.kloros_env"
OUTPUT="/home/kloros/.kloros_env.clean"
TEMP="/home/kloros/.kloros_env.clean.tmp"

# Process the file: strip inline comments
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines and full-line comments
    if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    # If line contains =, it's a variable assignment
    if [[ "$line" =~ = ]]; then
        # Extract key=value, strip inline comments
        key="${line%%=*}"
        value="${line#*=}"

        # Remove inline comment (everything after #)
        if [[ "$value" =~ '#' ]]; then
            value="${value%%#*}"
        fi

        # Trim whitespace
        key="$(echo "$key" | xargs)"
        value="$(echo "$value" | xargs)"

        # Write clean key=value
        echo "${key}=${value}"
    fi
done < "$INPUT" > "$TEMP"

# Atomic move
mv "$TEMP" "$OUTPUT"
chmod 644 "$OUTPUT"

echo "Generated clean environment file: $OUTPUT"
echo "Lines: $(wc -l < "$OUTPUT")"
