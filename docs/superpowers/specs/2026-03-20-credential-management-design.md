# Credential Management Design

**Date:** 2026-03-20
**Status:** Approved
**Topic:** Per-user credential management for multi-user / enterprise deployments

---

## Problem Statement

Agentspan today uses process-level environment variables for all credentials (LLM API keys, GitHub tokens, etc.). This works for single-user local development but breaks in multi-user scenarios: two users sharing a server cannot use different API keys, and distributed workers have no way to resolve per-user secrets at execution time.

This design introduces a credential management system that is:
- **Frictionless for local dev** — env vars still work, zero config required
- **First-class for self-hosters** — built-in encrypted store, no external dependencies
- **Enterprise-ready** — pluggable vault backends, OIDC, RBAC as a separate closed-source module
- **Consistent** — same store and same resolution path for LLM keys, tool credentials, and CLI tool tokens

---

## Architecture & Module Boundaries

Three layers with clean interfaces between them:

```
┌──────────────────────────────────────────────────────────┐
│             Enterprise Module  (closed source)           │
│                                                          │
│  OIDC/Auth0 + pluggable OIDC providers                   │
│  AWS SM · GCP SM · Azure KV · HashiCorp Vault            │
│  CyberArk · Doppler · Kubernetes Secrets                 │
│  Org/team RBAC · Audit store · Credential policies       │
└──────────────────┬───────────────────────────────────────┘
                   │ implements OSS interfaces
┌──────────────────▼───────────────────────────────────────┐
│              agentspan-server  (OSS)                     │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │           Credential Module (new)                 │   │
│  │                                                   │   │
│  │  Management APIs (UI / CLI consume these)         │   │
│  │  Runtime API (workers consume this)               │   │
│  │  CredentialStoreProvider interface                │   │
│  │  Built-in encrypted DB store (default)            │   │
│  │  Credential binding registry                      │   │
│  │  Execution token mint & validate                  │   │
│  │  CLI tool → credential auto-mapping registry      │   │
│  └───────────────────────────────────────────────────┘   │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │       Execution Engine (existing + extended)      │   │
│  │                                                   │   │
│  │  AIModelProvider — per-user LLM key resolution    │   │
│  │  VectorDBProvider — per-user vector DB resolution │   │
│  │  Both use same resolution pipeline as workers     │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────┬───────────────────────────────────────┘
                   │ Conductor polling + /api/credentials/resolve
┌──────────────────▼───────────────────────────────────────┐
│              Workers / Python SDK  (OSS)                 │
│                                                          │
│  WorkerCredentialFetcher                                 │
│  SubprocessIsolator (temp HOME + env injection)          │
│  CLI tool auto-mapping registry                          │
│  @tool(isolated=True, credentials=[...])                 │
│  Agent(cli_allowed_commands=[...]) → auto-mapped         │
└──────────────────────────────────────────────────────────┘
```

### OSS vs Enterprise boundary

| Concern | OSS | Enterprise |
|---|---|---|
| CredentialStoreProvider interface | ✓ | — |
| Built-in encrypted DB store | ✓ | — |
| Env var fallback | ✓ | — |
| Management + runtime APIs | ✓ | — |
| Execution token mint/validate | ✓ | — |
| CLI auto-mapping registry | ✓ | — |
| Subprocess isolation | ✓ | — |
| Per-user LLM/VectorDB resolution | ✓ | — |
| OIDC/SSO integration | — | ✓ |
| External vault backends | — | ✓ |
| Org/team RBAC | — | ✓ |
| Audit store | — | ✓ |
| Custom credential policies | — | ✓ |

---

## RequestContext & User Identity

### Types

```java
class RequestContext {
    String requestId;      // UUID per HTTP request — distributed tracing
    String traceId;        // OpenTelemetry trace ID
    String workflowId;     // = sessionId (existing convention preserved)
    String executionToken; // minted at workflow start, carried by workers
    User   user;
    Instant createdAt;
    // enterprise module adds authz context here without modifying User
}

class User {
    String id;         // unique ID (OIDC sub claim, or internal DB ID)
    String name;       // display name
    String email;
    String username;
}
```

`User` is pure identity. Authorization (roles, permissions, org context) is a separate concern handled by the enterprise module — it is not part of `User`.

`RequestContext` is stored in `ThreadLocal` (Spring request scope) for the duration of each request, making it available throughout the call stack without explicit passing.

### OSS Authentication

Username/password configured in `application.properties`. Default credentials work out of the box:

```properties
# Default — no setup required
agentspan.auth.users[0].username=agentspan
agentspan.auth.users[0].password=agentspan

# Add more users (all admin in OSS, no AuthZ)
agentspan.auth.users[1].username=alice
agentspan.auth.users[1].password=secret123

# Disable auth entirely (single-developer local mode)
agentspan.auth.enabled=false
```

When `auth.enabled=false`, every request gets a default admin RequestContext — no token required.

### Auth Filter

```
Inbound request
  → Authorization: Bearer <jwt>  → validate JWT → extract User from claims
  → X-API-Key: <key>             → look up in DB → load associated User
  → auth.enabled=false           → anonymous admin User (local dev)
  → neither + auth.enabled=true  → 401
```

Enterprise replaces this filter with OIDC token introspection — same `AuthFilter` interface, different implementation. Auth0, Okta, Azure AD, and any OIDC-compliant provider are supported.

### Execution Token

When a workflow starts, the server mints a short-lived execution token from the RequestContext and embeds it in Conductor workflow variables (`__agentspan_ctx__`). Workers present this token to `/api/credentials/resolve` — they never see the user's JWT or API key.

```
Token payload:
  jti:   UUID            (unique token ID — used for revocation deny-list)
  sub:   userId          (credential resolution lookup key)
  wid:   workflowId      (audit trail)
  iat:   issued-at
  exp:   issued-at + max(workflow_timeout, 1h)  (see token expiry below)
  scope: "credentials"   (narrow, single purpose)

Signed: HMAC-SHA256 with server master secret
```

Conductor propagates `__agentspan_ctx__` to every task automatically. Workers extract it from task variables.

**Token expiry for long-running workflows:** The TTL is set to `max(1h, agent.timeout_seconds)` at mint time. Agents with long timeouts (e.g., `timeout_seconds=6000` as in the coding agent example) receive a proportionally longer token. This avoids credential resolution failures mid-execution without requiring a refresh mechanism.

**Token revocation:** The `jti` claim enables server-side revocation. The server maintains an in-memory deny-list keyed by `jti`, with each entry expiring at the token's `exp` time (so the list is self-pruning). When a workflow is cancelled or terminated, its `jti` is added to the deny-list immediately. All subsequent `/api/credentials/resolve` calls with that token return 401. In OSS the deny-list is in-memory (lost on server restart; bounded risk since tokens expire with the workflow TTL). Enterprise module can persist the deny-list to a durable store.

**Conductor access control:** The `__agentspan_ctx__` variable is embedded in Conductor workflow metadata. Conductor must be deployed as an internal-only service with no external access — agentspan-server is the sole entry point for all external callers. In multi-tenant deployments, workers authenticate to Conductor using a shared service account (not user credentials), and the execution token is the only user-scoped material that travels through the system.

### Developer Experience

Three levels, each frictionless:

**Level 0 — unchanged from today:**
```bash
export OPENAI_API_KEY=sk-...
python my_agent.py   # env var fallback, credential system invisible
```

**Level 1 — set once, never again:**
```bash
agentspan credentials set OPENAI_API_KEY sk-...
python my_agent.py   # fetched from credential store, no env var needed
```

**Level 2 — SDK auto-auth on localhost:**
```python
# Local dev — auto-authenticates as default user, zero config
with AgentRuntime() as runtime:
    runtime.run(agent, "do the thing")

# Remote / explicit
with AgentRuntime(server_url="https://team.agentspan.io", api_key="asp_xxx") as runtime:
    runtime.run(agent, "do the thing")
```

**Level 3 — team / enterprise:**
```bash
agentspan login   # OSS: prompts username/password
                  # Enterprise: opens browser → OIDC flow
# token stored in ~/.agentspan/config.json
# all subsequent CLI + SDK calls use it automatically
```

---

## Credential Store, Management APIs & Resolution Pipeline

### Data Model

```sql
-- Stored secrets (encrypted at rest)
credentials_store (
    user_id        FK → users.id,
    name           TEXT,           -- e.g. "my-github-prod-key"
    encrypted_value BYTEA,         -- AES-256-GCM
    created_at     TIMESTAMP,
    updated_at     TIMESTAMP,
    PRIMARY KEY (user_id, name)
)

-- Logical key → stored secret binding
credentials_binding (
    user_id        FK → users.id,
    logical_key    TEXT,           -- what code declares: "GITHUB_TOKEN"
    store_name     TEXT,           -- what is stored:     "my-github-prod-key"
    PRIMARY KEY (user_id, logical_key)
)

-- Users (OSS simple model)
users (
    id             UUID PRIMARY KEY,
    name           TEXT,
    email          TEXT,
    username       TEXT UNIQUE,
    password_hash  TEXT,
    created_at     TIMESTAMP
)

-- API keys
api_keys (
    id             UUID PRIMARY KEY,
    user_id        FK → users.id,
    key_hash       TEXT UNIQUE,    -- SHA-256 of raw key
    label          TEXT,
    last_used_at   TIMESTAMP,
    created_at     TIMESTAMP
)
```

The binding table is the indirection layer. A user declares: "when any tool asks for `GITHUB_TOKEN`, use the secret I named `my-github-prod-key`." Enterprise vault backends slot into the same binding structure — the store provider resolves from AWS SM, HashiCorp, etc. instead of the local DB.

### Management APIs

```
# Credential values
GET    /api/credentials                    list (name + partial value + updated_at)
POST   /api/credentials                    create { name, value }
PUT    /api/credentials/{name}             update { value }
DELETE /api/credentials/{name}             delete
GET    /api/credentials/{name}             metadata + partial value

# Bindings
GET    /api/credentials/bindings           list all bindings
PUT    /api/credentials/bindings/{key}     set { store_name }
DELETE /api/credentials/bindings/{key}     remove

# Runtime (execution token required, separate from management auth)
POST   /api/credentials/resolve            { token, names: ["GITHUB_TOKEN"] }
```

The `/api/credentials/resolve` endpoint enforces a per-token rate limit (default: 120 calls/minute, configurable). Additionally, credential names in the resolve request are validated against the names declared by the `@tool` or `Agent` at compile/dispatch time — a token cannot resolve credentials beyond what its workflow declared. This bounds the blast radius of a compromised token.

**Partial value format** — consistent with OpenAI, GitHub, AWS. First 4 + `...` + last 4. Value is never returned after creation.

List response (`GET /api/credentials`):
```json
[
  { "name": "my-github-prod-key",  "partial": "ghp_...k2mn", "updated_at": "2026-03-15" },
  { "name": "openai-prod",         "partial": "sk-...4x9z",  "updated_at": "2026-03-10" }
]
```

Single item response (`GET /api/credentials/{name}`):
```json
{
  "name": "my-github-prod-key",
  "partial": "ghp_...k2mn",
  "created_at": "2026-03-10T12:00:00Z",
  "updated_at": "2026-03-15T09:30:00Z"
}
```

### CredentialStoreProvider Interface

```java
interface CredentialStoreProvider {
    String               get(String userId, String name);
    void                 set(String userId, String name, String value);
    void                 delete(String userId, String name);
    List<CredentialMeta> list(String userId);  // name + partial + updated_at, no values
}
```

OSS ships `EncryptedDbCredentialStoreProvider` (AES-256-GCM with server master key).

Enterprise module implements: `AwsSecretsManagerProvider`, `GcpSecretManagerProvider`, `AzureKeyVaultProvider`, `HashiCorpVaultProvider`, `CyberArkProvider`, `DopplerProvider`, `KubernetesSecretsProvider`.

Configuration:
```properties
agentspan.credentials.store=built-in    # default (OSS)
agentspan.credentials.store=aws-sm      # enterprise
agentspan.credentials.store=hashicorp   # enterprise
agentspan.credentials.strict-mode=false # set true in enterprise for compliance
```

#### Master Key Lifecycle (OSS built-in store)

The built-in store encrypts all credential values with AES-256-GCM using a server master key. The master key lifecycle must be explicitly managed:

**Sourcing:**
- **Production / self-hosted:** Set `AGENTSPAN_MASTER_KEY` env var (base64-encoded 256-bit key). Server refuses to start if absent and `agentspan.credentials.store=built-in`.
- **Local dev:** If `AGENTSPAN_MASTER_KEY` is unset and the server is running on localhost, a key is auto-generated and persisted to `~/.agentspan/master.key` with a startup warning. This ensures local dev stays frictionless while production requires an explicit decision.

Generate a key:
```bash
openssl rand -base64 32
```

**Rotation:** When the master key changes, existing encrypted values become unreadable. A migration command re-encrypts the store under the new key:
```bash
agentspan admin credentials re-encrypt --old-key <prev> --new-key <next>
```

**Loss:** There is no recovery path if the master key is lost — the encrypted values are permanently inaccessible. Self-hosters must back up the key independently (e.g., in a password manager or a separate secrets store). This is documented prominently in the deployment guide.

Enterprise vault backends (AWS SM, HashiCorp, etc.) delegate key management entirely to the vault — this concern only applies to the OSS built-in store.

### Resolution Pipeline

Single function used by both the `/api/credentials/resolve` endpoint and the server-side `AIModelProvider` / `VectorDBProvider`:

```
resolve(userId, logicalKey):

  1. Look up binding: userId + logicalKey → store_name
     └─ no binding found? → use logicalKey as store_name directly (convenience shortcut)
        NOTE: this is intentional silent fallthrough — if a user stores a credential
        literally named "GITHUB_TOKEN" with no binding, it resolves correctly without
        an explicit bind step. This is the 80% case. It is not an error.

  2. Fetch from store via CredentialStoreProvider

  3. Not found in store?
     strict_mode=false → check os.environ[logicalKey] → return if present
                        (intentional silent fallthrough — enables backward compat
                         and local dev without any credential store setup)
     strict_mode=true  → throw CredentialNotFoundError (no silent fallback)

  4. Return value
```

The three-step fallthrough (binding → store → env var) is intentional and documented. When debugging a credential resolution failure, check all three stages in order.

This pipeline is the single authority for credential resolution across all call paths:
- Worker tasks via `/api/credentials/resolve`
- LLM execution via `AIModelProvider` (per-user key overrides server env var)
- Vector DB execution via `VectorDBProvider` (same pattern)

---

## Worker Credential Resolution & SDK Changes

### Worker Flow

```
Worker polls Conductor → picks up task
  │
  ├─ 1. Read __agentspan_ctx__ from task variables → execution token
  │
  ├─ 2. Determine needed credentials:
  │       @tool declaration       → explicit credentials list
  │       Agent cli_commands      → auto-mapped from cli_allowed_commands
  │       explicit override       → credentials=[...] on Agent
  │
  ├─ 3. WorkerCredentialFetcher:
  │       token present → POST /api/credentials/resolve
  │       token absent  → env var fallback (local dev, no credential service)
  │
  └─ 4. SubprocessIsolator runs tool with credentials injected
```

### WorkerCredentialFetcher

```python
class WorkerCredentialFetcher:
    def fetch(self, execution_token: str, names: list[str]) -> dict:
        if not execution_token:
            return self._env_fallback(names)   # local dev path

        result = http_post(f"{server_url}/api/credentials/resolve",
                           json={"token": execution_token, "names": names})

        missing = [n for n in names if n not in result]
        if missing and not strict_mode:
            result.update(self._env_fallback(missing))
        elif missing and strict_mode:
            raise CredentialNotFoundError(missing)

        return result

    def _env_fallback(self, names):
        return {n: os.environ[n] for n in names if n in os.environ}
```

**HTTP error contract for `/api/credentials/resolve`:**

| Status | Behavior |
|---|---|
| 200 | Return resolved credentials; missing names → env fallback or error per strict_mode |
| 401 | Token expired or revoked — raise `CredentialAuthError` immediately, do not retry, do not fall through to env var |
| 429 | Rate limit hit — raise `CredentialRateLimitError` immediately, do not fall through to env var |
| 5xx | Server error — raise `CredentialServiceError`; in strict_mode never fall through to env var; in non-strict_mode implementer may choose env fallback with a warning log |

### SubprocessIsolator

Every tool runs in a fresh subprocess with an isolated HOME directory. Credentials are injected and cleaned up after task completion:

```python
class SubprocessIsolator:
    def run(self, fn: Callable, args, credentials: dict) -> Any:
        with tempfile.TemporaryDirectory(prefix="agentspan-") as tmp_home:
            env = os.environ.copy()
            env["HOME"] = tmp_home

            for name, value in credentials.items():
                if isinstance(value, str):
                    env[name] = value                        # env var type
                elif isinstance(value, CredentialFile):
                    path = f"{tmp_home}/{value.relative_path}"
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    Path(path).write_text(value.content)
                    os.chmod(path, 0o600)                    # owner read/write only
                    env[value.env_var] = path                # file type

            return _run_in_subprocess(fn, args, env=env)
        # tmp_home deleted here — credentials gone from disk
```

Two credential types:

```python
# String type — injected directly as env var
"GITHUB_TOKEN"

# File type — written to tmp_home, env var points to temp path
CredentialFile("KUBECONFIG", ".kube/config")
# → written to {tmp_home}/.kube/config
# → KUBECONFIG env var set to that path
```

### `@tool` SDK Changes

`isolated=True` is the default. Opt out only for native tools that use `get_credential()` directly:

```python
# Default — subprocess isolation, zero changes to tool internals
@tool(credentials=["GITHUB_TOKEN",
                   CredentialFile("KUBECONFIG", ".kube/config")])
def deploy_to_k8s(branch: str) -> str:
    # subprocess has GITHUB_TOKEN and KUBECONFIG injected
    subprocess.run(["kubectl", "apply", ...])

# Opt-out — no subprocess, uses credential accessor (lower latency)
@tool(isolated=False, credentials=["OPENAI_API_KEY"])
def call_openai(prompt: str) -> str:
    key = get_credential("OPENAI_API_KEY")   # reads from execution context
    client = OpenAI(api_key=key)
    ...
```

### `Agent` CLI Auto-mapping

`cli_allowed_commands` drives credential resolution automatically. No explicit credential declaration needed for common tools:

```python
# Credentials auto-mapped: gh → GITHUB_TOKEN, GH_TOKEN; git → same
git_fetch_issues = Agent(
    cli_commands=True,
    cli_allowed_commands=["gh", "git", "mktemp", "rm"],
)

# Explicit override when auto-map is insufficient
terraform_agent = Agent(
    cli_commands=True,
    cli_allowed_commands=["terraform", "aws"],
    credentials=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "TF_VAR_db_password"],
)
```

### CLI Auto-mapping Registry

Ships with both the Python SDK and agentspan-server (OSS). Enterprise module can extend without touching OSS code:

```python
CLI_CREDENTIAL_MAP = {
    "gh":        ["GITHUB_TOKEN", "GH_TOKEN"],
    "git":       ["GITHUB_TOKEN", "GH_TOKEN"],
    "aws":       ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"],
    "kubectl":   [CredentialFile("KUBECONFIG", ".kube/config")],
    "helm":      [CredentialFile("KUBECONFIG", ".kube/config")],
    "gcloud":    ["GOOGLE_CLOUD_PROJECT",
                  CredentialFile("GOOGLE_APPLICATION_CREDENTIALS",
                                 ".config/gcloud/application_default_credentials.json")],
    "az":        ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
                  "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"],
    "docker":    ["DOCKER_USERNAME", "DOCKER_PASSWORD"],
    "npm":       ["NPM_TOKEN"],
    "cargo":     ["CARGO_REGISTRY_TOKEN"],
    "terraform": None,  # no auto-mapping — raises ConfigurationError at agent definition
                        # time if no explicit credentials=[...] declared. Fail loud,
                        # not silently with zero credentials injected.
}
```

### Updated AgentConfig

```python
@dataclass
class AgentConfig:
    server_url: str              = "http://localhost:8080/api"
    api_key: str | None          = None    # Bearer token or static API key (Authorization header)
    auth_key: str | None         = None    # kept for backward compat
    auth_secret: str | None      = None    # kept for backward compat
    worker_poll_interval_ms: int = 100
    worker_thread_count: int     = 1
    auto_start_workers: bool     = True
    daemon_workers: bool         = True
    credential_strict_mode: bool = False   # True = disable env var fallback (strict compliance mode)

    @classmethod
    def from_env(cls) -> "AgentConfig": ...
```

---

## agentspan CLI Credentials

The CLI calls server management APIs directly. Credentials live on the server — the only local file is `~/.agentspan/config.json` (auth tokens).

```bash
# Auth
agentspan login                             # OSS: username/password prompt
                                            # Enterprise: browser OIDC flow
agentspan logout

# Common case — set by logical name, binding is implicit (name = key)
agentspan credentials set GITHUB_TOKEN ghp_xxx
agentspan credentials set OPENAI_API_KEY sk-xxx

# Advanced — named secret with explicit binding (multiple environments)
agentspan credentials set --name github-prod ghp_xxx
agentspan credentials bind GITHUB_TOKEN github-prod

# Inspect
agentspan credentials list                  # name + partial value + updated_at
agentspan credentials delete GITHUB_TOKEN
agentspan credentials bindings              # logical key → stored name mappings
```

---

## Security Model

### Execution Token

- Scoped to a single workflow execution (`wid` + `jti` in payload)
- TTL = `max(1h, workflow timeout)` — prevents expiry mid-execution for long-running agents
- HMAC-SHA256 signed — server validates on every resolve call
- Scope claim `"credentials"` — cannot be used for other operations
- Revocable via `jti` deny-list — added immediately on workflow cancel/terminate
- Credential names bounded to those declared at compile time — token cannot resolve undeclared secrets

### Credential Lifecycle

| Stage | Protection |
|---|---|
| At rest | AES-256-GCM, server master key |
| In transit | HTTPS only |
| After creation | Value never returned — partial display only |
| In worker process | Injected into subprocess env only, never parent process |
| After task | Temp HOME deleted synchronously, subprocess exited |
| Across tasks | No caching — fetched fresh per task execution |

### Strict Mode

```
strict_mode=false (default)
  credential service → os.environ fallback → CredentialNotFoundError

strict_mode=true (enterprise default)
  credential service only → CredentialNotFoundError
  (no env var leakage, compliance-friendly)
```

### Audit Log

Every `/api/credentials/resolve` call logged:
```json
{ "userId": "u123", "workflowId": "wf789", "taskId": "t456",
  "credentialNames": ["GITHUB_TOKEN"], "timestamp": "...", "ip": "..." }
```

OSS writes to server log. Enterprise module persists to a queryable audit store.

### Attack Surface

| Threat | Mitigation |
|---|---|
| Worker process compromised | Execution token only — 1h TTL, narrow scope, not the real credential |
| Concurrent task credential bleed | Subprocess isolation — parent never holds credentials in `os.environ` |
| `/proc/PID/environ` readable on Linux | Subprocess is short-lived and exits immediately after task; temp HOME deleted synchronously (credential files are gone before any external read is likely). LLM keys are a separate path — they never leave the server at all. |
| Token replay | `jti` deny-list + `exp` + `wid` — revocable, single-workflow-scoped |
| Malicious CLI tool reads temp HOME | Credential files written `0600`; temp dir deleted synchronously after task |
| Credential exfiltration via tool code | Token scope bounded to declared names; short TTL; revocation on cancel; audit trail |
| Excessive resolve calls (DoS / enumeration) | Per-token rate limit (default 120/min); names validated against declared set |
| Conductor variables readable by external callers | Conductor is internal-only; agentspan-server is sole external entry point |

---

## Summary of Changes by Component

| Component | Change |
|---|---|
| `agentspan-server` | Add Credential Module: store, binding, management APIs, `/resolve` endpoint, execution token, auth filter |
| `AIModelProvider` | Extend to resolve per-user LLM keys via resolution pipeline |
| `VectorDBProvider` | Same extension as AIModelProvider |
| `Python SDK` | `WorkerCredentialFetcher`, `SubprocessIsolator`, `CredentialFile` type, `get_credential()` accessor, `@tool(isolated, credentials)`, `Agent(credentials)`, `AgentConfig.credential_strict_mode` |
| `CLI auto-mapping registry` | Ships in both SDK and server (OSS) |
| `agentspan CLI (Go)` | `agentspan login/logout`, `agentspan credentials` subcommand group |
| `Enterprise module` | OIDC filter, vault provider implementations, RBAC, audit store |
