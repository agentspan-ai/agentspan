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
 * POST ${serverUrl}/credentials/resolve with { executionToken, names }
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
  const url = `${serverUrl}/credentials/resolve`;
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

// ── Credential injection ─────────────────────────────────

/**
 * Inject resolved credentials into the execution environment.
 *
 * @param serverUrl - Server URL for credential resolution
 * @param headers - Authorization headers
 * @param executionToken - Scoped execution token
 * @param credentials - Map of credential name -> resolved value
 * @param isolated - If true (default), set as process.env vars; if false, store in context for getCredential()
 * @returns Cleanup function that removes injected credentials
 */
export function injectCredentials(
  serverUrl: string,
  headers: Record<string, string>,
  executionToken: string,
  credentials: Record<string, string>,
  isolated: boolean = true,
): () => void {
  if (isolated) {
    // Set credentials as environment variables
    const previousValues: Record<string, string | undefined> = {};
    for (const [name, value] of Object.entries(credentials)) {
      previousValues[name] = process.env[name];
      process.env[name] = value;
    }

    // Return cleanup function
    return () => {
      for (const [name] of Object.entries(credentials)) {
        if (previousValues[name] === undefined) {
          delete process.env[name];
        } else {
          process.env[name] = previousValues[name];
        }
      }
    };
  } else {
    // In-process mode: set credential context for getCredential()
    setCredentialContext(serverUrl, headers, executionToken);

    // Return cleanup function
    return () => {
      clearCredentialContext();
    };
  }
}
