# AgentSpan — Testing, Deployment & Integration Validation: Scope & Gaps

**Status:** Working notes (for review)
**Owner:** validation / deployment side
**Companion to:** [agentspan-as-a-library.md](agentspan-as-a-library.md) — §9.1 (embedded e2e), §9.2 (three modes & version drift), §9.3 (upgrade & adoption)

This is a **gap analysis** of what the testing/deployment/integration-validation task still needs to
cover, given the design now in `agentspan-as-a-library.md`. It is intentionally scoped to the
*validation owner's* concerns, not the implementer's.

---

## Framing (settled in the design doc)

- **Three consumption modes** (§9.2): **A** standalone server, **B** external OSS self-embed,
  **C** orkes enterprise embed.
- **Customers consume whole releases, never hand-swapped jars** → API/ABI is the *release
  producer's* build-time concern (self-certify, §9.2). The consuming customer's job on upgrade is
  **data + ops only**.
- **Upgrade vs adoption** (§9.3): upgrade = stateful-app data migration; adoption (plain Conductor →
  +AgentSpan) is **additive** with a `>=` same-major engine-direction rule.

Everything below assumes that framing and asks: *what's still uncovered for validation?*

---

## Prerequisites — these gate everything else

1. **Conformance-suite instrument — already exists, no need to build.** *(Corrected.)* The SDK e2e
   suites (`sdk/{python,java,ts,csharp}/e2e/`) are **already** pure black-box HTTP clients
   parameterized only by `AGENTSPAN_SERVER_URL` (`sdk/python/e2e/conftest.py`). Point the env var at
   an embedded host and the *identical* suite runs — no code change. So the instrument is **not** a
   gap. The real remaining work is (a) standing up the embedded target to point it at, and (b) the
   reuse mechanism from the orkes repo — see "Reusing the suite from orkes" below.
2. **§6 engine coordinates (Mode C blocker).** Which orkes module/artifact provides the engine
   classes (`WorkflowExecutor`, `WorkflowSystemTask`, `ExecutionDAO`, `MetadataDAO`, …), and at what
   version. Until pinned, Phase 4 can't start → nothing to integration-test. Upstream of this task
   but blocks it.

### Reusing the SDK e2e suite from the orkes repo

The suite is reusable because it depends on the **SDK client package + a URL**, never on server
code (test input, not a build dependency — keeps the §3.1 direction clean). "Reuse" = assemble three
things at one matching `AGENTSPAN_VERSION`: the **suite files**, the **SDK client package** it
imports, and **`AGENTSPAN_SERVER_URL`** pointed at the booted orkes instance.

| Option | Mechanism | Status today | Notes |
| --- | --- | --- | --- |
| **A — checkout + in-repo run** | orkes `actions/checkout` of agentspan@`vX`, `pip install agentspan==vX`, `pytest e2e/` | **works now** (how agentspan CI runs it) | zero new infra; manual version discipline; orkes CI needs a Python/uv toolchain (or reuse the Java suite via `./gradlew test -Pe2e`) |
| **B — published test artifact** | publish suite as a wheel / Maven test-jar; orkes pulls `vX` | **not built** | decouples from repo layout; agentspan must publish |
| **C — conformance-runner container** | image with suite + client baked at `vX`; orkes `docker run -e AGENTSPAN_SERVER_URL=…` | **does NOT exist today** — proposed | best version-coherence (suite+client locked together), no Python toolchain in orkes CI; net-new Dockerfile + release workflow |

- **Today there is no `agentspan/conformance` image.** The only Docker image is the *server*
  (`server/Dockerfile` → `agentspan-runtime.jar`). The e2e suites run in-repo (pytest marker /
  `-Pe2e`), not as a published artifact. So **today's only orkes-reuse path is Option A.**
- **In every option the engine under test is the orkes conductor** — the suite/container is
  engine-free and only drives the booted orkes instance over HTTP.
- **Recommendation:** Option A to start (zero infra, matches §9.1); build **Option C** as the
  end-state to make cross-repo version-pinning robust instead of manual. Small, high-leverage.

---

## Security validation — covered; two residuals are out of OSS scope

*(Corrected after pressure-testing against the actual test tree — the earlier "entirely
uncovered, neither suite exercises it" framing was wrong.)* A dedicated server-side security test
layer already covers the auth-boundary, scoping, masking-pipeline, and cross-tenant claims that
were called gaps: token lifecycle + HMAC, declared-name bounding / rate limit / login rejection,
cross-tenant isolation, principal-scoped listing, masking advice routing + pipeline substitution,
the standalone request-filter → context bridge, and per-user identity resolution.

What is left is **two residuals, both genuinely not OSS work** — not a coverage gap to close here:

1. **The masking redaction *algorithm*.** Per-execution disclosure lookup, Jackson tree-walk, and
   JSON-escape handling live in the enterprise module. OSS ships `NoOpSecretOutputMasker` and has no
   disclosure tracking to redact against, so that correctness is — by design — tested where the real
   masker is provided. The OSS side (that the pipeline applies whatever the masker returns) is
   covered above. Two complementary coverage paths:
   - **Algorithm correctness (scaffolded now).** `SecretOutputMaskerContract` defines the behavioral
     spec (redacts disclosed plaintext incl. JSON-escaped/nested values, scoped by execution, never
     throws); the enterprise module extends it to run the spec against the real masker (publish OSS
     test sources as a test-jar — same cross-module reuse as the e2e "Option C").
     `ReferenceSecretOutputMaskerContractTest` keeps the spec honest in OSS by running it against a
     correct reference redactor.
   - **Wiring / disclosure-tracking (SDK e2e, gated on §6).** The contract test can't prove the real
     masker is actually wired into the response path and fed real disclosure data in the assembled
     system. An SDK e2e against the embedded orkes target closes that: create a secret, run a
     **deterministic** credential-using worker that surfaces the plaintext into task output (this
     populates `credential_disclosures`), read the execution back via `/api/agent/executions/{id}`,
     assert the plaintext is gone and `***NAME***` is present. Meaningless against OSS standalone
     (no-op masker passes the value through), so it **env-gates** to the embedded target, and stays
     **LLM-free** (deterministic worker, not an agent loop; assertion is a string check on the
     payload). Authored when the embedded target exists, since an always-skipped test can't be
     validated.
2. **The embed-mode host principal adapter.** In an embed, a host-supplied security adapter
   *replaces* `AuthFilter` as the source of identity. The standalone bridge it replaces is covered
   above (`AuthFilterContextBridgeTest`). **Validation vehicle: the SDK e2e suite, run against the
   embedded orkes target** — a request authenticated as user A flows through orkes' real auth adapter
   → `RequestContext.userId` → AgentSpan scoping, so an e2e that creates a secret as A and fails to
   read/list it as B exercises the adapter end-to-end (not a mock — that would be circular). This is
   meaningless against OSS standalone, where `AuthFilter` pins every request to one anonymous
   principal, so the test must **env-gate** (skip unless two identities, e.g. `AGENTSPAN_API_KEY_A`/
   `_B`, are configured) and stays **LLM-free** (assert at the `/api/secrets` layer; no agent run).
   Needs: a two-client e2e fixture (the SDK clients can already authenticate, just unconfigured
   today). **Gated on §6 engine coordinates** — authored when the embedded target exists, since an
   always-skipped test can't be validated.

## Entirely uncovered dimensions

1. **Performance / regression baseline.** Does embedding AgentSpan (`@Primary` HttpTask/MCPService
   overrides, the masking `@ControllerAdvice`) change engine throughput/latency? No baseline ⇒ can't
   detect upgrade regressions.

---

## Already covered — do NOT rebuild

After pressure-testing, several "gaps" turn out to be covered elsewhere. Re-testing them is wasted
work:

- **Engine executes workflows** → covered by **Conductor's own test suite** (upstream).
- **AgentSpan compiles agents → WorkflowDef** → covered by **SDK e2e `test_suite1`** (LLM-free).
- **Agent runs end-to-end (LLM↔tool loop)** → covered by the **SDK e2e execution suites**.

So there is **no net-new "agent smoke test" to write.** A post-deploy smoke is just a fast subset of
the existing SDK e2e suite (tag a few tests `@smoke`) pointed at the deployed URL — which is the
same mechanism as "stand up the embedded target + reuse the suite" below. No new test logic.

---

## Deployment — mechanics not yet discussed

1. **Multi-replica / rolling-deploy safety.** Confirm AgentSpan servers are stateless +
   horizontally scalable (like Conductor). `CredentialSchemaMigrator` claims multi-replica safety —
   validate concurrent replicas during a rolling upgrade don't race on schema init or task
   registration.
2. **Config / secrets provisioning at deploy.** SPI impl beans, master key, DB credentials for
   **both** datasources — the deploy-config story, especially in embed where the host wires every
   SPI.

---

## Testing — fixtures needed

1. **Realistic upgrade fixtures.** Validating §9.3's upgrade path needs a **populated** DB with
   **in-flight / long-paused HITL** executions (`AgentHumanTask`) spanning the bump, across **both**
   datasources — not a clean-start test.

---

## Embed coexistence checks (Mode C) — need an owner even without a formal checklist

- `@Primary` collision/behavior: `CredentialAwareHttpTask`, `CredentialAwareMcpService`,
  `AgentHumanTask`, event listener (§5.2).
- CORS / auth coexistence with host (§5.3).
- Endpoint path overlaps; scheduler intact; SSE intact.
- Missing SPI impl ⇒ **fail fast at startup** (the one property verifiable today, by construction).
- Kill-switch: `agentspan.embedded=false` returns a clean Conductor, no residual beans/paths.

### Host requirement: populate `RequestContextHolder` (the embed security bridge)

The only non-test code that sets `RequestContextHolder` is `AuthFilter`, which lives in
`conductor-agentspan-server` (standalone-only, stamps the anonymous user) and is **not on the embed
classpath**. The embeddable library ships only the `RequestContextHolder` API, not a populator. So
in Mode C **the host must register a request filter / security adapter that maps its authenticated
principal → `RequestContextHolder.set(...)` before any AgentSpan controller runs.** This is the
embed-mode host principal adapter that the "Security validation" residual #2 refers to — it lives in
the host (orkes-conductor), not this repo, and is unverified here.

`RequestContextHolder` is consumed synchronously on the HTTP request thread at: `/api/secrets` CRUD
(`SecretController.getRequiredUserId()`), agent start (`AgentService` — captures the principal into
`createdBy` **and the minted execution token's `userId`**), the masking advice, the skill registry,
and compile-time LLM calls. Task/worker execution does **not** read it — execution resolves the user
from the execution token (`__agentspan_ctx__`) minted at start, so the principal is captured exactly
once, at the `/api/agent` start call.

If the host does **not** wire the filter, two failure modes (worth an explicit embed test):

- **Secrets CRUD hard-fails** — `getRequiredUserId()` throws `IllegalStateException` ("No
  RequestContext on this thread") ⇒ `/api/secrets` 500s.
- **Execution silently degrades to single-tenant** — at agent start `principal == null` ⇒ **no
  execution token is minted**, `createdBy` unset ⇒ worker resolution falls back to the anonymous
  user. No error; per-user isolation quietly collapses. This is the more dangerous mode (fails
  open-ish, not closed) and is the highest-value thing to assert once the embed target exists.

---

## The real residue (after pressure-testing)

Most candidate "gaps" collapsed into *already covered* (Conductor tests the engine; the SDK e2e
suite tests compile + execution) or *already exists, just needs pointing* (the suite is endpoint-
parameterized). The honest residue is:

1. **Stand up the embedded orkes target + reuse the existing suite against it** (Option A today) —
   the instrument already exists; the work is the target + the cross-repo wiring. **Gated on §6.**
   The post-deploy "smoke" is a `@smoke` subset of this same suite — not separate work.
2. **Security validation is covered in OSS** — auth boundaries, declared-name bounding, rate
   limiting, token revocation, cross-tenant isolation, principal-scoped listing, the masking
   pipeline, and the standalone request-filter → context bridge are all exercised by a dedicated
   server-side test layer (see "Security validation" above). The only two remaining items are
   genuinely **not** OSS work: the masking redaction *algorithm* (enterprise module) and the
   embed-mode host principal adapter (gated on §6 engine coordinates).

Everything else (multi-replica, deploy config, upgrade fixtures, perf baseline) is real but
secondary. Building the Option C conformance container is a high-leverage follow-on, not a blocker.

---

## Open questions to resolve

- Does Conductor 3.30.2's relational persistence auto-migrate an existing populated schema on
  startup (Flyway forward-only), or require manual scripts? (Affects §9.3 upgrade + Mode A adoption.)
- Is Mode B (external OSS self-embed) a *supported* offering or an internal stepping-stone to C?
  (Changes how much B-specific validation is warranted.)
- Is the `Conductor-Built-Against` manifest breadcrumb (§9.2) going to be implemented? (Affects
  jar-consumer diagnosability in Mode B.)
