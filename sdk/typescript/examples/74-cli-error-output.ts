/**
 * 74 - CLI error output — verify the agent sees stdout/stderr on non-zero exit.
 *
 * Runs an agent that deliberately triggers a failing CLI command and then
 * asks the agent to report what it saw.  The test passes when the agent's
 * final output contains the stderr text produced by the failed command.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL  (e.g. http://localhost:6767/api)
 *   - AGENTSPAN_LLM_MODEL   (e.g. openai/gpt-4o-mini)
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

export const agent = new Agent({
  name: 'cli_error_tester',
  model: llmModel,
  instructions:
    'You have a run_command tool. ' +
    'Run the exact command the user asks you to run, then report ' +
    'the full stdout and stderr you received from the tool result.',
  cliCommands: true,
  cliAllowedCommands: ['ls'],
});

export const prompt =
  'Run: ls /nonexistent_path_that_does_not_exist\n' +
  'Then tell me the exact stderr you got back.';

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    result.printResult();
    const output = result.output ?? '';

    // Verify the agent saw the error output
    const saw = output.includes('No such file or directory') || output.includes('nonexistent');
    if (!saw) {
      console.error(`\nFAIL: agent did not surface CLI error output. Got: ${String(output)}`);
      process.exit(1);
    }
    console.log('\nPASS: agent correctly reported CLI error output');
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.includes('74-cli-error-output')) {
  main().catch(console.error);
}
