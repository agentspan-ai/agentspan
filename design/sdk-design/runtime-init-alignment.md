# Design: Align AgentRuntime initialization with the Java SDK

Status: **proposed** (for review — no code changed yet)
Date: 2026-06-21

## Problem

Only the Java SDK initializes `AgentRuntime` the way the design guide prescribes:
build on the Conductor `ApiClient`, which owns server URL, auth, **JWT token
management**, and timeouts; layer every typed client (agent control-plane,
workflow, worker poller, SSE) on that one client. The other SDKs roll their own
HTTP transport for the Agentspan `/agent/*` endpoints, and two of them get auth
wrong against secured (Orkes) servers.

### Current state

| SDK | Conductor client used for… | `/agent/*` transport | `/agent/*` auth | Inject client? |
|---|---|---|---|---|
| **Java** (ref) | everything (agent, workflow, workers, SSE) | `AgentClient` on the shared `ApiClient` | ApiClient token mgmt (key/secret→JWT) | ✅ `AgentRuntime(ApiClient, AgentConfig)` |
| **Python** | workflow / task / worker polling (`OrkesClients`) | custom `AgentClient` + raw `requests` | mints JWT via `POST /token`, caches ✓ | ❌ |
| **C#** | worker polling only (`Configuration`) | custom `AgentClient` (schedules folded in — single client) | mints JWT (`X-Authorization`) via `AgentAuthHandler`, caches ✓ | ❌ |
| **TypeScript** | worker polling + `AgentClient`/`WorkflowClient` on `@io-orkes/conductor-javascript` | `AgentClient` (raw `fetch` for `/agent/*`) + `WorkflowClient` on `workflowResource` | mints JWT (`X-Authorization`) via `tokenResource`, caches ✓ | ~ (built on conductor client, lazy) |

> Progress (2026-06-25): **the `/agent/*` JWT auth gap is now closed in all four
> SDKs.** TypeScript mints via the conductor client's `tokenResource` and exposes
> `runtime.client` (`AgentClient`) + `runtime.workflows` (`WorkflowClient`); C# mints
> via a new `AgentAuthHandler` (`X-Authorization`, cached). Remaining alignment items
> (still proposed, not yet done): **injectable Conductor client** for C#/Python/TS,
> and optionally routing `/agent/*` fully through the conductor client's HTTP.

> Naming update (2026-06-25): the control-plane client is now `AgentClient` in
> Python and C# (matching Java). Python keeps an `AgentHttpClient` alias for
> back-compat. The client also exposes control-plane `run`/`start`/`deploy`/
> `schedule` directly (run = start + poll, no local tool workers). This is
> orthogonal to the transport/auth alignment below — the ✗ rows still stand until
> that work lands.

### Concrete bug

Against an Orkes-secured server, an SDK that authenticates worker polling (via the
Conductor client) but sends raw key/secret to `/agent/*` will **401** on every
control-plane call (start/compile/deploy/status/respond/stream) while workers still
poll — a confusing partial failure. **Resolved (2026-06-25): all four SDKs now mint
a JWT from key/secret (cached to expiry) and send `X-Authorization`** on `/agent/*`
(Java via `ApiClient`; Python via `POST /token`; TypeScript via the conductor
client's `tokenResource`; C# via `AgentAuthHandler`). The schedule client rides the
same authenticated transport.

## Goal

Make all four SDKs match Java's contract, idiomatically:

1. **One source of connection + auth.** The Conductor client (`ApiClient` /
   `Configuration` / `conductorClient`) owns server URL, credentials, and the
   key/secret→JWT exchange. The agent control-plane layer reuses *that* client's
   auth — it never re-implements token minting or sends raw credentials.
2. **`AgentConfig` carries worker-runner tuning only** (poll interval, thread
   count, daemon). No connection/auth fields. (Already true in C#/Python; codify it.)
3. **Injectable Conductor client.** `AgentRuntime` accepts a pre-built Conductor
   client so users can configure proxies, mTLS, custom timeouts, or reuse an
   existing client. Env-based convenience constructors remain.
4. **No bespoke second/third transport.** Collapse the extra HTTP clients (C#'s
   scheduler `HttpClient`; redundant raw paths) onto the shared client.

The `/agent/*` routes are not in the Conductor typed clients, so a thin agent-API
helper stays — but it is **constructed from the Conductor client** and borrows its
token provider, exactly as Java's `AgentClient` does.

## Target design

### Common contract (all SDKs)

```
AgentRuntime(conductorClient, agentConfig?)     // inject a pre-built client
AgentRuntime(agentConfig?)                       // build client from env (default)
AgentRuntime(serverUrl, key?, secret?)           // convenience → builds client
```

- `conductorClient` owns URL + auth + token.
- `agentConfig` = `{ workerPollIntervalMs, workerThreadCount, daemon? }` only.
- Agent control-plane, workflow, worker, and SSE layers are all built from
  `conductorClient` (or its config/auth provider).

### Per-SDK

**Java** — reference; no change. (Confirm `AgentConfig` holds no connection fields — it doesn't.)

**Python**
- Add `AgentRuntime(configuration=<conductor Configuration>, config=<AgentConfig>)`
  injection; keep `server_url/api_key/api_secret` and `config` overloads
  (back-compat) that build the `Configuration` as today.
- Unify auth: `AgentHttpClient` should obtain its token from the same
  `Configuration`/Orkes auth provider used by `OrkesClients`, instead of minting
  its own. Net effect identical today (it already mints correctly); the win is one
  token cache + honoring an injected client's auth settings.

**C#** (largest change)
- New ctors: `AgentRuntime(Configuration conductorConfig, AgentRuntimeOptions?)`
  and keep `AgentRuntime(AgentRuntimeOptions?)` (env) for back-compat.
- `AgentHttpClient` takes the conductor `Configuration` and, when
  `AuthenticationSettings` is set, resolves a bearer token from it (the
  conductor-csharp Orkes token resource) and sends `X-Authorization`/`Bearer`
  instead of raw `X-Auth-Key/Secret`. **Fixes the Orkes bug.**
- Fold the schedules `HttpClient` onto the same auth path (token, not raw headers).
- `AgentConfig`/worker tuning already split out (done in the parity pass) — keep.

**TypeScript** (largest change)
- New ctor option: accept an injected `@io-orkes/conductor-javascript` client (or
  its config); default still builds from env.
- Add key/secret→JWT exchange used by `_buildAuthHeaders()` (mint via the orkes
  client / `POST /token`, cache to expiry, send `X-Authorization`). **Fixes the
  Orkes bug.** Reuse the same token for SSE + execution calls.

## Backward compatibility

- All existing constructors keep working; new injection overloads are additive.
- Wire format and endpoints unchanged.
- OSS/no-auth path unchanged (no token minted when no credentials).
- Only behavioral change: C#/TS now send a JWT on `/agent/*` when key/secret are
  configured — strictly more correct.

## Test plan (deterministic; no LLM)

1. **Auth-header unit tests** (C#, TS, Python): given key/secret, the agent-API
   request carries `X-Authorization: <jwt>` (mock the `/token` endpoint; assert the
   header and that the token is cached/reused). Counterfactual: no creds → no auth
   header.
2. **Injection unit test**: constructing `AgentRuntime` with a pre-built client uses
   its base URL/auth (assert outgoing request targets the injected URL).
3. **Env-default test**: unchanged behavior when nothing injected.
4. **Regression e2e** (OSS server already used in CI): existing suites must stay
   green — proves the refactor didn't change the working path.
5. **Orkes auth e2e** (gated, only if an Orkes test server/creds are available):
   start+compile+respond succeed with key/secret. Otherwise covered by the mocked
   `/token` unit test above.
6. Per project rule: fail-first each new test (break token injection → 401/asserts
   red → restore).

## Risks / open questions

- **conductor-csharp token access**: confirm the C# client exposes a way to obtain
  the current bearer token (token resource / `OrkesAuthenticationSettings`) for
  reuse by `AgentHttpClient`. If not, replicate the `POST /token` mint (like Python)
  but key it off the injected `Configuration`. *(Needs a spike before C# work.)*
- **conductor-javascript token access**: same question for the JS client; fall back
  to a `POST /token` mint keyed off config.
- **Full routing vs. token reuse**: this doc reuses the conductor client's *auth*
  but keeps a thin agent-API HTTP helper (the typed clients lack `/agent/*`). Fully
  routing through the conductor client's generic invoke (as Java does) is possible
  where the client supports it; deferred unless we want the stricter form.
- **Scope/sequencing**: suggest C# first (has the bug + the extra transport), then
  TS (bug), then Python (injection + token unification, no bug). Each shipped with
  its tests.

## Appendix: TypeScript on `@io-orkes/conductor-javascript` 3.0.3 (confirmed)

Verified against the installed type defs (the version the TS SDK already pins):

- **Factory:** `createConductorClient(config?: OrkesApiConfig, customFetch?): Promise<ConductorClient>`
  (alias `orkesConductorClient`). Reads `CONDUCTOR_SERVER_URL` / `CONDUCTOR_AUTH_KEY` /
  `CONDUCTOR_AUTH_SECRET` from env, or `config.keyId` / `keySecret`. Async.
- **Resource clients on the returned `ConductorClient`:** `workflowResource`,
  `taskResource`, `metadataResource`, `schedulerResource`, `tokenResource`.
- **Auto JWT:** `getAuthToken` + `tokenResource`/`generateToken` mint a token from
  keyId/keySecret against `/token` and attach it — the client handles the exchange
  the TS SDK currently skips on `/agent/*`.
- Worker runners exported: `TaskManager` (already used by `worker.ts`), `TaskRunner`,
  `WorkflowExecutor`.
- README on GitHub shows a higher-level surface (`OrkesClients.from()`,
  `getWorkflowClient()`, `@worker`, `TaskHandler`) that does NOT all match 3.0.3 —
  implement against the installed API.

### TS implementation sketch

- **`src/agent-client.ts` → `class AgentClient`**: control-plane `/agent/*`
  (compile/deploy/start/status/respond/stream) + control-plane `run`/`start`/`deploy`/
  `schedule` (run = start + poll, no local tool workers), matching C#/Python.
  - Lazily build + memoize a `ConductorClient` via `createConductorClient` (async).
  - Auth: when keyId/keySecret are set, mint a JWT via the client's `tokenResource`
    (cache to expiry) and send it as `X-Authorization: <jwt>` on the raw `/agent/*`
    calls — mirroring Python's proven Orkes contract. No creds → no header (OSS).
- **`src/workflow-client.ts` → `class WorkflowClient`**: thin wrapper over
  `client.workflowResource` (get workflow / execution status / token usage), replacing
  the inline `fetch` workflow reads on `AgentRuntime`. Task access over
  `client.taskResource` as needed.
- **`AgentRuntime`**: route its `/agent/*` and workflow reads through `AgentClient` /
  `WorkflowClient`; expose `runtime.client` (and a workflow accessor); share the one
  `ConductorClient` with `worker.ts`. Keep all existing public methods unchanged.
- **Constraint:** `createConductorClient` is async — use a memoized `getClient()`,
  not a sync constructor.

## Out of scope

Streaming/HITL semantics, agent features, and wire format — unchanged. This is
purely how the runtime acquires and authenticates its transport.
