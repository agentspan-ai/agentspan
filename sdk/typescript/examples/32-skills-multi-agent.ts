/**
 * Skills — Multi-agent workflows with skills as sub-agents.
 *
 * Demonstrates:
 *   - Skills as sub-agents in router, sequential, and parallel teams
 *   - Mixing skill-based agents with regular tool agents
 *   - Skills composed via agentTool() on an orchestrator
 *   - Skills in a pipeline with .pipe()
 *   - Full visibility: each skill sub-agent is a real Conductor SUB_WORKFLOW
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
 *   - /dg skill installed (https://github.com/v1r3n/dinesh-gilfoyle)
 *   - conductor skill installed (https://github.com/conductor-oss/conductor-skills)
 */

import { z } from 'zod';
import { Agent, AgentRuntime, OnTextMention, agentTool, skill, tool } from '../src/index.js';
import { llmModel, secondaryLlmModel } from './settings.js';

// ── Load skills ────────────────────────────────────────────────────
const dg = skill('~/.claude/skills/dg', { model: llmModel });
const conductorSkill = skill('~/.claude/skills/conductor', {
  model: secondaryLlmModel,
});

// ── Shared tools ───────────────────────────────────────────────────
const runTests = tool(
  async (args: { code: string }) => {
    if (!args.code) {
      return { result: 'ERROR: no code provided to test' };
    }
    if (args.code.includes('SELECT *') && args.code.includes("f'")) {
      return { result: 'FAIL: test_sql_injection detected SQL injection vulnerability' };
    }
    if (args.code.includes('subprocess') && args.code.includes('shell=True')) {
      return { result: 'FAIL: test_command_injection detected command injection' };
    }
    return { result: 'PASS: all tests passed' };
  },
  {
    name: 'run_tests',
    description: 'Run unit tests on the provided code (simulated).',
    inputSchema: z.object({ code: z.string().describe('Code to test') }),
  },
);

// ═══════════════════════════════════════════════════════════════════
// Example 1: Router — DevOps team routes to the right specialist
// ═══════════════════════════════════════════════════════════════════

async function exampleRouter() {
  const coder = new Agent({
    name: 'coder',
    model: llmModel,
    instructions:
      'You are a senior developer. Write clean, production-ready code. ' +
      'Always include error handling and type annotations.',
  });

  const devopsTeam = new Agent({
    name: 'devops_team',
    model: llmModel,
    agents: [dg, coder, conductorSkill],
    strategy: 'router',
    router: new Agent({
      name: 'router',
      model: llmModel,
      instructions:
        'Route tasks to the right specialist:\n' +
        '- Code review, PR review → dg\n' +
        '- Writing code, fixing bugs → coder\n' +
        '- Workflow orchestration → conductor',
    }),
  });

  const runtime = new AgentRuntime();
  try {
    console.log('=== Example 1: Router Team ===\n');
    const result = await runtime.run(
      devopsTeam,
      "Review this function for security issues:\n\n" +
        "def login(username, password):\n" +
        "    query = f\"SELECT * FROM users WHERE user='{username}' AND pass='{password}'\"\n" +
        '    return db.execute(query)\n',
    );
    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status:      ${result.status}`);
    console.log(`Tokens:      ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ═══════════════════════════════════════════════════════════════════
// Example 2: Sequential Pipeline — Review → Fix → Deploy
// ═══════════════════════════════════════════════════════════════════

async function examplePipeline() {
  const fixer = new Agent({
    name: 'fixer',
    model: secondaryLlmModel,
    instructions:
      'You receive a code review with findings. For each critical finding, ' +
      'rewrite the code with the fix applied. Include comments explaining each fix.',
  });

  const deployer = new Agent({
    name: 'deployer',
    model: llmModel,
    instructions:
      'You receive fixed code. Create a Conductor workflow definition that ' +
      'uses a SIMPLE task to run this code as a worker. Output the JSON.',
  });

  const reviewFixDeploy = dg.pipe(fixer).pipe(deployer);

  const runtime = new AgentRuntime();
  try {
    console.log('=== Example 2: Review → Fix → Deploy Pipeline ===\n');
    const result = await runtime.run(
      reviewFixDeploy,
      "Review, fix, and deploy:\n\n" +
        "def process_payment(amount, card_number):\n" +
        "    log.info(f'Processing {card_number} for ${amount}')\n" +
        '    if amount > 0:\n' +
        '        return charge_card(card_number, amount)\n' +
        "    return {'error': 'invalid amount'}\n",
    );
    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status:      ${result.status}`);
    console.log(`Tokens:      ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ═══════════════════════════════════════════════════════════════════
// Example 3: Parallel — Multiple reviewers simultaneously
// ═══════════════════════════════════════════════════════════════════

async function exampleParallel() {
  const securityReviewer = new Agent({
    name: 'security_reviewer',
    model: llmModel,
    instructions:
      'Review code ONLY for security: injection, credentials, auth gaps, OWASP Top 10.',
  });

  const performanceReviewer = new Agent({
    name: 'performance_reviewer',
    model: llmModel,
    instructions:
      'Review code ONLY for performance: O(n²), missing caching, N+1 queries, blocking calls.',
  });

  const parallelReview = new Agent({
    name: 'parallel_review',
    model: llmModel,
    agents: [dg, securityReviewer, performanceReviewer],
    strategy: 'parallel',
    instructions:
      'Run all three reviewers in parallel. Aggregate findings into a unified report.',
  });

  const runtime = new AgentRuntime();
  try {
    console.log('=== Example 3: Parallel Review ===\n');
    const result = await runtime.run(
      parallelReview,
      "Review this endpoint:\n\n" +
        'from flask import request\n' +
        'import subprocess\n\n' +
        "@app.route('/run')\n" +
        'def execute():\n' +
        "    cmd = request.args.get('cmd')\n" +
        '    output = subprocess.check_output(cmd, shell=True)\n' +
        '    return output.decode()\n',
    );
    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status:      ${result.status}`);
    console.log(`Tokens:      ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ═══════════════════════════════════════════════════════════════════
// Example 4: Skills as tools on an orchestrator
// ═══════════════════════════════════════════════════════════════════

async function exampleOrchestrator() {
  const techLead = new Agent({
    name: 'tech_lead',
    model: llmModel,
    instructions:
      'You are a tech lead managing a review and deployment pipeline.\n\n' +
      '1. Run code review using dg tool\n' +
      '2. If critical issues → stop and report\n' +
      '3. If passes → run tests\n' +
      '4. If tests pass → use conductor to create deployment workflow\n' +
      '5. Summarize the full pipeline result',
    tools: [
      agentTool(dg, { description: 'Run adversarial Dinesh vs Gilfoyle code review' }),
      agentTool(conductorSkill, { description: 'Create and manage Conductor workflows' }),
      runTests,
    ],
  });

  const runtime = new AgentRuntime();
  try {
    console.log('=== Example 4: Tech Lead Orchestrator ===\n');
    const result = await runtime.run(
      techLead,
      'Review and deploy this worker:\n\n' +
        'def enrich_customer(task):\n' +
        "    customer_id = task.input_data['customer_id']\n" +
        '    profile = fetch_profile(customer_id)\n' +
        '    enriched = {\n' +
        "        'name': profile['name'],\n" +
        "        'segment': classify_segment(profile),\n" +
        "        'ltv': calculate_ltv(profile['orders']),\n" +
        '    }\n' +
        "    return {'status': 'COMPLETED', 'output': enriched}\n",
    );
    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status:      ${result.status}`);
    console.log(`Tokens:      ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ═══════════════════════════════════════════════════════════════════
// Example 5: Swarm — Agents hand off to each other
// ═══════════════════════════════════════════════════════════════════

async function exampleSwarm() {
  const architect = new Agent({
    name: 'architect',
    model: secondaryLlmModel,
    instructions:
      'You are a software architect. Design the system for the given requirements. ' +
      'When ready, say HANDOFF_TO_DG for review. If review finds issues, redesign.',
  });

  const swarmTeam = new Agent({
    name: 'design_review_loop',
    model: llmModel,
    agents: [architect, dg],
    strategy: 'swarm',
    handoffs: [
      new OnTextMention({ text: 'HANDOFF_TO_DG', target: 'dg' }),
      new OnTextMention({ text: 'HANDOFF_TO_ARCHITECT', target: 'architect' }),
    ],
  });

  const runtime = new AgentRuntime();
  try {
    console.log('=== Example 5: Architect ↔ /dg Swarm ===\n');
    const result = await runtime.run(
      swarmTeam,
      'Design a rate limiter service with:\n' +
        '- Fixed window and sliding window algorithms\n' +
        '- Redis backend for distributed state\n' +
        '- REST API for configuration\n' +
        '- Middleware for Express.js',
    );
    console.log(`Execution ID: ${result.executionId}`);
    console.log(`Status:      ${result.status}`);
    console.log(`Tokens:      ${JSON.stringify(result.tokenUsage)}`);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// ── Main ───────────────────────────────────────────────────────────
async function main() {
  const choice = process.argv[2] ?? 'router';
  const examples: Record<string, () => Promise<void>> = {
    router: exampleRouter,
    pipeline: examplePipeline,
    parallel: exampleParallel,
    orchestrator: exampleOrchestrator,
    swarm: exampleSwarm,
  };

  if (choice === 'all') {
    for (const [name, fn] of Object.entries(examples)) {
      console.log(`\n${'='.repeat(60)}`);
      await fn();
    }
  } else if (choice in examples) {
    await examples[choice]();
  } else {
    console.log(`Usage: npx tsx ${process.argv[1]} [${Object.keys(examples).join('/')}/all]`);
  }
}

if (
  process.argv[1]?.endsWith('32-skills-multi-agent.ts') ||
  process.argv[1]?.endsWith('32-skills-multi-agent.js')
) {
  main().catch(console.error);
}
