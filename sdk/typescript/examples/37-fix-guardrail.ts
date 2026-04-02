/**
 * 37 - Fix Guardrail (onFail='fix')
 *
 * Demonstrates onFail="fix": when the guardrail fails, it provides a
 * corrected version of the output via fixedOutput. The workflow uses the
 * fixed output directly without calling the LLM again.
 *
 * This is useful when the correction is deterministic (e.g. stripping PII,
 * truncating, formatting) -- faster and cheaper than retry since no LLM
 * round-trip is needed.
 *
 * Comparison of onFail modes:
 *   - 'retry'  -- send feedback to LLM and regenerate (best for style issues)
 *   - 'fix'    -- replace output with fixedOutput (best for deterministic fixes)
 *   - 'raise'  -- terminate the workflow with an error
 *   - 'human'  -- pause for human review (see example 32)
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, guardrail, tool } from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Fix guardrail: redact phone numbers -------------------------------------
// Instead of asking the LLM to retry, this guardrail redacts phone
// numbers directly and returns the cleaned output.

const redactPhoneNumbers = guardrail(
  (content: string): GuardrailResult => {
    const phonePattern = /(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g;

    if (phonePattern.test(content)) {
      const redacted = content.replace(
        /(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g,
        '[PHONE REDACTED]',
      );
      return {
        passed: false,
        message: 'Phone numbers detected and redacted.',
        fixedOutput: redacted,
      };
    }
    return { passed: true };
  },
  {
    name: 'phone_redactor',
    position: 'output',
    onFail: 'fix',
  },
);

// -- Tool --------------------------------------------------------------------

const getContactInfo = tool(
  async (args: { name: string }) => {
    const contacts: Record<string, Record<string, string>> = {
      alice: {
        name: 'Alice Johnson',
        email: 'alice@example.com',
        phone: '(555) 123-4567',
        department: 'Engineering',
      },
      bob: {
        name: 'Bob Smith',
        email: 'bob@example.com',
        phone: '555-987-6543',
        department: 'Marketing',
      },
    };
    const key = args.name.toLowerCase().split(/\s+/)[0];
    return contacts[key] ?? { error: `No contact found for '${args.name}'` };
  },
  {
    name: 'get_contact_info',
    description: 'Look up contact information for a person.',
    inputSchema: z.object({
      name: z.string().describe('Name of the person to look up'),
    }),
  },
);

// -- Agent -------------------------------------------------------------------

export const agent = new Agent({
  name: 'directory_agent',
  model: llmModel,
  tools: [getContactInfo],
  instructions:
    'You are a company directory assistant. When asked about employees, ' +
    'look up their contact info and share everything you find.',
  guardrails: [redactPhoneNumbers],
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // -- Scenario 1: Guardrail TRIGGERS -- contact has phone number
    console.log('='.repeat(60));
    console.log('  Scenario 1: Contact with phone number (guardrail triggers)');
    console.log('='.repeat(60));
    const result = await runtime.run(
    agent,
    "What's Alice Johnson's contact information?",
    );
    result.printResult();

    const output = String(result.output);
    if (output.includes('(555) 123-4567') || output.includes('555-123-4567')) {
    console.log('[FAIL] Phone number leaked through the guardrail!');
    } else if (output.includes('[PHONE REDACTED]')) {
    console.log('[OK] Phone number was auto-redacted by fix guardrail');
    } else {
    console.log('[OK] No phone number in output');
    }

    // -- Scenario 2: Guardrail does NOT trigger -- no phone in response
    console.log('\n' + '='.repeat(60));
    console.log('  Scenario 2: General question (guardrail does not trigger)');
    console.log('='.repeat(60));
    const result2 = await runtime.run(
    agent,
    'What department does Alice work in? Just the department name.',
    );
    result2.printResult();

    const output2 = String(result2.output);
    if (output2.includes('[PHONE REDACTED]')) {
    console.log('[WARN] Unexpected redaction in clean response');
    } else {
    console.log('[OK] No redaction needed -- guardrail passed cleanly');
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents directory_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('37-fix-guardrail.ts') || process.argv[1]?.endsWith('37-fix-guardrail.js')) {
  main().catch(console.error);
}
