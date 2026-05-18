/**
 * Suite 15: Skills — loading, serialization, and execution of skill-based agents.
 *
 * Tests:
 *   - Skill loading discovers sub-agents from *-agent.md
 *   - Serialization preserves _framework_config
 *   - Counterfactual: plain Agent has no skill data
 *   - Nested skill in agent_tool preserves skill data
 *   - plan() produces a valid workflow for skills
 *   - Skill as agent_tool: workers registered and polled (regression)
 *   - Script discovery, params injection, worker creation
 *
 * No mocks. Real server. Algorithmic assertions.
 */

import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';

vi.setConfig({ testTimeout: 300_000 }); // 5 min — skill execution tests involve real LLM calls
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import {
  Agent,
  AgentRuntime,
  AgentConfigSerializer,
  skill,
  agentTool,
} from '@agentspan-ai/sdk';
import { checkServerHealth, getWorkflow, MODEL } from './helpers';

// ── Fixtures ─────────────────────────────────────────────────

let skillDir: string;
let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available — skipping e2e tests');

  runtime = new AgentRuntime();

  // Create a temp skill directory
  skillDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agentspan-skill-test-'));

  fs.writeFileSync(
    path.join(skillDir, 'SKILL.md'),
    [
      '---',
      'name: ts_test_skill',
      'params:',
      '  mode:',
      '    default: fast',
      '---',
      '## Overview',
      'A test skill with two sub-agents and a script tool.',
      '',
      '## Workflow',
      "1. Call the echo_args tool once with the user's input as the argument.",
      '2. Return the echo_args result to the user. Do NOT call any more tools after echo_args.',
    ].join('\n'),
  );

  // Script tool: echoes args with a deterministic prefix
  const scriptsDir = path.join(skillDir, 'scripts');
  fs.mkdirSync(scriptsDir);
  fs.writeFileSync(
    path.join(scriptsDir, 'echo_args.py'),
    '#!/usr/bin/env python3\nimport sys\nargs = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "no-args"\nprint(f"ECHO_ARGS_RESULT:{args}")\n',
    { mode: 0o755 },
  );

  fs.writeFileSync(path.join(skillDir, 'alpha-agent.md'), '# Alpha Agent\nYou analyze the input.\n');
  fs.writeFileSync(path.join(skillDir, 'beta-agent.md'), '# Beta Agent\nYou summarize the analysis.\n');
  fs.writeFileSync(path.join(skillDir, 'template.html'), '<html><body>Test template</body></html>');
});

afterAll(async () => {
  await runtime?.shutdown();
  if (skillDir) {
    fs.rmSync(skillDir, { recursive: true, force: true });
  }
});

const DG_SKILL_PATH = path.join(os.homedir(), '.claude', 'skills', 'dg');

// ── Helpers ──────────────────────────────────────────────────

/**
 * Fetch a skill sub-workflow from a parent execution and verify:
 * 1. The skill SUB_WORKFLOW task exists and COMPLETED
 * 2. No tasks stuck in SCHEDULED inside the sub-workflow (pollCount=0 regression)
 * 3. If echo_args was invoked, it COMPLETED with ECHO_ARGS_RESULT marker
 */
async function verifySkillSubWorkflow(
  executionId: string,
  skillTaskName = 'ts_test_skill',
): Promise<void> {
  const wf = await getWorkflow(executionId);
  const tasks = (wf.tasks ?? []) as Record<string, unknown>[];

  // Find the skill SUB_WORKFLOW task
  const skillTasks = tasks.filter(
    (t) => ((t.taskDefName as string) ?? '').includes(skillTaskName),
  );
  expect(skillTasks.length).toBeGreaterThan(0);
  for (const t of skillTasks) {
    expect(t.status).toBe('COMPLETED');
  }

  // Fetch the sub-workflow
  const subWfId = (skillTasks[0].outputData as Record<string, unknown>)?.subWorkflowId as string;
  expect(subWfId).toBeTruthy();

  const subWf = await getWorkflow(subWfId);
  const subTasks = (subWf.tasks ?? []) as Record<string, unknown>[];

  // CRITICAL: no tasks stuck in SCHEDULED — the original bug symptom.
  const scheduled = subTasks.filter((t) => t.status === 'SCHEDULED');
  expect(scheduled).toEqual([]);

  // If echo_args was invoked, verify it completed with deterministic marker
  const echoTasks = subTasks.filter(
    (t) => ((t.taskDefName as string) ?? '').includes('echo_args'),
  );
  if (echoTasks.length > 0) {
    for (const t of echoTasks) {
      expect(t.status).toBe('COMPLETED');
    }
    const anyMarker = echoTasks.some((t) =>
      JSON.stringify(t.outputData ?? {}).includes('ECHO_ARGS_RESULT:'),
    );
    expect(anyMarker).toBe(true);
  }
}

// ── Tests ────────────────────────────────────────────────────

describe('Suite 15: Skills', () => {
  // ── Loading & serialization (no server, instant) ───────────

  it('skill() discovers sub-agents from *-agent.md files', () => {
    const agent = skill(skillDir, { model: MODEL }) as unknown as Record<string, unknown>;

    expect(agent._framework).toBe('skill');
    const raw = agent._framework_config as Record<string, unknown>;
    const agentFiles = raw.agentFiles as Record<string, string>;
    expect(Object.keys(agentFiles)).toContain('alpha');
    expect(Object.keys(agentFiles)).toContain('beta');
  });

  it('serialized config preserves _framework_config data', () => {
    const agent = skill(skillDir, { model: MODEL });
    const serializer = new AgentConfigSerializer();
    const config = serializer.serializeAgent(agent);

    expect(config._framework).toBe('skill');
    expect(config.agentFiles).toBeDefined();
    expect(config.name).toBe('ts_test_skill');
    expect(config.skillMd).toBeDefined();
  });

  it('counterfactual: plain Agent has no skill data', () => {
    const plain = new Agent({ name: 'plain_agent', model: MODEL, instructions: 'You are a plain agent.' });
    const serializer = new AgentConfigSerializer();
    const config = serializer.serializeAgent(plain);

    expect(config._framework).toBeUndefined();
    expect(config.skillMd).toBeUndefined();
    expect(config.agentFiles).toBeUndefined();
  });

  it('nested skill in agent_tool preserves skill data in serialization', () => {
    const skillAgent = skill(skillDir, { model: MODEL });
    const at = agentTool(skillAgent, { description: 'Run test skill' });
    const parent = new Agent({ name: 'e2e_ts_skill_parent', model: MODEL, instructions: 'Use the skill tool.', tools: [at] });

    const serializer = new AgentConfigSerializer();
    const config = serializer.serializeAgent(parent);

    expect(config._framework).toBeUndefined();
    const tools = (config.tools ?? []) as Record<string, unknown>[];
    expect(tools.map((t) => t.name)).toContain('ts_test_skill');
  });

  it('discovers scripts from scripts/ directory', () => {
    const agent = skill(skillDir, { model: MODEL }) as unknown as Record<string, unknown>;
    const raw = agent._framework_config as Record<string, unknown>;
    const scripts = raw.scripts as Record<string, Record<string, string>>;

    expect(scripts.echo_args).toBeDefined();
    expect(scripts.echo_args.language).toBe('python');
    expect(scripts.echo_args.filename).toBe('echo_args.py');
  });

  it('params are injected into SKILL.md for server visibility', () => {
    const agent = skill(skillDir, { model: MODEL, params: { mode: 'turbo', rounds: 1 } }) as unknown as Record<string, unknown>;
    const raw = agent._framework_config as Record<string, unknown>;
    const skillMd = raw.skillMd as string;

    expect(skillMd).toContain('[Skill Parameters]');
    expect(skillMd).toContain('mode: turbo');
    expect(skillMd).toContain('rounds: 1');

    const params = raw.params as Record<string, unknown>;
    expect(params.mode).toBe('turbo');
    expect(params.rounds).toBe(1);
  });

  it('runtime params override defaults in merged params', () => {
    const agentOverride = skill(skillDir, { model: MODEL, params: { mode: 'slow' } }) as unknown as Record<string, unknown>;
    const overrideParams = agentOverride._skill_params as Record<string, unknown>;
    expect(overrideParams?.mode).toBe('slow');

    const raw = agentOverride._framework_config as Record<string, unknown>;
    expect((raw.skillMd as string)).toContain('mode: slow');
  });

  it('DG skill loads gilfoyle + dinesh agents', () => {
    if (!fs.existsSync(DG_SKILL_PATH)) {
      console.log(`DG skill not installed at ${DG_SKILL_PATH} — skipping`);
      return;
    }

    const agent = skill(DG_SKILL_PATH, { model: MODEL }) as unknown as Record<string, unknown>;
    expect(agent._framework).toBe('skill');

    const raw = agent._framework_config as Record<string, unknown>;
    const agentFiles = raw.agentFiles as Record<string, string>;
    expect(Object.keys(agentFiles)).toContain('gilfoyle');
    expect(Object.keys(agentFiles)).toContain('dinesh');
  });

  // ── Compilation (server call, no LLM) ──────────────────────

  it('plan() produces a valid workflow for a skill', async () => {
    const agent = skill(skillDir, { model: MODEL });
    const result = await runtime.plan(agent);

    expect(result.workflowDef).toBeDefined();
    const wf = result.workflowDef as Record<string, unknown>;
    expect(wf.name).toBe('ts_test_skill');

    const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
    expect(tasks.length).toBeGreaterThan(0);
    const taskTypes = new Set(tasks.map((t) => t.type));
    expect(taskTypes.has('LLM_CHAT_COMPLETE') || taskTypes.has('DO_WHILE')).toBe(true);
  });

  it('skill params visible in compiled workflow', async () => {
    const agent = skill(skillDir, { model: MODEL, params: { mode: 'turbo', rounds: 1 } });
    const result = await runtime.plan(agent);

    const wfStr = JSON.stringify(result.workflowDef);
    expect(wfStr.includes('Skill Parameters') || wfStr.includes('mode')).toBe(true);
  });

  // ── Execution (real LLM calls) ─────────────────────────────

  it('agent_tool skill workers registered and polled (regression)', async () => {
    /**
     * Regression test for _preDeployNestedSkills + worker polling.
     * The bug: skill workers were registered but never polled because
     * the parent had no @tool workers. Result: echo_args stuck in
     * SCHEDULED with pollCount=0.
     *
     * Validates:
     * - Parent execution COMPLETED
     * - Skill SUB_WORKFLOW COMPLETED
     * - Zero tasks stuck in SCHEDULED inside the sub-workflow
     * - echo_args COMPLETED with ECHO_ARGS_RESULT marker (if invoked)
     */
    const skillAgent = skill(skillDir, { model: MODEL });
    const at = agentTool(skillAgent, { description: 'Run test skill with echo_args' });

    const parent = new Agent({
      name: 'e2e_ts_skill_at_worker_reg',
      model: MODEL,
      instructions: "You have one tool: ts_test_skill. Call it once with the user's request, then return the result.",
      tools: [at],
      maxTurns: 3,
    });

    const result = await runtime.run(parent, "Echo 'proof42'");

    expect(String(result.status).toUpperCase()).toContain('COMPLETED');
    await verifySkillSubWorkflow(result.executionId);
  });
});
