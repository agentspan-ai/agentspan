/**
 * 63c - Direct Run — kept alongside the Python "run by name" variant for parity.
 *
 * The current TypeScript runtime accepts agent objects here, so this example
 * uses the imported agent definition directly. Deploy/serve remains the
 * commented production pattern below.
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { docAssistant } from './63-deploy.js';
import { AgentRuntime } from '../src/index.js';

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('63c-run-by-name.ts') || process.argv[1]?.endsWith('63c-run-by-name.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(docAssistant, 'How do I reset my password?');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(docAssistant);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents doc_assistant
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(docAssistant);
  } finally {
    await runtime.shutdown();
  }
}
