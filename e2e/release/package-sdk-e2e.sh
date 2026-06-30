#!/usr/bin/env bash
set -euo pipefail

# ── SDK E2E Release Packager ─────────────────────────────────────────────
# Packages each SDK's e2e suite into a self-contained, version-stamped
# tarball that downstream repos (e.g. orkes-io/orkes-conductor) can pin to a
# specific agentspan release and run against a live server.
#
# Each bundle is a standalone test project: it carries the test sources +
# support files and a generated build/manifest file that pins the PUBLISHED
# SDK at the release version (PyPI / npm / Maven Central / NuGet). It does NOT
# vendor the SDK source — the bundle's version is the contract.
#
# Usage:
#   ./e2e/release/package-sdk-e2e.sh --version 0.4.0
#   ./e2e/release/package-sdk-e2e.sh --version 0.4.0 --sdk java
#   ./e2e/release/package-sdk-e2e.sh --version 0.4.0 --sdk python --sdk typescript
#   ./e2e/release/package-sdk-e2e.sh --version 0.4.0 --out /tmp/dist
#
# Output: <out>/agentspan-sdk-e2e-<sdk>-<version>.tar.gz   (default out: e2e/release/dist)

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$REPO_ROOT/e2e/release/dist"
VERSION=""
SDKS=()

# ── Parse arguments ─────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --sdk)     SDKS+=("$2"); shift 2 ;;
    --out)     OUT_DIR="$2"; shift 2 ;;
    *)         echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "ERROR: --version is required (e.g. --version 0.4.0)" >&2
  exit 1
fi

# Default to all SDKs when none specified; expand the "all" alias.
if [[ ${#SDKS[@]} -eq 0 ]]; then
  SDKS=(python typescript java csharp)
fi
if [[ " ${SDKS[*]} " == *" all "* ]]; then
  SDKS=(python typescript java csharp)
fi

mkdir -p "$OUT_DIR"

# ── Helpers ──────────────────────────────────────────────────────────────

# Replace @VERSION@ in every generated file under the staging dir. Test
# sources are copied verbatim and never contain the placeholder, so this only
# touches the manifests/runners/READMEs we author below.
substitute_version() {
  local dir="$1"
  find "$dir" -type f -print0 | xargs -0 sed -i.bak "s/@VERSION@/$VERSION/g"
  find "$dir" -name '*.bak' -delete
}

make_tarball() {
  local name="$1"  # e.g. agentspan-sdk-e2e-python-0.4.0
  substitute_version "$OUT_DIR/$name"
  tar -czf "$OUT_DIR/$name.tar.gz" -C "$OUT_DIR" "$name"
  rm -rf "$OUT_DIR/$name"
  echo "  → $OUT_DIR/$name.tar.gz"
}

# ── Python ─────────────────────────────────────────────────────────────────

pack_python() {
  local name="agentspan-sdk-e2e-python-$VERSION"
  local stage="$OUT_DIR/$name"
  echo "Packaging Python e2e ($name)..."
  rm -rf "$stage"; mkdir -p "$stage/e2e"

  cp "$REPO_ROOT"/sdk/python/e2e/*.py "$stage/e2e/"

  cat > "$stage/requirements.txt" <<'EOF'
# Pins the published SDK to the agentspan release this bundle was cut from.
conductor-agent-sdk==@VERSION@

# Test runner + e2e support deps.
pytest>=7.0
pytest-xdist>=3.0
pytest-timeout>=2.0
pytest-rerunfailures>=14.0
requests>=2.28

# Live MCP server used by the MCP tool suites.
mcp-testkit
EOF

  cat > "$stage/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Runs the Python SDK e2e suite against a live agentspan server.
#
# Required services (NOT started by this script):
#   - agentspan server  → AGENTSPAN_SERVER_URL   (default http://localhost:6767/api)
#   - agentspan CLI      → AGENTSPAN_CLI_PATH      (default: `agentspan` on PATH)
#   - mcp-testkit        → MCP_TESTKIT_URL         (default http://localhost:3001)
# Optional:
#   - AGENTSPAN_LLM_MODEL (default openai/gpt-4o-mini) + provider API keys
#
# Usage: ./run.sh [extra pytest args]   e.g. ./run.sh -k suite1 -n 4
HERE="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="${RESULTS_DIR:-$HERE/e2e-results}"
mkdir -p "$RESULTS_DIR"

python -m pip install -r "$HERE/requirements.txt"

PYTEST_ARGS=("$HERE/e2e/" "-v" "--tb=short" "--junitxml=$RESULTS_DIR/junit.xml")
python -m pytest "${PYTEST_ARGS[@]}" "$@"

python "$HERE/e2e/report_generator.py" \
  "$RESULTS_DIR/junit.xml" "$RESULTS_DIR/report.html" || true
echo "Report: $RESULTS_DIR/report.html"
EOF
  chmod +x "$stage/run.sh"

  cat > "$stage/README.md" <<'EOF'
# agentspan Python SDK — E2E suite @VERSION@

Self-contained end-to-end tests for the agentspan Python SDK, pinned to
release **@VERSION@**. Pulls `conductor-agent-sdk==@VERSION@` from PyPI — no
SDK source is vendored, so the suite always tests the published artifact.

## Prerequisites (you provide these)

| Service          | Env var                | Default                      |
|------------------|------------------------|------------------------------|
| agentspan server | `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api`  |
| agentspan CLI    | `AGENTSPAN_CLI_PATH`   | `agentspan` (on `PATH`)      |
| mcp-testkit      | `MCP_TESTKIT_URL`      | `http://localhost:3001`      |
| LLM model        | `AGENTSPAN_LLM_MODEL`  | `openai/gpt-4o-mini`         |

The server, CLI, and `mcp-testkit` must already be running and must be the
**@VERSION@** build for results to be meaningful.

## Run

```bash
./run.sh            # full suite
./run.sh -k suite1  # filter, plus any pytest args
```

JUnit XML + HTML report land in `e2e-results/`.
EOF

  make_tarball "$name"
}

# ── TypeScript ───────────────────────────────────────────────────────────

pack_typescript() {
  local name="agentspan-sdk-e2e-typescript-$VERSION"
  local stage="$OUT_DIR/$name"
  echo "Packaging TypeScript e2e ($name)..."
  rm -rf "$stage"; mkdir -p "$stage/tests/e2e"

  cp "$REPO_ROOT"/sdk/typescript/tests/e2e/*.ts "$stage/tests/e2e/"

  cat > "$stage/package.json" <<'EOF'
{
  "name": "agentspan-sdk-e2e-typescript",
  "version": "@VERSION@",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run tests/e2e/"
  },
  "dependencies": {
    "@conductor-oss/conductor-agent-sdk": "@VERSION@"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "tsx": "^4.21.0",
    "typescript": "^5.4.0",
    "vitest": "^2.1.9",
    "zod": "^3.25.76",
    "zod-to-json-schema": "^3.23.5"
  }
}
EOF

  # Standalone vitest config: resolve the SDK from the installed npm package
  # (NO src alias, unlike the in-repo config) and collect the bundled e2e
  # tests from their real location here.
  cat > "$stage/vitest.config.ts" <<'EOF'
import { defineConfig } from 'vitest/config';

export default defineConfig({
  esbuild: {
    tsconfigRaw: {
      compilerOptions: {
        experimentalDecorators: true,
        emitDecoratorMetadata: true,
      },
    },
  },
  test: {
    globals: true,
    testTimeout: 60_000,
    pool: 'forks',
    poolOptions: { forks: { maxForks: 3, minForks: 1 } },
    include: ['tests/e2e/*.test.ts'],
    reporters: ['verbose', 'junit'],
    outputFile: { junit: 'e2e-results/junit-ts.xml' },
  },
});
EOF

  cat > "$stage/tsconfig.json" <<'EOF'
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ESNext"],
    "strict": true,
    "esModuleInterop": true,
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["tests/**/*.ts"]
}
EOF

  cat > "$stage/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Runs the TypeScript SDK e2e suite against a live agentspan server.
#
# Required services (NOT started by this script):
#   - agentspan server  → AGENTSPAN_SERVER_URL   (default http://localhost:6767/api)
#   - agentspan CLI      → AGENTSPAN_CLI_PATH      (default: `agentspan` on PATH)
#   - mcp-testkit        → MCP_TESTKIT_URL         (default http://localhost:3001)
# Optional:
#   - AGENTSPAN_LLM_MODEL (default openai/gpt-4o-mini) + provider API keys
#
# Usage: ./run.sh [extra vitest args]   e.g. ./run.sh tests/e2e/test_suite1_basic_validation.test.ts
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
mkdir -p e2e-results

npm install
npx vitest run tests/e2e/ --reporter=verbose --reporter=junit \
  --outputFile.junit=e2e-results/junit-ts.xml "$@"

npx tsx tests/e2e/generate-report.ts \
  e2e-results/junit-ts.xml e2e-results/report-ts.html || true
echo "Report: $HERE/e2e-results/report-ts.html"
EOF
  chmod +x "$stage/run.sh"

  cat > "$stage/README.md" <<'EOF'
# agentspan TypeScript SDK — E2E suite @VERSION@

Self-contained end-to-end tests for the agentspan TypeScript SDK, pinned to
release **@VERSION@**. Resolves `@conductor-oss/conductor-agent-sdk@@VERSION@`
from npm — no SDK source is vendored, so the suite tests the published package.

## Prerequisites (you provide these)

| Service          | Env var                | Default                      |
|------------------|------------------------|------------------------------|
| agentspan server | `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api`  |
| agentspan CLI    | `AGENTSPAN_CLI_PATH`   | `agentspan` (on `PATH`)      |
| mcp-testkit      | `MCP_TESTKIT_URL`      | `http://localhost:3001`      |
| LLM model        | `AGENTSPAN_LLM_MODEL`  | `openai/gpt-4o-mini`         |

## Run

```bash
./run.sh
```

JUnit XML + HTML report land in `e2e-results/`.
EOF

  make_tarball "$name"
}

# ── Java ───────────────────────────────────────────────────────────────────

pack_java() {
  local name="agentspan-sdk-e2e-java-$VERSION"
  local stage="$OUT_DIR/$name"
  echo "Packaging Java e2e ($name)..."
  rm -rf "$stage"; mkdir -p "$stage/src/test/java"

  # The e2e sources are in the default package (no package decl), so they live
  # directly under src/test/java in the standalone Gradle layout.
  cp "$REPO_ROOT"/sdk/java/e2e/*.java "$stage/src/test/java/"

  # Standalone build pins the published SDK; framework/test deps mirror the
  # SDK's own test classpath so the framework-bridge suites compile + link.
  cat > "$stage/build.gradle" <<'EOF'
plugins {
    id 'java'
}

group = 'org.conductoross.conductor'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

ext {
    junitVersion           = '5.11.0'
    langchain4jVersion     = '1.0.0'
    googleAdkVersion       = '1.3.0'
    langgraph4jVersion     = '1.6.0-beta5'
    conductorClientVersion = '5.0.1'
}

dependencies {
    // Pins the published SDK to the agentspan release this bundle was cut from.
    testImplementation 'org.conductoross.conductor:conductor-agent-sdk:@VERSION@'

    testImplementation "org.junit.jupiter:junit-jupiter:${junitVersion}"
    testImplementation "org.conductoross:conductor-client:${conductorClientVersion}"
    testImplementation 'com.fasterxml.jackson.core:jackson-databind:2.17.1'
    testImplementation "dev.langchain4j:langchain4j:${langchain4jVersion}"
    testImplementation "dev.langchain4j:langchain4j-open-ai:${langchain4jVersion}"
    testImplementation "com.google.adk:google-adk:${googleAdkVersion}"
    testImplementation "org.bsc.langgraph4j:langgraph4j-core:${langgraph4jVersion}"
    testImplementation "org.bsc.langgraph4j:langgraph4j-agent-executor:${langgraph4jVersion}"
    testRuntimeOnly 'org.slf4j:slf4j-simple:2.0.13'
}

compileTestJava.options.compilerArgs << '-parameters'

test {
    useJUnitPlatform()  // run every test, including @Tag("e2e")
    testLogging { events 'passed', 'skipped', 'failed' }
    systemProperty 'AGENTSPAN_SERVER_URL',
        System.getProperty('AGENTSPAN_SERVER_URL', System.getenv('AGENTSPAN_SERVER_URL') ?: 'http://localhost:6767/api')
    systemProperty 'AGENTSPAN_LLM_MODEL',
        System.getProperty('AGENTSPAN_LLM_MODEL', System.getenv('AGENTSPAN_LLM_MODEL') ?: 'openai/gpt-4o-mini')
}
EOF

  cat > "$stage/settings.gradle" <<'EOF'
rootProject.name = 'agentspan-sdk-e2e-java'
EOF

  cat > "$stage/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Runs the Java SDK e2e suite against a live agentspan server.
#
# Required services (NOT started by this script):
#   - agentspan server  → AGENTSPAN_SERVER_URL   (default http://localhost:6767/api)
#   - mcp-testkit        → MCP_TESTKIT_URL         (default http://localhost:3001)
# Optional:
#   - AGENTSPAN_LLM_MODEL (default openai/gpt-4o-mini) + provider API keys
#
# Requires a local `gradle` (>= 8) and JDK 21. Usage: ./run.sh [extra gradle args]
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
gradle test \
  -DAGENTSPAN_SERVER_URL="${AGENTSPAN_SERVER_URL:-http://localhost:6767/api}" \
  -DAGENTSPAN_LLM_MODEL="${AGENTSPAN_LLM_MODEL:-openai/gpt-4o-mini}" "$@"
echo "Report: $HERE/build/reports/tests/test/index.html"
EOF
  chmod +x "$stage/run.sh"

  cat > "$stage/README.md" <<'EOF'
# agentspan Java SDK — E2E suite @VERSION@

Self-contained end-to-end tests for the agentspan Java SDK, pinned to release
**@VERSION@**. Resolves `org.conductoross.conductor:conductor-agent-sdk:@VERSION@`
from Maven Central — no SDK source is vendored.

## Prerequisites (you provide these)

| Requirement      | Env var                | Default                      |
|------------------|------------------------|------------------------------|
| JDK 21 + Gradle 8| —                      | —                            |
| agentspan server | `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api`  |
| mcp-testkit      | `MCP_TESTKIT_URL`      | `http://localhost:3001`      |
| LLM model        | `AGENTSPAN_LLM_MODEL`  | `openai/gpt-4o-mini`         |

## Run

```bash
./run.sh                       # full suite
./run.sh --tests 'Suite1*'     # filter, plus any gradle args
```

HTML report lands in `build/reports/tests/test/`.
EOF

  make_tarball "$name"
}

# ── C# ─────────────────────────────────────────────────────────────────────

pack_csharp() {
  local name="agentspan-sdk-e2e-csharp-$VERSION"
  local stage="$OUT_DIR/$name"
  echo "Packaging C# e2e ($name)..."
  rm -rf "$stage"; mkdir -p "$stage/AgentspanE2eTests"

  cp "$REPO_ROOT"/sdk/csharp/tests/AgentspanE2eTests/*.cs "$stage/AgentspanE2eTests/"
  # Vendor the one shared file the in-repo csproj pulled from examples/.
  cp "$REPO_ROOT"/sdk/csharp/examples/Shared/Settings.cs "$stage/AgentspanE2eTests/Settings.cs"

  # Standalone csproj: published NuGet PackageReference replaces the in-repo
  # ProjectReference, and Settings.cs is compiled from the vendored copy.
  cat > "$stage/AgentspanE2eTests/AgentspanE2eTests.csproj" <<'EOF'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <IsPackable>false</IsPackable>
    <IsTestProject>true</IsTestProject>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="xunit" Version="2.9.3" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2">
      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
      <PrivateAssets>all</PrivateAssets>
    </PackageReference>
    <PackageReference Include="Xunit.SkippableFact" Version="1.4.13" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.12.0" />
    <!-- Pins the published SDK to the agentspan release this bundle was cut from. -->
    <PackageReference Include="conductor-agent-sdk" Version="@VERSION@" />
  </ItemGroup>
</Project>
EOF

  cat > "$stage/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Runs the C# SDK e2e suite against a live agentspan server.
#
# Required services (NOT started by this script):
#   - agentspan server  → AGENTSPAN_SERVER_URL   (default http://localhost:6767/api)
#   - mcp-testkit        → MCP_TESTKIT_URL         (default http://localhost:3001)
# Optional:
#   - AGENTSPAN_LLM_MODEL (default openai/gpt-4o-mini) + provider API keys
#
# Requires the .NET 10 SDK. Usage: ./run.sh [extra dotnet test args]
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/AgentspanE2eTests"
dotnet test "$@"
EOF
  chmod +x "$stage/run.sh"

  cat > "$stage/README.md" <<'EOF'
# agentspan C# SDK — E2E suite @VERSION@

Self-contained end-to-end tests for the agentspan .NET SDK, pinned to release
**@VERSION@**. Resolves the `conductor-agent-sdk` NuGet package at **@VERSION@**
— no SDK source is vendored.

## Prerequisites (you provide these)

| Requirement      | Env var                | Default                      |
|------------------|------------------------|------------------------------|
| .NET 10 SDK      | —                      | —                            |
| agentspan server | `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api`  |
| mcp-testkit      | `MCP_TESTKIT_URL`      | `http://localhost:3001`      |
| LLM model        | `AGENTSPAN_LLM_MODEL`  | `openai/gpt-4o-mini`         |

## Run

```bash
./run.sh                                  # full suite
./run.sh --filter 'FullyQualifiedName~Suite1'
```
EOF

  make_tarball "$name"
}

# ── Dispatch ─────────────────────────────────────────────────────────────

echo "Packaging e2e bundles for version $VERSION → $OUT_DIR"
for sdk in "${SDKS[@]}"; do
  case "$sdk" in
    python)     pack_python ;;
    typescript) pack_typescript ;;
    java)       pack_java ;;
    csharp)     pack_csharp ;;
    *)          echo "ERROR: unknown sdk '$sdk' (want python|typescript|java|csharp|all)" >&2; exit 1 ;;
  esac
done
echo "Done."
