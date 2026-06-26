import { describe, it, expect, afterEach } from "vitest";
import {
  getCredential,
  setCredentialContext,
  clearCredentialContext,
  runWithCredentialContext,
} from "../../src/credentials.js";
import { CredentialNotFoundError, CredentialAuthError } from "../../src/errors.js";

// Per-user secret values are resolved server-side and injected into a polled
// tool task's input (WorkerSecretPollAdvice). The worker scopes that map here so
// getCredential() returns values by name — there is no fetch.

describe("getCredential", () => {
  afterEach(() => {
    clearCredentialContext();
  });

  it("throws when no context is set", async () => {
    await expect(getCredential("MY_CRED")).rejects.toThrow(CredentialAuthError);
    await expect(getCredential("MY_CRED")).rejects.toThrow("No credential context available");
  });

  it("returns a value from the scoped secrets map", async () => {
    const value = await runWithCredentialContext({ MY_CRED: "secret-value" }, () =>
      getCredential("MY_CRED"),
    );
    expect(value).toBe("secret-value");
  });

  it("returns a value from the fallback context", async () => {
    setCredentialContext({ MY_CRED: "fallback-value" });
    expect(await getCredential("MY_CRED")).toBe("fallback-value");
  });

  it("throws CredentialNotFoundError when the name was not injected", async () => {
    await expect(
      runWithCredentialContext({ OTHER: "x" }, () => getCredential("MISSING")),
    ).rejects.toThrow(CredentialNotFoundError);
  });

  it("clearCredentialContext removes the fallback", async () => {
    setCredentialContext({ MY_CRED: "v" });
    clearCredentialContext();
    await expect(getCredential("MY_CRED")).rejects.toThrow(CredentialAuthError);
  });
});

describe("runWithCredentialContext", () => {
  afterEach(() => {
    clearCredentialContext();
  });

  it.each([1, 2, 3])("isolates concurrent executions (run %i)", async () => {
    // Each concurrent worker scopes its own injected secrets map; sibling
    // cleanups must not clobber an in-flight handler's context.
    async function workerHandler(value: string, delayMs: number) {
      return runWithCredentialContext({ MY_KEY: value }, async () => {
        await new Promise((r) => setTimeout(r, delayMs));
        return getCredential("MY_KEY");
      });
    }

    const results = await Promise.all([
      workerHandler("A", 30),
      workerHandler("B", 5),
      workerHandler("C", 20),
      workerHandler("D", 10),
      workerHandler("E", 15),
    ]);

    expect(results).toEqual(["A", "B", "C", "D", "E"]);
  });
});
