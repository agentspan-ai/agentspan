#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== @agentspan-ai/sdk Test Runner ==="
echo ""

# ── Unit Tests ────────────────────────────────────────────
echo "--- Unit Tests (no server required) ---"
npx vitest run
echo ""

# ── Type Check ────────────────────────────────────────────
echo "--- Type Check ---"
npx tsc --noEmit
echo ""

# ── Build ─────────────────────────────────────────────────
echo "--- Build (ESM + CJS) ---"
npx tsup
echo ""

# ── Validation (requires server + API keys) ───────────────
if [ "${AGENTSPAN_SERVER_URL:-}" != "" ]; then
  echo "--- Validation: SMOKE_TEST ---"
  npx tsx validation/runner.ts \
    --config validation/runs.toml.example \
    --run smoke \
    --group SMOKE_TEST
  echo ""

  if [ "${OPENAI_API_KEY:-}" != "" ]; then
    echo "--- Validation: VERCEL_AI ---"
    npx tsx validation/runner.ts \
      --config validation/runs.toml.example \
      --run vercel_ai
    echo ""

    echo "--- Validation: LANGGRAPH ---"
    npx tsx validation/runner.ts \
      --config validation/runs.toml.example \
      --run langgraph
    echo ""

    echo "--- Validation: LANGCHAIN ---"
    npx tsx validation/runner.ts \
      --config validation/runs.toml.example \
      --run langchain
    echo ""
  else
    echo "Skipping framework validation (OPENAI_API_KEY not set)"
  fi
else
  echo "Skipping validation (AGENTSPAN_SERVER_URL not set)"
  echo "To run: AGENTSPAN_SERVER_URL=http://localhost:8080/api OPENAI_API_KEY=sk-... ./scripts/test.sh"
fi

echo "=== Done ==="
