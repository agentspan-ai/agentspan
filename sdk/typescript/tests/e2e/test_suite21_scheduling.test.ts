/**
 * Suite 21: Agent scheduling (TypeScript SDK).
 *
 * Mirrors `sdk/python/e2e/test_suite21_scheduling.py` end-to-end against a
 * live agentspan-runtime with the scheduler module enabled. Skipped if the
 * `/scheduler/schedules` endpoint isn't reachable.
 */

import { describe, it, expect, beforeAll, beforeEach, afterAll } from 'vitest';

import {
  AgentRuntime,
  Schedule,
  ScheduleClient,
  ScheduleNameConflict,
  ScheduleNotFound,
} from '@agentspan-ai/sdk';

const SERVER_URL = process.env.AGENTSPAN_SERVER_URL ?? 'http://localhost:6767/api';

async function schedulerAvailable(): Promise<boolean> {
  try {
    const r = await fetch(`${SERVER_URL.replace(/\/$/, '')}/scheduler/schedules`, {
      signal: AbortSignal.timeout(3000),
    });
    return r.status === 200;
  } catch {
    return false;
  }
}

const available = await schedulerAvailable();

(available ? describe : describe.skip)('Suite 21: scheduling', () => {
  const agentName = `e2e_ts_sched_noop_${Math.random().toString(36).slice(2, 10)}`;
  let runtime: AgentRuntime;
  let client: ScheduleClient;

  beforeAll(async () => {
    runtime = new AgentRuntime();
    client = runtime.schedulesClient();

    // Register a bare no-op workflow def via Conductor's metadata API.
    const workflowDef = {
      name: agentName,
      version: 1,
      description: 'TS scheduling e2e no-op',
      ownerEmail: 'e2e@agentspan.test',
      schemaVersion: 2,
      timeoutSeconds: 60,
      timeoutPolicy: 'TIME_OUT_WF',
      tasks: [
        {
          name: 'noop_terminate',
          taskReferenceName: 'noop_terminate_ref',
          type: 'TERMINATE',
          inputParameters: { terminationStatus: 'COMPLETED', workflowOutput: { ok: true } },
        },
      ],
    };
    const r = await fetch(`${SERVER_URL}/metadata/workflow`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(workflowDef),
    });
    if (!(r.status === 200 || r.status === 204)) {
      throw new Error(`Workflow register failed: ${r.status} ${await r.text()}`);
    }
  });

  afterAll(async () => {
    try {
      await client.reconcile(agentName, []);
    } catch {
      // ignore
    }
    try {
      await fetch(`${SERVER_URL}/metadata/workflow/${agentName}/1`, { method: 'DELETE' });
    } catch {
      // ignore
    }
    await runtime.shutdown();
  });

  beforeEach(async () => {
    // Per-test isolation: purge any leftover schedules for this agent.
    await client.reconcile(agentName, []);
  });

  it('reconcile creates schedules', async () => {
    await client.reconcile(agentName, [
      new Schedule({ name: 'daily', cron: '0 0 9 * * ?', input: { k: 1 } }),
      new Schedule({ name: 'weekly', cron: '0 0 9 * * MON' }),
    ]);
    const infos = await client.listForAgent(agentName);
    const byShort = new Map(infos.map((i) => [i.shortName, i]));
    expect(new Set(byShort.keys())).toEqual(new Set(['daily', 'weekly']));
    expect(byShort.get('daily')!.name).toBe(`${agentName}-daily`);
    expect(byShort.get('daily')!.cron).toBe('0 0 9 * * ?');
    expect(byShort.get('daily')!.input).toEqual({ k: 1 });
    expect(byShort.get('daily')!.agent).toBe(agentName);
  });

  it('upsert and prune', async () => {
    await client.reconcile(agentName, [
      new Schedule({ name: 'a', cron: '0 0 1 * * ?' }),
      new Schedule({ name: 'b', cron: '0 0 2 * * ?' }),
    ]);
    await client.reconcile(agentName, [
      new Schedule({ name: 'a', cron: '0 0 9 * * ?' }),
      new Schedule({ name: 'c', cron: '0 0 17 * * ?' }),
    ]);
    const infos = new Map((await client.listForAgent(agentName)).map((i) => [i.shortName, i]));
    expect(new Set(infos.keys())).toEqual(new Set(['a', 'c']));
    expect(infos.get('a')!.cron).toBe('0 0 9 * * ?');
  });

  it('empty list purges', async () => {
    await client.reconcile(agentName, [new Schedule({ name: 'x', cron: '0 * * * * ?' })]);
    expect((await client.listForAgent(agentName)).length).toBe(1);
    await client.reconcile(agentName, []);
    expect(await client.listForAgent(agentName)).toEqual([]);
  });

  it('null preserves', async () => {
    await client.reconcile(agentName, [new Schedule({ name: 'x', cron: '0 * * * * ?' })]);
    await client.reconcile(agentName, null);
    const infos = await client.listForAgent(agentName);
    expect(infos.map((i) => i.shortName)).toEqual(['x']);
  });

  it('duplicate name raises before any IO', async () => {
    await expect(
      client.reconcile(agentName, [
        new Schedule({ name: 'dup', cron: '0 * * * * ?' }),
        new Schedule({ name: 'dup', cron: '0 0 9 * * ?' }),
      ]),
    ).rejects.toThrow(ScheduleNameConflict);
    expect(await client.listForAgent(agentName)).toEqual([]);
  });

  it('pause then resume', async () => {
    await client.reconcile(agentName, [new Schedule({ name: 'p', cron: '0 0 9 * * ?' })]);
    const wire = `${agentName}-p`;

    expect((await client.get(wire)).paused).toBe(false);

    await client.pause(wire, 'rate limit');
    expect((await client.get(wire)).paused).toBe(true);

    await client.resume(wire);
    expect((await client.get(wire)).paused).toBe(false);
  });

  it('paused-on-create preserves state (spec §10 Q3)', async () => {
    await client.reconcile(agentName, [
      new Schedule({ name: 'silent', cron: '0 0 9 * * ?', paused: true }),
    ]);
    expect((await client.get(`${agentName}-silent`)).paused).toBe(true);
  });

  it('delete removes', async () => {
    await client.reconcile(agentName, [new Schedule({ name: 'd', cron: '0 * * * * ?' })]);
    await client.delete(`${agentName}-d`);
    expect(await client.listForAgent(agentName)).toEqual([]);
  });

  it('get after delete raises', async () => {
    await client.reconcile(agentName, [new Schedule({ name: 'g', cron: '0 * * * * ?' })]);
    const wire = `${agentName}-g`;
    await client.delete(wire);
    await expect(client.get(wire)).rejects.toThrow(ScheduleNotFound);
  });

  it('previewNext returns N strictly increasing times', async () => {
    const times = await client.previewNext('0 0 9 * * ?', { n: 3 });
    expect(times.length).toBe(3);
    expect([...times].sort((a, b) => a - b)).toEqual(times);
    expect(new Set(times).size).toBe(times.length);
  });
});

