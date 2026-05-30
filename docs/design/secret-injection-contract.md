# SDK Secret-Injection Contract

**Status:** Required for every SDK that supports framework passthrough.
**Audience:** SDK implementors (Python, .NET, TypeScript, Java, future languages).

This document defines the contract every AgentSpan SDK must follow when injecting resolved secrets into third-party framework agents (LangChain, LangGraph, OpenAI Agents, Claude Agent SDK, Google ADK, Semantic Kernel, etc.). The contract exists because the obvious-looking implementation — mutate process environment, run framework, restore — is fundamentally unsafe under concurrency and has burned every SDK that's tried it.

---

## 1. The problem

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

---

## 2. The two-tier solution

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

---

## 3. Lock discipline

For tier 2 implementations:

1. **One lock per process**, not per execution. The shared resource is `os.environ` (or `process.env`, or `Environment`). All tier-2 framework workers contend for the same lock.
2. **The lock must wrap mutation + invoke + restore.** No yielding control (no `await` outside the lock in async contexts, no manual `Thread.yield()`).
3. **In async contexts, use an async lock** (`asyncio.Lock`, `SemaphoreSlim`, async mutex). Never use a sync lock around an `await` — you'll either deadlock or block the event loop.
4. **The lock applies only to tier-2 paths.** Tier-1 (explicit-key) invocations must NOT acquire the lock. Mixing them defeats the concurrency benefit of tier 1.

---

## 4. User-facing API

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

---

## 5. Test contract — every SDK MUST have these

Two deterministic tests, paired. Both go in the SDK's test suite under a stable filename so the contract is visible.

### 5.1 Counterfactual ("buggy" path)

Implements the broken pattern (no lock around invoke, or lock around mutation only). Uses a synchronization primitive (Barrier, Event, gate) to **force** the race deterministically: Thread A enters its fake invoke and blocks on a barrier; Thread B sets its env value; A is released and reads env. **Assertion: A observes B's value (or empty) — proving the race is observable under this implementation.**

If this test ever starts passing (A observes its own value despite the race), it means the counterfactual is no longer a real counterfactual. Investigate why before deleting.

### 5.2 Fix-verification ("correct" path)

Uses the same harness but invokes through the SDK's real injection helper. **Assertion: A always observes A's value, even when B is concurrently injecting B's value.**

### 5.3 Why deterministic, not stress

Race tests run with raw `Thread.Start()` and `assertEventually` are flaky — they pass 99% of the time even when broken. The barrier/gate technique makes the bug 100% reproducible. The fix test is 100% deterministic too. No flake, no `repeat(1000)`, no CI heartburn.

### 5.4 Reference test names (use these or equivalents)

- `test_buggy_injection_races` (or `_clobbers_concurrent_value`)
- `test_fixed_injection_isolates_concurrent_calls`

---

## 6. Guidance for new-language SDKs

Three rules in priority order:

1. **Start with tier 1.** Don't ship the SDK with env injection as the only path. If you have to ship env injection, build the explicit-key API in the same PR.
2. **The agent-factory API takes a `secrets` argument from day one.** Adding it later is a breaking change.
3. **Write the deterministic concurrent test before the feature ships.** §5 is a hard requirement, not a nice-to-have.

**Java is tier-1-only by language constraint.** `System.getenv()` returns an unmodifiable map at JVM start, so the SDK *cannot* implement tier-2 env injection without reflection hacks against private JDK internals. The Java SDK ships with `ai.agentspan.Secrets.get(name)` — a thread-local accessor populated by `WorkerManager` immediately before invoking each `@Tool` method. Tool authors read declared credentials via `Secrets.get(...)` and pass them explicitly to model client constructors. Framework passthrough that depends on env-var auto-discovery doesn't work in Java; users must construct framework clients with explicit `api_key` arguments. This is exactly the contract the doc recommends for new languages — Java got it for free because the language wouldn't let us cheat.

**Java ThreadLocal does not propagate across async boundaries.** `ai.agentspan.Secrets` is backed by a plain `ThreadLocal`, populated on the worker thread immediately before `@Tool` invocation and cleared immediately after. If a tool spawns an `ExecutorService.submit(...)`, `CompletableFuture.runAsync(...)`, virtual-thread `Thread.startVirtualThread(...)`, or any other handoff to a different carrier thread, the secret is **not visible** in the spawned task — `Secrets.get(name)` returns `null` there. This is a known limitation: tool authors who need a secret on a background thread must capture it on the calling thread (e.g. `String tok = Secrets.get("X"); pool.submit(() -> useToken(tok));`) rather than calling `Secrets.get` from inside the lambda. Reactor / RxJava / Kotlin-coroutine context propagation is the user's responsibility — there is no `InheritableThreadLocal` because it would leak across unrelated executions sharing a thread pool. See `Example16CredentialsTool` for the supported pattern.

---

## 7. Embedded deployments — the contract assumes a dedicated worker process

Everything in §1–§6 assumes the SDK runs in a **dedicated AgentSpan worker process** — a process whose only job is to poll Conductor and execute agent tools. Under that assumption, tier-2 (env-injection with a process-wide lock) is correct: the only code that reads `os.environ` during the injection window is the framework SDK itself, and concurrent agent invocations serialize via the lock.

The contract **breaks** when you embed the SDK inside a host application that also runs unrelated code in the same process: Django, FastAPI, Flask, Rails, ASP.NET, a long-running CLI, anything where third-party libraries might read `os.environ` at unpredictable times. The reason isn't subtle:

### 7.1 The cross-tenant leak in an embedded process

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

### 7.2 Recommended architecture for embedded use cases

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

### 7.3 If you must embed, the discipline required

If running a separate server isn't an option (single-binary deployment, edge-case constraints), the only safe pattern is **tier-1 explicit-key for every tool, with tier-2 hard-disabled**:

1. **Every tool reads secrets via the contextvars accessor** (`get_secret(name)` in Python, `getCredential(name)` in TS, `IToolContext.Secret(name)` in .NET) — never `os.environ` / `process.env` / `Environment.GetEnvironmentVariable`.
2. **Every secret value is passed explicitly to the underlying client**: `OpenAI(api_key=key)`, `ChatAnthropic(api_key=...)`, etc. No client construction relies on env-var auto-discovery.
3. **Framework passthrough integrations that require env-only configuration are unsupported in embedded mode.** Specifically: Claude Agent SDK CLI mode, Google ADK `genai.configure`, anything that reads env at module-import time. Use only frameworks that accept an explicit `api_key=` parameter.
4. **Hard-disable tier-2 with a config flag** (planned: `AGENTSPAN_DISALLOW_ENV_INJECTION=1`). When set, `inject_via_env` (and equivalents) raise instead of mutating env. Provides loud failure instead of silent leak.
5. **Test the host app for env-read leakage.** Add a test that runs two concurrent agent invocations with different secrets and asserts no host-app code observed a transient value. This is hard but worth doing once if you're committed to embedding.

The contextvars accessor is per-async-task / per-thread, so it doesn't suffer from the process-global problem. It's the *only* injection mechanism that's structurally safe inside a host application.

### 7.4 What the SDK can and can't enforce

- **Can enforce:** `inject_via_env` raises when the disallow-env flag is set (planned; not yet implemented).
- **Cannot enforce:** that tool authors actually use `get_secret()` instead of `os.environ[name]`. The flag will surface that mistake at runtime — the user's framework client will fail to find a key — but only if they were going to rely on tier-2 anyway. A tool that imports a library that reads env at *import* time (before the agent invocation begins) gets nothing.

### 7.5 Decision table

| Host app | Multi-tenant? | Recommended deployment |
|---|---|---|
| Standalone AgentSpan worker (no other code in the process) | n/a | tier-1 preferred, tier-2 acceptable |
| Single-user CLI tool, no concurrent users | n/a | tier-1 or tier-2; either fine |
| Django / FastAPI / Flask / Rails, single tenant | no | tier-1 only; run server separately if possible |
| Django / FastAPI / Flask / Rails, multi-tenant | **yes** | **Run server separately.** If embedding, tier-1 only + `AGENTSPAN_DISALLOW_ENV_INJECTION=1`. |
| Notebook / REPL / development | no | either fine |

The decision pivots on "is unrelated code reading `os.environ` in the same process while agents are running?" If yes, tier-2 is unsafe. If no, tier-2 is fine.

---

## 8. Scope — what the contract covers

The contract applies everywhere an SDK injects resolved secrets into a shared mutable global for the duration of an invocation. That includes:

1. **Native `@tool` / handler dispatch** — when a user-authored tool declares `secrets=[…]` and the SDK injects those for the tool function. Even though "Conductor workers default to `thread_count=1`" was historically used to justify skipping the lock, that's a config-dependent workaround. The fix must hold regardless of worker config.
2. **Third-party framework passthrough** — LangChain, LangGraph, OpenAI Agents, Claude Agent SDK, Google ADK, Semantic Kernel, etc.
3. **Any future code path** that mutates process environment around a callable.

**One process-wide lock, shared across all callers.** Native dispatch and framework passthrough MUST contend for the same lock. If you implement two locks (one per path) you reintroduce the bug for the case where a native `@tool` and a framework agent run concurrently. Every SDK's test suite must include the "shared single lock" test (Python's `test_native_dispatch_and_framework_share_one_lock` is the reference shape).

## 9. Where the contract is implemented

| SDK | Helper location | Used by |
|---|---|---|
| Python | `agentspan.agents.runtime.secret_injection.inject_via_env` | Native `_dispatch.py` + `frameworks/langchain.py`, `langgraph.py`, `claude_agent_sdk.py` |
| .NET | `Agentspan.SecretInjection.InjectViaEnvAsync` | `WorkerManager.cs` (covers native handlers + OpenAI / SemanticKernel / GoogleADK integrations) |
| TypeScript | `src/credentials.ts` (`injectSecretsForInvocation`) | `worker.ts` (covers native tools + LangChain / LangGraph serializers) |
| Java | `ai.agentspan.Secrets` (thread-local accessor) + `ai.agentspan.internal.WorkerCredentialFetcher` (HTTP client for `/api/workers/secrets`) | `internal.WorkerManager.executeTask` (covers every `@Tool` method; tier-1 explicit-key only — env injection structurally impossible in Java) |

---

## 10. References

- `docs/design/secrets.md` — overall secrets design including `/api/workers/secrets`
- `docs/design/secrets.md` §4.4 — framework passthrough mechanism
