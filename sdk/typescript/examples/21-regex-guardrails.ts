/**
 * Regex Guardrails -- pattern-based content validation.
 *
 * Demonstrates `RegexGuardrail` for blocking or allowing content based
 * on regex patterns.
 *
 * Examples:
 *   - Block mode: reject responses containing email addresses or SSNs
 *   - Allow mode: require responses to be valid JSON
 *
 * RegexGuardrails compile to Conductor InlineTasks -- the regex patterns
 * are evaluated server-side in JavaScript (GraalVM), so no local worker
 * process is needed.  This makes them lightweight and fast.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool, RegexGuardrail } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Block mode: reject responses with PII ----------------------------------

const noEmails = new RegexGuardrail({
  patterns: ['[\\w.+-]+@[\\w-]+\\.[\\w.-]+'],
  mode: 'block',
  name: 'no_email_addresses',
  message: 'Response must not contain email addresses. Redact them.',
  position: 'output',
  onFail: 'retry',
});

const noSsn = new RegexGuardrail({
  patterns: ['\\b\\d{3}-\\d{2}-\\d{4}\\b'],
  mode: 'block',
  name: 'no_ssn',
  message: 'Response must not contain Social Security Numbers.',
  position: 'output',
  onFail: 'raise',
});

// -- Agent with PII-blocking guardrails -------------------------------------

const getUserProfile = tool(
  async (_args: { user_id: string }) => {
    return JSON.stringify({
      name: 'Alice Johnson',
      email: 'alice.johnson@example.com', // PII - should be blocked
      ssn: '123-45-6789',                 // PII - should be blocked
      department: 'Engineering',
      role: 'Senior Developer',
    });
  },
  {
    name: 'get_user_profile',
    description: "Retrieve a user's profile from the database.",
    inputSchema: {
      type: 'object',
      properties: {
        user_id: { type: 'string', description: 'The user ID' },
      },
      required: ['user_id'],
    },
  },
);

export const agent = new Agent({
  name: 'hr_assistant',
  model: llmModel,
  tools: [getUserProfile],
  instructions:
    'You are an HR assistant. When asked about employees, look up their ' +
    'profile and share ALL the details you find.',
  guardrails: [noEmails, noSsn],
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // -- Scenario 1: Guardrail TRIGGERS -- PII in tool output -----------------
    console.log('='.repeat(60));
    console.log('  Scenario 1: Request PII -- guardrails trigger');
    console.log('='.repeat(60));

    const result = await runtime.run(
    agent,
    'Tell me everything about user U-001.',
    );
    result.printResult();

    const output = JSON.stringify(result.output);
    if (output.includes('alice.johnson@example.com')) {
    console.log('[FAIL] Email leaked!');
    } else {
    console.log('[OK] Email was blocked by RegexGuardrail');
    }

    if (output.includes('123-45-6789')) {
    console.log('[FAIL] SSN leaked!');
    } else {
    console.log('[OK] SSN was blocked by RegexGuardrail');
    }

    // -- Scenario 2: Guardrail does NOT trigger -- no PII ---------------------
    console.log('\n' + '='.repeat(60));
    console.log('  Scenario 2: Non-PII question -- guardrails pass');
    console.log('='.repeat(60));

    // New agent without PII-returning tool
    const cleanAgent = new Agent({
    name: 'dept_assistant',
    model: llmModel,
    instructions: 'You are an HR assistant. Answer questions about departments.',
    guardrails: [noEmails, noSsn],
    });

    const result2 = await runtime.run(
    cleanAgent,
    'What departments exist at the company?',
    );
    result2.printResult();

    if (result2.status === 'COMPLETED') {
    console.log('[OK] Clean response passed guardrails successfully');
    } else {
    console.log(`[WARN] Unexpected status: ${result2.status}`);
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents hr_assistant
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('21-regex-guardrails.ts') || process.argv[1]?.endsWith('21-regex-guardrails.js')) {
  main().catch(console.error);
}
