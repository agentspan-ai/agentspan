#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8000}"

mkdocs serve -a "127.0.0.1:${PORT}"
