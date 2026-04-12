#!/usr/bin/env bash
set -uo pipefail

# Run all matching examples in both Python and TypeScript SDKs.
# Outputs a markdown table with file name, status, and execution IDs.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TIMEOUT="${1:-30}"  # seconds per example

echo "| Framework | # | Example | Python | TS | Py ExecID | TS ExecID |"
echo "|-----------|---|---------|--------|----|-----------|-----------|"

for fw in langgraph openai adk quickstart; do
    py_dir="$REPO_ROOT/sdk/python/examples/$fw"
    ts_dir="$REPO_ROOT/sdk/typescript/examples/$fw"

    # Get Python files
    py_files=$(ls "$py_dir"/*.py 2>/dev/null | grep -v '__' | grep -v 'settings' | sort)

    for py_file in $py_files; do
        base=$(basename "$py_file" .py)
        num=$(echo "$base" | grep -oE '^[0-9]+' || echo "?")
        name=$(echo "$base" | sed 's/^[0-9]*_//')

        # Find matching TS file
        ts_file=$(ls "$ts_dir"/${num}-*.ts "$ts_dir"/${num}_*.ts 2>/dev/null | head -1)

        # Run Python
        py_s="-"; py_id="-"
        py_out=$( (cd "$REPO_ROOT/sdk/python" && timeout "$TIMEOUT" uv run python "examples/$fw/$base.py") 2>&1)
        py_id=$(echo "$py_out" | grep -oE "Execution ID: [0-9a-f-]{36}" | head -1 | cut -d' ' -f3)
        if echo "$py_out" | grep -q "Status: COMPLETED"; then py_s="✅"
        elif echo "$py_out" | grep -q "Status: FAILED"; then py_s="❌"
        elif echo "$py_out" | grep -q "ModuleNotFoundError\|ImportError"; then py_s="⚠️dep"
        elif echo "$py_out" | grep -q "EOFError"; then py_s="⚠️stdin"
        else py_s="⏱️"; fi
        [ -z "$py_id" ] && py_id="-"

        # Run TypeScript
        ts_s="-"; ts_id="-"
        if [ -n "$ts_file" ]; then
            ts_base=$(basename "$ts_file")
            ts_out=$( (cd "$REPO_ROOT/sdk/typescript" && timeout "$TIMEOUT" npx tsx "examples/$fw/$ts_base") 2>&1)
            ts_id=$(echo "$ts_out" | grep -oE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" | head -1)
            if echo "$ts_out" | grep -q "Status: COMPLETED"; then ts_s="✅"
            elif echo "$ts_out" | grep -q "Status: FAILED"; then ts_s="❌"
            elif echo "$ts_out" | grep -q "Cannot find module\|ERR_MODULE"; then ts_s="⚠️dep"
            elif echo "$ts_out" | grep -q "EOFError\|readline"; then ts_s="⚠️stdin"
            else ts_s="⏱️"; fi
            [ -z "$ts_id" ] && ts_id="-"
        fi

        echo "| $fw | $num | $name | $py_s | $ts_s | $py_id | $ts_id |"
    done
done
