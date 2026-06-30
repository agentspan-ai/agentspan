#!/usr/bin/env bash
set -euo pipefail

# ── Validator for package-sdk-e2e.sh ─────────────────────────────────────────
# Builds the bundles at a throwaway version and asserts, per bundle:
#   - tarball exists, extracts to the expected dir
#   - carries an executable, syntactically-valid run.sh + README + manifest
#   - every test source from the repo made it in (file-count parity)
#   - the SDK is pinned at the version, with no @VERSION@ placeholder left
#   - generated manifests are well-formed (JSON / XML) and wired correctly
# All checks are static + deterministic (no network, no live server).
# Run: ./e2e/release/test_package_sdk_e2e.sh

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="9.9.9-test"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "  ok: $*"; }

"$HERE/package-sdk-e2e.sh" --version "$VERSION" --out "$WORK/dist" >/dev/null

# Extract a bundle and run the checks shared by every SDK. Echoes the
# extracted bundle root so SDK-specific checks can keep going.
common_checks() {
  local sdk="$1" manifest="$2" pin="$3" source="$4" src_glob="$5"
  local tar="$WORK/dist/agentspan-sdk-e2e-$sdk-$VERSION.tar.gz"
  local dir="agentspan-sdk-e2e-$sdk-$VERSION"

  [[ -f "$tar" ]] || fail "$sdk: tarball not produced ($tar)"
  rm -rf "$WORK/x-$sdk"; mkdir -p "$WORK/x-$sdk"
  tar -xzf "$tar" -C "$WORK/x-$sdk"
  local root="$WORK/x-$sdk/$dir"

  [[ -d "$root" ]]           || fail "$sdk: tarball does not extract to $dir/"
  [[ -f "$root/run.sh" ]]    || fail "$sdk: missing run.sh"
  [[ -x "$root/run.sh" ]]    || fail "$sdk: run.sh not executable"
  bash -n "$root/run.sh"     || fail "$sdk: run.sh has a bash syntax error"
  [[ -f "$root/README.md" ]] || fail "$sdk: missing README.md"
  [[ -f "$root/$source" ]]   || fail "$sdk: missing test source $source"
  [[ -f "$root/$manifest" ]] || fail "$sdk: missing manifest $manifest"

  # No placeholder may survive anywhere in the bundle.
  ! grep -rq '@VERSION@' "$root" || fail "$sdk: leftover @VERSION@ placeholder"
  # Manifest must pin the published SDK at this exact version.
  grep -qF "$pin" "$root/$manifest" \
    || fail "$sdk: manifest $manifest does not pin SDK ($pin)"

  # Every test source in the repo must be present in the bundle.
  local want have
  want=$(find $src_glob -maxdepth 1 -type f | wc -l | tr -d ' ')
  have=$(find "$root" -type f \( -name '*.py' -o -name '*.ts' -o -name '*.java' -o -name '*.cs' \) \
         ! -name 'Settings.cs' | wc -l | tr -d ' ')
  [[ "$have" -ge "$want" ]] \
    || fail "$sdk: dropped sources — repo has $want, bundle has $have"

  echo "$root"
}

# ── Python ───────────────────────────────────────────────────────────────
root=$(common_checks python "requirements.txt" "conductor-agent-sdk==$VERSION" \
  "e2e/conftest.py" "$REPO_ROOT/sdk/python/e2e/*.py")
# Test sources must be syntactically valid Python (compile only, no imports).
python3 -m py_compile "$root"/e2e/*.py || fail "python: a test file has a syntax error"
grep -q "mcp-testkit" "$root/requirements.txt" || fail "python: requirements missing mcp-testkit"
pass "python: bundle valid, sources compile, pins SDK==$VERSION"

# ── TypeScript ─────────────────────────────────────────────────────────────
root=$(common_checks typescript "package.json" \
  "\"@conductor-oss/conductor-agent-sdk\": \"$VERSION\"" "tests/e2e/helpers.ts" \
  "$REPO_ROOT/sdk/typescript/tests/e2e/*.ts")
jq -e . "$root/package.json"  >/dev/null || fail "typescript: package.json is not valid JSON"
jq -e . "$root/tsconfig.json" >/dev/null || fail "typescript: tsconfig.json is not valid JSON"
# Standalone config must resolve the SDK from npm (no src alias) and target e2e.
! grep -q "src/index.ts" "$root/vitest.config.ts" \
  || fail "typescript: vitest.config still aliases the in-repo SDK source"
grep -q "tests/e2e" "$root/vitest.config.ts" \
  || fail "typescript: vitest.config does not include tests/e2e"
pass "typescript: bundle valid, config standalone, pins SDK@$VERSION"

# ── Java ─────────────────────────────────────────────────────────────────
root=$(common_checks java "build.gradle" \
  "org.conductoross.conductor:conductor-agent-sdk:$VERSION" \
  "src/test/java/BaseTest.java" "$REPO_ROOT/sdk/java/e2e/*.java")
[[ -f "$root/settings.gradle" ]] || fail "java: missing settings.gradle"
# Default-package sources must land directly under src/test/java.
[[ -f "$root/src/test/java/Suite1BasicValidation.java" ]] \
  || fail "java: sources not under src/test/java"
# Must NOT exclude the e2e-tagged tests (the in-repo build does by default).
! grep -q "excludeTags" "$root/build.gradle" \
  || fail "java: build.gradle excludes e2e-tagged tests"
pass "java: bundle valid, runs e2e tags, pins SDK:$VERSION"

# ── C# ─────────────────────────────────────────────────────────────────────
root=$(common_checks csharp "AgentspanE2eTests/AgentspanE2eTests.csproj" \
  "Include=\"conductor-agent-sdk\" Version=\"$VERSION\"" \
  "AgentspanE2eTests/Settings.cs" "$REPO_ROOT/sdk/csharp/tests/AgentspanE2eTests/*.cs")
csproj="$root/AgentspanE2eTests/AgentspanE2eTests.csproj"
python3 -c "import xml.dom.minidom,sys; xml.dom.minidom.parse(sys.argv[1])" "$csproj" \
  || fail "csharp: csproj is not well-formed XML"
# Must depend on the published NuGet, not the in-repo project.
! grep -q "ProjectReference" "$csproj" \
  || fail "csharp: csproj still uses in-repo ProjectReference"
[[ -f "$root/AgentspanE2eTests/Settings.cs" ]] \
  || fail "csharp: vendored Settings.cs missing"
pass "csharp: bundle valid, uses published NuGet, pins $VERSION"

echo "ALL BUNDLES VALID"
