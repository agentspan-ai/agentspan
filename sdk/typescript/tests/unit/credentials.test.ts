import { describe, it, expect, afterEach } from "vitest";
import {
  getCredential,
  setCredentialContext,
  clearCredentialContext,
  runWithCredentialContext,
} from "../../src/credentials.js";
import { CredentialNotFoundError, CredentialAuthError } from "../../src/errors.js";

// Worker secrets are delivered on the wire-only Task.runtimeMetadata (resolved by
// the conductor core at poll). getCredential() reads exclusively from that resolved
// map via the credential context — there is no server endpoint to pull from.

describe("getCredential", () => {
  afterEach(() => {
    clearCredentialContext();
  });

  it("throws when no context is set", async () => {
    await expect(getCredential("ANY")).rejects.toBeInstanceOf(CredentialAuthError);
  });

  it("reads a delivered credential from the ALS context", async () => {
    const value = await runWithCredentialContext(
      { GITHUB_TOKEN: "ghp_host_resolved" },
      async () => getCredential("GITHUB_TOKEN"),
    );
    expect(value).toBe("ghp_host_resolved");
  });

  it("reads from the fallback context set via setCredentialContext", async () => {
    setCredentialContext({ MY_KEY: "fallback-value" });
    expect(await getCredential("MY_KEY")).toBe("fallback-value");
  });

  it("throws CredentialNotFoundError for an undelivered name", async () => {
    await expect(
      runWithCredentialContext({ GITHUB_TOKEN: "ghp_host_resolved" }, async () =>
        getCredential("MISSING"),
      ),
    ).rejects.toBeInstanceOf(CredentialNotFoundError);
  });

  it("throws after the fallback context is cleared", async () => {
    setCredentialContext({ MY_KEY: "v" });
    clearCredentialContext();
    await expect(getCredential("MY_KEY")).rejects.toBeInstanceOf(CredentialAuthError);
  });
});

describe("runWithCredentialContext", () => {
  afterEach(() => {
    clearCredentialContext();
  });

  it.each([1, 2, 3])("isolates concurrent executions (run %i)", async () => {
    // Reproduce the worker race that breaks test_suite2_tool_calling:
    //   1. Worker A enters context, starts handler.
    //   2. Worker B enters context, finishes, exits.
    //   3. Worker A's handler later calls getCredential — without per-async
    //      isolation, B's exit would clobber A's context.
    // Test re-runs (1-3) to surface scheduling-dependent regressions.
    async function workerHandler(tag: string, delayMs: number) {
      return runWithCredentialContext({ MY_KEY: `${tag}:MY_KEY` }, async () => {
        await new Promise((r) => setTimeout(r, delayMs));
        return getCredential("MY_KEY");
      });
    }

    const results = await Promise.all([
      workerHandler("res-A", 30),
      workerHandler("res-B", 5),
      workerHandler("res-C", 20),
      workerHandler("res-D", 10),
      workerHandler("res-E", 15),
    ]);

    expect(results).toEqual([
      "res-A:MY_KEY",
      "res-B:MY_KEY",
      "res-C:MY_KEY",
      "res-D:MY_KEY",
      "res-E:MY_KEY",
    ]);
  });

  it("ALS context wins over the fallback context", async () => {
    setCredentialContext({ MY_KEY: "fallback" });
    const value = await runWithCredentialContext({ MY_KEY: "scoped" }, async () =>
      getCredential("MY_KEY"),
    );
    expect(value).toBe("scoped");
    // Outside the scope, the fallback is visible again.
    expect(await getCredential("MY_KEY")).toBe("fallback");
  });
});
