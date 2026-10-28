#!/bin/zsh
# Weekly self-improvement run: harvest feedback -> eval cases, try a gated playbook fix, post the report.
# Installed as a launchd job by scripts/install_weekly.sh; logs to ~/.oncall-agent/weekly.log.
set -u
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export PYTHONPATH=src
PY=.venv/bin/python
echo "=== $(date -u +%FT%TZ) weekly run"
$PY -u scripts/harvest_cases.py
$PY -u scripts/improve.py --attempts 2
$PY -u scripts/report.py --days 7 --post-dm
