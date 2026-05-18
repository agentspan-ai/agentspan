#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pnpm install --silent
node generate.mjs
echo "Done — updated src/docs/generated-api-data.ts"
