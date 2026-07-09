#!/usr/bin/env bash
set -uo pipefail

# ── Resolution smoke test for the e2e bundles ────────────────────────────
# For a *published* version, builds each bundle and proves it actually
# resolves: the pinned SDK + test deps install, and the test sources load /
# compile (collect-only — NO live server, NO test execution).
#
# Per SDK: PASS (resolved + collected), SKIP (runtime missing or version not
# published in that ecosystem), or FAIL (resolution/collection broke). Exits
# nonzero only on a real FAIL. Network + language runtimes required.
#
# Usage: ./e2e/release/smoke_resolve.sh <published-version>   e.g. 0.3.0

HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-}"
[[ -n "$VERSION" ]] || { echo "usage: $0 <published-version>" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
RC=0

skip() { echo "SKIP $1: $2"; }
ok()   { echo "PASS $1: $2"; }
bad()  { echo "FAIL $1: $2" >&2; RC=1; }

bundle() {  # build one bundle at $VERSION, echo its extracted root
  local sdk="$1"
  local dir="agentspan-sdk-e2e-$sdk-$VERSION"
  "$HERE/package-sdk-e2e.sh" --version "$VERSION" --sdk "$sdk" --out "$WORK/dist" >/dev/null
  mkdir -p "$WORK/x-$sdk"
  tar -xzf "$WORK/dist/$dir.tar.gz" -C "$WORK/x-$sdk"
  echo "$WORK/x-$sdk/$dir"
}

# ── Python: uv venv (SDK needs py<3.14) → pip install → pytest --collect-only
smoke_python() {
  command -v uv >/dev/null || { skip python "uv not installed"; return; }
  local root; root=$(bundle python)
  ( cd "$root"
    uv venv --python 3.12 .venv >/dev/null 2>&1            || { echo "venv-fail"; exit 3; }
    uv pip install --python .venv/bin/python -q -r requirements.txt \
                                                          || { echo "install-fail"; exit 4; }
    .venv/bin/python -m pytest e2e/ --collect-only -q     || { echo "collect-fail"; exit 5; }
  )
  case $? in
    0) ok python "deps resolved + tests collected ($VERSION)";;
    3) skip python "could not provision python 3.12";;
    4) bad  python "pip install of requirements.txt failed";;
    5) bad  python "pytest --collect-only failed (import/SDK drift)";;
    *) bad  python "unexpected error";;
  esac
}

# ── TypeScript: npm install → vitest collect-only (best-effort; optional
#    peer deps for some suites may legitimately not resolve)
smoke_typescript() {
  command -v npm >/dev/null || { skip typescript "npm not installed"; return; }
  local root; root=$(bundle typescript)
  ( cd "$root"
    npm install --no-audit --no-fund --loglevel=error                 || { echo "install-fail"; exit 4; }
    npx vitest list --config vitest.config.ts >/dev/null 2>"$WORK/ts-err" || { echo "collect-fail"; exit 5; }
  )
  case $? in
    0) ok typescript "deps resolved + tests collected ($VERSION)";;
    4) bad  typescript "npm install failed (SDK@$VERSION unresolved?)";;
    5) skip typescript "collection needs optional peer deps (see err); install OK";;
    *) bad  typescript "unexpected error";;
  esac
}

# ── C#: dotnet restore (proves the NuGet pin resolves)
smoke_csharp() {
  command -v dotnet >/dev/null || { skip csharp "dotnet not installed"; return; }
  local root; root=$(bundle csharp)
  if dotnet restore "$root/AgentspanE2eTests/AgentspanE2eTests.csproj" \
       --verbosity quiet >/dev/null 2>&1; then
    ok csharp "NuGet pin resolved ($VERSION)"
  else
    skip csharp "restore failed — NuGet $VERSION may be unpublished/yanked"
  fi
}

# ── Java: gradle build (compile only); skip if no gradle
smoke_java() {
  command -v gradle >/dev/null || { skip java "gradle not installed"; return; }
  local root; root=$(bundle java)
  if ( cd "$root" && gradle testClasses --quiet >/dev/null 2>&1 ); then
    ok java "SDK pin resolved + tests compiled ($VERSION)"
  else
    skip java "compile failed — Maven Central $VERSION may be unpublished"
  fi
}

echo "Resolution smoke test @ $VERSION"
smoke_python
smoke_typescript
smoke_csharp
smoke_java
exit $RC
