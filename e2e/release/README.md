# SDK E2E release bundles

Packages each SDK's end-to-end suite into a **self-contained, version-stamped
tarball** that is attached to every GitHub release. Downstream consumers (e.g.
[`orkes-io/orkes-conductor`](https://github.com/orkes-io/orkes-conductor)) pin
the e2e suite to the exact agentspan release they run against, instead of
copying or vendoring test code.

Each bundle pins the **published** SDK at the release version — it carries only
the test sources + support files + a generated manifest, never the SDK source:

| SDK        | Bundle                               | Pins                                                       |
|------------|--------------------------------------|------------------------------------------------------------|
| Python     | `agentspan-e2e-python-<v>.tar.gz`     | PyPI `conductor-agent-sdk==<v>`                            |
| TypeScript | `agentspan-e2e-typescript-<v>.tar.gz` | npm `@conductor-oss/conductor-agent-sdk@<v>`              |
| Java       | `agentspan-e2e-java-<v>.tar.gz`       | Maven `org.conductoross.conductor:conductor-agent-sdk:<v>` |
| C#         | `agentspan-e2e-csharp-<v>.tar.gz`     | NuGet `conductor-agent-sdk` `<v>`                          |

## How it ships

`.github/workflows/release-sdk-e2e-tests.yml` runs on `release: created` (and
manual dispatch), calls `package-e2e.sh`, validates the output, then attaches
the tarballs + `.sha256` checksums to the `vX.Y.Z` release as assets — the same
unified version every other release workflow (server, CLI, each SDK) publishes.

## Build locally

```bash
./e2e/release/package-e2e.sh --version 0.4.0            # all SDKs → e2e/release/dist/
./e2e/release/package-e2e.sh --version 0.4.0 --sdk java # one SDK
./e2e/release/test_package_e2e.sh                       # validate bundle structure + pins
```

## Consuming a bundle (downstream)

```bash
V=0.4.0; SDK=java
curl -fsSL -o e2e.tar.gz \
  "https://github.com/agentspan-ai/agentspan/releases/download/v$V/agentspan-e2e-$SDK-$V.tar.gz"
tar xzf e2e.tar.gz && cd "agentspan-e2e-$SDK-$V"
# Point at a running v$V server + mcp-testkit, then:
AGENTSPAN_SERVER_URL=http://localhost:6767/api ./run.sh
```

Each bundle's own `README.md` lists its prerequisites (server / CLI /
mcp-testkit / LLM model env vars) and runner usage. The bundle does **not**
start those services — the consumer provides a live, matching-version server.

## Adding/maintaining a suite

The standalone manifests (`requirements.txt`, `package.json`, `build.gradle`,
`*.csproj`), runners, and READMEs are generated inline in `package-e2e.sh` with
an `@VERSION@` placeholder substituted at package time. Test sources are copied
verbatim from `sdk/<lang>/.../e2e`. When a suite gains a new third-party test
dependency, update the corresponding generated manifest in `package-e2e.sh`.
