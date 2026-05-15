import { WorkflowExecution } from "types/Execution";

/**
 * Detect whether the workflow has an ``agentDef`` in its definition metadata.
 * Regular agents (those compiled from an ``Agent(...)`` declaration) always
 * carry an ``agentDef`` — the SDK serialization stamped by the server's
 * compiler. Workflows generated at runtime by ``PLAN_AND_COMPILE`` do NOT
 * carry this metadata.
 */
export function hasAgentDef(execution: WorkflowExecution): boolean {
  const meta = (execution as any)?.workflowDefinition?.metadata;
  return !!meta?.agentDef;
}

/**
 * A compiled-plan workflow is one created at runtime by ``PLAN_AND_COMPILE``
 * (the server-side plan compiler) and has no agent definition behind it. The
 * ``input._systemMetadata.dynamic`` flag alone is too coarse — many regular
 * agent sub-workflows are also "dynamic" in SDK parlance. The discriminator
 * is the absence of ``agentDef`` in workflow metadata.
 */
export function isCompiledPlanWorkflow(execution: WorkflowExecution): boolean {
  const sysMeta = (execution as any)?.input?._systemMetadata;
  if (sysMeta?.dynamic !== true) return false;
  return !hasAgentDef(execution);
}
