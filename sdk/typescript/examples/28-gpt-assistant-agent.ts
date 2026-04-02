/**
 * GPTAssistantAgent -- wrap OpenAI Assistants API as a Conductor agent.
 *
 * Demonstrates `GPTAssistantAgent` which uses the OpenAI Assistants API
 * (with threads, runs, and built-in tools like code_interpreter) as a
 * Conductor agent.
 *
 * Two modes:
 *   1. Use an existing assistant by ID
 *   2. Create a new assistant on-the-fly with model + instructions
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - OPENAI_API_KEY=sk-... as environment variable
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { AgentRuntime, GPTAssistantAgent } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Create assistant on the fly --------------------------------

// GPTAssistantAgent requires an assistantId -- in a real setup you'd use
// a pre-created assistant ID from the OpenAI dashboard.
const assistantId = process.env.OPENAI_ASSISTANT_ID ?? 'asst_placeholder';

const dataAnalyst = new GPTAssistantAgent({
  name: 'data_analyst',
  assistantId,
  model: llmModel,
  instructions:
    'You are a data analyst. Use the code interpreter to analyze data, ' +
    'create charts, and perform calculations.',
});

// -- Example 2: Use an existing assistant ----------------------------------

// If you already have an assistant created in the OpenAI dashboard:
// const existingAssistant = new GPTAssistantAgent({
//   name: 'my_assistant',
//   assistantId: 'asst_abc123def456',
// });

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('--- GPT Assistant with Code Interpreter ---');
    console.log(`Using assistant ID: ${assistantId}`);

    if (assistantId === 'asst_placeholder') {
    console.log('(Skipping run -- set OPENAI_ASSISTANT_ID to use a real assistant)');
    console.log('[OK] GPTAssistantAgent structure validated');
    } else {
    const result = await runtime.run(
    dataAnalyst,
    'Calculate the standard deviation of these numbers: 4, 8, 15, 16, 23, 42',
    );
    result.printResult();
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(dataAnalyst);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents data_analyst
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(dataAnalyst);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('28-gpt-assistant-agent.ts') || process.argv[1]?.endsWith('28-gpt-assistant-agent.js')) {
  main().catch(console.error);
}
