/**
 * Deterministic concurrent-injection contract tests.
 *
 * See docs/design/secret-injection-contract.md §5 — every SDK with framework
 * passthrough has a paired test:
 *   (1) counterfactual that proves the naive pattern races
 *   (2) fix-verification that proves the helper isolates concurrent calls
 *
 * Both use a manual gate (Promise + setter) to force interleaving across
 * `await` boundaries deterministically. No timers, no retries, no flake.
 *
 * Node is single-threaded but `process.env` is shared across all in-flight
 * async operations — two `await`s in different async tasks can interleave
 * around env mutation/restoration just like Python's threading. The same
 * bug class, the same fix shape.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { injectSecretsForInvocation } from "../../src/credentials";

const KEY = "_AS_TEST_RACE_KEY_TS";

beforeEach(() => {
  delete process.env[KEY];
});

afterEach(() => {
  delete process.env[KEY];
});

// ── Manual gate primitive used by both tests ────────────────────────────────

function makeGate() {
  let release!: () => void;
  const opened = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { opened, release };
}

// ── Counterfactual: buggy pattern races ────────────────────────────────────

/** The OLD broken pattern — mutate env, await, restore. No lock. */
async function buggyInject<T>(
  secrets: Record<string, string>,
  invoke: () => Promise<T>,
): Promise<T> {
  const previous: Record<string, string | undefined> = {};
  for (const [k, v] of Object.entries(secrets)) {
    previous[k] = process.env[k];
    process.env[k] = v;
  }
  try {
    return await invoke();
  } finally {
    for (const k of Object.keys(secrets)) {
      if (previous[k] === undefined) delete process.env[k];
      else process.env[k] = previous[k];
    }
  }
}

it(
  "counterfactual: buggy injection races deterministically (both threads see the same value)",
  async () => {
    const bothInside = makeGate();
    const allReleased = makeGate();
    let arrived = 0;

    let aObserved: string | undefined;
    let bObserved: string | undefined;

    const worker = (value: string, record: (v: string | undefined) => void) =>
      buggyInject({ [KEY]: value }, async () => {
        // Both async tasks reach this barrier before either reads env.
        arrived++;
        if (arrived === 2) bothInside.release();
        await bothInside.opened;
        record(process.env[KEY]);
        await allReleased.opened;
        return "ok";
      });

    const ta = worker("A", (v) => {
      aObserved = v;
    });
    const tb = worker("B", (v) => {
      bObserved = v;
    });
    // Once both have recorded, release them so finally{} can run.
    bothInside.opened.then(() => allReleased.release());
    await Promise.all([ta, tb]);

    // COUNTERFACTUAL: at least one task observed a clobbered value.
    // Because both wrote env before either read, both reads see the same
    // (latest-writer) value. If this assertion ever stops triggering, the
    // counterfactual is invalid — investigate before deleting.
    const aCorrect = aObserved === "A";
    const bCorrect = bObserved === "B";
    expect(aCorrect && bCorrect).toBe(false);
  },
);

// ── Fix verification: injectSecretsForInvocation isolates ───────────────────

it("injectSecretsForInvocation: concurrent calls do not clobber each other", async () => {
  const aInside = makeGate();
  const aCanFinish = makeGate();
  const aObservations: Array<string | undefined> = [];
  const bObservations: Array<string | undefined> = [];

  const taskA = injectSecretsForInvocation({ [KEY]: "A" }, async () => {
    aObservations.push(process.env[KEY]);   // first observation
    aInside.release();
    await aCanFinish.opened;                // hold the lock so B is forced to wait
    aObservations.push(process.env[KEY]);   // second observation, after B "tried" to enter
    return "ok";
  });

  // Wait until A is inside the lock, then start B. B will block on the
  // module-level mutex until A finishes.
  await aInside.opened;

  const taskB = injectSecretsForInvocation({ [KEY]: "B" }, async () => {
    bObservations.push(process.env[KEY]);
    return "ok";
  });

  // Yield twice so the scheduler has every chance to run B's mutation
  // (if the lock were broken, B's process.env[KEY]="B" would happen here).
  await Promise.resolve();
  await Promise.resolve();

  aCanFinish.release();
  await Promise.all([taskA, taskB]);

  // FIX: A's two reads are both "A" — env was never clobbered.
  expect(aObservations).toEqual(["A", "A"]);
  // FIX: B saw its own value after acquiring the lock.
  expect(bObservations).toEqual(["B"]);
  // FIX: env restored to pre-call state.
  expect(process.env[KEY]).toBeUndefined();
});

it("injectSecretsForInvocation: restores pre-existing env value", async () => {
  process.env[KEY] = "pre-existing";
  await injectSecretsForInvocation({ [KEY]: "injected" }, async () => {
    expect(process.env[KEY]).toBe("injected");
  });
  expect(process.env[KEY]).toBe("pre-existing");
});

it("injectSecretsForInvocation: restores on exception in invoke", async () => {
  await expect(
    injectSecretsForInvocation({ [KEY]: "should-cleanup" }, async () => {
      expect(process.env[KEY]).toBe("should-cleanup");
      throw new Error("boom");
    }),
  ).rejects.toThrow("boom");
  expect(process.env[KEY]).toBeUndefined();
});

it("injectSecretsForInvocation: empty secrets is a no-op pass-through", async () => {
  const result = await injectSecretsForInvocation({}, async () => "passed");
  expect(result).toBe("passed");
});
