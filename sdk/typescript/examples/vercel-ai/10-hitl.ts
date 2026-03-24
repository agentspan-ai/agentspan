/**
 * Vercel AI SDK -- Human-in-the-Loop (HITL)
 *
 * Demonstrates a Vercel AI SDK agent that pauses for human approval
 * before executing sensitive actions. The Agentspan runtime manages
 * the approval workflow.
 *
 * In production you would use:
 *   import { generateText } from 'ai';
 *   // Human approval gate managed by Agentspan Conductor HUMAN task
 */

import { AgentRuntime } from '../../src/index.js';

// -- Simulated approval state --
interface ApprovalRequest {
  action: string;
  description: string;
  risk: 'low' | 'medium' | 'high';
}

function checkApproval(request: ApprovalRequest): { approved: boolean; feedback: string } {
  // In production, this would pause and wait for human input via Agentspan UI/API
  // Here we simulate: approve low/medium risk, reject high risk
  if (request.risk === 'high') {
    return {
      approved: false,
      feedback: 'High-risk action rejected. Please provide additional justification.',
    };
  }
  return {
    approved: true,
    feedback: `Action approved (${request.risk} risk).`,
  };
}

// -- Mock Vercel AI SDK agent with HITL --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    const prompt = options.prompt.toLowerCase();
    const steps: string[] = [];

    // Step 1: Analyze the request
    steps.push('[Step 1] Analyzing request and determining risk level...');

    let risk: 'low' | 'medium' | 'high' = 'low';
    let action: string;

    if (prompt.includes('delete') || prompt.includes('drop') || prompt.includes('destroy')) {
      risk = 'high';
      action = 'destructive database operation';
    } else if (prompt.includes('update') || prompt.includes('modify') || prompt.includes('change')) {
      risk = 'medium';
      action = 'data modification operation';
    } else {
      risk = 'low';
      action = 'read-only query';
    }

    steps.push(`[Step 2] Risk assessment: ${risk.toUpperCase()} -- Action: ${action}`);

    // Step 2: Request human approval
    steps.push('[Step 3] Requesting human approval...');
    const approval = checkApproval({ action, description: options.prompt, risk });
    steps.push(`[Step 4] Approval result: ${approval.approved ? 'APPROVED' : 'REJECTED'} -- ${approval.feedback}`);

    // Step 3: Execute or abort based on approval
    if (approval.approved) {
      steps.push(`[Step 5] Executing action: ${action}`);
      steps.push('[Result] Operation completed successfully.');
    } else {
      steps.push('[Step 5] Action aborted -- awaiting revised request.');
    }

    return {
      text: steps.join('\n'),
      toolCalls: [],
      finishReason: 'stop' as const,
      metadata: { risk, approved: approval.approved },
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  id: 'vercel_hitl_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  // Test 1: Low risk (auto-approved)
  console.log('=== Test 1: Low risk query (should be approved) ===');
  let result = await runtime.run(
    vercelAgent,
    'Fetch the latest sales report for Q4 2024.',
  );
  console.log('Status:', result.status);
  result.printResult();

  // Test 2: Medium risk (approved)
  console.log('\n=== Test 2: Medium risk update (should be approved) ===');
  result = await runtime.run(
    vercelAgent,
    'Update the customer email address for account #12345.',
  );
  console.log('Status:', result.status);
  result.printResult();

  // Test 3: High risk (rejected)
  console.log('\n=== Test 3: High risk deletion (should be rejected) ===');
  result = await runtime.run(
    vercelAgent,
    'Delete all records from the staging database.',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
