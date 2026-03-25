/**
 * Framework auto-detection via duck-typing.
 *
 * Detection order (priority):
 * 1. agent instanceof Agent → null (native agentspan)
 * 2. .invoke() + (.getGraph() OR .nodes Map) → 'langgraph'
 * 3. .invoke() + .lc_namespace → 'langchain'
 * 4. .name + .instructions + .model + .tools + .handoffs → 'openai'
 * 5. .model + .instruction + ADK-specific props → 'google_adk'
 * 6. Otherwise → null
 *
 * All detection uses duck-typing — no imports of framework packages.
 */

import { Agent } from '../agent.js';
import type { FrameworkId } from '../types.js';

// ── Private detection helpers ───────────────────────────

/**
 * LangGraph.js: CompiledStateGraph has .invoke() and either .getGraph() or .nodes (Map).
 */
function hasInvokeAndGetGraph(obj: any): boolean {
  return (
    typeof obj?.invoke === 'function' &&
    (typeof obj?.getGraph === 'function' || obj?.nodes instanceof Map)
  );
}

/**
 * LangChain.js: AgentExecutor/Runnable has .invoke() and .lc_namespace.
 */
function hasInvokeAndLcNamespace(obj: any): boolean {
  return (
    typeof obj?.invoke === 'function' &&
    Array.isArray(obj?.lc_namespace)
  );
}

/**
 * OpenAI Agents SDK: Agent has .name, .instructions, .model, .tools, .handoffs,
 * .inputGuardrails, .outputGuardrails, .toJSON(), .asTool().
 * Note: run() is a standalone function, NOT a method on Agent.
 */
function hasOpenAIAgentMarkers(obj: any): boolean {
  if (typeof obj !== 'object' || obj === null) return false;
  const hasName = typeof obj.name === 'string';
  const hasInstructions = typeof obj.instructions === 'string' || typeof obj.instructions === 'function';
  const hasModel = typeof obj.model === 'string';
  const hasTools = Array.isArray(obj.tools);
  // OpenAI-specific: handoffs array, inputGuardrails, outputGuardrails, asTool method
  const hasOpenAIProps =
    Array.isArray(obj.handoffs) ||
    Array.isArray(obj.inputGuardrails) ||
    Array.isArray(obj.outputGuardrails) ||
    typeof obj.asTool === 'function' ||
    typeof obj.toolUseBehavior === 'string';
  return hasName && hasInstructions && hasModel && hasTools && hasOpenAIProps;
}

/**
 * Google ADK: LlmAgent has .model, .instruction, and ADK-specific properties
 * like .generateContentConfig, .outputKey, .subAgents, .beforeModelCallback.
 *
 * Note: The TS ADK LlmAgent does NOT have a .run() method (unlike Python's Agent).
 * Execution uses InMemoryRunner + InMemorySessionService.
 */
function hasADKMarkers(obj: any): boolean {
  if (typeof obj !== 'object' || obj === null) return false;
  const hasModel = typeof obj.model === 'string';
  const hasInstruction =
    typeof obj.instruction === 'string' || typeof obj.instruction === 'function';
  // ADK-specific properties that distinguish it from other frameworks
  const hasADKProps =
    'generateContentConfig' in obj ||
    'outputKey' in obj ||
    'beforeModelCallback' in obj ||
    'afterModelCallback' in obj ||
    'disallowTransferToParent' in obj ||
    'includeContents' in obj;
  // ADK multi-agent types (SequentialAgent, ParallelAgent, LoopAgent)
  // have .subAgents but no .model — they're orchestration-only
  const hasSubAgents = Array.isArray(obj.subAgents);
  if (hasSubAgents && !hasModel) return true;
  return hasModel && (hasInstruction || hasADKProps);
}

// ── Public API ──────────────────────────────────────────

/**
 * Detect which framework (if any) the given agent object belongs to.
 * Returns null for native agentspan Agent instances or unknown objects.
 */
export function detectFramework(agent: unknown): FrameworkId | null {
  // 1. Native agentspan Agent — not a framework
  if (agent instanceof Agent) return null;

  // 2. LangGraph.js: CompiledStateGraph has .invoke() + .getGraph() or .nodes
  if (hasInvokeAndGetGraph(agent)) return 'langgraph';

  // 3. LangChain.js: AgentExecutor/Runnable has .invoke() + .lc_namespace
  if (hasInvokeAndLcNamespace(agent)) return 'langchain';

  // 4. OpenAI Agents: has .name + .instructions + .model + .tools + .handoffs
  if (hasOpenAIAgentMarkers(agent)) return 'openai';

  // 5. Google ADK: LlmAgent with .model + .instruction + ADK-specific properties
  if (hasADKMarkers(agent)) return 'google_adk';

  // 6. Unknown — not a recognized framework
  return null;
}
