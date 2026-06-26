import { AsyncLocalStorage } from "node:async_hooks";

import { CredentialNotFoundError, CredentialAuthError } from "./errors.js";

// ── Per-async-call credential context ────────────────────
//
// Per-user secret values are resolved server-side and injected into a polled
// tool task's input at poll time (WorkerSecretPollAdvice). The worker reads that
// map and scopes it here so getCredential() can return values by name — there is
// no callback to the server.

type Secrets = Record<string, string>;

// AsyncLocalStorage scopes context per async-call chain so concurrent worker
// handlers each see their own credentials instead of clobbering a shared global.
const _credentialStore = new AsyncLocalStorage<Secrets>();

// Fallback used by setCredentialContext() — kept for callers that can't run
// inside runWithCredentialContext(). Reads always prefer the ALS store.
let _fallbackSecrets: Secrets | null = null;

function activeSecrets(): Secrets | null {
  return _credentialStore.getStore() ?? _fallbackSecrets;
}

/**
 * Run `fn` with the given resolved secrets active in AsyncLocalStorage.
 * Concurrent calls each see their own map — sibling cleanups can't clobber it.
 */
export function runWithCredentialContext<T>(secrets: Secrets, fn: () => Promise<T>): Promise<T> {
  return _credentialStore.run(secrets, fn);
}

/**
 * Set a fallback secrets map for getCredential().
 *
 * Prefer {@link runWithCredentialContext} — it scopes per async call and is safe
 * under concurrent workers. setCredentialContext writes to a shared module-level
 * slot consulted only when no ALS context is active.
 */
export function setCredentialContext(secrets: Secrets): void {
  _fallbackSecrets = secrets;
}

/**
 * Clear the fallback secrets. Does not affect ALS-scoped contexts.
 */
export function clearCredentialContext(): void {
  _fallbackSecrets = null;
}

// ── getCredential ────────────────────────────────────────

/**
 * Return a single credential by name from the secrets the server injected into
 * this task's input. Throws if no context is set (i.e., not called during worker
 * execution) or the name was not injected.
 */
export async function getCredential(name: string): Promise<string> {
  const secrets = activeSecrets();
  if (!secrets) {
    throw new CredentialAuthError(
      "No credential context available. getCredential() must be called during worker execution.",
    );
  }
  const value = secrets[name];
  if (value === undefined) {
    throw new CredentialNotFoundError(name);
  }
  return value;
}

// ── Concurrency-safe injection (Tier 2 fallback) ───────────────────────────────
//
// See docs/design/secret-injection-contract.md.
//
// A single module-scoped Promise chain serializes mutate-invoke-restore across
// all callers in this process. Node is single-threaded, but `process.env` is
// still shared across all in-flight async operations — two concurrent
// invocations would interleave across `await` boundaries and clobber each
// other's env if there were no lock.

let _envInjectionMutex: Promise<void> = Promise.resolve();

/**
 * Run `invoke()` with `secrets` injected into `process.env` for the duration
 * of the call. Mutation, invocation, and restoration happen atomically with
 * respect to any other call to this function in this process — concurrent
 * callers serialize.
 *
 * Tier-1 (explicit-key) integrations should NOT use this — they should pass
 * resolved values directly to model client constructors, bypassing `process.env`
 * entirely.
 *
 * @param secrets - name → plaintext (non-string values silently skipped)
 * @param invoke - async function that runs the framework
 * @returns Whatever `invoke()` resolves with.
 */
export async function injectSecretsForInvocation<T>(
  credentials: Record<string, string>,
  invoke: () => Promise<T>,
): Promise<T> {
  const clean: Record<string, string> = {};
  for (const [k, v] of Object.entries(credentials)) {
    if (typeof v === "string") clean[k] = v;
  }
  if (Object.keys(clean).length === 0) {
    return invoke();
  }

  // Enqueue this call after the current tail of the chain.
  const previous = _envInjectionMutex;
  let resolveSlot!: () => void;
  _envInjectionMutex = new Promise<void>((res) => {
    resolveSlot = res;
  });

  try {
    await previous;
    const restorers: Array<() => void> = [];
    for (const [k, v] of Object.entries(clean)) {
      const prev = process.env[k];
      process.env[k] = v;
      restorers.push(() => {
        if (prev === undefined) delete process.env[k];
        else process.env[k] = prev;
      });
    }
    try {
      return await invoke();
    } finally {
      for (const r of restorers) r();
    }
  } finally {
    resolveSlot();
  }
}
