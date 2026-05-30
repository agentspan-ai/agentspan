# Secrets — Design (As-Built)

**Status:** Implemented (OSS). Enterprise vault backends pending.
**Source specs:** [`specs/2026-03-20-credential-management-design.md`](specs/2026-03-20-credential-management-design.md), [`specs/2026-03-22-universal-credential-support-design.md`](specs/2026-03-22-universal-credential-support-design.md), [`specs/2026-03-20-credentials-ui-design.md`](specs/2026-03-20-credentials-ui-design.md).

This document is the consolidated, current-state design for credentials in AgentSpan. The dated specs above record the original proposals and rationale; this doc reflects what the codebase actually does today.

---

## 1. Goals

- **Frictionless local dev** — env vars work without any setup.
- **Multi-user safe** — two users on the same server use distinct keys.
- **Distributed-worker safe** — workers resolve per-execution credentials via a short-lived token, never see the user's session.
- **One pipeline** — same resolution code path for LLM keys, tool credentials, HTTP/MCP headers, CLI tools, and framework passthroughs.
- **Pluggable** — `SecretStoreProvider` interface lets Enterprise swap in AWS SM / HashiCorp Vault / Azure KV without touching OSS code.

---

## 2. Backend Architecture

### 2.1 Module layout (server)

`server/src/main/java/dev/agentspan/runtime/secrets/`:

| Class | Responsibility |
|---|---|
| `SecretStoreProvider` (iface) | `get/set/delete/list` over an opaque backend |
| `EncryptedDbSecretStoreProvider` | OSS default — AES-256-GCM in SQLite/Postgres |
| `MasterKeyConfig` | Sources `AGENTSPAN_MASTER_KEY`; falls back to `~/.agentspan/master.key` on localhost |
| `SecretDataSourceConfig` | Dedicated HikariCP pool (8 conns) for the credential DB |
| `SecretTagsService` | CRUD over `secret_tags` (key/value labels per secret) |
| `SecretResolutionService` | Single authority: `(userId, name) → plaintext` (direct lookup) |
| `ExecutionTokenService` | Mint/validate HMAC-SHA256 execution tokens; in-memory `jti` deny-list |
| `SecretEnvSeeder` | One-shot startup seeder for ~105 well-known provider env vars |
| `SecretAwareHttpTask` / `Config` | Resolves `${NAME}` in HTTP-task headers before dispatch |
| `SecretAwareMcpService` | Resolves `#{NAME}` in MCP tool headers |
| `controller/SecretController + WorkerController` | REST surface (management + `/resolve`) |

### 2.2 Data model

```sql
users(id UUID PK, username UNIQUE, password_hash, email, name, created_at)

api_keys(id UUID PK, user_id FK, key_hash SHA256 UNIQUE, label, last_used_at, created_at)

secrets_store(
    user_id FK,
    name TEXT,                   -- e.g. "GITHUB_TOKEN"
    encrypted_value BLOB,        -- [12B IV][ciphertext + 16B GCM tag]
    created_at, updated_at,
    PRIMARY KEY(user_id, name)
)

secret_tags(
    user_id FK,
    name TEXT,                   -- secret this tag belongs to
    tag_key TEXT,
    tag_value TEXT,
    PRIMARY KEY(user_id, name, tag_key, tag_value)
)

secret_disclosures(
    execution_id TEXT,           -- workflow / agent execution id
    user_id FK,
    name TEXT,                   -- secret name disclosed to this execution's worker
    disclosed_at TEXT,
    PRIMARY KEY(execution_id, name)
)
```

`secret_disclosures` is written by `WorkerController.resolveSecrets` on every successful name resolution and read by `SecretMaskingResponseAdvice` to redact those values from execution-read responses (§4.5).

The earlier `credentials_binding` table (logical-key → store-name indirection) was removed for parity with Conductor's flat-name secrets API. The legacy `credentials_store` table was renamed to `secrets_store` — `SecretSchemaMigrator` copies any existing rows on first startup and drops the old table. Both transitions are zero-downtime for self-hosters.

Schemas: `server/src/main/resources/schema-secrets.sql` (SQLite) and `schema-secrets-postgres.sql`.

### 2.3 Encryption at rest

- **Algorithm:** AES-256-GCM (authenticated).
- **IV:** 12 random bytes per value.
- **Blob layout:** `[IV 12B][ciphertext + 16B GCM tag]` — Conductor-portable.
- **Master key:** 32 bytes, sourced from `AGENTSPAN_MASTER_KEY` (base64) in production; auto-generated to `~/.agentspan/master.key` (mode `0600`) on localhost for dev.
- **Rotation:** `agentspan admin credentials re-encrypt --old-key … --new-key …`.
- **Loss:** unrecoverable — self-hosters must back up the key.

### 2.4 Execution token

Workers never present the user's JWT or API key to `/api/workers/secrets`. The server mints an execution-scoped token at workflow start and embeds it in Conductor workflow variables as `__agentspan_ctx__`.

```
jti    UUID                     unique ID, used for revocation deny-list
sub    userId                   resolution lookup key
wid    executionId              audit trail
iat    issued-at
exp    iat + max(1h, agent.timeout_seconds)
scope  "credentials"            narrow, single-purpose
sig    HMAC-SHA256 (master)
```

- **TTL:** `max(1h, execution timeout)` — long-running agents don't expire mid-run.
- **Revocation:** server keeps an in-memory deny-list keyed by `jti`. On execution cancel/terminate the `jti` is added; entries self-prune at `exp`. OSS = process-local; Enterprise can durably persist.
- **Declared-name binding:** at dispatch time the token records the set of secret names declared by the tool/agent. The resolve endpoint rejects names outside that set — bounds the blast radius of a compromised token. **Prefix-permissive for JSONPath:** if the parent `GCP_SVC` is declared, requests for `GCP_SVC.project_id` are allowed (the dot boundary is required — `FOO` does not permit `FOOBAR.x`). Rationale: JSONPath access doesn't expand the blast radius, since the parent secret already grants the whole blob.
- **Rate limit:** 120 calls/min/token (configurable).

### 2.5 Resolution pipeline

`SecretResolutionService.resolve(userId, name)`:

1. **Flat name** (no `.`): `storeProvider.get(userId, name)` → return value (or null).
2. **Dotted name** (Conductor-parity JSONPath): split on first `.`. Fetch the base secret, parse it as JSON, walk the remaining dotted path via Jackson, return the leaf as a string (text nodes unquoted; other types as compact JSON). Returns null if the base isn't JSON or the path doesn't resolve.

Examples:

```
GCP_SVC                       → raw stored value
GCP_SVC.project_id            → field "project_id" from JSON-valued GCP_SVC
BLOB.auth.oauth.client_id     → deeply nested extraction
GCP_SVC.does_not_exist        → null
FLAT_TOKEN.field              → null (FLAT_TOKEN isn't JSON)
```

Constraint: dotted resolution always splits on the **first** `.`. Don't put dots in secret names — store them under dot-free names and address fields via dotted paths.

No indirection layer beyond JSONPath. (Earlier designs had a `logical_key → store_name` binding table; it was removed for parity with Conductor's flat-namespace secrets API. Multi-environment use cases switch by changing the stored value, not by rebinding.)

The server itself does **not** perform an env-var fallback. Env-var convenience is provided by:

- **`SecretEnvSeeder`** — at server startup, copies any of ~105 well-known env vars (OpenAI, Anthropic, AWS, GCP, etc.) into the default user's credentials store. So `export OPENAI_API_KEY=…` still "just works" without any setup.
- **SDK fallback** — when `secret_strict_mode=false`, missing names from `/resolve` fall back to `os.environ` in the worker process (local-dev compat).

---

## 3. API Surface

Two namespaces, two auth primitives. **The path itself documents which auth is required.**

| Namespace | Auth | Consumer | Purpose |
|---|---|---|---|
| `/api/secrets/*`  | Login JWT or API key (`AuthFilter`) | UI, CLI, humans | Management — create / read / update / delete / list secrets |
| `/api/workers/*`  | Execution token (`ExecutionTokenService`) | Distributed workers | Runtime — pull declared secrets for the current execution |

This split is intentional. Earlier designs put both under `/api/secrets` with `/resolve` as a subpath, but that hid the auth-boundary difference behind a path segment. `/api/workers/*` is reserved for future token-mediated worker endpoints (heartbeat, lease extension, handoff, …) using the same execution-token primitive.

### 3.1 Conductor-parity surface

Mirrors `io.orkes.conductor.server.rest.SecretResource`.

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST`   | `/api/secrets`               | —              | `List<String>` of names |
| `GET`    | `/api/secrets`               | —              | `List<String>` (RBAC-filtered; same set as POST in OSS) |
| `GET`    | `/api/secrets/{key}`         | —              | plaintext value (`text/plain`); `404` if missing |
| `PUT`    | `/api/secrets/{key}`         | raw string     | `200` (upsert) |
| `DELETE` | `/api/secrets/{key}`         | —              | `204` |
| `GET`    | `/api/secrets/{key}/exists`  | —              | `true` / `false` |
| `GET`    | `/api/secrets/{key}/tags`    | —              | `List<{key, value}>` |
| `PUT`    | `/api/secrets/{key}/tags`    | `List<{key, value}>` | `200` (add) |
| `DELETE` | `/api/secrets/{key}/tags`    | `List<{key, value}>` | `200` (remove) |

`GET /{key}` returns plaintext (Conductor parity). Every read is audit-logged. RBAC will gate this in Enterprise; in OSS, anyone with management auth can read or overwrite, so hiding plaintext on GET would be theater.

### 3.2 V2 listing (AgentSpan extension, mirrors Conductor V2)

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/secrets/v2` | `List<SecretMeta>` — name + partial + created_at + updated_at + tags |

`partial` follows the OpenAI/GitHub convention: first-4 + `…` + last-4. The UI uses this endpoint for the secrets table; the v1 `POST /api/secrets` is reserved for strict-parity callers.

### 3.3 Worker secret fetch (AgentSpan-only)

Conductor has no equivalent — its workers receive substituted plaintext at task dispatch. AgentSpan workers are out-of-process (often user-written, sometimes on untrusted infra), so they pull declared secrets at runtime using the execution token embedded in `__agentspan_ctx__`.

Lives at `/api/workers/secrets` (not `/api/secrets/resolve`) because its auth model — execution token, not login session — is fundamentally different from the other `/api/secrets/*` endpoints. The path makes the boundary visible.

```
POST /api/workers/secrets
{
  "token": "<execution token>",
  "names": ["GITHUB_TOKEN", "OPENAI_API_KEY"]
}

200 → { "GITHUB_TOKEN": "ghp_…", "OPENAI_API_KEY": "sk-…" }
       (missing names omitted; SDK chooses env fallback or error per strict_mode)
401 → token expired / revoked / invalid       — no env fallback
429 → rate limit                              — no env fallback
5xx → server error
```

Every resolve call is audit-logged: `{userId, executionId, taskId, names, timestamp, ip}`.

The earlier `/api/credentials/*` surface was removed in favor of `/api/secrets/*` parity (Step 3 of the credentials→secrets migration).

---

## 4. Secret Injection by Tool Type

Credentials are declared at definition time and resolved at execution time. The injection mechanism varies by where the credential needs to land.

| Tool kind | Where resolved | Where injected | Mechanism |
|---|---|---|---|
| `@tool(secrets=[...])` | Worker, in-process | `os.environ` for the call | Server fetch → `inject_via_env` (lock-around-invoke) — see [secret-injection-contract.md](./secret-injection-contract.md) |
| `Agent(cli_commands=True)` | Worker, in-process | `os.environ` for the call | Auto-mapped from `CLI_CREDENTIAL_MAP`, same helper |
| HTTP tool (system task) | Server | Request headers | `${NAME}` rewritten by `SecretAwareHttpTask` |
| MCP tool (system task) | Server | Tool-server headers | `#{NAME}` rewritten by `SecretAwareMcpService` |
| Framework passthrough (LangGraph/LangChain/OpenAI/ADK) | Worker, in-process | `os.environ` for `invoke()` | Same `inject_via_env` helper as native tools |
| External worker | Caller's process | Caller's responsibility | Direct `POST /api/workers/secrets` with `__agentspan_ctx__` token |
| LLM provider keys | Server | Provider client init | Same pipeline via `AIModelProvider` |
| Vector DB keys | Server | Provider client init | Same pipeline via `VectorDBProvider` |

All in-process injection paths (the first three rows) share a single process-wide lock so concurrent invocations don't clobber each other's env. The lock is the only safety mechanism — there's no subprocess isolation. For throughput, scale by running additional worker processes.

### 4.1 SDK declaration

```python
# Declare secrets the tool needs — server resolves at runtime, value reaches
# os.environ for the duration of this call.
@tool(secrets=["GITHUB_TOKEN"])
def fetch_issues(repo: str) -> str:
    token = os.environ["GITHUB_TOKEN"]
    ...

# Same secrets, read via the contextvars accessor instead of env.
# Prefer this when the underlying SDK accepts an explicit api_key — avoids
# the env-mutation lock entirely.
@tool(secrets=["OPENAI_API_KEY"])
def call_openai(prompt: str) -> str:
    key = get_secret("OPENAI_API_KEY")
    client = OpenAI(api_key=key)
    ...

# Agent-level — auto-mapped for known CLIs
Agent(cli_commands=True, cli_allowed_commands=["gh", "git"])
# → resolves GITHUB_TOKEN, GH_TOKEN automatically
```

### 4.2 Worker flow

```
Conductor poll → task picked up
  │
  ├─ Read __agentspan_ctx__ → execution token
  ├─ Compute needed names: declared @tool/Agent set ∪ CLI auto-map
  ├─ WorkerCredentialFetcher.fetch(token, names):
  │     POST /api/workers/secrets
  │     ├─ 200 + missing names  → raise CredentialNotFoundError (terminal)
  │     ├─ 401                  → raise CredentialAuthError (terminal)
  │     ├─ 429                  → raise CredentialRateLimitError (terminal)
  │     └─ 5xx                  → raise CredentialServiceError (terminal)
  └─ inject_via_env(secrets, lambda: tool_fn(**kwargs)):
        with process_wide_lock:
          save previous os.environ values
          os.environ.update(secrets)
          try:    return tool_fn(**kwargs)
          finally: restore previous os.environ values
```

### 4.3 HTTP / MCP placeholder rewriting (server-side)

For tools that execute as Conductor system tasks (no worker process owns them), the server resolves credentials before dispatching the HTTP/MCP call. Both HTTP and MCP use the `#{NAME}` sigil (regex `#\{[\w.]+}`):

```
# HTTP task headers
Authorization: Bearer #{GITHUB_TOKEN}
X-Project:     #{GCP_SVC.project_id}        # JSONPath into a JSON-valued secret

# MCP tool headers
X-API-Key:     #{OPENAI_API_KEY}
X-Client-Id:   #{BLOB.auth.oauth.client_id} # nested JSONPath
```

Dotted names go through the same `SecretResolutionService` as worker-side resolution, so the JSONPath syntax is uniform across all four call paths (worker `/api/workers/secrets`, HTTP placeholder, MCP placeholder, server-side LLM/VectorDB providers).

This means credential material **never leaves the server** for system-task tools — workers don't see it, neither does Conductor (placeholders are rewritten on egress).

### 4.4 Framework passthrough (LangGraph / LangChain / OpenAI SDK / Google ADK)

Framework agents run third-party code in-process and read keys from `os.environ` (e.g. `langchain_openai` reads `OPENAI_API_KEY` itself). The runtime resolves declared credentials, temporarily sets them in `os.environ` around the framework invocation, then restores prior state. This path is **single-threaded by construction** — the worker holds a process-wide lock during the framework call to prevent credential bleed across concurrent executions. Multi-threaded scaling for framework agents requires separate worker processes.

### 4.5 Output masking (defense in depth on the read path)

Even with all the controls above, a tool's *output* can leak a secret value verbatim — e.g. `gh` prints `error: authentication failed (token: ghp_realtoken123)` to stderr, and that string ends up in the Conductor task output. Anyone with execution-read permission would then see the plaintext.

The masker closes that gap:

1. **Disclosure tracking** — `WorkerController.resolveSecrets` writes one row to `secret_disclosures` per successfully resolved name, scoped to the execution id + user id.
2. **Read-side redaction** — `SecretMaskingResponseAdvice` is a Spring `@ControllerAdvice` that activates on per-execution read URIs: `/api/agent/executions/{id}` (+ `/full`, `/tasks`), `/api/agent/execution/{id}`, and the bare-id `/api/agent/{id}/status`. It pulls the disclosed names from `secret_disclosures`, fetches their **current** plaintext from the secret store, parses the response body as JSON, walks every string node, and replaces each occurrence of a disclosed value with `***NAME***`. Tree-walking (rather than literal `String.replace` on the JSON text) is required so values that contain newlines, quotes, or other JSON-escaped characters are still matched — JSON serialization would have escaped them in the wire payload.

Key properties:

- **Read-time, not write-time.** Storage rewrite would be irreversible. Rotation handles itself: the always-current store value is what gets masked.
- **Minimum-length floor (8 chars).** Shorter values produce too many false positives in natural-language output.
- **Literal substring replace** (not regex) — safe for values containing metacharacters.
- **JSON-aware** — values containing `"`, `\`, newlines, or other characters that JSON serialization escapes are still masked because the masker matches against unescaped text-node values, not the wire payload.
- **Best effort.** If anything fails (parse error, no user context, no disclosures), the body passes through unchanged. Masking should never block a response.
- **Bounded retention.** `secret_disclosures` rows are pruned hourly by `SecretDisclosureService.pruneScheduled` with a default 30-day retention (configurable via `agentspan.secrets.disclosure-retention-days`). Older execution payloads remain readable but will not be masked — by design: a 30-day-old disclosed token should have been rotated anyway.

What this does **not** cover:

- **List endpoints** (`GET /api/agent/list`, `GET /api/agent/executions`, `GET /api/agent/executions/search`) — these return aggregate metadata, not per-execution payload bodies. The advice intentionally does **not** activate on list responses: there is no single execution id to scope disclosures against, and list rows surface summary fields (status, timestamps, names) rather than task outputs. If a secret can appear in a *list-row* field (e.g. an agent name shaped like an env-var template), file it as a separate masking gap.
- **POST / mutation endpoints** that echo input (e.g. `/{executionId}/respond`, `/{executionId}/signal`) — the input body is what the caller already supplied, so masking it would help nothing; the *task output* it triggers is still masked when read back through the GET path.
- **Live SSE streams** (`/api/agent/stream/{id}`) — events flow through the streaming converter, which the advice doesn't intercept. Follow-up work.
- **Bypassing AgentSpan to hit Conductor directly** — Conductor is internal-only per the existing security model.
- **Off-server log files** — worker stdout captured by the orchestrator. AgentSpan can't reach into those.

---

## 5. Developer Experience Tiers

| Tier | Setup | What happens |
|---|---|---|
| 0 — local dev | `export OPENAI_API_KEY=…; python agent.py` | Seeder copies env into default-user store at boot; resolve serves it back |
| 1 — set once | `agentspan credentials set OPENAI_API_KEY sk-…` | No env var needed; persists across restarts |
| 2 — SDK auto-auth | `AgentRuntime()` on localhost | Auto-authenticates as default user; zero config |
| 3 — team / enterprise | `agentspan login` (OIDC in Enterprise) | Token in `~/.agentspan/config.json`; CLI + SDK both use it |

`AgentConfig.secret_strict_mode = True` disables the SDK env-var fallback and the startup seeder — required for compliance-sensitive deployments. Recommended default in Enterprise.

---

## 6. Security Model (summary)

| Threat | Mitigation |
|---|---|
| Worker process compromise | Token has 1h+ TTL, narrow scope, declared-name binding, revocable |
| Credential bleed across concurrent agent invocations | `inject_via_env` holds a process-wide lock across mutation + invoke + restore. See [secret-injection-contract.md](./secret-injection-contract.md). |
| `/proc/PID/environ` exposure | Env mutations are scoped to the duration of a single tool call and restored synchronously; only present during the locked region. |
| Token replay | `jti` deny-list + `exp` + `wid` |
| Tool exfiltration via egress | Names bounded to declared set; audit trail; rate-limited |
| Conductor variable leakage | Conductor is internal-only; agentspan-server is sole external entry point |
| Master key loss | Documented; backup is operator's responsibility |
| Plaintext leaks via tool output (e.g. CLI error messages echo a token) | **Output masking** — `SecretMaskingResponseAdvice` redacts disclosed values from execution-read response bodies |
| **Cross-tenant leak when SDK is embedded in a host app** (e.g. Django, FastAPI) | **Run agentspan-server as a separate service.** The process-wide env-injection lock is insufficient when arbitrary host-app code can read `os.environ` during the injection window. See [secret-injection-contract.md §7](./secret-injection-contract.md#7-embedded-deployments--the-contract-assumes-a-dedicated-worker-process). |

---

## 7. OSS vs Enterprise Boundary

| Concern | OSS | Enterprise |
|---|:-:|:-:|
| `SecretStoreProvider` interface, encrypted DB store | ✓ | — |
| Env-var seeding + SDK fallback | ✓ | — |
| Management + `/resolve` APIs | ✓ | — |
| Execution token mint/validate (in-memory deny-list) | ✓ | — |
| CLI auto-mapping registry | ✓ | — |
| Subprocess isolation | ✓ | — |
| HTTP/MCP placeholder resolution | ✓ | — |
| Per-user LLM / VectorDB resolution | ✓ | — |
| OIDC / SSO authentication | — | ✓ |
| AWS SM / GCP SM / Azure KV / HashiCorp / CyberArk / Doppler / K8s Secrets | — | ✓ |
| Org / team RBAC, credential policies | — | ✓ |
| Durable audit store, durable token revocation | — | ✓ |

Enterprise plugs in via the same `SecretStoreProvider` and `AuthFilter` interfaces — no OSS changes required.

---

## 8. Known Gaps & Follow-ups

- **Enterprise vault providers** — design done; implementations not yet shipped.
- **Durable token revocation** — OSS deny-list is in-memory; bounded risk because TTL ≤ execution timeout, but a server crash drops revocations.
- **Multi-threaded framework passthrough throughput** — tier-2 (env-injection) calls serialize under the shared lock; scale by adding worker processes. Tier-1 (explicit-key via `get_secret()` or factory `secrets=` arg) runs fully concurrent.
- **TypeScript SDK** — credential resolution path needs verification against the Python SDK's contract.
- **Java SDK framework passthrough** — Java SDK has runtime credential resolution (`ai.agentspan.Secrets` accessor, `@Tool(credentials={…})` declaration). What's NOT supported: framework integrations (LangChain4j, OpenAI-Agents) that depend on env-var auto-discovery — Java's `System.getenv()` is immutable, so users must construct those clients with explicit `api_key` arguments.
- **Credential rotation / expiry** — no first-class TTL on stored credentials; rotation is a `PUT` from the operator.

---

## 9. References

- Specs: [`specs/2026-03-20-credential-management-design.md`](specs/2026-03-20-credential-management-design.md), [`specs/2026-03-22-universal-credential-support-design.md`](specs/2026-03-22-universal-credential-support-design.md), [`specs/2026-03-20-credentials-ui-design.md`](specs/2026-03-20-credentials-ui-design.md).
- Implementation plans: `plans/2026-03-20-credential-management-server.md`, `plans/2026-03-20-credential-management-python-sdk.md`, `plans/2026-03-20-credential-management-go-cli.md`, `plans/2026-03-21-credentials-ui.md`, `plans/2026-03-22-universal-credential-support.md`.
- Server code: `server/src/main/java/dev/agentspan/runtime/secrets/`.
- Python SDK examples: `sdk/python/examples/16_credentials_*.py` (a–k).
- Tests: `server/src/test/java/.../credentials/`, `sdk/python/tests/{unit,e2e}/test_*credential*.py`, `ui/e2e/credentials.spec.ts`.
