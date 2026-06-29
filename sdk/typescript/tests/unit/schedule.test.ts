import { describe, it, expect } from "vitest";
import {
  Schedule,
  ScheduleClient,
  ScheduleNameConflict,
  ScheduleNotFound,
  InvalidCronExpression,
  _prefix,
  _unprefix,
  _toSaveRequest,
  _fromWorkflowSchedule,
  _checkUniqueNames,
  _translate,
  type SchedulerFetcher,
} from "../../src/schedule.js";

describe("Schedule construction", () => {
  it("minimal", () => {
    const s = new Schedule({ name: "daily", cron: "0 0 9 * * ?" });
    expect(s.name).toBe("daily");
    expect(s.timezone).toBe("UTC");
    expect(s.input).toEqual({});
    expect(s.catchup).toBe(false);
    expect(s.paused).toBe(false);
  });

  it("full", () => {
    const s = new Schedule({
      name: "w",
      cron: "0 0 9 * * MON",
      timezone: "America/Los_Angeles",
      input: { c: "#eng" },
      catchup: true,
      paused: true,
      startAt: 1000,
      endAt: 2000,
      description: "desc",
    });
    expect(s.timezone).toBe("America/Los_Angeles");
    expect(s.input).toEqual({ c: "#eng" });
    expect(s.startAt).toBe(1000);
    expect(s.endAt).toBe(2000);
  });

  it("rejects empty name", () => {
    expect(() => new Schedule({ name: "", cron: "* * * * * ?" })).toThrow(/name/);
    expect(() => new Schedule({ name: "  ", cron: "* * * * * ?" })).toThrow(/name/);
  });

  it("rejects empty cron", () => {
    expect(() => new Schedule({ name: "x", cron: "" })).toThrow(/cron/);
  });

  it("rejects inverted window", () => {
    expect(
      () => new Schedule({ name: "x", cron: "* * * * * ?", startAt: 2000, endAt: 1000 }),
    ).toThrow(/startAt/);
    expect(
      () => new Schedule({ name: "x", cron: "* * * * * ?", startAt: 1000, endAt: 1000 }),
    ).toThrow(/startAt/);
  });
});

describe("Wire-name prefix/unprefix", () => {
  it("roundtrips", () => {
    const wire = _prefix("daily_digest", "9am");
    expect(wire).toBe("daily_digest-9am");
    expect(_unprefix("daily_digest", wire)).toBe("9am");
  });

  it("returns input when prefix doesn't match", () => {
    expect(_unprefix("agent", "unrelated")).toBe("unrelated");
  });

  it("handles agent name with hyphen", () => {
    const wire = _prefix("my-agent", "daily");
    expect(wire).toBe("my-agent-daily");
    expect(_unprefix("my-agent", wire)).toBe("daily");
  });
});

describe("Payload mapping", () => {
  it("toSaveRequest minimal", () => {
    const req = _toSaveRequest(new Schedule({ name: "daily", cron: "0 0 9 * * ?" }), "digest");
    expect(req.name).toBe("digest-daily");
    expect(req.cronExpression).toBe("0 0 9 * * ?");
    expect(req.zoneId).toBe("UTC");
    expect(req.paused).toBe(false);
    expect(req.runCatchupScheduleInstances).toBe(false);
    expect((req.startWorkflowRequest as Record<string, unknown>).name).toBe("digest");
    expect((req.startWorkflowRequest as Record<string, unknown>).input).toEqual({});
  });

  it("toSaveRequest full", () => {
    const req = _toSaveRequest(
      new Schedule({
        name: "w",
        cron: "0 0 9 * * MON",
        timezone: "America/Los_Angeles",
        input: { c: "#eng", n: 42 },
        catchup: true,
        paused: true,
        startAt: 1000,
        endAt: 2000,
        description: "weekly",
      }),
      "digest",
    );
    expect(req.zoneId).toBe("America/Los_Angeles");
    expect(req.paused).toBe(true);
    expect(req.runCatchupScheduleInstances).toBe(true);
    expect(req.scheduleStartTime).toBe(1000);
    expect(req.scheduleEndTime).toBe(2000);
    expect(req.description).toBe("weekly");
    expect((req.startWorkflowRequest as Record<string, unknown>).input).toEqual({ c: "#eng", n: 42 });
  });

  it("input is copied not shared", () => {
    const original = { a: 1 };
    const req = _toSaveRequest(new Schedule({ name: "x", cron: "* * * * * ?", input: original }), "a");
    ((req.startWorkflowRequest as Record<string, unknown>).input as Record<string, unknown>).mutated = true;
    expect((original as Record<string, unknown>).mutated).toBeUndefined();
  });

  it("fromWorkflowSchedule with hint", () => {
    const ws = {
      name: "digest-daily",
      cronExpression: "0 0 9 * * ?",
      zoneId: "UTC",
      paused: false,
      runCatchupScheduleInstances: false,
      startWorkflowRequest: { name: "digest", input: { c: "#eng" } },
      createTime: 111,
      updatedTime: 222,
      createdBy: "alice",
    };
    const info = _fromWorkflowSchedule(ws, "digest");
    expect(info.name).toBe("digest-daily");
    expect(info.shortName).toBe("daily");
    expect(info.agent).toBe("digest");
    expect(info.cron).toBe("0 0 9 * * ?");
    expect(info.input).toEqual({ c: "#eng" });
    expect(info.createTime).toBe(111);
    expect(info.createdBy).toBe("alice");
  });

  it("fromWorkflowSchedule derives agent when omitted", () => {
    const ws = {
      name: "digest-daily",
      cronExpression: "0 0 9 * * ?",
      startWorkflowRequest: { name: "digest" },
    };
    const info = _fromWorkflowSchedule(ws);
    expect(info.agent).toBe("digest");
    expect(info.shortName).toBe("daily");
  });
});

describe("Unique-name validation", () => {
  it("distinct ok", () => {
    _checkUniqueNames([
      new Schedule({ name: "a", cron: "* * * * * ?" }),
      new Schedule({ name: "b", cron: "* * * * * ?" }),
    ]);
  });

  it("duplicate raises", () => {
    expect(() =>
      _checkUniqueNames([
        new Schedule({ name: "a", cron: "* * * * * ?" }),
        new Schedule({ name: "a", cron: "0 0 9 * * ?" }),
      ]),
    ).toThrow(ScheduleNameConflict);
  });
});

describe("Error translation", () => {
  it("404 → ScheduleNotFound", () => {
    const exc = new Error("nope") as Error & { status?: number; body?: string };
    exc.status = 404;
    exc.body = "schedule not found";
    expect(_translate(exc)).toBeInstanceOf(ScheduleNotFound);
  });

  it("400 + cron → InvalidCronExpression", () => {
    const exc = new Error("bad cron") as Error & { status?: number; body?: string };
    exc.status = 400;
    exc.body = "Invalid cron expression";
    expect(_translate(exc)).toBeInstanceOf(InvalidCronExpression);
  });

  it("other passthrough", () => {
    const exc = new RuntimeError("x");
    expect(_translate(exc)).toBe(exc);
  });
});

class RuntimeError extends Error {}

// ── Reconcile (mocked fetcher) ─────────────────────────────────────────

function mockFetcher(): { fetcher: SchedulerFetcher; calls: Array<[string, string, unknown]>; store: Map<string, Record<string, unknown>> } {
  const store = new Map<string, Record<string, unknown>>();
  const calls: Array<[string, string, unknown]> = [];
  const fetcher: SchedulerFetcher = {
    async request(method, path, body) {
      calls.push([method, path, body]);
      if (method === "POST" && path === "/scheduler/schedules") {
        const req = body as Record<string, unknown>;
        store.set(req.name as string, req);
        return;
      }
      if (method === "GET" && path.startsWith("/scheduler/schedules?workflowName=")) {
        const wf = decodeURIComponent(path.split("=")[1]);
        return [...store.values()].filter(
          (r) => (r.startWorkflowRequest as Record<string, unknown>).name === wf,
        );
      }
      if (method === "DELETE" && path.startsWith("/scheduler/schedules/")) {
        const name = decodeURIComponent(path.split("/").pop()!);
        store.delete(name);
        return;
      }
      throw new Error(`Unexpected ${method} ${path}`);
    },
  };
  return { fetcher, calls, store };
}

describe("Reconcile (declarative)", () => {
  it("null is no-op", async () => {
    const { fetcher, calls, store } = mockFetcher();
    store.set("digest-x", { name: "digest-x", startWorkflowRequest: { name: "digest" } });
    const client = new ScheduleClient(fetcher);
    await client.reconcile("digest", null);
    expect(calls.filter((c) => c[0] !== "GET")).toEqual([]);
  });

  it("empty list purges", async () => {
    const { fetcher, store } = mockFetcher();
    const client = new ScheduleClient(fetcher);
    await client.save(new Schedule({ name: "a", cron: "* * * * * ?" }), "digest");
    await client.save(new Schedule({ name: "b", cron: "* * * * * ?" }), "digest");
    expect(store.size).toBe(2);
    await client.reconcile("digest", []);
    expect(store.size).toBe(0);
  });

  it("upsert and prune", async () => {
    const { fetcher, store } = mockFetcher();
    const client = new ScheduleClient(fetcher);
    await client.save(new Schedule({ name: "a", cron: "0 0 1 * * ?" }), "digest");
    await client.save(new Schedule({ name: "b", cron: "0 0 2 * * ?" }), "digest");

    await client.reconcile("digest", [
      new Schedule({ name: "a", cron: "0 0 9 * * ?" }),
      new Schedule({ name: "c", cron: "0 0 17 * * ?" }),
    ]);

    expect([...store.keys()].sort()).toEqual(["digest-a", "digest-c"]);
    expect(store.get("digest-a")!.cronExpression).toBe("0 0 9 * * ?");
  });

  it("only affects this agent's schedules", async () => {
    const { fetcher, store } = mockFetcher();
    const client = new ScheduleClient(fetcher);
    await client.save(new Schedule({ name: "x", cron: "* * * * * ?" }), "digest");
    await client.save(new Schedule({ name: "x", cron: "* * * * * ?" }), "other");

    await client.reconcile("digest", []);
    expect(store.has("digest-x")).toBe(false);
    expect(store.has("other-x")).toBe(true);
  });

  it("duplicate names raise before any IO", async () => {
    const { fetcher, calls, store } = mockFetcher();
    const client = new ScheduleClient(fetcher);
    await expect(
      client.reconcile("digest", [
        new Schedule({ name: "a", cron: "* * * * * ?" }),
        new Schedule({ name: "a", cron: "0 0 9 * * ?" }),
      ]),
    ).rejects.toThrow(ScheduleNameConflict);
    expect(calls.length).toBe(0);
    expect(store.size).toBe(0);
  });
});
