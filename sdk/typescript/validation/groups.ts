/**
 * Example group definitions for the validation framework.
 *
 * Each group maps to a list of example names (relative to examples/).
 * Names use the file stem without .ts extension.
 */

export const GROUPS: Record<string, string[]> = {
  SMOKE_TEST: [
    '01-basic-agent',
    '02-tools',
    '03-structured-output',
    '05-handoffs',
    '06-sequential-pipeline',
    '07-parallel-agents',
    '08-router-agent',
    '11-streaming',
  ],

  VERCEL_AI: [
    'vercel-ai/01-passthrough',
    'vercel-ai/02-tools-compat',
    'vercel-ai/03-streaming',
    'vercel-ai/04-structured-output',
    'vercel-ai/05-multi-step',
    'vercel-ai/06-middleware',
    'vercel-ai/07-stop-conditions',
    'vercel-ai/08-agent-handoff',
    'vercel-ai/09-credentials',
    'vercel-ai/10-hitl',
  ],

  LANGGRAPH: [
    'langgraph/01-hello-world',
    'langgraph/02-react-with-tools',
    'langgraph/03-memory',
    'langgraph/04-simple-stategraph',
    'langgraph/05-tool-node',
    'langgraph/06-conditional-routing',
    'langgraph/07-system-prompt',
    'langgraph/08-structured-output',
    'langgraph/09-math-agent',
    'langgraph/10-research-agent',
  ],

  LANGCHAIN: [
    'langchain/01-hello-world',
    'langchain/02-react-with-tools',
    'langchain/03-custom-tools',
    'langchain/04-structured-output',
    'langchain/05-prompt-templates',
    'langchain/06-chat-history',
    'langchain/07-memory-agent',
    'langchain/08-multi-tool-agent',
    'langchain/09-math-calculator',
    'langchain/10-web-search-agent',
  ],

  OPENAI: [
    'openai/01-basic-agent',
    'openai/02-function-tools',
    'openai/03-structured-output',
    'openai/04-handoffs',
    'openai/05-guardrails',
    'openai/06-model-settings',
    'openai/07-streaming',
    'openai/08-agent-as-tool',
    'openai/09-dynamic-instructions',
    'openai/10-multi-model',
  ],

  ADK: [
    'adk/00-hello-world',
    'adk/01-basic-agent',
    'adk/02-function-tools',
    'adk/03-structured-output',
    'adk/04-sub-agents',
    'adk/05-generation-config',
    'adk/06-streaming',
    'adk/07-output-key-state',
    'adk/08-instruction-templating',
    'adk/09-multi-tool-agent',
  ],
};

/** Framework passthrough groups — examples that bypass agentspan LLM calls. */
export const FRAMEWORK_GROUPS = new Set([
  'VERCEL_AI',
  'LANGGRAPH',
  'LANGCHAIN',
  'OPENAI',
  'ADK',
]);

/**
 * Check whether an example name belongs to a framework passthrough group.
 */
export function isFrameworkPassthrough(exampleName: string): boolean {
  const prefix = exampleName.split('/')[0];
  return ['vercel-ai', 'langgraph', 'langchain', 'openai', 'adk'].includes(prefix);
}
