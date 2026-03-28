/**
 * Shared utility to classify agent tasks by their role in the workflow.
 * Used by both TaskCard (workflow diagram) and AgentDetailPanel.
 */

export type AgentTaskCategory =
  | "tool" // User-defined @tool
  | "agent_tool" // Sub-agent as tool
  | "guardrail" // Guardrail task
  | "http" // HTTP tool
  | "mcp" // MCP integration
  | "rag" // RAG tool
  | "handoff" // Handoff check / transfer
  | "system" // Internal system task (termination, check_transfer, etc.)
  | "passthrough" // Framework passthrough
  | "unknown";

/**
 * Categorise a single tool entry by its toolType field.
 * This is the shared version of the logic originally in AgentDetailPanel.
 */
export function toolCategory(toolType: string | undefined): AgentTaskCategory {
  const tt = (toolType ?? "").toLowerCase();
  if (tt === "agent_tool" || tt === "agent") return "agent_tool";
  if (tt === "guardrail") return "guardrail";
  if (tt === "http") return "http";
  if (tt === "mcp") return "mcp";
  if (tt === "rag") return "rag";
  return "tool"; // worker, tool, simple, or unknown
}

/**
 * Map AgentTaskCategory back to the narrower ToolCategory used by
 * AgentDetailPanel (which only cares about tool-level classification).
 */
export type ToolCategory = "agent" | "tool" | "guardrail" | "http" | "mcp" | "rag";
export function toolCategoryForPanel(
  t: Record<string, unknown>,
): ToolCategory {
  const cat = toolCategory(t.toolType as string | undefined);
  if (cat === "agent_tool") return "agent";
  if (
    cat === "guardrail" ||
    cat === "http" ||
    cat === "mcp" ||
    cat === "rag"
  )
    return cat;
  return "tool";
}

/**
 * Classify a task name using the agentDef from workflow metadata.
 * Returns the category for rendering-specific icons/colors in the diagram.
 */
export function classifyTask(
  taskName: string,
  agentDef: Record<string, unknown> | undefined | null,
): AgentTaskCategory {
  if (!agentDef) return "unknown";

  // Check tools
  const tools = (agentDef.tools as Array<Record<string, unknown>>) || [];
  for (const tool of tools) {
    if (tool.name === taskName) {
      return toolCategory(tool.toolType as string | undefined);
    }
  }

  // Check system task patterns
  if (taskName.endsWith("_termination") || taskName.endsWith("_stop_when"))
    return "system";
  if (
    taskName.endsWith("_handoff_check") ||
    taskName.includes("_transfer_to_")
  )
    return "handoff";
  if (taskName.endsWith("_check_transfer")) return "handoff";
  if (taskName.endsWith("_gate")) return "system";
  if (taskName.endsWith("_router_fn") || taskName.endsWith("_router"))
    return "system";
  if (taskName.endsWith("_output_guardrail")) return "guardrail";

  // Check if it's a passthrough framework worker
  const metadata = (agentDef.metadata as Record<string, unknown>) || {};
  if (metadata._framework_passthrough) return "passthrough";

  // Check sub-agents
  const agents =
    (agentDef.agents as Array<Record<string, unknown>>) || [];
  for (const sub of agents) {
    if (sub.name === taskName) return "agent_tool";
  }

  return "tool"; // Default: user-defined tool
}
