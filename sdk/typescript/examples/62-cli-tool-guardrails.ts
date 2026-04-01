/**
 * 62 - CLI Tool with Guardrails — safe command execution.
 *
 * Demonstrates tool-level guardrails on CLI commands. The agent can run
 * whitelisted commands, but guardrails block dangerous patterns.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, RegexGuardrail } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Guardrails --------------------------------------------------------------

const blockDestructive = new RegexGuardrail({
  patterns: [
    'rm\\s+-rf\\s+/',      // rm -rf /
    'mkfs\\.',              // mkfs.ext4, mkfs.xfs, ...
    '\\bdd\\s+if=',        // dd if=/dev/zero ...
  ],
  mode: 'block',
  name: 'block_destructive',
  message: 'Destructive system commands are not allowed.',
  onFail: 'raise',         // hard stop -- no retry
});

const reviewSudo = new RegexGuardrail({
  patterns: ['\\bsudo\\b'],
  mode: 'block',
  name: 'review_sudo',
  message:
    'Commands requiring sudo are not permitted. ' +
    'Rewrite the command without elevated privileges.',
  onFail: 'retry',         // LLM gets another chance
  maxRetries: 2,
});

// -- Agent -------------------------------------------------------------------

export const opsAgent = new Agent({
  name: 'ops_agent',
  model: llmModel,
  instructions:
    'You are a DevOps assistant. Use the run_command tool to help ' +
    'the user inspect and manage their system. You can list files, ' +
    'check disk usage, read logs, and run git commands.\n\n' +
    'IMPORTANT: Never use sudo or destructive commands like rm -rf.',
  cliConfig: {
    enabled: true,
    allowedCommands: ['ls', 'cat', 'df', 'du', 'git', 'ps', 'uname', 'wc'],
    timeout: 15,
    guardrails: [blockDestructive.toGuardrailDef(), reviewSudo.toGuardrailDef()],
  },
});

// -- Run ---------------------------------------------------------------------

const prompt = 'Show me the disk usage summary and list files in the current directory.';

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(opsAgent);
    // await runtime.serve(opsAgent);
    // Direct run for local development:
    console.log('='.repeat(60));
    console.log('  CLI Tool with Guardrails');
    console.log('  Allowed: ls, cat, df, du, git, ps, uname, wc');
    console.log('  Blocked: rm -rf, sudo, mkfs, dd');
    console.log('='.repeat(60));
    console.log(`\nPrompt: ${prompt}\n`);
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(opsAgent, prompt);
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('62-cli-tool-guardrails.ts') || process.argv[1]?.endsWith('62-cli-tool-guardrails.js')) {
  main().catch(console.error);
}
