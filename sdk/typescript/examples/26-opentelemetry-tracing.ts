/**
 * OpenTelemetry Tracing -- industry-standard observability.
 *
 * Demonstrates OTel instrumentation for agent execution. When
 * opentelemetry-sdk is installed and configured, all agent runs
 * automatically emit spans for:
 *
 * - agent.run (top-level execution)
 * - agent.compile (workflow compilation)
 * - agent.llm_call (each LLM invocation)
 * - agent.tool_call (each tool execution)
 * - agent.handoff (agent transitions)
 *
 * Requirements:
 *   - npm install @opentelemetry/api @opentelemetry/sdk-trace-base
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool, isTracingEnabled } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Check if OTel is available --------------------------------------------

console.log(`OpenTelemetry available: ${isTracingEnabled()}`);

if (isTracingEnabled()) {
  // In a real app you'd configure OTel here:
  // import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
  // import { ConsoleSpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
  // const provider = new NodeTracerProvider();
  // provider.addSpanProcessor(new SimpleSpanProcessor(new ConsoleSpanExporter()));
  // provider.register();
  console.log('OTel is configured -- spans will be emitted');
} else {
  console.log('OTel not configured -- set OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_SERVICE_NAME to enable');
}

// -- Agent with tools ------------------------------------------------------

const lookup = tool(
  async (args: { query: string }) => {
    return `Result for '${args.query}': Python was created by Guido van Rossum in 1991.`;
  },
  {
    name: 'lookup',
    description: 'Look up information.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The query to look up' },
      },
      required: ['query'],
    },
  },
);

export const agent = new Agent({
  name: 'traced_agent',
  model: llmModel,
  tools: [lookup],
  instructions: 'You are a helpful assistant. Use the lookup tool when needed.',
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('26-opentelemetry-tracing.ts') || process.argv[1]?.endsWith('26-opentelemetry-tracing.js')) {
  const runtime = new AgentRuntime();
  try {
    // The runtime automatically creates spans if OTel is configured.
    const result = await runtime.run(agent, 'Who created Python?');
    result.printResult();

    if (result.tokenUsage) {
      console.log(`Tokens: ${result.tokenUsage.totalTokens}`);
    }
  } finally {
    await runtime.shutdown();
  }
}
