/**
 * Suite 15: Skills — loading, serialization, and execution of skill-based agents.
 *
 * Tests:
 *   - Skill loading discovers sub-agents from *-agent.md
 *   - Serialization preserves _framework_config
 *   - Counterfactual: plain Agent has no skill data
 *   - Nested skill in agent_tool preserves skill data
 *   - plan() produces a valid workflow for skills
 *   - Skill execution produces SUB_WORKFLOW tasks
 *   - Skill as agent_tool execution works
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
      'A test skill with two sub-agents.',
      '',
      '## Workflow',
      'Alpha analyzes, Beta summarizes.',
    ].join('\n'),
  );

  fs.writeFileSync(
    path.join(skillDir, 'alpha-agent.md'),
    '# Alpha Agent\nYou analyze the input.\n',
  );

  fs.writeFileSync(
    path.join(skillDir, 'beta-agent.md'),
    '# Beta Agent\nYou summarize the analysis.\n',
  );

  fs.writeFileSync(
    path.join(skillDir, 'template.html'),
    '<html><body>Test template</body></html>',
  );
});

afterAll(async () => {
  await runtime?.shutdown();
  if (skillDir) {
    fs.rmSync(skillDir, { recursive: true, force: true });
  }
});

const DG_SKILL_PATH = path.join(os.homedir(), '.claude', 'skills', 'dg');

// ── Tests ────────────────────────────────────────────────────

describe('Suite 15: Skills', () => {
  it('skill() discovers sub-agents from *-agent.md files', () => {
    const agent = skill(skillDir, { model: MODEL }) as unknown as Record<string, unknown>;

    expect(agent._framework).toBe('skill');

    const raw = agent._framework_config as Record<string, unknown>;
    expect(raw).toBeDefined();

    const agentFiles = raw.agentFiles as Record<string, string>;
    expect(agentFiles).toBeDefined();
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

    const agentFiles = config.agentFiles as Record<string, string>;
    expect(Object.keys(agentFiles)).toContain('alpha');
    expect(Object.keys(agentFiles)).toContain('beta');
  });

  it('counterfactual: plain Agent has no skill data', () => {
    const plain = new Agent({
      name: 'plain_agent',
      model: MODEL,
      instructions: 'You are a plain agent.',
    });

    const serializer = new AgentConfigSerializer();
    const config = serializer.serializeAgent(plain);

    expect(config._framework).toBeUndefined();
    expect(config.skillMd).toBeUndefined();
    expect(config.agentFiles).toBeUndefined();
  });

  it('nested skill in agent_tool preserves skill data in serialization', () => {
    const skillAgent = skill(skillDir, { model: MODEL });
    const at = agentTool(skillAgent, { description: 'Run test skill' });

    const parent = new Agent({
      name: 'e2e_ts_skill_parent',
      model: MODEL,
      instructions: 'Use the skill tool.',
      tools: [at],
    });

    const serializer = new AgentConfigSerializer();
    const config = serializer.serializeAgent(parent);

    // Parent is not a skill
    expect(config._framework).toBeUndefined();

    // Tool list should contain the skill
    const tools = (config.tools ?? []) as Record<string, unknown>[];
    const skillToolNames = tools.map((t) => t.name);
    expect(skillToolNames).toContain('ts_test_skill');
  });

  it('plan() produces a valid workflow for a skill', async () => {
    const agent = skill(skillDir, { model: MODEL });

    const result = await runtime.plan(agent);

    expect(result).toBeDefined();
    expect(result.workflowDef).toBeDefined();

    const wf = result.workflowDef as Record<string, unknown>;
    expect(wf.name).toBe('ts_test_skill');

    const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
    expect(tasks.length).toBeGreaterThan(0);

    // Should have LLM_CHAT_COMPLETE (orchestrator) and a loop structure
    const taskTypes = new Set(tasks.map((t) => t.type));
    expect(taskTypes.has('LLM_CHAT_COMPLETE') || taskTypes.has('DO_WHILE')).toBe(true);
  });

  it('skill execution produces SUB_WORKFLOW tasks', async () => {
    const agent = skill(skillDir, { model: MODEL });

    const result = await runtime.run(agent, "Analyze the word 'hello'");

    expect(result).toBeDefined();
    expect(String(result.status).toUpperCase()).toContain('COMPLETED');

    const wf = await getWorkflow(result.executionId);
    const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
    expect(tasks.length).toBeGreaterThan(0);

    const taskTypes = new Set(tasks.map((t) => (t.taskType ?? t.type) as string));
    expect(taskTypes.has('SUB_WORKFLOW')).toBe(true);
  });

  it('skill as agent_tool executes successfully', async () => {
    const skillAgent = skill(skillDir, { model: MODEL });
    const at = agentTool(skillAgent, { description: 'Analyze with test skill' });

    const parent = new Agent({
      name: 'e2e_ts_skill_at_parent',
      model: MODEL,
      instructions: 'Use the ts_test_skill tool to analyze the input.',
      tools: [at],
    });

    const result = await runtime.run(parent, "Analyze 'skill test'");

    expect(result).toBeDefined();
    expect(String(result.status).toUpperCase()).toContain('COMPLETED');
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

    // Verify serialization preserves DG config
    const serializer = new AgentConfigSerializer();
    const config = serializer.serializeAgent(agent as unknown as Agent);
    expect(config._framework).toBe('skill');
    expect((config.agentFiles as Record<string, string>)?.gilfoyle).toBeDefined();
  });
});
