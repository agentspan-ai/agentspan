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

## Entirely uncovered dimensions

3. **Security validation — biggest blind spot.** Not in scope anywhere yet:
   - Two auth boundaries (per §2 secrets note): `SecretController` `/api/secrets` (login-JWT /
     API-key) vs `WorkerController` `/api/workers/secrets` (HMAC execution-token, declared-name
     bounded, rate-limited). Validate the token bounding actually holds.
   - Output masking: `CredentialOutputMasker` redacts; no secret leakage in logs/payloads; masking
     advice covers `/api/workflow/{id}` reads.
   - **Embed only:** the security-context bridge (host identity → `RequestContextHolder`) does not
     grant cross-tenant access.
4. **Performance / regression baseline.** Does embedding AgentSpan (`@Primary` HttpTask/MCPService
   overrides, the masking `@ControllerAdvice`) change engine throughput/latency? No baseline ⇒ can't
   detect upgrade regressions.

---

## Deployment — mechanics not yet discussed

5. **Post-deploy liveness, not just "context loads."** Deterministic smoke test proving agents
   actually run end-to-end (define → start → terminal status). **No LLM-judged output** (per
   `CLAUDE.md`) — assert on compile/start/status only.
6. **Multi-replica / rolling-deploy safety.** Confirm AgentSpan servers are stateless +
   horizontally scalable (like Conductor). `CredentialSchemaMigrator` claims multi-replica safety —
   validate concurrent replicas during a rolling upgrade don't race on schema init or task
   registration.
7. **Config / secrets provisioning at deploy.** SPI impl beans, master key, DB credentials for
   **both** datasources — the deploy-config story, especially in embed where the host wires every
   SPI.

---

## Testing — fixtures needed

8. **Realistic upgrade fixtures.** Validating §9.3's upgrade path needs a **populated** DB with
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

---

## Top 3 for this task (if prioritizing)

1. **Stand up the embedded orkes target + reuse the existing suite against it** (Option A today) —
   the instrument already exists; the work is the target + the cross-repo wiring. Gated on §6.
2. **Stand up security validation** — the largest currently-uncovered surface.
3. **Deterministic agent-runs-end-to-end smoke test** — for post-deploy confidence.

The rest are real but secondary. (Building the Option C conformance container is a high-leverage
follow-on, not a blocker.)

---

## Open questions to resolve

- Does Conductor 3.30.2's relational persistence auto-migrate an existing populated schema on
  startup (Flyway forward-only), or require manual scripts? (Affects §9.3 upgrade + Mode A adoption.)
- Is Mode B (external OSS self-embed) a *supported* offering or an internal stepping-stone to C?
  (Changes how much B-specific validation is warranted.)
- Is the `Conductor-Built-Against` manifest breadcrumb (§9.2) going to be implemented? (Affects
  jar-consumer diagnosability in Mode B.)
