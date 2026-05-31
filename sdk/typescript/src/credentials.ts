import { AsyncLocalStorage } from "node:async_hooks";

import {
  CredentialNotFoundError,
  CredentialAuthError,
  CredentialRateLimitError,
  CredentialServiceError,
} from "./errors.js";

// ── Per-async-call credential context ────────────────────

interface CredentialContext {
  serverUrl: string;
  headers: Record<string, string>;
  executionToken: string;
}

// AsyncLocalStorage scopes context per async-call chain so concurrent worker
// handlers each see their own credentials instead of clobbering a shared global.
const _credentialStore = new AsyncLocalStorage<CredentialContext>();

// Fallback used by setCredentialContext() — kept for callers that can't run
// inside runWithCredentialContext(). Reads always prefer the ALS store.
let _fallbackContext: CredentialContext | null = null;

function activeContext(): CredentialContext | null {
  return _credentialStore.getStore() ?? _fallbackContext;
}

/**
 * Run `fn` with the given credential context active in AsyncLocalStorage.
 * Concurrent calls each see their own context — sibling cleanups can't clobber it.
 */
export function runWithCredentialContext<T>(
  serverUrl: string,
  headers: Record<string, string>,
  executionToken: string,
  fn: () => Promise<T>,
): Promise<T> {
  return _credentialStore.run({ serverUrl, headers, executionToken }, fn);
}

/**
 * Set a fallback credential context for getCredential().
 *
 * Prefer {@link runWithCredentialContext} — it scopes context per async call
 * and is safe under concurrent workers. setCredentialContext writes to a
 * shared module-level slot and is only consulted when no ALS context is
 * active; sibling clears can race with concurrent reads.
 */
export function setCredentialContext(
  serverUrl: string,
  headers: Record<string, string>,
  executionToken: string,
): void {
  _fallbackContext = { serverUrl, headers, executionToken };
}

/**
 * Clear the fallback credential context. Does not affect ALS-scoped contexts.
 */
export function clearCredentialContext(): void {
  _fallbackContext = null;
}

// ── Execution token extraction ───────────────────────────

/**
 * Extract the execution token from task input.
 *
 * Two-level fallback (base spec section 14.16):
 * 1. Primary: taskInput.__agentspan_ctx__.executionToken
 * 2. Fallback: taskInput.workflowInput?.__agentspan_ctx__.executionToken
 */
export function extractExecutionToken(taskInput: Record<string, unknown>): string | null {
  // Primary path
  const ctx = taskInput.__agentspan_ctx__;
  if (ctx != null && typeof ctx === "object") {
    const ctxObj = ctx as Record<string, unknown>;
    if (typeof ctxObj.executionToken === "string") {
      return ctxObj.executionToken;
    }
    // Also support snake_case from wire format
    if (typeof ctxObj.execution_token === "string") {
      return ctxObj.execution_token;
    }
  }

  // Fallback path: workflowInput.__agentspan_ctx__
  const workflowInput = taskInput.workflowInput;
  if (workflowInput != null && typeof workflowInput === "object") {
    const wiObj = workflowInput as Record<string, unknown>;
    const wiCtx = wiObj.__agentspan_ctx__;
    if (wiCtx != null && typeof wiCtx === "object") {
      const wiCtxObj = wiCtx as Record<string, unknown>;
      if (typeof wiCtxObj.executionToken === "string") {
        return wiCtxObj.executionToken;
      }
      if (typeof wiCtxObj.execution_token === "string") {
        return wiCtxObj.execution_token;
      }
    }
  }

  return null;
}

// ── Credential resolution ────────────────────────────────

/**
 * Resolve credentials from the server.
 *
 * POST ${serverUrl}/workers/secrets with { executionToken, names }
 *
 * Error mapping:
 * - 404 -> CredentialNotFoundError
 * - 401 -> CredentialAuthError
 * - 429 -> CredentialRateLimitError
 * - 5xx -> CredentialServiceError
 */
export async function resolveCredentials(
  serverUrl: string,
  headers: Record<string, string>,
  executionToken: string,
  names: string[],
): Promise<Record<string, string>> {
  const url = `${serverUrl}/workers/secrets`;
  let response: Response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: JSON.stringify({ token: executionToken, names }),
    });
  } catch (err) {
    throw new CredentialServiceError(
      `Failed to connect to credential service: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");

    if (response.status === 404) {
      // Try to extract credential name from response
      let credName = names.join(", ");
      try {
        const parsed = JSON.parse(body);
        if (parsed.name) credName = parsed.name;
        if (parsed.credentialName) credName = parsed.credentialName;
      } catch {
        // Use default
      }
      throw new CredentialNotFoundError(credName);
    }

    if (response.status === 401) {
      throw new CredentialAuthError(body || "Credential authentication failed");
    }

    if (response.status === 429) {
      throw new CredentialRateLimitError(body || "Credential rate limit exceeded");
    }

    if (response.status >= 500) {
      throw new CredentialServiceError(body || `Credential service error (${response.status})`);
    }

    // Other errors
    throw new CredentialServiceError(`Credential resolution failed (${response.status}): ${body}`);
  }

  const data = (await response.json()) as Record<string, string>;

  // Check that all requested credentials were resolved
  const missing = names.filter((n) => data[n] == null);
  if (missing.length > 0) {
    throw new CredentialNotFoundError(missing.join(", "));
  }

  return data;
}

// ── getCredential ────────────────────────────────────────

/**
 * Resolve a single credential by name.
 *
 * Uses the active credential context (per-async via {@link runWithCredentialContext},
 * falling back to {@link setCredentialContext} for legacy callers).
 * Throws if no context is set (i.e., not called during worker execution).
 */
export async function getCredential(name: string): Promise<string> {
  const ctx = activeContext();
  if (!ctx) {
    throw new CredentialAuthError(
      "No credential context available. getCredential() must be called during worker execution.",
    );
  }

  const { serverUrl, headers, executionToken } = ctx;
  const resolved = await resolveCredentials(serverUrl, headers, executionToken, [name]);

  const value = resolved[name];
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
