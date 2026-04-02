/**
 * Skills — Load conductor skill for workflow management.
 *
 * Demonstrates:
 *   - Loading a skill with scripts (conductor_api.py) as auto-wrapped tools
 *   - Progressive disclosure: reference docs loaded on demand via read_skill_file
 *   - Each conductor_api call is a visible SIMPLE task in the Conductor DAG
 *   - Composing the conductor skill with /dg in a multi-agent team
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
 *   - conductor-skills installed (https://github.com/conductor-oss/conductor-skills)
 */

import { Agent, AgentRuntime, agentTool, loadSkills, skill } from '../src/index.js';
import { llmModel, secondaryLlmModel } from './settings.js';

// ── Load conductor skill ───────────────────────────────────────────
const conductorSkill = skill('~/.claude/skills/conductor', {
  model: llmModel,
});

// ── Example 1: Run conductor skill standalone ──────────────────────
async function runStandalone() {
  const runtime = new AgentRuntime();
  try {
    console.log('=== Conductor Skill — Workflow Management ===\n');

    const result = await runtime.run(
      conductorSkill,
      'Create a simple HTTP workflow that fetches https://httpbin.org/get, ' +
        'then transforms the response with a JSON_JQ_TRANSFORM to extract the origin IP. ' +
        'Start the workflow and show me the result.',
    );

    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status: ${result.status}`);
    console.log(`Tokens: ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ── Example 2: Load all skills from a directory ────────────────────
async function runWithLoadSkills() {
  const skills = loadSkills('~/.claude/skills/', { model: llmModel });

  console.log(`Loaded ${Object.keys(skills).length} skills: ${Object.keys(skills).join(', ')}\n`);

  if (skills['conductor']) {
    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(skills['conductor'], 'List all workflow definitions');
      console.log(`Execution ID: ${result.executionId}`);
      console.log(`Status: ${result.status}`);
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
  }
}

// ── Example 3: Multi-skill team — /dg + conductor ─────────────────
async function runMultiSkillTeam() {
  const dgSkill = skill('~/.claude/skills/dg', { model: secondaryLlmModel });

  const team = new Agent({
    name: 'devops_team',
    model: llmModel,
    instructions:
      'You are a DevOps team lead. Route tasks to the right specialist:\n' +
      '- Code review requests → use the dg agent (adversarial code review)\n' +
      '- Workflow/orchestration tasks → use the conductor agent\n' +
      '- For tasks that need both, run review first then deploy',
    tools: [
      agentTool(dgSkill, { description: 'Run adversarial code review with Dinesh vs Gilfoyle' }),
      agentTool(conductorSkill, {
        description: 'Create, run, and manage Conductor workflows',
      }),
    ],
  });

  const runtime = new AgentRuntime();
  try {
    console.log('=== DevOps Team — /dg + Conductor ===\n');

    const result = await runtime.run(
      team,
      'Review this workflow worker code, then create a Conductor workflow that uses it:\n\n' +
        '```python\n' +
        "def process_order(task):\n" +
        "    order = task.input_data.get('order')\n" +
        "    total = sum(item['price'] for item in order['items'])\n" +
        '    if total > 10000:\n' +
        "        return {'status': 'REQUIRES_APPROVAL', 'total': total}\n" +
        "    return {'status': 'APPROVED', 'total': total}\n" +
        '```',
    );

    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status: ${result.status}`);

    if (result.subResults) {
      console.log('\nSub-agent executions:');
      for (const [agentName, subResult] of Object.entries(result.subResults)) {
        console.log(`  - ${agentName}: ${JSON.stringify(subResult)}`);
      }
    }

    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ── Main ───────────────────────────────────────────────────────────
async function main() {
  const choice = process.argv[2] ?? 'standalone';
  const examples: Record<string, () => Promise<void>> = {
    standalone: runStandalone,
    load_skills: runWithLoadSkills,
    team: runMultiSkillTeam,
  };

  if (choice in examples) {
    await examples[choice]();
  } else {
    console.log(`Usage: npx tsx ${process.argv[1]} [${Object.keys(examples).join('/')}]`);
  }
}

if (
  process.argv[1]?.endsWith('31-skills-conductor.ts') ||
  process.argv[1]?.endsWith('31-skills-conductor.js')
) {
  main().catch(console.error);
}
