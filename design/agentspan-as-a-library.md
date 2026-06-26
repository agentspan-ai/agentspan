# AgentSpan as a Library: Module Split & SPI Design

**Status:** Proposed
**Author:** (design draft)
**Date:** 2026-06-04
**Goal:** Invert the dependency direction between AgentSpan and Conductor. Today the
AgentSpan server bundles Conductor and runs as a standalone app. We want AgentSpan to be a
**library that Conductor (starting with orkes-conductor) depends on**, with clean, swappable SPIs
so the enterprise build can supply its own persistence/secret implementations while OSS uses the
bundled ones as-is.

---

## 1. Goals & Non-Goals

### Goals
1. **Invert the dependency.** `orkes-conductor` depends on the `conductor-agentspan` artifact, not
   the other way around. AgentSpan stops shipping its own Conductor runtime in the embedded case.
2. **Two modules** (`conductor-` prefix — these are Conductor-ecosystem artifacts):
   - **`conductor-agentspan`** — the library. **Interfaces (SPIs) + core logic only.** Agent
     domain, compilers, the Conductor integration, and all services that *operate on* the SPIs.
     No concrete store/DAO/crypto implementations.
   - **`conductor-agentspan-server`** — the OSS runtime + standalone app. Bundles the **default
     implementations** of every SPI (JDBC secret store, filesystem skill stores, file/env master
     key, HMAC tokens, …), the Conductor runtime, and the thin launcher (bootJar + Docker).
3. **Implementations are the host's, contributed as beans.** Each persistence/secret concern is
   an SPI; the library contains no impl. A host provides one impl bean per SPI:
   `conductor-agentspan-server` ships the OSS defaults; orkes-conductor supplies its own
   (enterprise secret manager, identity, etc.). This is the same `@ConditionalOnMissingBean` /
   `@ConditionalOnProperty` contribution pattern orkes already uses for `http-task`, DAOs, and
   security — just with the impls living entirely outside the library.
4. **No reliance on the host's component scan.** AgentSpan registers itself through Spring
   Boot auto-configuration (`META-INF/spring/...AutoConfiguration.imports`), so it works even
   though orkes-conductor's `@ComponentScan` does **not** cover `dev.agentspan.*`.
5. **Conductor version owned by the host.** `conductor-agentspan` compiles against Conductor APIs
   as `compileOnly`/provided, so orkes-conductor's own Conductor version wins at runtime.
6. **Standalone still works.** `conductor-agentspan-server` remains a runnable OSS distribution
   (bootJar + Docker) that bundles an OSS Conductor runtime.

### Non-Goals (for this effort)
- Replacing Conductor with another execution engine, or a backend-neutral workflow IR. The
  compilers keep emitting Conductor `WorkflowDef`/`WorkflowTask` (stable `conductor-common`
  models). This is also why a separate engine-free "core" module buys nothing — see §3.
- Rewriting the agent compilation logic. The split is structural; compiler internals are
  untouched.
- A separate SPI over Conductor execution. Conductor's `WorkflowService`/`MetadataService`/
  `ExecutionService` already are that interface (see §4.1).

---

## 2. Current State (verified)

- **Single Gradle module** `agentspan-runtime`, Spring Boot `3.3.5`, Java 21, Conductor
  `3.30.2` (`org.conductoross:conductor-*`). `bootJar` is the only output.
- **~110 source files** under `dev.agentspan.runtime.*`. Beans are discovered through a wide
  `@ComponentScan` over `com.netflix.conductor`, `io.orkes.conductor`,
  `org.conductoross.conductor`, **and** `dev.agentspan.runtime` (`AgentRuntime.java`).
- **No `META-INF/spring` auto-config** exists yet. Everything relies on the scan.
- Conductor coupling is **not uniform** — it falls into three sharply different tiers:

| Tier | Conductor artifact | Examples | Stability | Where it's used |
|------|--------------------|----------|-----------|-----------------|
| **A. Stable data models** | `conductor-common` | `WorkflowDef`, `WorkflowTask`, `Task`, `TaskDef`, `TaskResult`, `TaskExecLog`, `Workflow`, `WorkflowSummary`, `SearchResult`, `StartWorkflowRequest`, `RerunWorkflowRequest`, `SubWorkflowParams` | Serialized to DB; cross-version safe | **All compilers**, `AgentController`, `AgentService` |
| **B. Engine internals** | `conductor-core` | `WorkflowExecutor`, `ExecutionDAO`, `MetadataDAO`, `WorkflowService`, `ExecutionService`, `WorkflowSystemTask`, `WorkflowModel`, `TaskModel`, `StartWorkflowInput`, `TaskMapperContext`, `ConductorProperties`, `HttpTask` | Version-coupled, no stable contract | `AgentService`, all custom system tasks, `Join`, `CredentialAwareHttpTask` |
| **C. AI provider SPI** | `conductor-ai` (`org.conductoross.conductor.ai`) | `AIModelProvider`, `AIModelTaskMapper`, `LLMWorkerInput`, `ChatCompletion`, ... | Orkes-maintained extension point | `AgentspanAIModelProvider`, `AgentChatCompleteTaskMapper` |

**Key finding:** the **compilers** (`AgentCompiler`, `ToolCompiler`, `GuardrailCompiler`,
`MultiAgentCompiler`, etc.) touch **only Tier A** (`conductor-common`). The tight Tier B
coupling is concentrated in **`AgentService` + the custom system tasks + the credential-aware
HTTP task**. This is what makes a clean split possible.

Verified `AgentService` Tier-B surface (lives in `conductor-agentspan`, used directly — §4.1):

```
ExecutionDAO       executionDAO;     // getWorkflow / updateWorkflow (WorkflowModel)
MetadataDAO        metadataDAO;      // create/update/get/remove WorkflowDef & TaskDef
WorkflowExecutor   workflowExecutor; // startWorkflow(StartWorkflowInput)
WorkflowService    workflowService;  // pause/resume/terminate/restart/retry/rerun/search
ExecutionService   executionService; // getExecutionStatus / updateTask / removeWorkflow / getTaskLogs
```

> **Secrets update (commit `c873e60b`):** the credentials feature was renamed to **secrets** for
> Conductor API parity. The change is at the **API / DB-table / UI / SDK** layer — the internal
> Java package is still `dev.agentspan.runtime.credentials` with `Credential*` class names. What
> changed that matters for this design:
> - **Bindings/aliases removed.** `CredentialBindingService` and the `credentials_binding` table
>   are gone; resolution is now a direct `(userId, name)` lookup with **dotted JSONPath** into a
>   JSON-valued secret (`GCP_SVC.project_id`) and **prefix-permissive declared-name bounding**.
> - **Two REST surfaces with two auth boundaries** (Conductor parity): `SecretController`
>   `/api/secrets` (login-JWT / API-key, via `AuthFilter`) and `WorkerController`
>   `/api/workers/secrets` (HMAC **execution-token**, declared-name bounded, rate-limited).
> - **New enterprise-override seam:** `CredentialOutputMasker` ships as an **OSS no-op**;
>   enterprise replaces it with disclosure-tracking masking (queries an enterprise-only
>   `credential_disclosures` table). Wired into responses by `CredentialMaskingResponseAdvice`
>   (`@ControllerAdvice`), which also masks the host's `/api/workflow/{id}` reads.
> - `CredentialSchemaMigrator` — one-shot idempotent JDBC cleanup on `ApplicationReadyEvent`.
> - `CredentialAwareMcpService` now **extends Conductor's `MCPService`** (`@Primary`) → it is
>   Conductor-coupled (resolves my earlier "verify" item).

The split runs **interface vs implementation**. Interfaces (and the logic that calls them) go to
the library; concrete impls go to the server.

Already an interface (the impl just moves to the server):
- `CredentialStoreProvider` — secret-store SPI → **lib**. Impl `EncryptedDbCredentialStoreProvider`
  (JDBC over `credentials_store`, AES-256-GCM, atomic `INSERT ... ON CONFLICT`) → **server**.
- `SkillPackageStore` → **lib**. Impls `FileSystemSkillPackageStore` /
  `ConductorPayloadSkillPackageStore` (Conductor `ExternalPayloadStorage`) → **server**.

Concrete today — extract an interface (→ lib), impl → server:
- `SkillRegistryService` metadata persistence → new `SkillMetadataDAO` (lib); filesystem-JSON impl
  → server. (The *registry service logic* stays in the lib — it operates on the two skill SPIs.)
- `MasterKeyConfig` → `MasterKeyProvider` (lib); file/env impl → server (enterprise: KMS/Vault).
- `ExecutionTokenService` → `ExecutionTokenIssuer` (lib); HMAC impl → server.
- `CredentialOutputMasker` → `SecretOutputMasker` (lib); OSS **no-op** impl → server (enterprise:
  disclosure-tracking masker).

Pure infra that goes to the server wholesale (not logic, not an SPI the lib calls): the JDBC
`DataSource` config, `CredentialSchemaMigrator`, `CredentialEnvSeeder`, and the `schema-*.sql`.

> **Auth is NOT an SPI.** `AuthFilter`/`UserRepository`/`ApiKeyRepository`/`AuthController`/
> `AuthUserSeeder` exist but are **off by default** (`agentspan.auth.enabled=false` → `AuthFilter`
> short-circuits to an anonymous admin user and never reads the repositories). They are optional
> **standalone-only** scaffolding, so they live in `conductor-agentspan-server`, not the library.
> Conductor OSS has no authN/authZ; orkes-conductor owns identity and API-key management and we
> use the host's. The only thing the **library** needs is the current principal (`userId`) for
> secret scoping, carried by `RequestContextHolder`/`RequestContext`/`User`; *who populates it* is
> the host's job (`AuthFilter` standalone, an orkes security adapter when embedded).

---

## 3. Target Architecture

### 3.1 Module graph

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │                      conductor-agentspan-server                       │  (OSS runtime + standalone app)
   │  DEFAULT SPI IMPLEMENTATIONS (the OSS defaults):                       │  bootJar + Docker
   │   - EncryptedDbCredentialStoreProvider (JDBC secret store)            │
   │   - FileSystemSkillPackageStore / ConductorPayloadSkillPackageStore   │
   │   - FileSystemSkillMetadataDAO, file/env MasterKeyProvider,           │
   │     HMAC ExecutionTokenIssuer, no-op SecretOutputMasker               │
   │   - DataSource config, schema-*.sql, schema-migrator, env-seeder      │
   │  + AgentRuntime (main), web/UI config, application.properties,        │
   │    standalone auth enforcement, OSS Conductor RUNTIME (persistence,   │
   │    scheduler, rest, http-task, json-jq-task) — the only real engine   │
   └───────────────────────────────────┬──────────────────────────────────┘
                                        │ depends on
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                          conductor-agentspan                          │  (plain jar — interfaces + logic)
   │  SPI INTERFACES ONLY (no impls): CredentialStore, SkillPackageStore,   │
   │    SkillMetadataDAO, MasterKeyProvider, ExecutionTokenIssuer,          │
   │    SecretOutputMasker  (package dev.agentspan.runtime.spi)             │
   │  CORE LOGIC that operates on those interfaces + on Conductor:          │
   │   - model/, normalizer/, compiler/*                                    │
   │   - AgentService, AgentDagService, AgentStreamRegistry (use Conductor's │
   │     WorkflowService/MetadataService/ExecutionService directly — §4.1)  │
   │   - System tasks (PlanAndCompile, ListApiTools, …, Join); AI provider  │
   │   - CredentialResolutionService, CredentialMaskingResponseAdvice,      │
   │     CredentialAwareHttpTask / McpService (call the SPIs, hold no store) │
   │   - REST controllers (Agent, Secret, Worker, Skill)                    │
   │   - principal carrier: RequestContextHolder/RequestContext/User        │
   │   - AgentSpanAutoConfiguration (wires the logic beans; expects an impl  │
   │     bean per SPI to be contributed by the host)                        │
   │  Conductor deps (common + core + ai) = compileOnly → host supplies them │
   └────────────────────────────────────────────────────────────────────────┘
```

**Why two, not three.** An engine-free "core" module would only matter if something consumed the
compilers *without* Conductor — but the compilers emit Conductor `WorkflowDef`/`WorkflowTask`, we
killed the idea of a second backend, and no such consumer exists. So agent logic and Conductor
integration always travel together; merging them removes a boundary nobody uses.

**Embedding model & a key consequence.** `orkes-conductor` depends on `conductor-agentspan`
directly (its own engine satisfies the `compileOnly` Conductor deps). Because the library carries
**no default impls**, the host **must contribute one impl bean per SPI**:
- `conductor-agentspan-server` ships the OSS defaults → standalone/OSS works out of the box.
- orkes-conductor supplies its own (enterprise secret manager, KMS, etc.).
- A context with no impl for an SPI **fails fast at startup** — that's intentional (a missing
  secret store should not silently no-op).

> *Future option (non-goal now):* if Conductor OSS — not orkes — ever wants to embed AgentSpan and
> reuse the JDBC/filesystem defaults *without* the full standalone app, lift those impls into a
> small `conductor-agentspan-defaults` jar. Until there's a consumer, they live in the server.

### 3.2 What lives where

Default is **`conductor-agentspan`** (the library = interfaces + logic). Rows marked **server** are
the concrete impls + the standalone app, in `conductor-agentspan-server`.

| Current package | → Module | Notes |
|-----------------|----------|-------|
| `model/`, `normalizer/`, `compiler/*`, `util/*` | library | agent domain + compilation (emits `conductor-common` models) |
| `auth/{User,RequestContext,RequestContextHolder}` | library | principal carrier for secret scoping |
| `auth/{AuthFilter,UserRepository,ApiKeyRepository,AuthController,AuthUserSeeder,AuthProperties}` | **server** | standalone-only auth (off by default); host owns identity when embedded |
| `credentials/` SPI interfaces (`CredentialStoreProvider`, + new `MasterKeyProvider`/`ExecutionTokenIssuer`/`SecretOutputMasker`) | library | contracts only |
| `credentials/CredentialResolutionService`, `CredentialMaskingResponseAdvice` | library | logic over the SPIs (resolution + JSONPath; masking advice calls `SecretOutputMasker`) |
| `credentials/CredentialAwareHttpTask` (+ config), `CredentialAwareMcpService` | library | extend Conductor `HttpTask`/`MCPService`; resolve `#{NAME}` via the resolution service — hold no store (`@Primary`, opt-in — §5.2) |
| `credentials/{EncryptedDbCredentialStoreProvider, MasterKeyConfig, ExecutionTokenService, CredentialOutputMasker(no-op), CredentialDataSourceConfig, CredentialSchemaMigrator, CredentialEnvSeeder}` | **server** | the OSS impls + JDBC `DataSource` + bootstrap |
| `service/{AgentService,AgentDagService,AgentStreamRegistry}` | library | use Conductor `WorkflowService`/`MetadataService`/`ExecutionService` directly (§4.1) |
| `service/SkillRegistryService` | library | registry **logic** — operates on `SkillPackageStore` + `SkillMetadataDAO` SPIs |
| `service/skill/{SkillPackageStore (interface), StoredSkillPackage}` | library | contract + value type |
| `service/skill/{FileSystemSkillPackageStore,ConductorPayloadSkillPackageStore}` + `SkillMetadataDAO` impl | **server** | FS default + `ExternalPayloadStorage`-backed + filesystem-JSON metadata |
| `service/{PlanAndCompileTask,ListApiToolsTask,PlannerContextFetchTask,AgentHumanTask}`, `tasks/Join` | library | extend `WorkflowSystemTask` |
| `ai/*` | library | `conductor-ai` provider + task mapper |
| `controller/*` (`AgentController`, `SecretController` `/api/secrets`, `WorkerController` `/api/workers/secrets`, `SkillController`) | library | the REST API surface. `WorkerController` = execution-token boundary |
| `controller/AuthController` | **server** | login endpoint — part of standalone auth |
| `config/{Cors,UiRouting,StaticDocs,Shutdown}` | **server** | web/UI presentation — host controls these when embedded |
| `AgentRuntime` (main) | **server** | standalone launcher |
| `resources/application*.properties`, `static/` | **server** | runtime config + UI bundle |
| `resources/schema-credentials*.sql` | **server** | DDL ships with the JDBC default store impl |

---

## 4. The SPI Layer (the core of this design)

All SPI **interfaces** live in `conductor-agentspan` (package `dev.agentspan.runtime.spi`); they
cover **AgentSpan-owned data**, not Conductor execution (see §4.1). The library holds **no impls**.
A host contributes one impl bean per SPI; the default impls below live in
`conductor-agentspan-server` (or, for orkes, are replaced by enterprise beans). Whoever declares
the impl uses `@ConditionalOnMissingBean` so a deployment can still override it — the same
contribution pattern orkes uses for `http-task`/DAOs/security.

| SPI (in library) | Default impl (in `conductor-agentspan-server`) | Enterprise impl (orkes) |
|------------------|------------------------------------------------|--------------------------|
| `CredentialStore` *(exists as `CredentialStoreProvider`)* | `EncryptedDbCredentialStoreProvider` (JDBC `credentials_store` + AES-GCM) | orkes Secrets Manager / Vault / KMS-backed |
| `MasterKeyProvider` | `FileOrEnvMasterKeyProvider` | AWS KMS / Vault |
| `ExecutionTokenIssuer` | `HmacExecutionTokenIssuer` (current `ExecutionTokenService`) | orkes JWT infra |
| `SecretOutputMasker` *(exists as `CredentialOutputMasker`)* | **no-op** (returns payload unchanged) | disclosure-tracking masker (Jackson tree-walk over `credential_disclosures`) |
| `SkillPackageStore` *(exists)* | `FileSystemSkillPackageStore` (or `ConductorPayloadSkillPackageStore`) | S3 / object store |
| `SkillMetadataDAO` | `FileSystemSkillMetadataDAO` | DB-backed |

> **No `UserStore` / `ApiKeyStore`.** AgentSpan's user/API-key management is off by default and
> not enforced (see §2). Identity is the host's: orkes-conductor supplies user + API-key
> management; Conductor OSS has none (→ anonymous, same as AgentSpan's default). The principal
> reaches the library via `RequestContextHolder`; the enforcement stack ships only in
> `conductor-agentspan-server`.
>
> **Naming:** new storage SPIs follow Conductor's `*DAO` convention (`SkillMetadataDAO`). The two
> pre-existing interfaces keep their current code names (`CredentialStoreProvider`,
> `SkillPackageStore`) to avoid a churny rename; align them to `*DAO` later if desired.

> **No `CredentialBindingStore`** — bindings/aliases were removed in `c873e60b`. Resolution is a
> direct `(userId, name)` lookup with dotted JSONPath into JSON-valued secrets, implemented in
> `CredentialResolutionService` on top of `CredentialStore`. Nothing to abstract there.
>
> **`SecretOutputMasker` is the cleanest new enterprise seam.** The web wiring
> (`CredentialMaskingResponseAdvice`, a `@ControllerAdvice`) lives in the **library** and calls the
> SPI; the **no-op default impl** lives in the server, and the enterprise masker (disclosure
> tracking + redaction) is contributed by orkes — exactly what the bean-contribution pattern is
> for.

### 4.1 Conductor execution is *not* an SPI

There is **no** AgentSpan abstraction over workflow execution. Conductor's own
`WorkflowService` / `MetadataService` / `ExecutionService` (and the DAOs beneath them) already
**are** the interface, and we are not swapping the execution engine (non-goal). Wrapping them in
a parallel `WorkflowExecutionBackend` would add a redundant layer with no override value.

Therefore `AgentService` (and `AgentDagService`) just live in `conductor-agentspan` and depend on
Conductor's service interfaces directly. The engine is `compileOnly`, so the host
(orkes-conductor or `conductor-agentspan-server`) supplies the implementations and version. The
five injected types — `WorkflowService`, `MetadataDAO`/`MetadataService`, `ExecutionService`,
`WorkflowExecutor`, `ExecutionDAO` — remain as-is.

> **Optional cleanup (not required):** where `AgentService` currently reaches for low-level DAOs
> (`metadataDAO.updateWorkflowDef`, and the `executionDAO.getWorkflow`/`updateWorkflow`
> `WorkflowModel` mutation at ~lines 619-636), consider routing through the higher-level
> `MetadataService`/`WorkflowService` where an equivalent exists, so the coupling sits on the
> stabler service layer. The `WorkflowModel` variable-mutation site can stay on the DAO if no
> service method fits — it's internal to the library, so it leaks nowhere.

### 4.2 Persistence SPIs (extracted from concrete services)

```java
public interface MasterKeyProvider { byte[] masterKey(); }           // file/env default; KMS override

public interface ExecutionTokenIssuer {                              // HMAC default; orkes JWT override
    String mint(String userId, String executionId, List<String> declaredNames, long timeoutSeconds);
    TokenPayload validate(String token);
    void revoke(String jti, long exp);
}

// OSS default returns payload unchanged; enterprise redacts disclosed secret values.
public interface SecretOutputMasker { String mask(String executionId, String userId, String payload); }

public interface SkillMetadataDAO {                                 // filesystem JSON default; DB override
    SkillDetail save(SkillDetail detail);
    List<SkillSummary> list(boolean allVersions, String ownerId);
    Optional<SkillDetail> get(String ownerId, String name, String version);
    void delete(String ownerId, String name, String version);
}
```

`CredentialStoreProvider` and `SkillPackageStore` already exist — move the **interfaces** into the
`spi` package; their impls go to the server. (No `User`/`ApiKey` SPI — see §4 note; identity is the
host's.)

---

## 5. Spring Wiring Strategy

### 5.1 Auto-configuration instead of component scan

Replace the wide `@ComponentScan` with auto-configuration exported via the Spring Boot 3 imports
file. This is mandatory: orkes-conductor's scan covers `com.netflix.conductor`,
`io.orkes.conductor`, `org.conductoross` — **not** `dev.agentspan`.

```
conductor-agentspan/src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
        → dev.agentspan.runtime.config.AgentSpanAutoConfiguration
```

There are **two** config layers:

**(a) Library** — `AgentSpanAutoConfiguration` wires the *logic* beans. They take the SPIs as
constructor dependencies; they do **not** create impls. Each is guarded `@ConditionalOnBean` on the
SPIs it needs, so the context fails fast (with a clear message) if the host forgot to contribute an
impl, rather than half-wiring.

```java
@AutoConfiguration
@EnableConfigurationProperties({AgentSpanProperties.class})
public class AgentSpanAutoConfiguration {

    @Bean @ConditionalOnMissingBean @ConditionalOnBean(CredentialStore.class)
    public CredentialResolutionService credentialResolutionService(CredentialStore store) {
        return new CredentialResolutionService(store);          // logic: lookup + JSONPath
    }

    @Bean @ConditionalOnMissingBean
        @ConditionalOnBean({SkillPackageStore.class, SkillMetadataDAO.class})
    public SkillRegistryService skillRegistryService(SkillPackageStore pkg, SkillMetadataDAO meta) {
        return new SkillRegistryService(pkg, meta);             // logic over the two skill SPIs
    }

    @Bean @ConditionalOnMissingBean
    public AgentCompiler agentCompiler(/* ... */) { return new AgentCompiler(/* ... */); }

    // AgentService, system tasks (by TASK_TYPE), AI provider, controllers, masking advice,
    // CredentialAware* tasks ... — all @Bean here, all operating on injected SPIs. No impls.

    @Bean @ConditionalOnMissingBean
    public NormalizerRegistry normalizerRegistry(List<AgentConfigNormalizer> normalizers) {
        return new NormalizerRegistry(normalizers);
    }
}
```

**(b) Host** — contributes one impl bean per SPI. `conductor-agentspan-server` ships the OSS
defaults; orkes contributes its own. Example (server):

```java
@Configuration
public class AgentSpanDefaultImplConfiguration {
    @Bean @ConditionalOnMissingBean
    public CredentialStore credentialStore(MasterKeyProvider keys,
                                           @Qualifier("agentspanJdbc") NamedParameterJdbcTemplate jdbc) {
        return new EncryptedDbCredentialStoreProvider(keys, jdbc);  // JDBC impl lives in the server
    }
    @Bean @ConditionalOnMissingBean
    public SecretOutputMasker secretOutputMasker() { return (e, u, payload) -> payload; }  // no-op
    // MasterKeyProvider, ExecutionTokenIssuer, SkillPackageStore, SkillMetadataDAO, DataSource ...
}
```

One library auto-config is simplest. If it grows, split it internally (e.g. an engine-coupled
group gated `@ConditionalOnClass(WorkflowExecutor.class)`) and list each in the imports file.

> **Stereotype → explicit `@Bean` conversion.** Today ~40 classes use `@Component`/`@Service`/
> `@Repository`/`@RestController` and rely on scanning. For a library that supports per-bean
> override, the orkes pattern is explicit `@Bean` + `@ConditionalOnMissingBean` (see
> `HttpTaskAutoConfiguration`). Plan: **drop the stereotype annotations** and declare them in the
> auto-config. Controllers are the one wrinkle — `@RestController` beans can be declared via
> `@Bean`, but if that proves awkward, register them through a single nested `@Configuration` with
> a **narrowly scoped** `@ComponentScan("dev.agentspan.runtime.controller")` that the host imports
> explicitly. Decide during Phase 2; prefer explicit `@Bean`.

### 5.2 The `@Primary` landmines (must become opt-in)

Several beans currently use `@Primary` to **override Conductor's own beans**. When embedded in
orkes-conductor — which already provides these — `@Primary` will either conflict or silently
hijack host behavior. Each must become **conditional/opt-in**. (The `CredentialAware*` integrations
are library beans; the `DataSource` is now a **server**-module bean — in embedded orkes it isn't
present at all, since orkes contributes its own `CredentialStore` impl.)

| AgentSpan bean | Today | Conflict in orkes | Fix |
|----------------|-------|-------------------|-----|
| `credentialDataSource` (server module) | `@Primary DataSource` | orkes already has a `@Primary` Postgres `DataSource` | Rename to `@Qualifier("agentspanDataSource")`, **not** `@Primary`; `@ConditionalOnMissingBean(name=...)`. Only the server module declares it; orkes never sees it |
| `CredentialAwareHttpTask` | `@Bean("HTTP") @Primary` | orkes has its own `http-task` `HTTP` handler | Gate behind `@ConditionalOnProperty(agentspan.tasks.http.override)` (default true standalone, false embedded) |
| `CredentialAwareMcpService` | `@Component @Primary extends MCPService` | orkes may have its own `MCPService` | Same: property-gated / `@ConditionalOnMissingBean`, default off when embedded |
| `AgentHumanTask` | `@Bean(HUMAN) @Primary` | orkes has a `human` module | Same: property-gated, default off when embedded |
| `AgentEventListener` | `@Primary` status listener | `conductor.*-status-listener.type=agent` | Keep property-driven; document that the host sets the listener type |

**DataSource policy:** in the embedded/enterprise case, the host overrides `CredentialStore`,
`SkillMetadataDAO`, etc. entirely, so AgentSpan's JDBC `DataSource` is never created. In the OSS
embedded case (orkes OSS without enterprise stores), AgentSpan's defaults activate against their
**own qualified** `DataSource` — never `@Primary`, so they never collide with Conductor's.

### 5.3 Auth / CORS / security coexistence

AgentSpan now has **two distinct auth boundaries** (Conductor parity), and they coexist with the
host differently:

1. **User boundary** — `/api/secrets` (`SecretController`), `/api/agent/*`, `/api/skill`,
   `/api/auth`. AgentSpan's own `AuthFilter` is **standalone-only** (ships in `conductor-agentspan-server`,
   off by default) — it is **not on the embedded classpath**. When embedded, the host owns user
   authn/authz; an orkes security adapter populates `RequestContextHolder` with the principal so
   secret scoping works. `SecretController.listGrantable()` is already RBAC-shaped (OSS returns
   all) — an enterprise `SecretAccessPolicy` can filter here.
2. **Worker boundary** — `/api/workers/secrets` (`WorkerController`), guarded by HMAC
   **execution tokens** (`ExecutionTokenService`), **independent of user auth**. This must stay
   reachable by in-flight workers regardless of the host's user security. Ensure the host's
   security chain does **not** block `/api/workers/**`, and that the execution-token check is the
   only gate. Declared-name bounding + rate-limit are AgentSpan's, not the host's.

Other web wiring:
- `CredentialMaskingResponseAdvice` (`@ControllerAdvice`) wraps execution-read responses,
  **including the host's `/api/workflow/{id}`**. In OSS the masker is a no-op so this is inert;
  with an enterprise `SecretOutputMasker` it will redact the host's workflow-read payloads too.
  That is almost certainly desired, but **flag it**: an advice from the AgentSpan jar mutating a
  host endpoint's body is surprising. Make it `@ConditionalOnBean(SecretOutputMasker)` /
  property-gated so the host opts in.
- `CorsConfig`, `UiRoutingConfig`, `StaticDocsConfig` move to **`conductor-agentspan-server`** so
  they never alter the host's web config. Embedded REST controllers still register; only the
  presentation/UI/CORS wiring is standalone-only.
- Confirm no REST path collisions: AgentSpan uses `/api/agent`, `/api/skill`, `/api/auth`,
  `/api/secrets`, `/api/workers/secrets`; Conductor uses `/api/workflow`, `/api/metadata`, etc.
  No overlap expected — **verify** against orkes' gateway.

---

## 6. Conductor Version Alignment (top integration risk)

orkes-conductor pins `revConductor = 3.30.0.rc8`, and its `subprojects` block **excludes**
`com.netflix.conductor` (group) and `org.conductoross:conductor-core`, supplying the engine from
its own modules. AgentSpan currently compiles against `org.conductoross:conductor-*:3.30.2`. If
AgentSpan ships those as transitive `implementation` deps, we get a version clash on the host
classpath.

> This section covers the **build/classpath mechanics** of alignment. For *who owns* alignment in
> each deployment, see the three-consumption-mode table in §9.2: Mode A (standalone) is drift-free
> by construction, Mode C (orkes) is one host-pinned pair, and Mode B (external OSS self-embed) is
> explicitly best-effort + self-certify.

**Strategy — `compileOnly`/provided for ALL Conductor artifacts:**

- `conductor-agentspan` declares `conductor-common`, `conductor-core`, `conductor-ai` (and
  `conductor-http-task` for `CredentialAwareHttpTask`) as **`compileOnly`** (provided). The host
  (orkes-conductor or `conductor-agentspan-server`) supplies the concrete engine at its own
  version at runtime. This mirrors how orkes' `http-task` declares Spring as `compileOnly`.
  - Note `conductor-common` types appear on the library's public API (`WorkflowDef` on compiler
    methods). `compileOnly` is fine because **both** consumers — orkes and our own server — have
    `conductor-common` on their classpath. Nobody consumes the library without an engine.
- `conductor-agentspan-server` brings the **real** OSS Conductor runtime
  (`conductor-common`, `-core`, `-ai`, `-rest`, `-sqlite-persistence`, `-postgres-persistence`,
  `-scheduler-*`, `-http-task`, `-json-jq-task`) as `implementation` — the only module that ships
  a runnable Conductor.

> ❗ **Must verify before coding:** which orkes module/artifact provides the
> `com.netflix.conductor.core.*` engine classes (`WorkflowExecutor`, `WorkflowSystemTask`,
> `ExecutionDAO`, `MetadataDAO`, `WorkflowModel`, `TaskModel`) and at exactly what version. The
> custom system tasks and `AgentService` compile against those package names; they
> must match the host's. Pin `compileOnly` to that version. Also confirm orkes' `conductor-ai`
> coordinates/version for the AI provider.

---

## 7. Build / Gradle Restructure

### 7.1 `settings.gradle`

```groovy
rootProject.name = 'agentspan'
include 'conductor-agentspan'
include 'conductor-agentspan-server'
```

Root `build.gradle` holds the version catalog (`conductorVersion`, etc.), Java toolchain,
spotless, and the `subprojects {}` common config. `bootJar` disabled for `conductor-agentspan`,
enabled for `conductor-agentspan-server`.

### 7.2 `conductor-agentspan/build.gradle` (the library)

```groovy
plugins { id 'java-library'; id 'maven-publish' }
bootJar { enabled = false }; jar { enabled = true }

dependencies {
    // ALL Conductor artifacts are PROVIDED — host (orkes or our server) supplies the version.
    compileOnly "org.conductoross:conductor-common:${conductorVersion}"   // on the public compiler API
    compileOnly "org.conductoross:conductor-core:${conductorVersion}"
    compileOnly "org.conductoross:conductor-ai:${conductorVersion}"
    compileOnly "org.conductoross:conductor-http-task:${conductorVersion}" // CredentialAwareHttpTask extends HttpTask
    compileOnly 'org.springframework.boot:spring-boot-starter-web'         // wiring/web, provided
    compileOnly 'org.springframework.boot:spring-boot-autoconfigure'

    // Logic-only deps. No JDBC, no sqlite, no security-crypto — those belong to the impls (server).
    implementation "com.networknt:json-schema-validator:${jsonSchemaVersion}"  // compiler/validation

    compileOnly    "org.projectlombok:lombok:${lombokVersion}"
    annotationProcessor "org.projectlombok:lombok:${lombokVersion}"

    // Tests run against a REAL engine + Spring (and may use the server's default impls as fixtures):
    testImplementation "org.conductoross:conductor-core:${conductorVersion}"
    testImplementation "org.conductoross:conductor-common:${conductorVersion}"
    testImplementation "org.conductoross:conductor-ai:${conductorVersion}"
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 7.3 `conductor-agentspan-server/build.gradle` (thin app)

Essentially today's `build.gradle`, minus the source (now in the library), plus:

```groovy
plugins { id 'org.springframework.boot'; id 'java' }
dependencies {
    implementation project(':conductor-agentspan')
    // SPI default IMPLEMENTATIONS live here — their infra deps come with them:
    implementation 'org.springframework:spring-jdbc'                              // JDBC stores
    implementation "org.xerial:sqlite-jdbc:${sqliteJdbcVersion}"
    implementation "org.springframework.security:spring-security-crypto:${springSecVersion}" // BCrypt (auth)
    // The ONLY module that ships a runnable Conductor (satisfies the library's compileOnly deps):
    implementation "org.conductoross:conductor-common:${conductorVersion}"
    implementation "org.conductoross:conductor-core:${conductorVersion}"
    implementation "org.conductoross:conductor-ai:${conductorVersion}"
    implementation "org.conductoross:conductor-rest:${conductorVersion}"
    implementation "org.conductoross:conductor-sqlite-persistence:${conductorVersion}"
    implementation "org.conductoross:conductor-postgres-persistence:${conductorVersion}"
    implementation "org.conductoross:conductor-scheduler-core:${conductorVersion}"
    implementation "org.conductoross:conductor-scheduler-sqlite-persistence:${conductorVersion}"
    implementation "org.conductoross:conductor-scheduler-postgres-persistence:${conductorVersion}"
    implementation "org.conductoross:conductor-http-task:${conductorVersion}"
    implementation "org.conductoross:conductor-json-jq-task:${conductorVersion}"
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:2.6.0'
    // web/UI/actuator/log4j2 as today; the UI build tasks (buildUi/syncUiStatic) move here
}
bootJar { archiveFileName = 'agentspan-runtime.jar' }
```

### 7.4 Publishing

`conductor-agentspan` publishes as a plain JAR (`maven-publish`, `from components.java`) under
`dev.agentspan:conductor-agentspan` (group is a positioning choice — could also live under the
Conductor group). Match the artifact repo orkes consumes from (orkes uses an S3-backed maven
repo; mirror that or publish to the shared registry the orkes build can resolve).
`conductor-agentspan-server` is not published as a library (it's the app/Docker artifact).

---

## 8. Implementation Plan (phased)

Each phase is independently shippable and keeps the standalone server green. Per the repo's
testing rule (**write a test, prove it fails, then implement**), every phase starts with a
failing test that pins the target behavior.

### Phase 0 — Two-module skeleton (no behavior change)
1. Convert to a two-module `settings.gradle`; create `conductor-agentspan` and
   `conductor-agentspan-server`.
2. Move source: **everything into `conductor-agentspan`** except the thin launcher
   (`AgentRuntime`), web/UI config (`config/*`), the auth-enforcement stack (`AuthFilter`,
   `UserRepository`, `ApiKeyRepository`, `AuthController`, `AuthUserSeeder`, `AuthProperties`),
   `application*.properties`, and `static/` → those go to `conductor-agentspan-server`.
   - The concrete store/crypto impls (`EncryptedDbCredentialStoreProvider`, `MasterKeyConfig`,
     `ExecutionTokenService`, `CredentialOutputMasker`, the FS skill stores, `DataSource` config,
     schema, seeder, migrator) stay in the library **for now** — they can't move to the server
     until their interfaces exist (the library can't depend upward on the server). Phase 1 moves
     them.
3. Conductor artifacts become `compileOnly` in the library; the server brings the real runtime.
   **Transitional wiring:** leave `AgentRuntime`'s `@ComponentScan` over `dev.agentspan.runtime`
   in place for now so the standalone app still wires the old way while we restructure.
4. Verify: `./gradlew :conductor-agentspan-server:bootJar` produces the same runnable jar; the
   existing suite passes unchanged.
   - *Test-first:* a smoke test that boots the context and hits `/api/agent` health — green
     before and after the move.

### Phase 1 — Extract SPI interfaces (lib) and push impls to the server
1. In the library, introduce `dev.agentspan.runtime.spi` interfaces: `MasterKeyProvider`,
   `ExecutionTokenIssuer`, `SecretOutputMasker`, `SkillMetadataDAO`; move the existing
   `CredentialStoreProvider` and `SkillPackageStore` interfaces in. (No binding store, and **no
   `UserStore`/`ApiKeyStore`** — bindings removed in `c873e60b`, identity is the host's; see §4.)
   Repoint all library logic (`CredentialResolutionService`, `SkillRegistryService`, masking
   advice, `CredentialAware*`, controllers) at the **interfaces**.
2. **Move the concrete impls to `conductor-agentspan-server`:** `EncryptedDbCredentialStoreProvider`,
   `FileSystemSkillPackageStore`/`ConductorPayloadSkillPackageStore`, the `SkillMetadataDAO` impl,
   `MasterKeyConfig`, `ExecutionTokenService` (HMAC), the no-op `CredentialOutputMasker`, the
   `DataSource` config, `schema-*.sql`, `CredentialSchemaMigrator`, `CredentialEnvSeeder`. Declare
   them as beans in a server `AgentSpanDefaultImplConfiguration` (each `@ConditionalOnMissingBean`).
   - *Test-first:* a library-only test that wires the logic against **fake** in-memory SPI impls
     and asserts behavior (resolution + JSONPath, skill register/list) — proves the lib needs no
     concrete impls. Red before the interfaces exist.
   - *Test-first:* a masking test in the server with a non-no-op `SecretOutputMasker` bean asserts
     the advice (in the lib) redacts; with the no-op, payloads pass through.
3. Qualify the server `DataSource` (`agentspanDataSource`), drop `@Primary`.

### Phase 2 — Auto-configuration; drop `@ComponentScan` reliance
1. Write the library `AgentSpanAutoConfiguration` (one class, or an internally-split pair) wiring
   the **logic** beans via explicit `@Bean`, each `@ConditionalOnBean` on the SPIs it needs; add
   the `AutoConfiguration.imports` file in `conductor-agentspan`. Register system tasks under their
   `TASK_TYPE` bean names, the AI provider, `AgentService`, controllers, etc.
2. Remove stereotype annotations from the library classes; decide controller registration (§5.1).
   Then drop the transitional `@ComponentScan` from `AgentRuntime`.
3. Convert the `@Primary` overrides (`CredentialAwareHttpTask`/`McpService`, `AgentHumanTask`,
   event listener) to property-gated/conditional beans (§5.2).
   - *Test-first:* a `@SpringBootTest` slice that loads the library auto-config **plus** the
     server's default-impl config (no component scan) and asserts every expected bean is present
     (incl. system tasks by `TASK_TYPE`); and that **omitting** an SPI impl makes the context fail
     fast (the `@ConditionalOnBean` guard). Write it red, then add the auto-config.
   - *Test-first:* a custom `CredentialStore` `@Bean` wins over the server default
     (`@ConditionalOnMissingBean`); and `agentspan.tasks.http.override=false` ⇒ no
     `CredentialAwareHttpTask` bean (host's HTTP task wins).

### Phase 3 — Verify the thin server
1. `conductor-agentspan-server` = the SPI default impls + `AgentRuntime` + web/UI config +
   `application*.properties` + `static/` + UI gradle tasks + standalone auth stack + OSS Conductor
   runtime deps.
2. Verify the standalone bootJar and Docker image behave identically to today (same endpoints,
   same e2e suite).
   - *Test-first:* run the existing e2e/integration suite against the new server module —
     **no LLM-based validation** (per `CLAUDE.md`); assert on deterministic compile/start/status.

### Phase 4 — Integrate into orkes-conductor (separate repo/PR)
1. After verifying §6 (engine artifact + version), add `dev.agentspan:conductor-agentspan` to
   `orkes-conductor/server/build.gradle`.
2. orkes contributes an **impl bean for every SPI** (secret store, master key/KMS, token issuer,
   output masker, skill stores) — there is no bundled default to fall back on. Bridge orkes'
   security context → `RequestContextHolder`.
3. Smoke + integration test inside orkes: deploy an agent, start it, observe status, exercise a
   tool call. Confirm no bean conflicts, no path collisions, scheduler/SSE intact, and that a
   missing SPI impl fails startup loudly. See §9.1 for the two embedded-mode e2e layers
   (in-orkes server e2e + reused SDK e2e) and the version-pinning requirement.

---

## 9. Testing Strategy

Honoring `CLAUDE.md`:
- **No LLM in validation** except where we're explicitly judging quality/evals. All structural
  tests assert on compiled `WorkflowDef`/`WorkflowTask`, bean presence, SPI delegation, and HTTP
  responses — deterministic, no model calls.
- **Prove each test fails first.** For every extraction (SPI seam, auto-config, backend
  refactor), write the test against the *target* shape so it red-fails (missing interface/bean),
  then implement to green.

New test types introduced:
1. **Library-purity check** — the `conductor-agentspan` jar contains **no** concrete store/crypto
   impl and no JDBC/sqlite/persistence on its runtime classpath; all `conductor-*` artifacts are
   `provided`/optional. An ArchUnit/POM assertion fails if an impl (e.g. `EncryptedDb*`) or a
   `conductor-*-persistence`/JDBC dependency sneaks into the library.
2. **Missing-impl fail-fast test** — the library context without an SPI impl bean fails startup
   with a clear message (the `@ConditionalOnBean` guard), not a half-wired no-op.
3. **SPI contribution/override tests** — the host's impl bean is picked up; a second custom
   `@Bean` overrides the default (`@ConditionalOnMissingBean` contract).
4. **Auto-config slice tests** — library auto-config + server default-impls load with **no**
   component scan; all expected beans present; `@Primary`/conditional overrides behave.
5. **`AgentService` tests** against mocked Conductor services (`WorkflowService`/`MetadataDAO`/
   `ExecutionService`) — Conductor's own interfaces, no AgentSpan wrapper.
6. **Embedded-mode conflict test** — a test context that simulates a host already providing
   `DataSource`/HTTP task and asserts AgentSpan does not collide.
7. **Secret masking seam test** — with a non-no-op `SecretOutputMasker`, assert
   `CredentialMaskingResponseAdvice` redacts execution-read responses; with the no-op (OSS),
   assert payloads pass through unchanged. No real secrets/LLM — deterministic fixtures.

### 9.1 Embedded-mode e2e (orkes repo)

Test types 1–7 above cover the **standalone** module and the library boundary *in this repo*. The
**embedded** deployment (AgentSpan-as-a-library inside orkes-conductor) is verified in the
**orkes-conductor repo**, because that's the only side that can depend on both — orkes depends on
`conductor-agentspan`, never the reverse (§3.1). It splits into two layers:

1. **Server e2e (in-JVM, host-specific) — lives in orkes.** The Phase-4 §8 smoke/integration
   tests: a `@SpringBootTest` that boots orkes' context with the embedded library **plus orkes'
   own SPI impl beans**, then asserts deploy → start → status → tool-call, no bean conflicts, no
   `/api/...` path collisions, scheduler/SSE intact, and that **omitting** an SPI impl fails
   startup loudly. These compile against orkes' application class and its impl beans, so they
   *cannot* live here — the dependency direction forbids it.

2. **SDK e2e (black-box HTTP) — reused, not rewritten.** The existing per-language suites
   (`sdk/{java,python,ts,csharp}`) are pure HTTP clients parameterized only by
   `AGENTSPAN_SERVER_URL`; they don't depend on either server at the code level. So the **same
   suites** run against a booted orkes instance — the only delta is the URL (and orkes' base
   path/port). This is the behavioral-equivalence oracle: if the suites that pass against
   `agentspan-runtime.jar` also pass against orkes, the embedding behaves identically.

**Where the pipeline lives.** The embedded-e2e workflow is configured in the **orkes repo** (its
CI secrets, runners, backing services — Postgres/Redis/ES). It: builds orkes-with-lib → boots it →
runs layer 1 (its own tests) and layer 2 (agentspan's suites). orkes *reads* the agentspan repo
for layer 2 (`actions/checkout` of the suite, or a published test artifact) — that's test input,
not a build dependency, so the direction stays clean.

**Version pinning (required).** Layer 2 is only a valid oracle for the exact server version it was
written against. The embedded library coordinate
(`dev.agentspan:conductor-agentspan:vX`), the checked-out suite (`ref: vX`), **and** the SDK
client package the suite imports (`agentspan==X` / `@agentspan-ai/sdk@X` / Maven / NuGet) must all
be the **same `vX`** — drive them from one `AGENTSPAN_VERSION` variable so they can't drift.
Mismatched versions yield false failures (suite expects a field the lib doesn't emit) or false
passes (suite too old to cover a new path). This is distinct from the §6 *Conductor*-version pin.

**Validation stays LLM-free** in both layers (compile/start/status/tool-call assertions), same as
the standalone e2e.

### 9.2 Interoperability & version drift (scoped to three consumption modes)

Conductor-version alignment is an **ongoing** concern, not a one-time "verify before coding" item:
`compileOnly` means **nothing bundles or enforces an engine version — the host's classpath wins**,
so a mismatch is silent until runtime. Two failure classes:

1. **Linkage (ABI)** — `NoSuchMethodError`/`ClassNotFoundException` the first time a path hits a
   method that moved or a class the host repackaged. The surface is small and enumerable: the
   injected Conductor services (`WorkflowService`, `MetadataDAO`/`MetadataService`,
   `ExecutionService`, `WorkflowExecutor`, `ExecutionDAO`), the extended base classes
   (`WorkflowSystemTask`, `HttpTask`, `MCPService`), and `conductor-common` models on the public API
   (`WorkflowDef`/`WorkflowTask` — §10.8).
2. **Semantic** — even when it links, engines may differ (JOIN, sub-workflow, HTTP task, scheduler,
   SSE). No static check; the **SDK conformance suite (§9.1 layer 2) is the only oracle** — "is it
   interoperable" = "does the same suite pass on each engine."

Rather than reason about "any host at any version," scope the concern to the **three concrete ways
a consumer actually picks an AgentSpan + Conductor pair**. Each mode has a different owner and a
different (or zero) drift risk:

| Mode | What the consumer takes | AgentSpan ver. | Conductor ver. | Drift risk | Owner |
| --- | --- | --- | --- | --- | --- |
| **A — Standalone** | `conductor-agentspan-server` bootJar / Docker | our release | **fixed**, bundled | **none** (consistent by construction) | us |
| **B — Self-embed (external OSS)** | `conductor-agentspan` library | library ver. | host-supplied, arbitrary | **real, unbounded** | the host |
| **C — Enterprise embed** | `orkes-conductor` (embeds the library) | orkes picks | orkes pins (`3.30.0.rc8`) | **real, but single pinned pair** | orkes |

**Mode A — drift-free by construction.** The standalone bootJar reads the **single**
`conductorVersion` (`server/build.gradle`) at the same commit for both lib and server (§7), so the
lib is always compiled against the engine it ships with. This protection holds *only* while it stays
one variable — **don't split it.** No extra handling needed; the boot/smoke test already links lib
against the bundled engine.

**Mode C — one pinned pair, host-certified.** orkes pins its engine (`3.30.0.rc8`, §6) and runs its
own integration + conformance suite against that pair. Compatibility is proven at *its* one version,
re-validated whenever orkes bumps the engine. No range, no matrix — exactly one certified pair, owned
by orkes.

**Mode B — the genuinely open case; both sides are OSS, so the host owns the pairing.** When the
external host runs a Conductor version that differs from our pinned `conductorVersion`, there are two
paths, and we recommend the first:

1. **Build from source against your engine (recommended).** Clone the repo, set `conductorVersion`
   to *your* engine version, and build `conductor-agentspan` yourself. The library is then compiled
   against the exact engine you run — drift is eliminated **by construction**, the same guarantee
   Mode A gets, because the `compileOnly` deps resolve to your version at compile time. No trust, no
   breadcrumb, no self-certify guesswork. This is the right path for anyone off our pinned version,
   and it's the natural OSS answer: the source is right there.
2. **Take the published jar + self-certify (fallback).** `conductor-agentspan` publishes to Maven
   Central, and `compileOnly` deps **don't appear in the POM**, so the published jar is compiled
   against *our* pinned `conductorVersion` and carries **no version constraint**. Drop it onto a
   different engine and you are trusting ABI compatibility you haven't verified. We **cannot** and
   **do not** promise this works across arbitrary versions. If you go this route:
   - **We state only the point fact we get for free:** "built/tested against `conductorVersion`"
     (auto-derived, always true, nothing to maintain). Surface it where the POM can't — release
     notes / README, and a `Conductor-Built-Against` jar-manifest breadcrumb so a mismatch is
     diagnosable at a glance rather than a bare runtime `NoSuchMethodError`. It is **informational,
     not a constraint** (deps stay `compileOnly`, host's version still wins — §6).
   - **The host self-certifies**, exactly as a JDBC driver vendor certifies against the spec rather
     than the spec enumerating drivers. Re-running the SDK conformance suite (§9.1 layer 2) against
     their engine is the only honest proof; the burden sits with the implementor.

**A declared *range* is out of scope either way.** "Compatible with 3.30.x" is only honest if we test
across it and keep re-testing as Conductor moves — the matrix maintenance we are deliberately not
signing up for. An unverified range is a false promise. Build-from-source sidesteps the question
entirely; the published jar gets a point-fact, not a range.

> Why the residual risk is *only* drift, not structure: §4.1 keeps the interop surface tiny (no
> execution SPI). Modes A and C are each a single pinned pair re-checked on bump; Mode B's
> recommended path (build from source) inherits Mode A's by-construction guarantee, with
> take-the-jar + self-certify as the best-effort fallback. No maintained compatibility range, no new
> abstraction.

### 9.3 Upgrade & adoption

Both paths consume **whole releases, never hand-swapped jars** — so API/ABI is the release
producer's build-time concern (§9.2 self-certify), and the consuming customer's job is **data + ops
only**.

**Version upgrade** (existing AgentSpan deployment → newer release) — like any stateful app:

- Two schema lifecycles migrate on startup: Conductor's (engine-owned) **and** AgentSpan's
  `credentials_store`. Back up both datasources.
- In-flight workflows must deserialize under the new engine — note **long-paused HITL**
  (`AgentHumanTask`) makes such executions routine, not rare.
- Rollback = **restore from backup** (Flyway is forward-only), not redeploy-old-artifact.

**Adoption** (plain Conductor → +AgentSpan) is **additive**: it adds `credentials_store`, custom
task types, and agent `WorkflowDef`s; existing Conductor data is untouched. Net-new concerns:

- **Engine direction is `>=`, same major** (no downgrade: forward-only Flyway + model
  serialization); *equal* = pure additive, no migration.
  - **Mode A:** customer must pick a server release whose bundled engine `>=` theirs; if their
    engine is ahead of every release, fall back to **Mode B**.
  - **Mode B (build-from-source):** aligned to the host's own engine by construction.
  - **Mode C:** `>=` auto-enforced by moving forward along orkes' release line; orkes owns it.
- Host supplies one impl bean per SPI (no embedded default) — a missing one fails fast at startup.

**Removal asymmetry:** backing AgentSpan out is clean *before* any agent runs (`credentials_store`
is a harmless orphan); *after* agents exist, their custom `TASK_TYPE`s no longer resolve.

---

## 10. Risks & Open Questions (verify before/while coding)

1. **Engine artifact/version in orkes (highest risk).** Which module/artifact provides
   `com.netflix.conductor.core.*`, `conductor-ai`, and Conductor's `MCPService` in
   orkes-conductor, and at what version? The system tasks, `AgentService`,
   `CredentialAwareHttpTask`, and `CredentialAwareMcpService` must compile against the same
   package names and a compatible version. orkes excludes `com.netflix.conductor` group and
   `org.conductoross:conductor-core` — confirm the replacement source. **Pin `compileOnly` to it.**
2. **Masking advice on the host's route.** `CredentialMaskingResponseAdvice` matches
   `/api/workflow/{id}` — i.e. it would wrap orkes' own workflow-read responses. Make it opt-in
   (`@ConditionalOnBean(SecretOutputMasker)` / property), and confirm the host wants AgentSpan
   redacting those payloads.
3. **Worker-secrets endpoint reachability.** `/api/workers/secrets` is gated only by the
   execution token. Verify orkes' security chain does **not** additionally block it and that
   workers can reach it with just the token.
4. **Controller registration without component scan** — confirm `@RestController` via `@Bean`
   works cleanly, or fall back to a narrowly-scoped `@ComponentScan` for the controller package.
5. **`@Primary` overrides** (`HTTP`, `MCPService`, `HUMAN`, status listener, `DataSource`) — every
   one must become opt-in; verify orkes' equivalents and the intended default per mode.
6. **REST path collisions** with orkes' API gateway (`/api/...`), incl. `/api/secrets`.
7. **Scheduler** (`conductor-scheduler-*`) — currently AgentSpan bundles it; in embedded mode
   the host owns scheduling. Confirm agent cron scheduling routes through the host's scheduler.
8. **`conductor-common` version on AgentSpan's public API** — since it's `api`-scoped in core,
   a host on a divergent `conductor-common` could see binary incompatibility on
   `WorkflowDef`/`WorkflowTask`. Mitigated by orkes' force-resolution, but validate.
9. **Enterprise-only tables.** `credential_disclosures` (masking) and any `secret_tags` (RBAC)
   are not in OSS schema; the enterprise `SecretOutputMasker` / `SecretAccessPolicy` impls own
   their own DDL. Keep OSS schema (`credentials_store`, `users`, `api_keys`) free of them.

---

## 11. Appendix — File move map (summary)

Two targets: **lib** = `conductor-agentspan`, **server** = `conductor-agentspan-server`.

| From `dev.agentspan.runtime.*` | To | Notes |
|--------------------------------|----|-------|
| `model/**`, `normalizer/**`, `compiler/**`, `util/**` | lib | agent domain + compilation |
| `auth/{User,RequestContext,RequestContextHolder}` | lib | principal carrier for secret scoping |
| `auth/{AuthFilter,UserRepository,ApiKeyRepository,AuthController,AuthUserSeeder,AuthProperties}` | server | standalone-only auth (off by default); no SPI — host owns identity |
| `credentials/{CredentialStoreProvider, SkillPackageStore→spi}` interfaces + new `MasterKeyProvider`/`ExecutionTokenIssuer`/`SecretOutputMasker` | lib | contracts only (→ `spi/`). Bindings removed |
| `credentials/{CredentialResolutionService, CredentialMaskingResponseAdvice}` | lib | logic over the SPIs (resolution + JSONPath; masking advice) |
| `credentials/CredentialAwareHttpTask*` | lib | extends `HttpTask`; resolves via the SPIs, holds no store |
| `credentials/CredentialAwareMcpService` | lib | extends Conductor `MCPService` (`@Primary`, opt-in) |
| `credentials/{EncryptedDbCredentialStoreProvider, MasterKeyConfig, ExecutionTokenService, CredentialOutputMasker(no-op), CredentialDataSourceConfig, CredentialSchemaMigrator, CredentialEnvSeeder}` | **server** | the OSS SPI impls + JDBC `DataSource` + bootstrap; qualify DataSource (drop `@Primary`) |
| `service/{AgentService,AgentDagService,AgentStreamRegistry}` | lib | use Conductor services directly |
| `service/SkillRegistryService` | lib | registry **logic** over `SkillPackageStore` + `SkillMetadataDAO` |
| `service/skill/{SkillPackageStore (interface), StoredSkillPackage}` + new `SkillMetadataDAO` | lib | contract + value type |
| `service/skill/{FileSystemSkillPackageStore,ConductorPayloadSkillPackageStore}` + `SkillMetadataDAO` impl | **server** | FS default + `ExternalPayloadStorage`-backed + filesystem-JSON metadata |
| `service/{PlanAndCompileTask,ListApiToolsTask,PlannerContextFetchTask,AgentHumanTask}*`, `tasks/Join` | lib | `WorkflowSystemTask` |
| `service/AgentEventListener`, `ai/**` | lib | event hooks; `conductor-ai` provider |
| `controller/{AgentController,SecretController,WorkerController,SkillController}` | lib | REST API surface; `WorkerController` = execution-token boundary |
| `controller/AuthController` | server | login endpoint — part of standalone auth |
| `config/{Cors,UiRouting,StaticDocs,Shutdown}` | server | web/UI presentation |
| `AgentRuntime` | server | main |
| `resources/application*.properties`, `static/**`, `schema-credentials*.sql` | server | runtime config, UI bundle, DDL for the JDBC impls |
| new `config/AgentSpanAutoConfiguration` + `META-INF/spring/...imports` | lib | wires logic beans; replaces `@ComponentScan` |
| new `config/AgentSpanDefaultImplConfiguration` | server | declares the OSS SPI impl beans |
| new `spi/**` | lib | the interfaces in §4 |
```
