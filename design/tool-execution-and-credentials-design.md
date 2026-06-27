# Tool Execution and Credentials Design

**Status:** Consolidated 2026-06-26

**Scope:** This is the canonical design for two coupled subsystems in AgentSpan. The first half covers **tool and code execution** — how an agent's LLM runs code via the `execute_code` tool, the executor types (local, Docker, Jupyter, serverless), the interpreter table, command validation, timeouts, and how tools register as Conductor workers. The second half covers **credentials and secrets** — the encrypted-at-rest store, execution-token auth for distributed workers, per-user LLM keys, output masking on the read path, the SDK secret-injection contract every SDK must honor, and the **Secrets** management UI. The two halves meet at secret injection into tools: a tool declares the secrets it needs, and the credentials pipeline resolves and injects them at execution time. Siblings: [agentspan-design.md](agentspan-design.md) (overall architecture), [api-design.md](api-design.md) (REST surface), [sdk-design.md](sdk-design.md) (cross-SDK contracts), [framework-integration.md](framework-integration.md) (framework passthrough). Framework-passthrough credential injection detail is shared with [framework-integration.md](framework-integration.md).

---

# Part 1 — Tool & Code Execution

Local code execution lets an agent's LLM run code on the user's machine (or in a sandbox) via an `execute_code` tool. The LLM sends code + language; a **worker** on the SDK side executes it and returns stdout/stderr/exit code. The contract below is the *target* shape; coverage varies by SDK — see §2.10 for the as-built matrix. There is no Go SDK (Python, TypeScript, Java, and C#/.NET only).

```
LLM  ──tool_call──►  Conductor  ──task──►  SDK Worker  ──subprocess──►  Result
     (execute_code)               (SIMPLE)              (temp file)
```

## 2.1 ExecutionResult

A data object returned by every executor.

| Field       | Type    | Description                                 |
|-------------|---------|---------------------------------------------|
| `output`    | string  | Captured stdout                             |
| `error`     | string  | Captured stderr                             |
| `exit_code` | int     | Process exit code (0 = success)             |
| `timed_out` | bool    | Whether execution hit the timeout           |

**Derived property:** `success` = `exit_code == 0 && !timed_out`

## 2.2 CodeExecutor (interface / abstract base)

Every SDK must implement this interface:

```
interface CodeExecutor {
    execute(code: string) -> ExecutionResult
}
```

**Constructor parameters:**

| Param         | Type   | Default    | Description                           |
|---------------|--------|------------|---------------------------------------|
| `language`    | string | `"python"` | Target interpreter language            |
| `timeout`     | int    | `30`       | Max execution time in seconds          |
| `working_dir` | string | `null`     | Working directory for the subprocess   |

## 2.3 Executor implementations

### 2.3a LocalCodeExecutor

Runs code in a local subprocess via a temp file.

**Algorithm:**

1. If `code` is empty/null, return `ExecutionResult(output="No code provided. Nothing to execute.", exit_code=0)`.
2. Map `language` to interpreter command using the interpreter table (below).
3. Write `code` to a temp file with the appropriate extension.
4. Run `subprocess(interpreter, temp_file)` with:
   - `timeout` applied
   - `working_dir` as cwd (if set)
   - stdout and stderr captured separately
5. Return `ExecutionResult(stdout, stderr, exit_code)`.
6. On timeout: return `ExecutionResult(error="...", exit_code=-1, timed_out=true)`.
7. **Always** delete the temp file in a finally block.

**Interpreter table:**

| Language       | Command(s)      | File Extension |
|----------------|-----------------|----------------|
| `python`       | `python3`       | `.py`          |
| `python3`      | `python3`       | `.py`          |
| `bash`         | `bash`          | `.sh`          |
| `sh`           | `sh`            | `.sh`          |
| `node`         | `node`          | `.js`          |
| `javascript`   | `node`          | `.js`          |
| `ruby`         | `ruby`          | `.rb`          |

> **Portability note:** On Windows, `python3` may not exist; fall back to `python`. For Node.js, use `node` on all platforms.

### 2.3b DockerCodeExecutor

Runs code inside a Docker container for isolation.

**Algorithm:**

1. Build Docker command:
   ```
   docker run --rm -i [--network=none] [--memory LIMIT]
     [-v host:container:ro ...] IMAGE INTERPRETER -c CODE
   ```
2. Pass code via stdin (not a temp file — avoids volume mounts for code).
3. Capture stdout/stderr from the container.
4. Add extra timeout buffer (e.g. +10s) for container startup.
5. Default: `--network=none` (disable network).

**Constructor extras:**

| Param             | Type              | Default             |
|-------------------|-------------------|---------------------|
| `image`           | string            | `"python:3.12-slim"`|
| `network_enabled` | bool              | `false`             |
| `memory_limit`    | string            | `null`              |
| `volumes`         | map<string,string>| `{}`                |

### 2.3c JupyterCodeExecutor

Uses a Jupyter kernel for stateful execution (state persists between calls).

> **Note:** This is the exception to the "isolated per call" rule. Only include this executor in SDKs where Jupyter kernels are available. As-built: **Python is the only real implementation.** The TypeScript `JupyterCodeExecutor` is a **stub** — it returns the error `"JupyterCodeExecutor requires a running Jupyter runtime. Not yet implemented."` Java and C# have no Jupyter executor at all.

### 2.3d ServerlessCodeExecutor

Delegates execution to an HTTP endpoint.

**Request:**
```json
POST /execute
{
  "code": "...",
  "language": "python",
  "timeout": 30
}
```

**Response:**
```json
{
  "output": "...",   // or "stdout"
  "error": "...",    // or "stderr"
  "exit_code": 0
}
```

This is the most portable executor — any SDK can implement an HTTP client.

## 2.4 CodeExecutionConfig

Declarative configuration attached to an Agent.

| Field               | Type           | Default      | Description                        |
|---------------------|----------------|--------------|------------------------------------|
| `enabled`           | bool           | `true`       | Whether code execution is active   |
| `allowed_languages` | list\<string\> | `["python"]` | Languages the LLM may use          |
| `allowed_commands`  | list\<string\> | `[]`         | Allowed shell commands (empty = no restriction) |
| `executor`          | CodeExecutor   | `null`       | Executor instance (null = auto-create LocalCodeExecutor) |
| `timeout`           | int            | `30`         | Seconds                            |
| `working_dir`       | string         | `null`       | Working directory                  |

## 2.5 CommandValidator

Best-effort regex-based validator that checks code for shell command invocations against an allowed-command whitelist.

**Important:** This is NOT a security boundary. For untrusted code, use DockerCodeExecutor or ServerlessCodeExecutor.

**Validation rules per language:**

- **Python:** Scan for `subprocess.run/call(["CMD"...])`, `os.system("CMD")`, `os.popen("CMD")`, Jupyter `!CMD` syntax.
- **Bash/sh:** Extract command names from the script (skip builtins like `if`, `echo`, `export`, etc.), check each against the whitelist.
- **Other languages:** Skip validation (no patterns defined).

## 2.6 The `execute_code` tool

A tool function registered as a Conductor SIMPLE worker.

**Tool schema:**

```json
{
  "name": "execute_code",
  "description": "Execute code in a sandboxed environment. Supported languages: {langs}. Timeout: {timeout}s.",
  "parameters": {
    "code": { "type": "string", "description": "The code to execute" },
    "language": { "type": "string", "default": "python", "description": "Programming language" }
  }
}
```

**Output format:**

The tool always returns structured JSON (never raises on code errors):

```json
{"status": "success", "stdout": "hello world\n", "stderr": ""}
{"status": "error",   "stdout": "",              "stderr": "NameError: name 'x' is not defined\nExit code: 1"}
```

When the tool returns a `dict`, the worker sets it directly as `task_result.output_data` — the server passes `outputData` straight through to the LLM as the tool result.

**Execution flow:**

```
1. Receive task with { code, language }
2. If code is empty/null → COMPLETE with {"status":"success","stdout":"No code provided...","stderr":""}
3. If language not in allowed_languages → raise ValueError (FAILED — tool misconfiguration)
4. If allowed_commands is set → CommandValidator.validate(code, language)
   If violation → raise ValueError (FAILED — tool misconfiguration)
5. Create executor for the language (LocalCodeExecutor per invocation,
   since each language needs its own interpreter)
6. result = executor.execute(code)
7. If result.success → COMPLETE with {"status":"success","stdout":"...","stderr":"..."}
8. If !result.success → COMPLETE with {"status":"error","stdout":"...","stderr":"..."}
```

**Key behavior:** Code execution errors always complete the task so the LLM receives the error as a normal tool result and can self-correct without wasting Conductor retries. Only tool misconfiguration errors (invalid language, disallowed commands) fail the task.

## 2.7 Agent integration

### Shorthand API

Every SDK should support a simple boolean flag:

```python
# Python
Agent(name="coder", model="...", local_code_execution=True)

// JavaScript
new Agent({ name: "coder", model: "...", localCodeExecution: true })

// Java
Agent.builder().name("coder").model("...").localCodeExecution(true).build()
```

This auto-creates a `CodeExecutionConfig` with defaults and attaches the `execute_code` tool to the agent.

### Extended API

For fine-grained control:

```python
# Python
Agent(
    name="coder",
    model="...",
    code_execution=CodeExecutionConfig(
        allowed_languages=["python", "bash"],
        allowed_commands=["pip", "ls"],
        executor=DockerCodeExecutor(image="python:3.12-slim"),
        timeout=60,
    ),
)
```

### Serialization

When the agent config is sent to the server for compilation, the code execution config is serialized as:

```json
{
  "codeExecution": {
    "enabled": true,
    "allowedLanguages": ["python", "bash"],
    "allowedCommands": ["pip", "ls"],
    "timeout": 60
  }
}
```

The `executor` field is NOT serialized — it lives only on the SDK side. The server uses this config to inject instructions into the LLM system prompt (see below).

## 2.8 Server-side (Java)

The server does not execute code. It:

1. Reads `codeExecution` from the agent config.
2. Injects instructions into the LLM system prompt via `AgentCompiler.buildCodeExecInstructions()`:
   ```
   You have code execution capabilities. Use the execute_code tool to write
   and run code. Supported languages: python, bash.
   Each execution runs in an isolated environment — no state, variables, or
   imports persist between calls.
   Always include all necessary imports at the top of every code block
   (e.g. import subprocess, import os, import json).
   Allowed shell commands: pip, ls. Do not use other commands.
   ```
3. The `execute_code` tool appears in the LLM's tool spec as a SIMPLE Conductor task. The SDK-side worker picks it up and executes it.

## 2.9 Worker registration

Each SDK must:

1. Detect agents that have code execution enabled.
2. Register the `execute_code` function as a Conductor worker (SIMPLE task).
3. Start polling for tasks.

The worker must handle:
- Empty/null code (return success with message)
- Language validation
- Command validation (if configured)
- Execution via the configured executor
- Timeout handling
- Error formatting for LLM consumption

### Implementation checklist for new SDKs

- [ ] `ExecutionResult` data class with `output`, `error`, `exit_code`, `timed_out`, `success`
- [ ] `CodeExecutor` interface with `execute(code) -> ExecutionResult`
- [ ] `LocalCodeExecutor` — subprocess + temp file, interpreter table, cleanup
- [ ] `DockerCodeExecutor` — Docker container execution (optional)
- [ ] `ServerlessCodeExecutor` — HTTP endpoint delegation (optional)
- [ ] `CodeExecutionConfig` data class
- [ ] `CommandValidator` with Python and Bash patterns
- [ ] `execute_code` tool function with the execution flow above
- [ ] Agent shorthand: `localCodeExecution: true` flag
- [ ] Config serialization to JSON for server compilation
- [ ] Conductor worker registration and polling
- [ ] Tests: empty code, language validation, command validation, execution success/failure/timeout

## 2.10 As-built executor coverage per SDK

The four-executor family above is the contract, **not** a uniform reality. Coverage today:

| SDK | Local | Docker | Jupyter | Serverless | CommandValidator | Notes |
|---|:-:|:-:|:-:|:-:|:-:|---|
| **Python** | ✓ | ✓ | ✓ | ✓ | ✓ | All four real. Validator in `code_execution_config.py`. |
| **TypeScript** | ✓ | ✓ | **stub** | ✓ | ✓ | Jupyter executor is a stub ("Not yet implemented"). |
| **Java** | — | ✓ | — | — | inline | **Docker only.** No Local/Jupyter/Serverless executor classes; command validation is inline in `CliCommandExecutor`. |
| **C# / .NET** | inline | ✓ | — | — | inline | **Docker only (executor class).** C# now ships a `DockerCodeExecutor`; no Local/Jupyter/Serverless executor classes. Local execution remains inline `ExecuteLocalCodeAsync` in `WorkerManager`; command validation is inline. |

Source locations:

- Python: `sdk/python/src/conductor/ai/agents/code_executor.py` (+ `code_execution_config.py`).
- TypeScript: `sdk/typescript/src/code-execution.ts`.
- Java: `sdk/java/.../execution/{CodeExecutor,DockerCodeExecutor,CliCommandExecutor}.java`.
- C#: `sdk/csharp/src/Conductor.AI/DockerCodeExecutor.cs` + inline `ExecuteLocalCodeAsync` in `sdk/csharp/src/Conductor.AI/WorkerManager.cs`.

---

# Part 2 — Credentials & Secrets

This half reflects what the codebase does today, not historical proposals.

## 3. Goals

- **Frictionless local dev** — env vars work without any setup.
- **Multi-user safe** — two users on the same server use distinct keys.
- **Distributed-worker safe** — workers resolve per-execution credentials via a short-lived token, never see the user's session.
- **One pipeline** — same resolution code path for LLM keys, tool credentials, HTTP/MCP headers, CLI tools, and framework passthroughs.
- **Pluggable** — `CredentialStoreProvider` interface lets Enterprise swap in AWS SM / HashiCorp Vault / Azure KV without touching OSS code.

## 3.1 Backend architecture

### Module layout (server)

The server namespace is `dev.agentspan.*`. The credential implementation classes live under `server/conductor-agentspan/.../runtime/credentials/` (interfaces/SPI in `runtime/spi/`, controllers in `runtime/controller/`); the OSS-only built-in store implementations live in the `conductor-agentspan-server` module.

| Class | Responsibility |
|---|---|
| `CredentialStoreProvider` (iface, `runtime/spi`) | `get/set/delete/list` over an opaque backend |
| `EncryptedDbCredentialStoreProvider` (server module) | OSS default — AES-256-GCM in SQLite/Postgres |
| `CredentialResolutionService` | Single authority: `(userId, name) → plaintext` — flat lookup + dotted-JSONPath |
| `ExecutionTokenService` | Mint/validate HMAC-SHA256 execution tokens; in-memory `jti` deny-list |
| `KnownProviderEnvVars` | The ~35 well-known provider env-var names to seed |
| `CredentialEnvSeeder` (server module) | One-shot startup seeder that copies those env vars into the default-user store |
| `SecretOutputMasker` (iface, `runtime/spi`) | `mask(executionId, userId, payload)` — output redaction hook |
| `NoOpSecretOutputMasker` (server module) | OSS default — returns the payload unchanged (no masking in OSS) |
| `CredentialMaskingResponseAdvice` (`runtime/controller`) | `@ControllerAdvice` that delegates to `SecretOutputMasker` on execution-read URIs |
| `SecretAwareHttpTask` / `Config` | Resolves `${NAME}` in HTTP-task headers before dispatch |
| `SecretAwareMcpService` | Resolves `#{NAME}` in MCP tool headers |
| `controller/SecretController + WorkerController` | REST surface (management at `/api/secrets`, worker resolve at `/api/workers/secrets`) |

> **Naming:** the user-facing REST API (`/api/secrets`) and the UI page ("Secrets") keep the *Secrets* name for Conductor parity; the internal store/resolution/masking classes are named `Credential*`.

### Data model

The OSS schema (`schema-credentials.sql`) defines exactly **one** table:

```sql
credentials_store(
    user_id TEXT,
    name TEXT,                   -- e.g. "GITHUB_TOKEN"
    encrypted_value BLOB,        -- [12B IV][ciphertext + 16B GCM tag]
    created_at TEXT, updated_at TEXT,
    PRIMARY KEY(user_id, name)
)
```

There are **no** `users`, `api_keys`, `secret_tags`, or `secret_disclosures` tables in OSS. (AgentSpan's standalone server runs anonymous; tag-based RBAC and per-execution disclosure tracking for output masking are **Enterprise** features. The schema file's own comment notes that `credential_disclosures` is enterprise-only and not in the OSS schema.)

The earlier `credentials_binding` table (logical-key → store-name indirection) was removed for parity with Conductor's flat-name secrets API. `credentials_store` is the canonical table name; a transient dev name (`secrets_store`) was never the canonical form.

Schema: `server/conductor-agentspan-server/src/main/resources/schema-credentials.sql`.

### Encryption at rest

- **Algorithm:** AES-256-GCM (authenticated).
- **IV:** 12 random bytes per value.
- **Blob layout:** `[IV 12B][ciphertext + 16B GCM tag]` — Conductor-portable.
- **Master key:** 32 bytes, sourced from `AGENTSPAN_MASTER_KEY` (base64) in production; auto-generated to `~/.agentspan/master.key` (mode `0600`) on localhost for dev.
- **Rotation:** `agentspan admin credentials re-encrypt --old-key … --new-key …`.
- **Loss:** unrecoverable — self-hosters must back up the key.

## 3.2 Execution token

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

### Resolution pipeline

`CredentialResolutionService.resolve(userId, name)`:

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

- **`CredentialEnvSeeder`** (driven by the `KnownProviderEnvVars` list) — at server startup, copies any of the ~35 well-known provider env vars (OpenAI, Anthropic, AWS, GCP, etc.) into the default user's credentials store. So `export OPENAI_API_KEY=…` still "just works" without any setup.
- **SDK fallback** — when `secret_strict_mode=false`, missing names from `/resolve` fall back to `os.environ` in the worker process (local-dev compat).

## 3.3 API surface

Two namespaces, two auth primitives. **The path itself documents which auth is required.** See [api-design.md](api-design.md) for the full REST surface.

| Namespace | Auth | Consumer | Purpose |
|---|---|---|---|
| `/api/secrets/*`  | Login JWT or API key (`AuthFilter`) | UI, CLI, humans | Management — create / read / update / delete / list secrets |
| `/api/workers/*`  | Execution token (`ExecutionTokenService`) | Distributed workers | Runtime — pull declared secrets for the current execution |

This split is intentional. Earlier designs put both under `/api/secrets` with `/resolve` as a subpath, but that hid the auth-boundary difference behind a path segment. `/api/workers/*` is reserved for future token-mediated worker endpoints (heartbeat, lease extension, handoff, …) using the same execution-token primitive.

### Conductor-parity surface

Mirrors `io.orkes.conductor.server.rest.SecretResource`.

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST`   | `/api/secrets`               | —              | `List<String>` of names |
| `GET`    | `/api/secrets`               | —              | `List<String>` (RBAC-filtered; same set as POST in OSS) |
| `GET`    | `/api/secrets/{key}`         | —              | plaintext value (`text/plain`); `404` if missing |
| `PUT`    | `/api/secrets/{key}`         | raw string     | `200` (upsert) |
| `DELETE` | `/api/secrets/{key}`         | —              | `204` |
| `GET`    | `/api/secrets/{key}/exists`  | —              | `true` / `false` |

> Tag CRUD (`/api/secrets/{key}/tags`) is **not** in OSS — `secret_tags` is an Enterprise feature.

`GET /{key}` returns plaintext (Conductor parity). Every read is audit-logged. RBAC will gate this in Enterprise; in OSS, anyone with management auth can read or overwrite, so hiding plaintext on GET would be theater.

### V2 listing (AgentSpan extension, mirrors Conductor V2)

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/secrets/v2` | `List<SecretMeta>` — name + partial + created_at + updated_at |

`partial` follows the OpenAI/GitHub convention: first-4 + `…` + last-4. The UI uses this endpoint for the secrets table; the v1 `POST /api/secrets` is reserved for strict-parity callers.

### Worker secret fetch (AgentSpan-only)

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

## 3.4 Secret injection by tool type

Credentials are declared at definition time and resolved at execution time. The injection mechanism varies by where the credential needs to land.

| Tool kind | Where resolved | Where injected | Mechanism |
|---|---|---|---|
| `@tool(secrets=[...])` | Worker, in-process | `os.environ` for the call | Server fetch → `inject_via_env` (lock-around-invoke) — see §4 |
| `Agent(cli_commands=True)` | Worker, in-process | `os.environ` for the call | Auto-mapped from `CLI_CREDENTIAL_MAP`, same helper |
| HTTP tool (system task) | Server | Request headers | `${NAME}` rewritten by `SecretAwareHttpTask` |
| MCP tool (system task) | Server | Tool-server headers | `#{NAME}` rewritten by `SecretAwareMcpService` |
| Framework passthrough (LangGraph/LangChain/OpenAI/ADK) | Worker, in-process | `os.environ` for `invoke()` | Same `inject_via_env` helper as native tools — see [framework-integration.md](framework-integration.md) |
| External worker | Caller's process | Caller's responsibility | Direct `POST /api/workers/secrets` with `__agentspan_ctx__` token |
| LLM provider keys | Server | Provider client init | Same pipeline via `AIModelProvider` |
| Vector DB keys | Server | Provider client init | Same pipeline via `VectorDBProvider` |

All in-process injection paths (the first three rows) share a single process-wide lock so concurrent invocations don't clobber each other's env. The lock is the only safety mechanism — there's no subprocess isolation. For throughput, scale by running additional worker processes. The full SDK injection contract is §4.

### SDK declaration

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

### Worker flow

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

### HTTP / MCP placeholder rewriting (server-side)

For tools that execute as Conductor system tasks (no worker process owns them), the server resolves credentials before dispatching the HTTP/MCP call. Both HTTP and MCP use the `#{NAME}` sigil (regex `#\{[\w.]+}`):

```
# HTTP task headers
Authorization: Bearer #{GITHUB_TOKEN}
X-Project:     #{GCP_SVC.project_id}        # JSONPath into a JSON-valued secret

# MCP tool headers
X-API-Key:     #{OPENAI_API_KEY}
X-Client-Id:   #{BLOB.auth.oauth.client_id} # nested JSONPath
```

Dotted names go through the same `CredentialResolutionService` as worker-side resolution, so the JSONPath syntax is uniform across all four call paths (worker `/api/workers/secrets`, HTTP placeholder, MCP placeholder, server-side LLM/VectorDB providers).

This means credential material **never leaves the server** for system-task tools — workers don't see it, neither does Conductor (placeholders are rewritten on egress).

### Framework passthrough (LangGraph / LangChain / OpenAI SDK / Google ADK)

Framework agents run third-party code in-process and read keys from `os.environ` (e.g. `langchain_openai` reads `OPENAI_API_KEY` itself). The runtime resolves declared credentials, temporarily sets them in `os.environ` around the framework invocation, then restores prior state. This path is **single-threaded by construction** — the worker holds a process-wide lock during the framework call to prevent credential bleed across concurrent executions. Multi-threaded scaling for framework agents requires separate worker processes. The full mechanism and per-framework specifics live in [framework-integration.md](framework-integration.md); the injection contract every SDK must honor is §4 below.

### Per-user LLM provider keys

LLM provider keys and Vector DB keys are resolved **server-side** through the same `CredentialResolutionService` pipeline (last two rows of the table above). `AIModelProvider` / `VectorDBProvider` resolve `(userId, name)` at client-init time, so two users on one server transparently use distinct keys and credential material never reaches a worker process for these paths. This is the foundation for per-user / per-tenant model routing.

## 3.5 Output masking (defense in depth on the read path)

Even with all the controls above, a tool's *output* can leak a secret value verbatim — e.g. `gh` prints `error: authentication failed (token: ghp_realtoken123)` to stderr, and that string ends up in the Conductor task output. Anyone with execution-read permission would then see the plaintext.

> **OSS is a no-op; output masking + disclosure tracking are ENTERPRISE.** The OSS server wires the read-path hook (`CredentialMaskingResponseAdvice`, a Spring `@ControllerAdvice`), but it delegates to the `SecretOutputMasker` SPI whose OSS implementation (`NoOpSecretOutputMasker`) returns the payload unchanged. There is no `secret_disclosures`/`credential_disclosures` table in the OSS schema (§3.1). The mechanism described below is the **Enterprise** behavior, which plugs a real masker into the same hook.

The Enterprise masker closes that gap:

1. **Disclosure tracking** — `WorkerController.resolveSecrets` writes one disclosure row per successfully resolved name, scoped to the execution id + user id (Enterprise table).
2. **Read-side redaction** — `CredentialMaskingResponseAdvice` activates on per-execution read URIs: `/api/agent/executions/{id}` (+ `/full`, `/tasks`), `/api/agent/execution/{id}`, and the bare-id `/api/agent/{id}/status`. The Enterprise masker pulls the disclosed names, fetches their **current** plaintext from the credential store, parses the response body as JSON, walks every string node, and replaces each occurrence of a disclosed value with `***NAME***`. Tree-walking (rather than literal `String.replace` on the JSON text) is required so values that contain newlines, quotes, or other JSON-escaped characters are still matched — JSON serialization would have escaped them in the wire payload.

Key properties (Enterprise masker):

- **Read-time, not write-time.** Storage rewrite would be irreversible. Rotation handles itself: the always-current store value is what gets masked.
- **Minimum-length floor (8 chars).** Shorter values produce too many false positives in natural-language output.
- **Literal substring replace** (not regex) — safe for values containing metacharacters.
- **JSON-aware** — values containing `"`, `\`, newlines, or other characters that JSON serialization escapes are still masked because the masker matches against unescaped text-node values, not the wire payload.
- **Best effort.** If anything fails (parse error, no user context, no disclosures), the body passes through unchanged. Masking should never block a response.
- **AgentSpan-owned paths only by default.** The advice always masks AgentSpan's own `/api/agent/*` reads. The raw Conductor `/api/workflow/{id}` read is host-owned, so masking it is **opt-in** via `agentspan.credentials.mask-workflow-reads=true` (default `false`) — this keeps the library from mutating an embedding host's workflow responses just by being on the classpath.
- **Bounded retention.** Enterprise prunes disclosure rows on a retention schedule; older execution payloads remain readable but will not be masked — by design, a long-since-disclosed token should have been rotated anyway.

What this does **not** cover:

- **List endpoints** (`GET /api/agent/list`, `GET /api/agent/executions`, `GET /api/agent/executions/search`) — these return aggregate metadata, not per-execution payload bodies. The advice intentionally does **not** activate on list responses: there is no single execution id to scope the disclosure set against, and list rows surface summary fields (status, timestamps, names) rather than task outputs. If a secret can appear in a *list-row* field (e.g. an agent name shaped like an env-var template), file it as a separate masking gap.
- **POST / mutation endpoints** that echo input (e.g. `/{executionId}/respond`, `/{executionId}/signal`) — the input body is what the caller already supplied, so masking it would help nothing; the *task output* it triggers is still masked when read back through the GET path.
- **Live SSE streams** (`/api/agent/stream/{id}`) — events flow through the streaming converter, which the advice doesn't intercept. Follow-up work.
- **Bypassing AgentSpan to hit Conductor directly** — Conductor is internal-only per the existing security model.
- **Off-server log files** — worker stdout captured by the orchestrator. AgentSpan can't reach into those.

## 3.6 Developer experience tiers

| Tier | Setup | What happens |
|---|---|---|
| 0 — local dev | `export OPENAI_API_KEY=…; python agent.py` | Seeder copies env into default-user store at boot; resolve serves it back |
| 1 — set once | `agentspan credentials set OPENAI_API_KEY sk-…` | No env var needed; persists across restarts |
| 2 — SDK auto-auth | `AgentRuntime()` on localhost | Auto-authenticates as default user; zero config |
| 3 — team / enterprise | `agentspan login` (OIDC in Enterprise) | Token in `~/.agentspan/config.json`; CLI + SDK both use it |

`AgentConfig.secret_strict_mode = True` disables the SDK env-var fallback and the startup seeder — required for compliance-sensitive deployments. Recommended default in Enterprise.

## 3.7 Security model (summary)

| Threat | Mitigation |
|---|---|
| Worker process compromise | Token has 1h+ TTL, narrow scope, declared-name binding, revocable |
| Credential bleed across concurrent agent invocations | `inject_via_env` holds a process-wide lock across mutation + invoke + restore. See §4. |
| `/proc/PID/environ` exposure | Env mutations are scoped to the duration of a single tool call and restored synchronously; only present during the locked region. |
| Token replay | `jti` deny-list + `exp` + `wid` |
| Tool exfiltration via egress | Names bounded to declared set; audit trail; rate-limited |
| Conductor variable leakage | Conductor is internal-only; agentspan-server is sole external entry point |
| Master key loss | Documented; backup is operator's responsibility |
| Plaintext leaks via tool output (e.g. CLI error messages echo a token) | **Output masking (Enterprise)** — a real `SecretOutputMasker` behind `CredentialMaskingResponseAdvice` redacts disclosed values from execution-read response bodies (§3.5); OSS masker is a no-op |
| **Cross-tenant leak when SDK is embedded in a host app** (e.g. Django, FastAPI) | **Run agentspan-server as a separate service.** The process-wide env-injection lock is insufficient when arbitrary host-app code can read `os.environ` during the injection window. See §4.6. |

## 3.8 OSS vs Enterprise boundary

| Concern | OSS | Enterprise |
|---|:-:|:-:|
| `CredentialStoreProvider` interface, encrypted DB store | ✓ | — |
| Env-var seeding + SDK fallback | ✓ | — |
| Management + `/resolve` APIs | ✓ | — |
| Execution token mint/validate (in-memory deny-list) | ✓ | — |
| CLI auto-mapping registry | ✓ | — |
| Subprocess isolation | ✓ | — |
| HTTP/MCP placeholder resolution | ✓ | — |
| Per-user LLM / VectorDB resolution | ✓ | — |
| Output masking (`SecretOutputMasker`): OSS no-op vs real masker | no-op | ✓ |
| Disclosure tracking (per-execution disclosed-name table) | — | ✓ |
| Secret tags / tag-based RBAC | — | ✓ |
| OIDC / SSO authentication | — | ✓ |
| AWS SM / GCP SM / Azure KV / HashiCorp / CyberArk / Doppler / K8s Secrets | — | ✓ |
| Org / team RBAC, credential policies | — | ✓ |
| Durable audit store, durable token revocation | — | ✓ |

Enterprise plugs in via the same `CredentialStoreProvider`, `SecretOutputMasker`, and `AuthFilter` interfaces — no OSS changes required.

---

# Part 4 — SDK Secret-Injection Contract

**Status:** Required for every SDK that supports framework passthrough.
**Audience:** SDK implementors (Python, .NET, TypeScript, Java, future languages). See [sdk-design.md](sdk-design.md) for the broader cross-SDK contract.

This part defines the contract every AgentSpan SDK must follow when injecting resolved secrets into third-party framework agents (LangChain, LangGraph, OpenAI Agents, Claude Agent SDK, Google ADK, Semantic Kernel, etc.). The contract exists because the obvious-looking implementation — mutate process environment, run framework, restore — is fundamentally unsafe under concurrency and has burned every SDK that's tried it.

## 4.1 The problem

Frameworks like `langchain_openai.ChatOpenAI()` or `OpenAI()` read the API key from the process environment (`OPENAI_API_KEY`) at client-construction time. To support per-execution secrets, an SDK has to make the framework see a *specific* key value for *this* invocation.

The naïve approach: set the env var, run the framework, unset.

```
# THIS IS THE BROKEN PATTERN — do not implement it
os.environ["OPENAI_API_KEY"] = resolved_value
try:
    framework.invoke(...)
finally:
    os.environ.pop("OPENAI_API_KEY", None)
```

Process-level environment is a **single shared mutable global**. Two concurrent invocations clobber each other:

```
T=0   Thread A:  os.environ["OPENAI_API_KEY"] = "keyA"
T=1                                                     Thread B:  os.environ["OPENAI_API_KEY"] = "keyB"
T=2   Thread A:  framework.invoke()  → reads env, sees "keyB"  ← WRONG TENANT
T=3                                                     Thread B:  framework.invoke()
T=4   Thread A:  pop OPENAI_API_KEY                     ← removes B's value too
T=5                                                     Thread B:  reads env, sees nothing
```

Three failure modes for Thread A's call: wrong key, no key, or wrong-then-no-key mid-stream. This isn't hypothetical — it triggers every time two framework agents run concurrently on one worker process. Conductor polls multiple tasks in parallel by default, so this happens on the very first concurrent invocation.

A lock around just the *mutation* step doesn't help — the framework reads env *after* the lock is released. The lock must cover **mutation + framework invocation + restoration** as one atomic region. That fixes correctness but serializes everything: one worker process = one framework call at a time.

## 4.2 The two-tier solution

Every SDK must implement both tiers and prefer **tier 1** wherever the framework supports it.

### Tier 1 — Explicit-key injection (preferred, concurrent)

The framework's model client accepts an explicit `api_key` parameter. Resolve the secret, hand it directly to the client constructor, never touch process environment.

```python
# Python — preferred
client = ChatOpenAI(api_key=resolved_secrets["OPENAI_API_KEY"])
```

```csharp
// .NET — preferred
var client = new OpenAIClient(apiKey: resolved["OPENAI_API_KEY"]);
```

```typescript
// TypeScript — preferred
const client = new ChatOpenAI({ apiKey: resolved["OPENAI_API_KEY"] });
```

No shared global state. Multiple threads can construct independent clients with independent keys. Fully concurrent. **This is the default path.**

Where tier 1 lands cleanly:

| Framework | Key parameter |
|---|---|
| LangChain `ChatOpenAI`, `ChatAnthropic`, etc. | `api_key=` on the model constructor |
| LangGraph (uses LangChain models underneath) | same |
| OpenAI SDK (`openai.OpenAI`, `AsyncOpenAI`) | `api_key=` on the client |
| Anthropic SDK | `api_key=` |
| Vercel AI SDK | `apiKey` in the provider config |
| Semantic Kernel | `apiKey:` argument to `AddOpenAIChatCompletion` etc. |

### Tier 2 — Env-injection with lock-around-full-invoke (fallback, serialized)

Some SDKs don't accept an explicit key — they only read from process env. Examples: Google ADK (`genai.configure` is process-global), Claude Agent SDK in CLI mode, anything that reads env at module-import time.

For these, env injection is unavoidable. But the lock **must cover the entire framework invocation**, not just the mutation step:

```python
# Tier 2 — env injection. Note the lock scope.
with _global_env_lock:
    previous = {k: os.environ.get(k) for k in secrets}
    os.environ.update(secrets)
    try:
        result = framework.invoke(...)     # ← still inside the lock
    finally:
        for k, v in previous.items():
            if v is None: os.environ.pop(k, None)
            else:         os.environ[k] = v
```

Trade-off: tier 2 calls are strictly serial within one worker process. Throughput scales by adding worker processes (Conductor replicas), not by adding threads. **Document this limitation in the SDK's per-framework docs.**

## 4.3 Lock discipline

For tier 2 implementations:

1. **One lock per process**, not per execution. The shared resource is `os.environ` (or `process.env`, or `Environment`). All tier-2 framework workers contend for the same lock.
2. **The lock must wrap mutation + invoke + restore.** No yielding control (no `await` outside the lock in async contexts, no manual `Thread.yield()`).
3. **In async contexts, use an async lock** (`asyncio.Lock`, `SemaphoreSlim`, async mutex). Never use a sync lock around an `await` — you'll either deadlock or block the event loop.
4. **The lock applies only to tier-2 paths.** Tier-1 (explicit-key) invocations must NOT acquire the lock. Mixing them defeats the concurrency benefit of tier 1.

**One process-wide lock, shared across all callers.** Native `@tool` dispatch and framework passthrough MUST contend for the same lock. If you implement two locks (one per path) you reintroduce the bug for the case where a native `@tool` and a framework agent run concurrently. Every SDK's test suite must include the "shared single lock" test (Python's `test_native_dispatch_and_framework_share_one_lock` is the reference shape).

## 4.4 User-facing API

To enable tier 1, the SDK's agent-factory API must allow secrets to flow into the user's framework construction code. The recommended shape:

```python
# Python — factory accepts a `secrets` dict
@agent(secrets=["OPENAI_API_KEY"])
def my_agent(secrets):  # ← new parameter
    return AgentExecutor.from_agent_and_tools(
        agent=create_openai_functions_agent(
            ChatOpenAI(api_key=secrets["OPENAI_API_KEY"]),
            tools=[...]
        )
    )
```

```typescript
// TypeScript
defineAgent({
  secrets: ["OPENAI_API_KEY"],
  build: ({ secrets }) => new AgentExecutor({
    llm: new ChatOpenAI({ apiKey: secrets["OPENAI_API_KEY"] }),
    ...
  })
});
```

```csharp
// .NET
[Agent(Secrets = ["OPENAI_API_KEY"])]
static Agent BuildAgent(IReadOnlyDictionary<string, string> secrets) =>
    new AgentBuilder()
        .WithModel(new OpenAIClient(apiKey: secrets["OPENAI_API_KEY"]))
        ...
        .Build();
```

**Backwards-compatibility for agents that don't accept the `secrets` argument:** the SDK falls back to tier 2 (env injection with lock-around-invoke). The fallback should log a warning recommending migration to the explicit-key API for concurrency.

## 4.5 Test contract — every SDK MUST have these

Two deterministic tests, paired. Both go in the SDK's test suite under a stable filename so the contract is visible.

### Counterfactual ("buggy" path)

Implements the broken pattern (no lock around invoke, or lock around mutation only). Uses a synchronization primitive (Barrier, Event, gate) to **force** the race deterministically: Thread A enters its fake invoke and blocks on a barrier; Thread B sets its env value; A is released and reads env. **Assertion: A observes B's value (or empty) — proving the race is observable under this implementation.**

If this test ever starts passing (A observes its own value despite the race), it means the counterfactual is no longer a real counterfactual. Investigate why before deleting.

### Fix-verification ("correct" path)

Uses the same harness but invokes through the SDK's real injection helper. **Assertion: A always observes A's value, even when B is concurrently injecting B's value.**

### Why deterministic, not stress

Race tests run with raw `Thread.Start()` and `assertEventually` are flaky — they pass 99% of the time even when broken. The barrier/gate technique makes the bug 100% reproducible. The fix test is 100% deterministic too. No flake, no `repeat(1000)`, no CI heartburn.

### Reference test names (use these or equivalents)

- `test_buggy_injection_races` (or `_clobbers_concurrent_value`)
- `test_fixed_injection_isolates_concurrent_calls`

> **As-built gap (C#/.NET):** the .NET suite (`CredentialInjectionConcurrentTest.cs`) ships only the fix-verification side (`FixedInjection_IsolatesConcurrentCalls` plus restore/exception cases). The paired **counterfactual** ("buggy") test is **missing** and should be added to satisfy this contract.

## 4.6 Embedded deployments — the contract assumes a dedicated worker process

Everything in §4.1–§4.5 assumes the SDK runs in a **dedicated AgentSpan worker process** — a process whose only job is to poll Conductor and execute agent tools. Under that assumption, tier-2 (env-injection with a process-wide lock) is correct: the only code that reads `os.environ` during the injection window is the framework SDK itself, and concurrent agent invocations serialize via the lock.

The contract **breaks** when you embed the SDK inside a host application that also runs unrelated code in the same process: Django, FastAPI, Flask, Rails, ASP.NET, a long-running CLI, anything where third-party libraries might read `os.environ` at unpredictable times. The reason isn't subtle:

### The cross-tenant leak in an embedded process

```
Thread A (AgentSpan worker)              Thread B (e.g. Django request handler)
─────────────────────────────             ───────────────────────────────────────
inject_via_env({OPENAI_API_KEY: "userA"})
os.environ["OPENAI_API_KEY"] = "userA"
                                          a request from user X invokes:
                                              openai.OpenAI()       ← reads OPENAI_API_KEY
                                              → uses userA's key ❌
framework.invoke()
restore: pop OPENAI_API_KEY
                                          another request reads env → no key
```

The lock prevents AgentSpan-vs-AgentSpan races. It cannot synchronize with arbitrary host-app code reading `os.environ`. Every Django middleware, signal handler, ORM connection initializer, Celery worker bootstrap, third-party library doing lazy env reads — any of them observing env during the injection window picks up the wrong tenant's secret. **This is a real cross-tenant credential leak** in any multi-tenant embedded deployment.

The lock is the only safety mechanism for tier-2. It's local to AgentSpan code paths. It is fundamentally insufficient when the surrounding process runs code AgentSpan doesn't control.

### Recommended architecture for embedded use cases

**Run `agentspan-server` as a separate service** and have the host application call it as an HTTP client. The host process never holds a secret value, never mutates env, and never contends for the lock with arbitrary code.

```
┌─────────────────────────────┐   HTTP   ┌──────────────────────────────┐
│  Host app (Django/FastAPI)  │ ───────> │  agentspan-server            │
│  - request handlers         │          │  - dedicated worker pool     │
│  - calls AgentRuntime().run │ <─────── │  - inject_via_env is safe    │
│  - NO agent workers here    │          │    (no host-app code in proc)│
└─────────────────────────────┘          └──────────────────────────────┘
```

The Python SDK supports this today — construct `AgentRuntime(server_url=…, auto_start_workers=False)` and the runtime becomes a thin HTTP client. The TS/.NET SDKs have equivalent client-only modes.

### If you must embed, the discipline required

If running a separate server isn't an option (single-binary deployment, edge-case constraints), the only safe pattern is **tier-1 explicit-key for every tool, with tier-2 hard-disabled**:

1. **Every tool reads secrets via the contextvars/thread-local accessor** (`get_secret(name)` in Python, `getCredential(name)` in TS, `ToolContext.getCredential(name)` in Java, `ToolContext.GetCredential(name)` / `Secrets.Get(name)` in C#) — never `os.environ` / `process.env` / `Environment`. The tier-1 accessor is now present in **all four SDKs** (C# added), so the strict embedded discipline can be satisfied in every SDK. (Tier-2 env injection remains available as a fallback — C# `Conductor.AI.CredentialInjection.InjectViaEnvAsync`.)
2. **Every secret value is passed explicitly to the underlying client**: `OpenAI(api_key=key)`, `ChatAnthropic(api_key=...)`, etc. No client construction relies on env-var auto-discovery.
3. **Framework passthrough integrations that require env-only configuration are unsupported in embedded mode.** Specifically: Claude Agent SDK CLI mode, Google ADK `genai.configure`, anything that reads env at module-import time. Use only frameworks that accept an explicit `api_key=` parameter.
4. **Hard-disable tier-2 with a config flag** (planned: `AGENTSPAN_DISALLOW_ENV_INJECTION=1`). When set, `inject_via_env` (and equivalents) raise instead of mutating env. Provides loud failure instead of silent leak.
5. **Test the host app for env-read leakage.** Add a test that runs two concurrent agent invocations with different secrets and asserts no host-app code observed a transient value. This is hard but worth doing once if you're committed to embedding.

The contextvars accessor is per-async-task / per-thread, so it doesn't suffer from the process-global problem. It's the *only* injection mechanism that's structurally safe inside a host application.

### What the SDK can and can't enforce

- **Can enforce:** `inject_via_env` raises when the disallow-env flag is set (planned; not yet implemented).
- **Cannot enforce:** that tool authors actually use `get_secret()` instead of `os.environ[name]`. The flag will surface that mistake at runtime — the user's framework client will fail to find a key — but only if they were going to rely on tier-2 anyway. A tool that imports a library that reads env at *import* time (before the agent invocation begins) gets nothing.

### Decision table

| Host app | Multi-tenant? | Recommended deployment |
|---|---|---|
| Standalone AgentSpan worker (no other code in the process) | n/a | tier-1 preferred, tier-2 acceptable |
| Single-user CLI tool, no concurrent users | n/a | tier-1 or tier-2; either fine |
| Django / FastAPI / Flask / Rails, single tenant | no | tier-1 only; run server separately if possible |
| Django / FastAPI / Flask / Rails, multi-tenant | **yes** | **Run server separately.** If embedding, tier-1 only + `AGENTSPAN_DISALLOW_ENV_INJECTION=1`. |
| Notebook / REPL / development | no | either fine |

The decision pivots on "is unrelated code reading `os.environ` in the same process while agents are running?" If yes, tier-2 is unsafe. If no, tier-2 is fine.

## 4.7 Per-language notes

**Java is tier-1-only by language constraint.** `System.getenv()` returns an unmodifiable map at JVM start, so the SDK *cannot* implement tier-2 env injection without reflection hacks against private JDK internals. The Java SDK exposes `ToolContext.getCredential(name)` on the `ToolContext` passed to each `@Tool` method, backed by the `internal.CredentialContext` thread-local populated by the worker immediately before invocation. Tool authors read declared credentials via `ctx.getCredential(...)` and pass them explicitly to model client constructors. Framework passthrough that depends on env-var auto-discovery doesn't work in Java; users must construct framework clients with explicit `api_key` arguments. This is exactly the contract the doc recommends for new languages — Java got it for free because the language wouldn't let us cheat.

**Java ThreadLocal does not propagate across async boundaries.** `internal.CredentialContext` (the `ThreadLocal` behind `ToolContext.getCredential`) is populated on the worker thread immediately before `@Tool` invocation and cleared immediately after. If a tool spawns an `ExecutorService.submit(...)`, `CompletableFuture.runAsync(...)`, virtual-thread `Thread.startVirtualThread(...)`, or any other handoff to a different carrier thread, the secret is **not visible** in the spawned task — `ctx.getCredential(name)` returns `null` there. This is a known limitation: tool authors who need a secret on a background thread must capture it on the calling thread (e.g. `String tok = ctx.getCredential("X"); pool.submit(() -> useToken(tok));`) rather than calling `ctx.getCredential` from inside the lambda. Reactor / RxJava / Kotlin-coroutine context propagation is the user's responsibility — there is no `InheritableThreadLocal` because it would leak across unrelated executions sharing a thread pool. See `Example16CredentialsTool` for the supported pattern.

### Guidance for new-language SDKs

Three rules in priority order:

1. **Start with tier 1.** Don't ship the SDK with env injection as the only path. If you have to ship env injection, build the explicit-key API in the same PR.
2. **The agent-factory API takes a `secrets` argument from day one.** Adding it later is a breaking change.
3. **Write the deterministic concurrent test before the feature ships.** §4.5 is a hard requirement, not a nice-to-have.

## 4.8 Scope — what the contract covers

The contract applies everywhere an SDK injects resolved secrets into a shared mutable global for the duration of an invocation. That includes:

1. **Native `@tool` / handler dispatch** — when a user-authored tool declares `secrets=[…]` and the SDK injects those for the tool function. Even though "Conductor workers default to `thread_count=1`" was historically used to justify skipping the lock, that's a config-dependent workaround. The fix must hold regardless of worker config.
2. **Third-party framework passthrough** — LangChain, LangGraph, OpenAI Agents, Claude Agent SDK, Google ADK, Semantic Kernel, etc.
3. **Any future code path** that mutates process environment around a callable.

## 4.9 Where the contract is implemented

| SDK | Helper location | Used by |
|---|---|---|
| Python | `conductor.ai.agents.runtime.secret_injection.inject_via_env` | Native `_dispatch.py` + `frameworks/langchain.py`, `langgraph.py`, `claude_agent_sdk.py` |
| .NET | `Conductor.AI.CredentialInjection.InjectViaEnvAsync` | `WorkerManager.cs` (covers native handlers + OpenAI / SemanticKernel / GoogleADK integrations) |
| TypeScript | `src/credentials.ts` (`injectSecretsForInvocation`) | `worker.ts` (covers native tools + LangChain / LangGraph serializers) |
| Java | `ToolContext.getCredential` (backed by `internal.CredentialContext` thread-local) + `internal.WorkerCredentialFetcher` (HTTP client for `/api/workers/secrets`) | `internal.WorkerManager.executeTask` (covers every `@Tool` method; tier-1 explicit-key only — env injection structurally impossible in Java) |

---

# Part 5 — Secrets Management UI

A **Secrets** management page in the AgentSpan UI lets users store, view, update, and delete per-user secrets. It follows the existing React 18 + MUI 7 + React Query design language. The page is flat-name only (no bindings UI — the logical-key → store-name indirection was removed backend-side for Conductor parity, see §3.1).

> **Naming:** the page and route are *Secrets*, matching the `/api/secrets` REST surface. (Internally the server classes are named `Credential*`; see §3.1.)

## 5.1 Architecture

### Page structure

A single `/secrets` route (`SECRETS_URL.BASE`), registered as `SecretsPage` at `ui/src/pages/secrets/SecretsPage.tsx`. No sub-routes. It sits in the existing **Definitions** sidebar submenu — there is **no** `/credentials` route, no `Settings` submenu, and no `ui/src/pages/credentials/` directory.

### State management

React Query via `useFetchContext` + a thin `secretFetch` wrapper. Same pattern as the other definition list pages. Local `useState` for dialog visibility and toast messages.

### Auth — none in OSS

The standalone AgentSpan server runs **anonymous**, so the Secrets page sends **no per-request token**. There is **no** `useCredentialAuth` hook, **no** `LoginDialog`, **no** `credentialFetch`/login flow, and **no** `POST /auth/login`. The page passes `{ token: null, onUnauthorized: () => {} }` to its API hooks; auth, when present, is the embedding host's concern.

## 5.2 File structure

| File | Responsibility |
|------|---------------|
| `ui/src/pages/secrets/SecretsPage.tsx` | Main page: table, add/edit dialog, delete confirm, toasts |
| `ui/src/pages/secrets/hooks/useSecretsApi.ts` | `secretFetch` wrapper + hooks: `useListSecrets` (`GET /api/secrets/v2`), create/update/delete |

Route + sidebar wiring (existing files):

| File | Entry |
|------|-------|
| `ui/src/utils/constants/route.ts` | `SECRETS_URL.BASE = "/secrets"` |
| `ui/src/routes/routes.tsx` | route for `SecretsPage` at `SECRETS_URL.BASE` |
| `ui/src/components/Sidebar/sidebarCoreItems.tsx` | `secretsItem` (title "Secrets", `linkTo: SECRETS_URL.BASE`) under the **Definitions** submenu at **position 300** (`CORE_SIDEBAR_POSITIONS.DEFINITIONS.secretsItem = 300`) |

## 5.3 Data model

API responses the UI consumes (served by `GET /api/secrets/v2`, see §3.3):

```typescript
// list item — name + masked partial + timestamp (from GET /api/secrets/v2)
type SecretListItem = {
  name: string;         // store name, e.g. "GITHUB_TOKEN"
  partial: string;      // e.g. "ghp_...6789"
  updated_at: string;   // ISO-8601
};
```

There is no login request/response type — the OSS server is anonymous.

## 5.4 Component details

### SecretsPage

- **Header**: `SectionHeader` titled "Secrets" with an `+ Add Secret` primary action. A descriptive note ("Values are encrypted at rest and never shown after creation") sits as a `Typography` subtitle below the header. No Logout control (anonymous server).
- **Search**: quick-filter `TextField` filters the list client-side by secret name.
- **Table**: MUI `Table` / `TableHead` / `TableBody`. Columns: Name | Value (partial) | Last updated | Actions.
- **Add button**: opens the add/edit dialog in "add" mode.
- **Edit icon**: opens the dialog in "edit" mode (Name read-only, Value cleared — user re-enters to update).
- **Delete icon**: `useState<string | null>(null)` for `confirmDeleteName`; conditionally renders `{confirmDeleteName && <ConfirmChoiceDialog ... />}` (`ConfirmChoiceDialog` has no `open` prop and must be conditionally mounted) with `isInputConfirmation` + `valueToBeDeleted`. On confirm, calls the delete mutation.
- **Toast**: `{toastMessage && <SnackbarMessage ... />}` — guard required because `message` is a required prop.

### Add/Edit dialog

- **Fields**: Name (monospace, required; read-only in edit mode) + Value (password input with show/hide toggle, required in add and edit).
- **Validation**: Name must be non-empty. UPPER_SNAKE_CASE is *suggested* in helper text but not enforced — the backend supports lowercase/hyphen names too. Only blank names are rejected.
- **Submit**: `POST /api/secrets` (add) or `PUT /api/secrets/{name}` (edit) via `secretFetch`.

### useSecretsApi

- `secretFetch(path, ctx, options, onUnauthorized)` wraps `fetchWithContext`, inheriting the `VITE_WF_SERVER` base URL and `cleanPath` logic. In OSS it is called with `token: null` and a no-op `onUnauthorized`.
- `useListSecrets({ token, onUnauthorized })` → `GET /api/secrets/v2`, cache key `[ctx.stack, "/secrets/v2"]`, `retry: false`.
- Create / update / delete mutations accept `onSuccess` / `onError` callbacks so the page can set toast messages, and invalidate the list cache key on success.

## 5.5 Sidebar

The `secretsItem` lives in the existing **Definitions** submenu at position 300 — no new submenu, no renumbering:

```typescript
// CORE_SIDEBAR_POSITIONS.DEFINITIONS
secretsItem: 300,

// Sidebar item (under the Definitions submenu)
{
  id: "secretsItem",
  title: "Secrets",
  icon: null,
  linkTo: SECRETS_URL.BASE,
  activeRoutes: [SECRETS_URL.BASE],
  position: D.secretsItem,   // 300
}
```

## 5.6 Error handling

| Scenario | Behaviour |
|----------|-----------|
| 404 on delete (already gone) | Toast: "Secret not found — it may have already been deleted", severity=warning |
| 409 on create (name exists) | Form-level error on Name field: "A secret with this name already exists" |
| Network error | Toast: "Network error — please try again", severity=error |

(There is no 401/login handling in OSS — the server is anonymous.)

## 5.7 Testing

- Tests live alongside the Secrets page (`ui/src/pages/secrets/`).
- **SecretsPage**: renders list from `/api/secrets/v2`; delete shows `ConfirmChoiceDialog`, typing the name enables confirm; delete success shows toast and refetches.
- **Add/Edit dialog**: blank name rejected; submit calls `POST` (add) or `PUT` (edit); show/hide toggle changes input type.

---

# Part 6 — Known Gaps & Follow-ups

- **Enterprise vault providers** — design done; implementations not yet shipped.
- **Durable token revocation** — OSS deny-list is in-memory; bounded risk because TTL ≤ execution timeout, but a server crash drops revocations.
- **Multi-threaded framework passthrough throughput** — tier-2 (env-injection) calls serialize under the shared lock; scale by adding worker processes. Tier-1 (explicit-key via `get_secret()` or factory `secrets=` arg) runs fully concurrent.
- **TypeScript SDK** — credential resolution path needs verification against the Python SDK's contract.
- **Java SDK framework passthrough** — Java SDK has runtime credential resolution (`ToolContext.getCredential` accessor, `@Tool(credentials={…})` declaration). What's NOT supported: framework integrations (LangChain4j, OpenAI-Agents) that depend on env-var auto-discovery — Java's `System.getenv()` is immutable, so users must construct those clients with explicit `api_key` arguments.
- **Credential rotation / expiry** — no first-class TTL on stored credentials; rotation is a `PUT` from the operator.
- **`AGENTSPAN_DISALLOW_ENV_INJECTION` flag** — planned hard-disable for tier-2 in embedded deployments; not yet implemented.
- **Live SSE stream masking** — `CredentialMaskingResponseAdvice` doesn't intercept `/api/agent/stream/{id}`; even with the Enterprise masker, secrets in streamed task output are not masked.
- **Code execution sandboxing** — `LocalCodeExecutor` + `CommandValidator` are not security boundaries; untrusted code requires Docker/serverless executors. Per-language Docker images and a managed serverless backend are follow-ups.

---

# References

- Sibling design docs: [agentspan-design.md](agentspan-design.md), [api-design.md](api-design.md), [sdk-design.md](sdk-design.md), [framework-integration.md](framework-integration.md).
- Server code: `server/conductor-agentspan/src/main/java/dev/agentspan/runtime/{credentials,spi,controller}/` (+ built-in store impls in the `conductor-agentspan-server` module).
- Python SDK examples: `sdk/python/examples/16_credentials_*.py` (a–k).
- Tests: `server/src/test/java/.../credentials/`, `sdk/python/tests/{unit,e2e}/test_*credential*.py`, `ui/e2e/credentials.spec.ts`.
