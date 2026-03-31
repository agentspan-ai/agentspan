/**
 * 63c - Run by Name — execute a pre-deployed agent without its definition.
 *
 * Demonstrates the concept of running a deployed agent by workflow name.
 *
 * NOTE: The TypeScript SDK's runtime.run() currently requires an Agent
 * object. To run by name, use the HTTP API directly:
 *   POST /api/agent/run { "name": "agent_doc_assistant", "prompt": "..." }
 *
 * Requirements:
 *   - Conductor server running
 *   - Agent deployed (run 63-deploy.ts first)
 *   - Workers running (run 63b-serve.ts in another terminal)
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 */

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('63c-run-by-name.ts') || process.argv[1]?.endsWith('63c-run-by-name.js')) {
  console.log('Run by Name -- Workflow Name Execution');
  console.log('');
  console.log('The TypeScript SDK currently requires an Agent object for runtime.run().');
  console.log('To run a deployed agent by name, use the HTTP API directly:');
  console.log('');
  console.log('  // Run by name (synchronous)');
  console.log('  POST /api/agent/run');
  console.log('  { "name": "agent_doc_assistant", "prompt": "How do I reset my password?" }');
  console.log('');
  console.log('  // Start by name (fire-and-forget)');
  console.log('  POST /api/agent/start');
  console.log('  { "name": "agent_ops_bot", "prompt": "Check the status of the API gateway" }');
  console.log('');
  console.log('  // Stream by name');
  console.log('  GET /api/agent/stream/{executionId}');
  console.log('');
  console.log('Or use the Python SDK which supports runtime.run("workflow_name", prompt).');
}
