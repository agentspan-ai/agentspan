#!/usr/bin/env bash
# Export the SDK e2e suites as a self-contained bundle that downstream hosts
# (e.g. orkes-conductor) download from an agentspan release and run against
# their own embedded server — so the e2e suites stay single-source-of-truth
# here and are pinned by release tag there.
#
# Consumed by orkes-conductor's .github/workflows/agentspan-sdk-e2e.yaml, which
# downloads the two release assets this produces:
#   - agentspan-e2e-bundle.tar.gz        (top-level dir: agentspan-e2e/)
#   - agentspan-e2e-bundle.manifest.txt  (provenance)
#
# Layout inside the tarball (consumer sets BUNDLE=.../agentspan-e2e):
#   sdk/java/        standalone gradle project -> ./gradlew test -Pe2e
#   sdk/python/      uv project                -> uv run pytest e2e/
#   sdk/typescript/  npm project               -> npx vitest run tests/e2e/
#   sdk/csharp/      dotnet solution           -> dotnet test tests/AgentspanE2eTests/...
#   cli/             go module                 -> go build -o agentspan .
#   e2e/TEST_SETUP.md
#
# Uses `git archive`, so the bundle contains exactly the tracked files at REF
# (no build/, node_modules/, .venv/, bin/, obj/ — those are gitignored). That
# keeps it reproducible and tied to the release commit.
#
# Usage: e2e/export-e2e-bundle.sh [OUT_DIR] [REF]
#   OUT_DIR  directory for the output assets (default: dist)
#   REF      git ref to export             (default: HEAD)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${1:-dist}"
REF="${2:-HEAD}"

# Paths included in the bundle. Each must be tracked in git at REF.
PATHS=(sdk/java sdk/python sdk/typescript sdk/csharp cli e2e/TEST_SETUP.md)

# Provenance.
VERSION="$(sed -n 's/^version=//p' sdk/java/gradle.properties 2>/dev/null | head -1)"
COMMIT="$(git rev-parse "$REF")"
SHORT="$(git rev-parse --short "$REF")"
DESCRIBE="$(git describe --tags --always "$REF" 2>/dev/null || echo "$SHORT")"
BUILT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
STAGING="$(mktemp -d)"
DEST="$STAGING/agentspan-e2e"
mkdir -p "$DEST"
trap 'rm -rf "$STAGING"' EXIT

echo "Exporting tracked files at $REF ($SHORT) into bundle ..."
# git archive preserves full paths (sdk/java/..., cli/..., e2e/TEST_SETUP.md).
git archive --format=tar "$REF" -- "${PATHS[@]}" | tar -x -C "$DEST"

# Fail loud if anything the consumer relies on is missing.
for p in sdk/java sdk/python sdk/typescript sdk/csharp cli e2e/TEST_SETUP.md; do
  if [[ ! -e "$DEST/$p" ]]; then
    echo "ERROR: '$p' is missing from the bundle (not tracked at $REF?)." >&2
    exit 1
  fi
done

TARBALL="$OUT_DIR/agentspan-e2e-bundle.tar.gz"
MANIFEST="$OUT_DIR/agentspan-e2e-bundle.manifest.txt"

tar -czf "$TARBALL" -C "$STAGING" agentspan-e2e

cat > "$MANIFEST" <<EOF
AgentSpan SDK E2E Bundle
repo:     agentspan-ai/agentspan
ref:      $REF
describe: $DESCRIBE
commit:   $COMMIT
version:  ${VERSION:-unknown}
built:    $BUILT
sdks:     java, python, typescript, csharp
cli:      included
layout:   agentspan-e2e/{sdk/<lang>, cli, e2e/TEST_SETUP.md}
EOF

echo "Wrote:"
echo "  $TARBALL ($(du -h "$TARBALL" | cut -f1))"
echo "  $MANIFEST"
echo "--- manifest ---"
cat "$MANIFEST"
