import {
  AgentEvent,
  AgentRunData,
  AgentStatus,
  AgentStrategy,
  AgentTurn,
  EventType,
  ExecutionMetrics,
  FinishReason,
  TokenUsage,
} from "./types";

/** Map a model name to its provider icon path in /integrations-icons/ */
export function getModelIconPath(model: string | undefined): string | null {
  if (!model) return null;
  const m = model.toLowerCase();
  if (m.includes("claude"))                                          return "/integrations-icons/anthropic.svg";
  if (m.includes("openai") || m.includes("gpt") || m.includes("o1") || m.includes("o3")) return "/integrations-icons/openAI.svg";
  if (m.includes("gemini"))                                          return "/integrations-icons/googlegemini.svg";
  if (m.includes("mistral"))                                         return "/integrations-icons/mistralai.svg";
  if (m.includes("bedrock"))                                         return "/integrations-icons/bedrock.svg";
  if (m.includes("azure"))                                           return "/integrations-icons/azureOpenAI.svg";
  if (m.includes("cohere"))                                          return "/integrations-icons/cohere.svg";
  if (m.includes("ollama") || m.includes("llama"))                   return "/integrations-icons/ollama.svg";
  if (m.includes("vertex"))                                          return "/integrations-icons/vertexAI.svg";
  if (m.includes("perplexity"))                                      return "/integrations-icons/perplexity.svg";
  if (m.includes("hugging") || m.startsWith("hf-"))                 return "/integrations-icons/huggingFace.svg";
  return null;
}
import {
  ExecutionTask,
  WorkflowExecution,
  WorkflowExecutionStatus,
} from "types/Execution";

const TURN_END_EVENTS = new Set([
  EventType.MESSAGE,
  EventType.DONE,
  EventType.ERROR,
  EventType.HANDOFF,
]);

/** Build a CONTEXT_CONDENSED event from task inputData if _condensation metadata is present */
function maybeCondensationEvent(task: ExecutionTask): AgentEvent | null {
  const info = (task.inputData as Record<string, unknown> | undefined)?._condensation;
  if (!info || typeof info !== "object") return null;
  const c = info as Record<string, unknown>;
  const condensationInfo = {
    trigger: String(c.trigger ?? ""),
    messagesBefore: Number(c.messagesBefore ?? 0),
    messagesAfter: Number(c.messagesAfter ?? 0),
    exchangesCondensed: Number(c.exchangesCondensed ?? 0),
  };
  return {
    id: `${task.taskId}-condensed`,
    type: EventType.CONTEXT_CONDENSED,
    timestamp: task.startTime ?? 0,
    summary: `Context condensed: ${condensationInfo.messagesBefore} → ${condensationInfo.messagesAfter} messages`,
    condensationInfo,
  };
}

/** Split a flat event stream into turns at MESSAGE/DONE/ERROR/HANDOFF boundaries */
export function groupEventsIntoTurns(events: AgentEvent[]): AgentTurn[] {
  if (events.length === 0) return [];

  const turns: AgentTurn[] = [];
  let currentEvents: AgentEvent[] = [];
  let turnNumber = 1;

  for (const event of events) {
    currentEvents.push(event);
    if (TURN_END_EVENTS.has(event.type)) {
      turns.push(buildTurn(turnNumber, currentEvents));
      turnNumber++;
      currentEvents = [];
    }
  }

  // Any remaining events form a partial/incomplete turn
  if (currentEvents.length > 0) {
    turns.push(buildTurn(turnNumber, currentEvents, true));
  }

  return turns;
}

function buildTurn(
  turnNumber: number,
  events: AgentEvent[],
  incomplete = false,
): AgentTurn {
  const hasError = events.some(
    (e) => e.type === EventType.ERROR || e.success === false,
  );
  const status = incomplete
    ? AgentStatus.RUNNING
    : hasError
      ? AgentStatus.FAILED
      : AgentStatus.COMPLETED;

  const durationMs = events.reduce((sum, e) => sum + (e.durationMs ?? 0), 0);
  const tokens = sumTokens(
    events
      .map((e) => e.tokens)
      .filter((t): t is TokenUsage => t != null),
  );

  return {
    turnNumber,
    events,
    status,
    durationMs,
    tokens,
    subAgents: [],
  };
}

function sumTokens(tokensList: TokenUsage[]): TokenUsage {
  return tokensList.reduce(
    (acc, t) => ({
      promptTokens: acc.promptTokens + t.promptTokens,
      completionTokens: acc.completionTokens + t.completionTokens,
      totalTokens: acc.totalTokens + t.totalTokens,
    }),
    { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
  );
}

/** Compute aggregate metrics recursively across all agents */
export function computeMetrics(run: AgentRunData): ExecutionMetrics {
  const allRuns = collectAllRuns(run);
  const totalTokens = sumTokens(allRuns.map((r) => r.totalTokens));
  const totalTurns = allRuns.reduce((sum, r) => sum + r.turns.length, 0);
  const totalDurationMs = run.totalDurationMs; // Use root agent's wall-clock time
  const failedAgents = allRuns.filter(
    (r) => r.status === AgentStatus.FAILED,
  ).length;
  const waitingAgents = allRuns.filter(
    (r) => r.status === AgentStatus.WAITING,
  ).length;

  return {
    totalAgents: allRuns.length,
    totalTurns,
    totalTokens,
    totalDurationMs,
    failedAgents,
    waitingAgents,
  };
}

function collectAllRuns(run: AgentRunData): AgentRunData[] {
  const result: AgentRunData[] = [run];
  for (const turn of run.turns) {
    for (const sub of turn.subAgents) {
      result.push(...collectAllRuns(sub));
    }
  }
  return result;
}

/** Format duration in ms to a human-readable string */
export function formatDuration(ms: number): string {
  if (ms <= 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Format token count for display */
export function formatTokens(count: number): string {
  if (count < 1000) return String(count);
  return `${(count / 1000).toFixed(1)}k`;
}

/** Get display label for agent strategy */
export function getStrategyLabel(
  strategy: AgentStrategy | undefined,
  count: number,
): string {
  if (!strategy) return `${count} sub-agent${count !== 1 ? "s" : ""}`;
  switch (strategy) {
    case AgentStrategy.HANDOFF:
      return `${count} handoff`;
    case AgentStrategy.PARALLEL:
      return `${count} parallel`;
    case AgentStrategy.SEQUENTIAL:
      return `${count} sequential`;
    case AgentStrategy.ROUTER:
      return `${count} routed`;
    default:
      return `${count} sub-agent${count !== 1 ? "s" : ""}`;
  }
}

// ─── Workflow Execution Transformers ────────────────────────────────────────

const ZERO_TOKENS: TokenUsage = {
  promptTokens: 0,
  completionTokens: 0,
  totalTokens: 0,
};

function toMs(value: string | number | undefined | null): number {
  if (value == null || value === 0 || value === "") return 0;
  return typeof value === "number" ? value : parseInt(value, 10) || 0;
}

/** Maps task status to a tri-state success flag: true=completed, false=failed, undefined=in-progress */
function taskSuccess(status: string): boolean | undefined {
  if (status === "COMPLETED") return true;
  if (status === "FAILED") return false;
  return undefined; // IN_PROGRESS → caller shows spinner
}

function mapTaskStatus(status: string): AgentStatus {
  switch (status) {
    case "COMPLETED":
      return AgentStatus.COMPLETED;
    case "FAILED":
      return AgentStatus.FAILED;
    case "IN_PROGRESS":
      return AgentStatus.RUNNING;
    default:
      return AgentStatus.RUNNING;
  }
}

function mapWorkflowStatus(status: WorkflowExecutionStatus): AgentStatus {
  switch (status) {
    case WorkflowExecutionStatus.COMPLETED:
      return AgentStatus.COMPLETED;
    case WorkflowExecutionStatus.FAILED:
    case WorkflowExecutionStatus.TIMED_OUT:
    case WorkflowExecutionStatus.TERMINATED:
      return AgentStatus.FAILED;
    case WorkflowExecutionStatus.PAUSED:
      return AgentStatus.WAITING;
    default:
      return AgentStatus.RUNNING;
  }
}

/** Extract trailing iteration number from task name (e.g. "foo__3" → 3) */
function getIterationNum(name: string): number | null {
  const m = name.match(/__(\d+)$/);
  return m ? parseInt(m[1], 10) : null;
}

/** Extract agent name from sub-workflow task reference name.
 * HANDOFF pattern:  "workflow_handoff_0_planner_t1__1" → "planner_t1"
 * SWARM pattern:    "workflow_agent_1_engineering_lead__2" → "engineering_lead"
 * PARALLEL pattern: "coordinator_parallel_0_researcher" → "researcher"
 * Simple pattern:   "researcher__1" → "researcher"
 */
function extractAgentName(name: string): string | null {
  let m = name.match(/_handoff_\d+_(.+?)__\d+$/);
  if (m) return m[1];
  m = name.match(/_agent_\d+_(.+?)__\d+$/);
  if (m) return m[1];
  // Parallel fork: "coordinator_parallel_0_researcher" → "researcher"
  m = name.match(/_parallel_\d+_(.+?)(?:__\d+)?$/);
  if (m) return m[1];
  // Simple: strip __N iteration suffix → "researcher__1" → "researcher"
  m = name.match(/^(.+?)__\d+$/);
  return m ? m[1] : null;
}

/** All SUB_WORKFLOW tasks in agent context are sub-agents */
function isAgentSubWorkflow(task: ExecutionTask): boolean {
  return task.taskType === "SUB_WORKFLOW";
}

// ─── Sequential chain detection ──────────────────────────────────────────────

/** Returns the step index (N) if ref matches {chain}_step_{N}_{agent} SUB_WORKFLOW pattern */
function getChainStepNum(ref: string): number | null {
  const m = ref.match(/_step_(\d+)_/);
  return m ? parseInt(m[1], 10) : null;
}

/** Extract agent name from a chain step ref: {chain_name}_step_{N}_{agent_name} */
function getChainAgentName(ref: string): string | null {
  const m = ref.match(/_step_\d+_(.+)$/);
  return m ? m[1] : null;
}

/**
 * A chain workflow has SUB_WORKFLOW tasks with _step_N_ in their ref names,
 * no DO_WHILE, and no __N iteration suffix on those step tasks.
 */
function isChainWorkflow(tasks: ExecutionTask[]): boolean {
  const hasDoWhile = tasks.some(t => t.taskType === "DO_WHILE");
  if (hasDoWhile) return false;
  return tasks.some(
    t => t.taskType === "SUB_WORKFLOW" && /_step_\d+_/.test(t.referenceTaskName),
  );
}

/**
 * Transform a sequential chain workflow into AgentRunData.
 * Each step becomes a "turn" whose only sub-agent is the step agent.
 * Gate INLINE tasks become gate events within the turn.
 */
function transformChainWorkflowToAgentRun(execution: WorkflowExecution): AgentRunData {
  const tasks: ExecutionTask[] = execution.tasks ?? [];
  const startMs = toMs(execution.startTime as any);
  const endMs   = toMs(execution.endTime as any);
  const isRunning = execution.status === WorkflowExecutionStatus.RUNNING;
  const totalDurationMs =
    endMs > 0 ? endMs - startMs
    : isRunning ? Date.now() - startMs
    : execution.executionTime ?? 0;

  // Collect step SUB_WORKFLOW tasks, indexed by step N
  const stepMap = new Map<number, ExecutionTask>();
  // Collect gate INLINE tasks, indexed by step N (gate_N evaluates output of step N)
  const gateMap = new Map<number, ExecutionTask>();

  for (const task of tasks) {
    const stepN = getChainStepNum(task.referenceTaskName);
    if (stepN !== null && task.taskType === "SUB_WORKFLOW") {
      stepMap.set(stepN, task);
    }
    // Gate INLINE: ref ends with _gate_{N} (not _gate_switch_{N})
    const gateM = task.referenceTaskName.match(/_gate_(\d+)$/);
    if (gateM && task.taskType === "INLINE") {
      gateMap.set(parseInt(gateM[1], 10), task);
    }
  }

  const sortedSteps = Array.from(stepMap.entries()).sort(([a], [b]) => a - b);

  // Grab the per-step agent configs from the definition metadata for gate label info
  const agentsDef = ((execution.workflowDefinition?.metadata?.agentDef as any)?.agents ?? []) as Array<Record<string, unknown>>;

  const turns: AgentTurn[] = sortedSteps.map(([stepN, task], idx): AgentTurn => {
    const agentName = getChainAgentName(task.referenceTaskName) ?? task.referenceTaskName;
    const subWorkflowId = task.outputData?.subWorkflowId as string | undefined;
    const result = task.outputData?.result;
    const resultStr = typeof result === "string" && result.length > 0 ? result : undefined;
    const durationMs = task.endTime && task.startTime ? task.endTime - task.startTime : 0;

    const subAgent: AgentRunData = {
      id: subWorkflowId ?? task.taskId ?? `chain-step-${stepN}`,
      agentName,
      subWorkflowId,
      turns: resultStr ? [{
        turnNumber: 1,
        status: mapTaskStatus(task.status),
        durationMs,
        tokens: ZERO_TOKENS,
        subAgents: [],
        events: [{
          id: `${task.taskId}-msg`,
          type: EventType.MESSAGE,
          timestamp: task.startTime ?? 0,
          summary: resultStr.slice(0, 120) + (resultStr.length > 120 ? "..." : ""),
          detail: resultStr,
          durationMs,
        }],
      }] : [],
      status: mapTaskStatus(task.status),
      totalTokens: ZERO_TOKENS,
      totalDurationMs: durationMs,
      strategy: AgentStrategy.SINGLE,
      output: resultStr,
      failureReason: task.reasonForIncompletion ?? undefined,
    };

    const events: AgentEvent[] = [];

    // Gate event: evaluates the output of this step before proceeding to next
    const gateTask = gateMap.get(stepN);
    if (gateTask) {
      const gateResult = gateTask.outputData?.result as { decision?: string } | undefined;
      const decision = gateResult?.decision ?? "continue";
      const isStop = decision === "stop";
      const gateDuration = gateTask.endTime && gateTask.startTime ? gateTask.endTime - gateTask.startTime : 0;
      const stepAgentDef = agentsDef[stepN];
      const gateCfg = stepAgentDef?.gate as Record<string, unknown> | undefined;
      const sentinel = gateCfg?.text ? `"${gateCfg.text}"` : "";
      const gateLabel = isStop
        ? `Gate${sentinel ? ` ${sentinel}` : ""} matched — chain stopped here`
        : `Gate${sentinel ? ` ${sentinel}` : ""} not matched — chain continues`;

      events.push({
        id: `${gateTask.taskId}-gate`,
        type: isStop ? EventType.GUARDRAIL_FAIL : EventType.GUARDRAIL_PASS,
        timestamp: gateTask.startTime ?? 0,
        summary: gateLabel,
        toolName: "gate",
        success: !isStop,
        durationMs: gateDuration,
        detail: { decision, ...(gateCfg ? { gate: gateCfg } : {}) },
      });
    }

    const timestamps = [task.startTime, task.endTime, gateTask?.startTime, gateTask?.endTime]
      .filter((v): v is number => v != null && v > 0);

    return {
      turnNumber: idx + 1,
      events,
      status: mapTaskStatus(task.status),
      durationMs: timestamps.length
        ? Math.max(...timestamps) - Math.min(...timestamps)
        : durationMs,
      tokens: ZERO_TOKENS,
      subAgents: [subAgent],
      strategy: AgentStrategy.SEQUENTIAL,
    };
  });

  const agentDef = execution.workflowDefinition?.metadata?.agentDef as Record<string, unknown> | undefined;
  const finishReason =
    execution.status === WorkflowExecutionStatus.COMPLETED ? FinishReason.STOP
    : execution.status === WorkflowExecutionStatus.FAILED ||
      execution.status === WorkflowExecutionStatus.TIMED_OUT ||
      execution.status === WorkflowExecutionStatus.TERMINATED ? FinishReason.ERROR
    : undefined;
  const execInput = execution.input as any;
  const agentInput: string | undefined =
    typeof execInput === "string" ? execInput || undefined
    : typeof execInput === "object" && execInput !== null
      ? (execInput.prompt || execInput.conversation || execInput.message || undefined)
    : undefined;

  // Root output: last step's result, or workflow output field
  const lastStep = sortedSteps[sortedSteps.length - 1];
  let chainOutput: string | undefined;
  if (lastStep) {
    const r = lastStep[1].outputData?.result;
    if (typeof r === "string" && r.length > 0) chainOutput = r;
  }
  if (!chainOutput && execution.output) {
    const wfOut = execution.output;
    const candidate = wfOut.result ?? wfOut.output ?? wfOut.message;
    if (typeof candidate === "string" && (candidate as string).length > 0) chainOutput = candidate as string;
  }

  const chainModel = (agentDef?.model as string | undefined) ??
    tasks.find(t => t.taskType === "LLM_CHAT_COMPLETE")?.inputData?.model as string | undefined;

  return {
    id: execution.workflowId,
    agentName: (execution as any).workflowName ?? execution.workflowType ?? "agent",
    model: chainModel,
    turns,
    status: mapWorkflowStatus(execution.status),
    agentDef,
    totalTokens: ZERO_TOKENS,
    totalDurationMs,
    finishReason,
    strategy: AgentStrategy.SEQUENTIAL,
    input: agentInput,
    output: chainOutput,
  };
}

/**
 * Transform a top-level WorkflowExecution into AgentRunData for the Agent Execution tab.
 * Groups tasks by DO_WHILE iteration; each iteration becomes one turn.
 * Each handoff SUB_WORKFLOW task within an iteration becomes a sub-agent.
 */
export function transformWorkflowExecutionToAgentRun(
  execution: WorkflowExecution,
): AgentRunData {
  const tasks: ExecutionTask[] = execution.tasks ?? [];

  // Sequential chain: delegate to dedicated transformer
  if (isChainWorkflow(tasks)) {
    return transformChainWorkflowToAgentRun(execution);
  }

  const startMs = toMs(execution.startTime as any);
  const endMs = toMs(execution.endTime as any);
  const isRunning = execution.status === WorkflowExecutionStatus.RUNNING;
  const totalDurationMs =
    endMs > 0
      ? endMs - startMs
      : isRunning
        ? Date.now() - startMs
        : execution.executionTime ?? 0;

  // Infrastructure task types to skip everywhere
  const ITER_INFRA = new Set([
    "SET_VARIABLE", "SWITCH", "INLINE", "DO_WHILE",
    "FORK", "FORK_JOIN", "FORK_JOIN_DYNAMIC", "JOIN",
  ]);

  // Debug: log all task types and reference names for diagnosis
  if (tasks.length > 0) {
    console.debug("[AgentExecution] tasks", tasks.map(t => ({
      ref: t.referenceTaskName, type: t.taskType, status: t.status,
    })));
  }

  // Build set of guardrail function names from agentDef for robust detection
  const agentDefMeta = (execution as any).workflowDefinition?.metadata?.agentDef as Record<string, unknown> | undefined;
  const guardrailFnNames = new Set<string>();
  for (const gList of [
    (agentDefMeta?.input_guardrails as Array<Record<string, unknown>> | undefined) ?? [],
    (agentDefMeta?.output_guardrails as Array<Record<string, unknown>> | undefined) ?? [],
    (agentDefMeta?.guardrails as Array<Record<string, unknown>> | undefined) ?? [],
  ]) {
    for (const g of gList) {
      const fn = (g.guardrail_function ?? g) as Record<string, unknown>;
      const name = (fn._worker_ref ?? fn.name) as string | undefined;
      if (name) guardrailFnNames.add(name.toLowerCase());
    }
  }

  // Group tasks by DO_WHILE iteration number; collect root-level tasks separately
  const iterMap = new Map<number, ExecutionTask[]>();
  const rootActiveTasks: ExecutionTask[] = [];
  for (const task of tasks) {
    const iter = getIterationNum(task.referenceTaskName);
    if (iter !== null) {
      if (!iterMap.has(iter)) iterMap.set(iter, []);
      iterMap.get(iter)!.push(task);
    } else if (!ITER_INFRA.has(task.taskType)) {
      // Root-level non-infrastructure: final LLM tasks, or entire simple agents
      rootActiveTasks.push(task);
    }
  }

  const sortedIters = Array.from(iterMap.entries()).sort(([a], [b]) => a - b);

  // The root agent's own name — used to detect SWARM self-calls
  const rootAgentName: string =
    (execution as any).workflowName ?? execution.workflowType ?? "";

  const turns: AgentTurn[] = sortedIters
    .map(([, iterTasks], idx) => {
      const agentTasks = iterTasks.filter(isAgentSubWorkflow);

      // LLM tasks directly in this iteration (tool-calling agent pattern)
      const iterLlmTasks = iterTasks.filter(
        (t) => t.taskType === "LLM_CHAT_COMPLETE",
      );

      // Tool worker tasks — any non-infra, non-subworkflow, non-LLM task
      const toolWorkerTasks = iterTasks.filter(
        (t) =>
          !ITER_INFRA.has(t.taskType) &&
          t.taskType !== "SUB_WORKFLOW" &&
          t.taskType !== "LLM_CHAT_COMPLETE",
      );

      // SWARM self-calls: iterations where the agent IS the root agent itself
      // (e.g. CEO calling itself to make a routing decision)
      const selfCalls = agentTasks.filter(
        (t) => extractAgentName(t.referenceTaskName) === rootAgentName,
      );
      // Real sub-agent calls: exclude router tasks (orchestration machinery)
      // and self-calls — both are handled separately above/below.
      const subAgentTasks = agentTasks.filter(
        (t) =>
          extractAgentName(t.referenceTaskName) !== rootAgentName &&
          !t.referenceTaskName.includes("_router_"),
      );

      const events: AgentEvent[] = [];

      // Self-calls → HANDOFF events (the agent deciding where to route)
      for (const task of selfCalls) {
        const transferTo = task.outputData?.transfer_to as string | undefined;
        const isTransfer = task.outputData?.is_transfer as boolean | undefined;
        const durationMs =
          task.endTime && task.startTime ? task.endTime - task.startTime : 0;

        if (isTransfer && transferTo) {
          events.push({
            id: `${task.taskId}-handoff`,
            type: EventType.HANDOFF,
            timestamp: task.endTime ?? 0,
            summary: `→ ${transferTo}`,
            targetAgent: transferTo,
            detail: { transfer_to: transferTo, agent: rootAgentName },
            durationMs,
          });
        } else {
          // Self-call with no transfer → agent responded directly (final response)
          events.push({
            id: `${task.taskId}-msg`,
            type: EventType.MESSAGE,
            timestamp: task.endTime ?? 0,
            summary: "Agent responded",
            durationMs,
          });
        }
      }

      // Also handle HANDOFF-strategy router tasks (team_t1 style)
      if (selfCalls.length === 0) {
        const routerTask = iterTasks.find((t) =>
          t.referenceTaskName.includes("_router_"),
        );
        const routingDecision = routerTask?.outputData?.result as
          | string
          | undefined;
        if (routingDecision && subAgentTasks.length > 0) {
          events.push({
            id: `iter-${idx}-route`,
            type: EventType.HANDOFF,
            timestamp: routerTask?.endTime ?? 0,
            summary: `→ ${routingDecision}`,
            targetAgent: routingDecision,
            detail: { routing_decision: routingDecision },
          });
        }
      }

      // Build sub-agents from real sub-agent calls
      const subAgents: AgentRunData[] = subAgentTasks.map((task): AgentRunData => {
        // Prefer subWorkflowName from inputData (Conductor populates this with the workflow name).
        // For "agent-as-tool" tasks (ref name = call_{toolCallId}__N), workflowTask.name holds
        // the actual agent/sub-workflow name (e.g. "deep_analyst_68").
        // Otherwise fall back to regex extraction then raw reference name.
        const isAgentAsTool = /^call_[A-Za-z0-9]+__\d+$/.test(task.referenceTaskName);
        const agentName =
          (task.inputData?.subWorkflowName as string | undefined) ??
          (isAgentAsTool ? task.workflowTask?.name : null) ??
          extractAgentName(task.referenceTaskName) ??
          task.referenceTaskName;
        const subWorkflowId = task.outputData?.subWorkflowId as
          | string
          | undefined;
        const result = task.outputData?.result;
        const resultStr =
          typeof result === "string" && result.length > 0 ? result : undefined;
        // Agent-as-tool: input is nested under workflowInput.prompt
        const agentInput = isAgentAsTool
          ? ((task.inputData as any)?.workflowInput?.prompt as string | undefined)
          : undefined;
        const durationMs =
          task.endTime && task.startTime
            ? task.endTime - task.startTime
            : 0;

        const subTurns: AgentTurn[] = resultStr
          ? [
              {
                turnNumber: 1,
                status: mapTaskStatus(task.status),
                durationMs,
                tokens: ZERO_TOKENS,
                subAgents: [],
                events: [
                  {
                    id: `${task.taskId}-msg`,
                    type: EventType.MESSAGE,
                    timestamp: task.startTime ?? 0,
                    summary:
                      resultStr.slice(0, 120) +
                      (resultStr.length > 120 ? "..." : ""),
                    detail: resultStr,
                    durationMs,
                  },
                  {
                    id: `${task.taskId}-done`,
                    type: EventType.DONE,
                    timestamp: task.endTime ?? 0,
                    summary: "Agent completed",
                    success: task.status === "COMPLETED",
                  },
                ],
              },
            ]
          : [];

        return {
          id: subWorkflowId ?? task.taskId ?? `sub-${agentName}`,
          agentName,
          subWorkflowId,
          turns: subTurns,
          status: mapTaskStatus(task.status),
          totalTokens: ZERO_TOKENS,
          totalDurationMs: durationMs,
          strategy: AgentStrategy.SINGLE,
          input: agentInput,
          output: resultStr,
          failureReason: task.reasonForIncompletion ?? undefined,
        };
      });

      // LLM events: one block per LLM call showing input + output
      for (const llmTask of iterLlmTasks) {
        const condensed = maybeCondensationEvent(llmTask);
        if (condensed) events.push(condensed);

        const model = llmTask.inputData?.model as string | undefined;
        const finishReason =
          ((llmTask.outputData?.finishReason as string) ?? "stop").toLowerCase();
        const result = llmTask.outputData?.result;
        const promptTokens = (llmTask.outputData?.promptTokens as number) || 0;
        const completionTokens =
          (llmTask.outputData?.completionTokens as number) || 0;
        const messages =
          (llmTask.inputData?.messages as Array<{ role: string; message: string }>) ?? [];
        const tools = (llmTask.inputData?.tools as unknown[]) ?? [];
        const llmDuration =
          llmTask.endTime && llmTask.startTime
            ? llmTask.endTime - llmTask.startTime
            : 0;
        const isStop = finishReason === "stop";

        // Show instructions (system prompt) + last user message only
        const sysMsg = messages.find((m) => m.role === "system");
        const lastMsg = [...messages].reverse().find((m) => m.role !== "system");

        // ONE block: LLM call — instructions + last message + output
        events.push({
          id: `${llmTask.taskId}-llm`,
          type: EventType.THINKING,
          timestamp: llmTask.startTime ?? 0,
          toolName: model,
          summary: `${model ?? "LLM"} · ${messages.length} messages${tools.length ? ` · ${tools.length} tools` : ""}`,
          detail: {
            input: {
              ...(sysMsg ? { instructions: sysMsg.message } : {}),
              ...(lastMsg ? { message: lastMsg.message } : {}),
            },
            output: llmTask.outputData,
          },
          result: isStop && typeof result === "string" ? result : result,
          tokens: { promptTokens, completionTokens, totalTokens: promptTokens + completionTokens },
          durationMs: llmDuration,
          success: taskSuccess(llmTask.status),
          condensationInfo: condensed?.condensationInfo,
        });

        // If the LLM returned a text response, show it as "Output" (DONE event)
        if (isStop && typeof result === "string" && result.length > 0) {
          events.push({
            id: `${llmTask.taskId}-output`,
            type: EventType.DONE,
            timestamp: llmTask.endTime ?? 0,
            summary: result.slice(0, 120) + (result.length > 120 ? "..." : ""),
            detail: result,
            success: true,
            tokens: { promptTokens, completionTokens, totalTokens: promptTokens + completionTokens },
            durationMs: llmDuration,
          });
        }
      }

      // Tool worker events — ONE combined block per call showing input + output
      // Track whether a HANDOFF was already emitted this turn to avoid duplicates.
      let handoffEmittedThisTurn = false;

      for (const toolTask of toolWorkerTasks) {
        const idData = (toolTask.inputData ?? {}) as Record<string, unknown>;
        const od = (toolTask.outputData ?? {}) as Record<string, unknown>;
        const toolName = toolTask.taskType;
        const failed = toolTask.status === "FAILED";
        const toolDuration =
          toolTask.endTime && toolTask.startTime
            ? toolTask.endTime - toolTask.startTime
            : 0;

        // Strip only the large internal state blob; keep method + actual args
        const cleanInput = Object.fromEntries(
          Object.entries(idData).filter(([k]) => k !== "_agent_state"),
        );

        // ── Handoff / transfer tools ──────────────────────────────────────────
        // Tools named transfer_to_* or handoff_to_* are agent-handoff mechanisms,
        // not real user tools. Convert them to a HANDOFF event.
        const isHandoffTool =
          /^(transfer_to_|handoff_to_|route_to_|delegate_to_)/i.test(toolName);
        if (isHandoffTool) {
          // Extract target agent name: everything after the prefix
          const target =
            toolName
              .replace(/^(transfer_to_|handoff_to_|route_to_|delegate_to_)/i, "")
              .replace(/_/g, " ")
              .trim() || toolName;
          if (!handoffEmittedThisTurn) {
            events.push({
              id: `${toolTask.taskId}-handoff`,
              type: EventType.HANDOFF,
              timestamp: toolTask.endTime ?? 0,
              summary: `→ ${target}`,
              targetAgent: target,
              detail: { transfer_to: target },
              durationMs: toolDuration,
            });
            handoffEmittedThisTurn = true;
          }
          continue;
        }

        // ── Transfer-check tasks (e.g. coder_check_transfer__N) ───────────────
        // These are orchestration infrastructure tasks that confirm a handoff decision.
        // Detected by output shape { is_transfer: bool, transfer_to: string }.
        // Emit HANDOFF only as a fallback when no handoff tool ran.
        const isTransferCheck = "is_transfer" in od;
        if (isTransferCheck) {
          const isTransfer = od.is_transfer === true;
          const transferTo = od.transfer_to as string | undefined;
          if (isTransfer && transferTo && !handoffEmittedThisTurn) {
            events.push({
              id: `${toolTask.taskId}-handoff`,
              type: EventType.HANDOFF,
              timestamp: toolTask.endTime ?? 0,
              summary: `→ ${transferTo}`,
              targetAgent: transferTo,
              detail: { transfer_to: transferTo },
              durationMs: toolDuration,
            });
            handoffEmittedThisTurn = true;
          }
          // Always skip — pure orchestration infra, never show as a tool call
          continue;
        }

        // ── Detect guardrail tasks by name convention or agentDef declaration ──
        const refName = (toolTask.referenceTaskName ?? toolTask.taskRefName ?? "").toLowerCase();
        const isGuardrail =
          toolName.toLowerCase().includes("guardrail") ||
          refName.includes("guardrail") ||
          guardrailFnNames.has(toolName.toLowerCase());
        if (isGuardrail) {
          // Extract the actual content the guardrail checked (strip redundant alias fields)
          const guardrailInput =
            idData.content ?? idData.agent_output ?? idData.input_text ?? idData.output ?? idData.input;
          // Look for the INLINE evaluation result in the same iteration
          const evalRefPrefix = refName.replace(/_worker(_|$)/, "$1");
          const evalTask = iterTasks.find(
            t => t.taskType === "INLINE" &&
                 (t.referenceTaskName ?? "").toLowerCase().startsWith(evalRefPrefix),
          );
          const evalResult = evalTask?.outputData?.result as Record<string, unknown> | undefined;
          // Build a clean output: merge worker output with evaluation result
          const guardrailOutput = evalResult ?? od;

          // Guardrail "failure" is expressed in the output data, not the task status.
          // The worker task COMPLETES even when the guardrail triggers — check output fields.
          const guardrailTriggered =
            failed ||
            od.tripwire_triggered === true ||
            evalResult?.passed === false;
          const reason =
            (evalResult?.message as string | undefined) ??
            (od.output_info as any)?.reason ??
            (guardrailTriggered ? (toolTask.reasonForIncompletion ?? "content blocked") : "passed");

          events.push({
            id: `${toolTask.taskId}-guardrail`,
            type: guardrailTriggered ? EventType.GUARDRAIL_FAIL : EventType.GUARDRAIL_PASS,
            timestamp: toolTask.startTime ?? 0,
            toolName,
            summary: guardrailTriggered
              ? `${toolName} blocked: ${reason}`
              : `${toolName} — ${reason}`,
            detail: { input: guardrailInput, output: guardrailOutput },
            success: !guardrailTriggered,
            durationMs: toolDuration,
            taskMeta: {
              taskId: toolTask.taskId,
              taskType: toolTask.taskType,
              referenceTaskName: toolTask.referenceTaskName ?? toolTask.taskRefName,
              scheduledTime: toolTask.scheduledTime ?? undefined,
              startTime: toolTask.startTime ?? undefined,
              endTime: toolTask.endTime ?? undefined,
              workerId: (toolTask as any).workerId ?? undefined,
              reasonForIncompletion: toolTask.reasonForIncompletion ?? undefined,
              retryCount: toolTask.retryCount,
              pollCount: toolTask.pollCount,
              seq: toolTask.seq,
              queueWaitTime: toolTask.queueWaitTime,
            },
          });
          continue;
        }

        // Build a readable output preview for the summary line
        const outputPreview = failed
          ? `Error: ${toolTask.reasonForIncompletion ?? "failed"}`
          : (() => {
              // Prefer unwrapped result if the only key is 'result'
              const keys = Object.keys(od);
              const val = keys.length === 1 && keys[0] === "result" ? od["result"] : od;
              try {
                return (JSON.stringify(val) ?? "").slice(0, 80);
              } catch {
                return "[complex data]";
              }
            })();

        events.push({
          id: `${toolTask.taskId}-tool`,
          type: EventType.TOOL_CALL,
          timestamp: toolTask.startTime ?? 0,
          toolName,
          summary: `${toolName} → ${outputPreview}`,
          detail: { input: cleanInput, output: failed ? toolTask.reasonForIncompletion : od },
          toolArgs: cleanInput,
          result: failed ? undefined : od,
          success: taskSuccess(toolTask.status),
          durationMs: toolDuration,
          taskMeta: {
            taskId: toolTask.taskId,
            taskType: toolTask.taskType,
            referenceTaskName: toolTask.referenceTaskName ?? toolTask.taskRefName,
            scheduledTime: toolTask.scheduledTime ?? undefined,
            startTime: toolTask.startTime ?? undefined,
            endTime: toolTask.endTime ?? undefined,
            workerId: (toolTask as any).workerId ?? undefined,
            reasonForIncompletion: toolTask.reasonForIncompletion ?? undefined,
            retryCount: toolTask.retryCount,
            pollCount: toolTask.pollCount,
            seq: toolTask.seq,
            queueWaitTime: toolTask.queueWaitTime,
          },
        });
      }

      // If this iteration has no meaningful events (e.g. a done_noop termination
      // iteration), produce nothing — the turn will be filtered out below.
      const isDone =
        agentTasks.length === 0 &&
        iterLlmTasks.length === 0 &&
        toolWorkerTasks.length === 0 &&
        selfCalls.length === 0;

      const timestamps = iterTasks
        .flatMap((t) => [t.startTime, t.endTime])
        .filter((v): v is number => v != null && v > 0);
      const turnStart = timestamps.length ? Math.min(...timestamps) : 0;
      const turnEnd = timestamps.length ? Math.max(...timestamps) : 0;

      // Token counts from LLM tasks in this iteration
      const turnPromptTokens = iterLlmTasks.reduce(
        (s, t) => s + ((t.outputData?.promptTokens as number) || 0),
        0,
      );
      const turnCompletionTokens = iterLlmTasks.reduce(
        (s, t) => s + ((t.outputData?.completionTokens as number) || 0),
        0,
      );

      const subStatuses = subAgents.map((s) => s.status);
      const anyRunning =
        subStatuses.includes(AgentStatus.RUNNING) ||
        iterTasks.some((t) => t.status === "IN_PROGRESS");
      const anyFailed =
        subStatuses.includes(AgentStatus.FAILED) ||
        iterTasks.some((t) => t.status === "FAILED");
      const turnStatus =
        anyRunning
          ? AgentStatus.RUNNING
          : anyFailed
            ? AgentStatus.FAILED
            : AgentStatus.COMPLETED;

      return {
        turnNumber: idx + 1,
        events,
        status: turnStatus,
        durationMs: turnEnd > turnStart ? turnEnd - turnStart : 0,
        tokens: {
          promptTokens: turnPromptTokens,
          completionTokens: turnCompletionTokens,
          totalTokens: turnPromptTokens + turnCompletionTokens,
        },
        subAgents,
        strategy:
          subAgents.length > 1 ? AgentStrategy.PARALLEL : AgentStrategy.HANDOFF,
      };
    })
    .filter((t) => t.events.length > 0 || t.subAgents.length > 0);

  // Build sub-agents from root-level SUB_WORKFLOW tasks (merged into root events turn below).
  const rootSubWorkflows = rootActiveTasks.filter(isAgentSubWorkflow);
  const rootSubAgents: AgentRunData[] = rootSubWorkflows.map((task) => {
    const agentName =
      extractAgentName(task.referenceTaskName)
      ?? task.inputData?.subWorkflowName as string
      ?? task.workflowTask?.name
      ?? task.referenceTaskName;
    const subWfId = task.outputData?.subWorkflowId as string | undefined;
    const dur = task.endTime && task.startTime ? task.endTime - task.startTime : 0;

    // Extract input from workflowInput (Claude Code / agent-as-tool pattern)
    const wfInput = task.inputData?.workflowInput as Record<string, unknown> | undefined;
    const agentInput =
      (wfInput?.prompt as string | undefined) ??
      (wfInput?.description as string | undefined) ??
      undefined;

    // Extract output: try result, then tool_response content blocks
    let outputStr: string | undefined;
    const directResult = task.outputData?.result;
    if (typeof directResult === "string" && directResult.length > 0) {
      outputStr = directResult;
    } else {
      const toolResp = task.outputData?.tool_response as Record<string, unknown> | undefined;
      if (toolResp) {
        const content = toolResp.content as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(content)) {
          const textBlock = content.find(c => c.type === "text");
          if (textBlock && typeof (textBlock as any).text === "string") {
            outputStr = (textBlock as any).text;
          }
        }
        if (!outputStr && typeof toolResp.result === "string") {
          outputStr = toolResp.result as string;
        }
      }
    }

    const failReason = task.reasonForIncompletion ?? undefined;

    const subTurns: AgentTurn[] = outputStr ? [{
      turnNumber: 1,
      status: mapTaskStatus(task.status),
      durationMs: dur,
      tokens: ZERO_TOKENS,
      subAgents: [],
      events: [{
        id: `${task.taskId}-msg`,
        type: EventType.MESSAGE,
        timestamp: task.startTime ?? 0,
        summary: outputStr.slice(0, 120) + (outputStr.length > 120 ? "..." : ""),
        detail: outputStr,
        durationMs: dur,
      }, {
        id: `${task.taskId}-done`,
        type: EventType.DONE,
        timestamp: task.endTime ?? 0,
        summary: "Agent completed",
        success: task.status === "COMPLETED",
      }],
    }] : [];

    return {
      id: subWfId ?? task.taskId,
      subWorkflowId: subWfId,
      agentName,
      turns: subTurns,
      status: mapWorkflowStatus(task.status as any),
      totalTokens: ZERO_TOKENS,
      totalDurationMs: dur,
      input: agentInput,
      output: outputStr,
      failureReason: failReason,
    } as AgentRunData;
  });

  // Build events + turn for root-level tasks (outside DO_WHILE).
  // This handles: simple single-LLM agents (greeter, triage_router_wf),
  // final synthesis tasks, and Claude Code agent tool calls + sub-agents.
  // Sub-agents are included in the same turn to preserve execution order.
  let finalOutput: string | undefined;
  if (rootActiveTasks.length > 0) {
    const rootEvents: AgentEvent[] = [];
    let rootPrompt = 0, rootCompletion = 0;

    for (const task of rootActiveTasks) {
      // Skip the framework task (_fw_task) — it represents the agent itself, not a tool call.
      // Its outputData is used for the final agent output below.
      if (task.referenceTaskName === "_fw_task") continue;

      if (task.taskType === "LLM_CHAT_COMPLETE") {
        const condensed = maybeCondensationEvent(task);
        if (condensed) rootEvents.push(condensed);

        const model = task.inputData?.model as string | undefined;
        const finishReason = ((task.outputData?.finishReason as string) ?? "stop").toLowerCase();
        const result = task.outputData?.result;
        const promptTokens = (task.outputData?.promptTokens as number) || 0;
        const completionTokens = (task.outputData?.completionTokens as number) || 0;
        const messages = (task.inputData?.messages as Array<{ role: string; message: string }>) ?? [];
        const tools = (task.inputData?.tools as unknown[]) ?? [];
        const dur = task.endTime && task.startTime ? task.endTime - task.startTime : 0;
        rootPrompt += promptTokens;
        rootCompletion += completionTokens;

        const rootSysMsg = messages.find((m) => m.role === "system");
        const rootLastMsg = [...messages].reverse().find((m) => m.role !== "system");

        rootEvents.push({
          id: `${task.taskId}-llm`,
          type: EventType.THINKING,
          toolName: model,
          timestamp: task.startTime ?? 0,
          summary: `${model ?? "LLM"} · ${messages.length} messages${tools.length ? ` · ${tools.length} tools` : ""}`,
          detail: {
            input: {
              ...(rootSysMsg ? { instructions: rootSysMsg.message } : {}),
              ...(rootLastMsg ? { message: rootLastMsg.message } : {}),
            },
            output: task.outputData,
          },
          tokens: { promptTokens, completionTokens, totalTokens: promptTokens + completionTokens },
          durationMs: dur,
          success: taskSuccess(task.status),
          condensationInfo: condensed?.condensationInfo,
        });

        if (finishReason === "stop" && typeof result === "string" && result.length > 0) {
          finalOutput = result;
          rootEvents.push({
            id: `${task.taskId}-output`,
            type: EventType.DONE,
            timestamp: task.endTime ?? 0,
            summary: result.slice(0, 120) + (result.length > 120 ? "..." : ""),
            detail: result,
            success: true,
            tokens: { promptTokens, completionTokens, totalTokens: promptTokens + completionTokens },
            durationMs: dur,
          });
        }
      } else if (!ITER_INFRA.has(task.taskType) && task.taskType !== "SUB_WORKFLOW") {
        // Root-level tool worker task (no DO_WHILE iteration suffix)
        const od = (task.outputData ?? {}) as Record<string, unknown>;
        const idData = (task.inputData ?? {}) as Record<string, unknown>;
        const failed = task.status === "FAILED";
        const dur = task.endTime && task.startTime ? task.endTime - task.startTime : 0;
        const cleanInput = Object.fromEntries(Object.entries(idData).filter(([k]) => k !== "_agent_state"));

        // Handoff/transfer tools → HANDOFF event, not TOOL_CALL
        if (/^(transfer_to_|handoff_to_|route_to_|delegate_to_)/i.test(task.taskType)) {
          const target = task.taskType.replace(/^(transfer_to_|handoff_to_|route_to_|delegate_to_)/i, "").replace(/_/g, " ").trim();
          rootEvents.push({
            id: `${task.taskId}-handoff`,
            type: EventType.HANDOFF,
            timestamp: task.endTime ?? 0,
            summary: `→ ${target}`,
            targetAgent: target,
            detail: { transfer_to: target },
            durationMs: dur,
          });
        // Transfer-check infra tasks → emit HANDOFF only if is_transfer=true, else skip
        } else if ("is_transfer" in od) {
          if (od.is_transfer === true && od.transfer_to) {
            rootEvents.push({
              id: `${task.taskId}-handoff`,
              type: EventType.HANDOFF,
              timestamp: task.endTime ?? 0,
              summary: `→ ${od.transfer_to}`,
              targetAgent: od.transfer_to as string,
              detail: { transfer_to: od.transfer_to },
              durationMs: dur,
            });
          }
          // skip regardless
        } else {
          const isGuardrail = task.taskType.toLowerCase().includes("guardrail");
          if (isGuardrail) {
            rootEvents.push({
              id: `${task.taskId}-guardrail`,
              type: failed ? EventType.GUARDRAIL_FAIL : EventType.GUARDRAIL_PASS,
              timestamp: task.startTime ?? 0,
              toolName: task.taskType,
              summary: failed
                ? `${task.taskType} blocked: ${task.reasonForIncompletion ?? "content blocked"}`
                : `${task.taskType} passed`,
              detail: { input: cleanInput, output: failed ? task.reasonForIncompletion : od },
              success: !failed,
              durationMs: dur,
            });
          } else {
            rootEvents.push({
              id: `${task.taskId}-tool`,
              type: EventType.TOOL_CALL,
              timestamp: task.startTime ?? 0,
              toolName: task.taskType,
              summary: task.taskType,
              detail: { input: cleanInput, output: failed ? task.reasonForIncompletion : od },
              toolArgs: cleanInput,
              result: failed ? undefined : od,
              success: taskSuccess(task.status),
              durationMs: dur,
              taskMeta: {
                taskId: task.taskId,
                taskType: task.taskType,
                referenceTaskName: task.referenceTaskName ?? (task as any).taskRefName,
                scheduledTime: task.scheduledTime ?? undefined,
                startTime: task.startTime ?? undefined,
                endTime: task.endTime ?? undefined,
                workerId: (task as any).workerId ?? undefined,
                reasonForIncompletion: task.reasonForIncompletion ?? undefined,
                retryCount: task.retryCount,
                pollCount: task.pollCount,
                seq: task.seq,
                queueWaitTime: task.queueWaitTime,
              },
            });
          }
        }
      }
    }

    if (rootEvents.length > 0 || rootSubAgents.length > 0) {
      const rootTimestamps = rootActiveTasks
        .flatMap((t) => [t.startTime, t.endTime])
        .filter((v): v is number => v != null && v > 0);
      turns.push({
        turnNumber: turns.length + 1,
        events: rootEvents,
        status: AgentStatus.COMPLETED,
        durationMs: rootTimestamps.length
          ? Math.max(...rootTimestamps) - Math.min(...rootTimestamps)
          : 0,
        tokens: { promptTokens: rootPrompt, completionTokens: rootCompletion, totalTokens: rootPrompt + rootCompletion },
        subAgents: rootSubAgents,
      });
    }
  }

  // Check the framework task (_fw_task) for output — Claude Code agent pattern
  if (!finalOutput) {
    const fwTask = rootActiveTasks.find(t => t.referenceTaskName === "_fw_task");
    const fwResult = fwTask?.outputData?.result;
    if (typeof fwResult === "string" && fwResult.length > 0) {
      finalOutput = fwResult;
    }
  }

  // If no finalOutput found from root tasks, check last iteration's final STOP LLM
  if (!finalOutput && turns.length > 0) {
    for (const event of [...turns[turns.length - 1].events].reverse()) {
      if (event.type === EventType.DONE && typeof event.detail === "string") {
        finalOutput = event.detail;
        break;
      }
    }
  }

  // Last resort: check the Conductor workflow output field
  if (!finalOutput && execution.output) {
    const wfOut = execution.output;
    const candidate = wfOut.result ?? wfOut.output ?? wfOut.message;
    if (typeof candidate === "string" && candidate.length > 0) {
      finalOutput = candidate;
    }
  }

  // Extract the initial user prompt from execution input
  const execInput = execution.input as any;
  const agentInput: string | undefined =
    typeof execInput === "string"
      ? execInput || undefined
      : typeof execInput === "object" && execInput !== null
        ? (execInput.prompt || execInput.conversation || execInput.message || undefined)
        : undefined;

  // Accumulate total tokens from all turns
  const totalPromptTokens = turns.reduce((s, t) => s + t.tokens.promptTokens, 0);
  const totalCompletionTokens = turns.reduce((s, t) => s + t.tokens.completionTokens, 0);

  const finishReason =
    execution.status === WorkflowExecutionStatus.COMPLETED
      ? FinishReason.STOP
      : execution.status === WorkflowExecutionStatus.FAILED ||
          execution.status === WorkflowExecutionStatus.TIMED_OUT ||
          execution.status === WorkflowExecutionStatus.TERMINATED
        ? FinishReason.ERROR
        : undefined;

  const agentDef = (execution.workflowDefinition?.metadata?.agentDef as Record<string, unknown> | undefined);

  // Extract model from agentDef metadata or from first LLM task
  const agentModel =
    (agentDef?.model as string | undefined) ??
    tasks.find(t => t.taskType === "LLM_CHAT_COMPLETE")?.inputData?.model as string | undefined;

  return {
    id: execution.workflowId,
    agentName: (execution as any).workflowName ?? execution.workflowType ?? "agent",
    model: agentModel,
    turns,
    status: mapWorkflowStatus(execution.status),
    agentDef,
    totalTokens: {
      promptTokens: totalPromptTokens,
      completionTokens: totalCompletionTokens,
      totalTokens: totalPromptTokens + totalCompletionTokens,
    },
    totalDurationMs,
    finishReason,
    strategy: rootSubWorkflows.length > 1 ? AgentStrategy.PARALLEL : sortedIters.length > 0 ? AgentStrategy.HANDOFF : AgentStrategy.SINGLE,
    input: agentInput,
    output: finalOutput,
  };
}

// Task types to skip when building events (infrastructure noise)
const SKIP_TASK_TYPES = new Set([
  "SET_VARIABLE",
  "SWITCH",
  "DO_WHILE",
  "FORK_JOIN",
  "FORK_JOIN_DYNAMIC",
  "FORK",
  "JOIN",
  "INLINE",
  "SUB_WORKFLOW", // handled separately as sub-agents
]);

/**
 * Build events from a single task for the drill-in detail view.
 *
 * LLM_CHAT_COMPLETE:
 *   - System prompt            → THINKING  (gray / brain)
 *   - User/assistant history   → MESSAGE   (chat bubble) — collapsed by default
 *   - LLM invocation summary   → THINKING  "Calling gpt-4o-mini with N messages"
 *   - Text response (stop)     → MESSAGE   (the actual output — most important)
 *   - Tool-call response       → TOOL_CALL per called function
 *
 * Worker / custom task:
 *   - Invocation               → TOOL_CALL
 *   - Result                   → TOOL_RESULT
 */
function taskToEvents(task: ExecutionTask): AgentEvent[] {
  const events: AgentEvent[] = [];
  const durationMs =
    task.endTime && task.startTime ? task.endTime - task.startTime : 0;

  if (task.taskType === "LLM_CHAT_COMPLETE") {
    const condensed = maybeCondensationEvent(task);
    if (condensed) events.push(condensed);

    const messages = (
      task.inputData?.messages as
        | Array<{ role: string; message: string }>
        | undefined
    ) ?? [];
    const model = task.inputData?.model as string | undefined;
    const result = task.outputData?.result;
    const finishReason = (task.outputData?.finishReason as string | undefined)
      ?.toLowerCase() ?? "stop";
    const promptTokens = (task.outputData?.promptTokens as number) || 0;
    const completionTokens = (task.outputData?.completionTokens as number) || 0;
    const tools = (task.inputData?.tools as unknown[]) ?? [];
    const isToolCall = finishReason === "tool_calls";

    const systemMsg = messages.find((m) => m.role === "system");
    const lastMsg = [...messages].reverse().find((m) => m.role !== "system");

    // Single LLM block: instructions + last message + output
    events.push({
      id: `${task.taskId}-invoke`,
      type: EventType.THINKING,
      toolName: model,
      timestamp: task.startTime ?? 0,
      summary: `${model ?? "LLM"} · ${messages.length} messages${tools.length ? ` · ${tools.length} tools` : ""}`,
      detail: {
        input: {
          ...(systemMsg ? { instructions: systemMsg.message } : {}),
          ...(lastMsg ? { message: lastMsg.message } : {}),
        },
        output: task.outputData,
      },
      durationMs,
      tokens: { promptTokens, completionTokens, totalTokens: promptTokens + completionTokens },
      success: taskSuccess(task.status),
      condensationInfo: condensed?.condensationInfo,
    });

    if (isToolCall) {
      // LLM decided to call tools — the actual tool executions follow as separate
      // worker tasks in the same turn bucket, so don't emit duplicate TOOL_CALL
      // events from the LLM's declared function call list here.
      // The THINKING event above already signals the tool-call intent.
    } else {
      // LLM responded with text → DONE with full content (consistent with
      // transformWorkflowExecutionToAgentRun which also uses DONE for stop responses)
      const textResult = typeof result === "string" ? result : null;
      if (textResult) {
        events.push({
          id: `${task.taskId}-done`,
          type: EventType.DONE,
          timestamp: task.endTime ?? 0,
          summary: textResult.slice(0, 120) + (textResult.length > 120 ? "..." : ""),
          detail: textResult,
          success: true,
          tokens: { promptTokens, completionTokens, totalTokens: promptTokens + completionTokens },
          durationMs,
        });
      }
    }
  } else {
    // Generic worker / custom task
    const inputData = task.inputData ?? {};
    const outputData = (task.outputData ?? {}) as Record<string, unknown>;
    const failed = task.status === "FAILED";

    // Handoff/transfer tools → HANDOFF event
    if (/^(transfer_to_|handoff_to_|route_to_|delegate_to_)/i.test(task.taskType)) {
      const target = task.taskType.replace(/^(transfer_to_|handoff_to_|route_to_|delegate_to_)/i, "").replace(/_/g, " ").trim();
      events.push({
        id: `${task.taskId}-handoff`,
        type: EventType.HANDOFF,
        timestamp: task.endTime ?? 0,
        summary: `→ ${target}`,
        targetAgent: target,
        detail: { transfer_to: target },
        durationMs,
      });
    // Transfer-check infra → HANDOFF if transferring, else skip
    } else if ("is_transfer" in outputData) {
      if (outputData.is_transfer === true && outputData.transfer_to) {
        events.push({
          id: `${task.taskId}-handoff`,
          type: EventType.HANDOFF,
          timestamp: task.endTime ?? 0,
          summary: `→ ${outputData.transfer_to}`,
          targetAgent: outputData.transfer_to as string,
          detail: { transfer_to: outputData.transfer_to },
          durationMs,
        });
      }
    } else if (
      task.taskType.toLowerCase().includes("guardrail") ||
      (task.referenceTaskName ?? task.taskRefName ?? "").toLowerCase().includes("guardrail")
    ) {
      // Extract meaningful content being checked (strip redundant alias fields)
      const grInput =
        (inputData as any).content ?? (inputData as any).agent_output ??
        (inputData as any).input_text ?? (inputData as any).output ?? (inputData as any).input;
      const grReason = (outputData.output_info as any)?.reason;
      // Guardrail "failure" is in the output data, not the task status
      const grTriggered = failed || outputData.tripwire_triggered === true;
      events.push({
        id: `${task.taskId}-guardrail`,
        type: grTriggered ? EventType.GUARDRAIL_FAIL : EventType.GUARDRAIL_PASS,
        timestamp: task.startTime ?? 0,
        toolName: task.taskType,
        summary: grTriggered
          ? `${task.taskType} blocked: ${grReason ?? "triggered"}`
          : `${task.taskType} — ${grReason ?? "passed"}`,
        detail: { input: grInput ?? inputData, output: failed ? task.reasonForIncompletion : outputData },
        success: !grTriggered,
        durationMs,
        taskMeta: {
          taskId: task.taskId,
          taskType: task.taskType,
          referenceTaskName: task.referenceTaskName ?? task.taskRefName,
          scheduledTime: task.scheduledTime ?? undefined,
          startTime: task.startTime ?? undefined,
          endTime: task.endTime ?? undefined,
          workerId: (task as any).workerId ?? undefined,
          reasonForIncompletion: task.reasonForIncompletion ?? undefined,
          retryCount: task.retryCount,
          pollCount: task.pollCount,
          seq: task.seq,
          queueWaitTime: task.queueWaitTime,
        },
      });
    } else {
      events.push({
        id: `${task.taskId}-call`,
        type: EventType.TOOL_CALL,
        timestamp: task.startTime ?? 0,
        summary: `${task.taskRefName ?? task.taskType}`,
        toolName: task.taskRefName ?? task.taskType,
        toolArgs: inputData as Record<string, unknown> | undefined,
        detail: {
          input: inputData,
          output: failed ? task.reasonForIncompletion : outputData,
        },
        result: failed ? undefined : outputData,
        success: taskSuccess(task.status),
        durationMs,
        taskMeta: {
          taskId: task.taskId,
          taskType: task.taskType,
          referenceTaskName: task.referenceTaskName ?? task.taskRefName,
          scheduledTime: task.scheduledTime ?? undefined,
          startTime: task.startTime ?? undefined,
          endTime: task.endTime ?? undefined,
          workerId: (task as any).workerId ?? (task as any).workerTask?.workerId ?? undefined,
          reasonForIncompletion: task.reasonForIncompletion ?? undefined,
          retryCount: task.retryCount,
          pollCount: task.pollCount,
          seq: task.seq,
          queueWaitTime: task.queueWaitTime,
        },
      });
    }
  }

  return events;
}

/**
 * Transform a fetched sub-workflow execution into AgentRunData for drill-in view.
 * - If the sub-workflow has a DO_WHILE loop (complex multi-agent), delegates to
 *   transformWorkflowExecutionToAgentRun for proper turn/sub-agent structure.
 * - Otherwise (simple LLM agent), shows all tasks as events within turns grouped
 *   by LLM_CHAT_COMPLETE boundaries.
 */
export function transformSubWorkflowToAgentRun(
  subExecution: WorkflowExecution,
  agentName: string,
): AgentRunData {
  const tasks: ExecutionTask[] = subExecution.tasks ?? [];

  // If it has a DO_WHILE, it's a complex multi-agent — use the full transformer
  const hasDoWhile = tasks.some((t) => t.taskType === "DO_WHILE");
  if (hasDoWhile) {
    return transformWorkflowExecutionToAgentRun(subExecution);
  }

  // Simple agent: group tasks into turns split at each LLM_CHAT_COMPLETE boundary
  const activeTasks = tasks.filter((t) => !SKIP_TASK_TYPES.has(t.taskType));

  // Split into turn buckets at each LLM_CHAT_COMPLETE task
  const turnBuckets: ExecutionTask[][] = [];
  let bucket: ExecutionTask[] = [];
  for (const task of activeTasks) {
    bucket.push(task);
    if (task.taskType === "LLM_CHAT_COMPLETE") {
      turnBuckets.push(bucket);
      bucket = [];
    }
  }
  if (bucket.length > 0) turnBuckets.push(bucket);
  if (turnBuckets.length === 0) turnBuckets.push(activeTasks);

  const turns: AgentTurn[] = turnBuckets.map((bucketTasks, idx): AgentTurn => {
    const events: AgentEvent[] = bucketTasks.flatMap(taskToEvents);
    const llmTask = bucketTasks.find((t) => t.taskType === "LLM_CHAT_COMPLETE");
    const promptTokens = (llmTask?.outputData?.promptTokens as number) || 0;
    const completionTokens =
      (llmTask?.outputData?.completionTokens as number) || 0;
    const timestamps = bucketTasks
      .flatMap((t) => [t.startTime, t.endTime])
      .filter((v): v is number => v != null && v > 0);
    const turnStart = timestamps.length ? Math.min(...timestamps) : 0;
    const turnEnd = timestamps.length ? Math.max(...timestamps) : 0;
    const hasError = bucketTasks.some((t) => t.status === "FAILED");
    const hasRunning = bucketTasks.some((t) => t.status === "IN_PROGRESS");

    return {
      turnNumber: idx + 1,
      events,
      status: hasError
        ? AgentStatus.FAILED
        : hasRunning
          ? AgentStatus.RUNNING
          : AgentStatus.COMPLETED,
      durationMs: turnEnd > turnStart ? turnEnd - turnStart : 0,
      tokens: {
        promptTokens,
        completionTokens,
        totalTokens: promptTokens + completionTokens,
      },
      subAgents: [],
    };
  });

  const totalPrompt = turns.reduce((s, t) => s + t.tokens.promptTokens, 0);
  const totalCompletion = turns.reduce(
    (s, t) => s + t.tokens.completionTokens,
    0,
  );
  const model = activeTasks.find((t) => t.taskType === "LLM_CHAT_COMPLETE")
    ?.inputData?.model as string | undefined;
  const startMs = toMs(subExecution.startTime as any);
  const endMs = toMs(subExecution.endTime as any);
  const subIsRunning = subExecution.status === WorkflowExecutionStatus.RUNNING;
  const subDuration =
    endMs > 0
      ? endMs - startMs
      : subIsRunning
        ? Date.now() - startMs
        : subExecution.executionTime ?? 0;

  const subFinishReason =
    subExecution.status === WorkflowExecutionStatus.COMPLETED
      ? FinishReason.STOP
      : subExecution.status === WorkflowExecutionStatus.FAILED ||
          subExecution.status === WorkflowExecutionStatus.TIMED_OUT ||
          subExecution.status === WorkflowExecutionStatus.TERMINATED
        ? FinishReason.ERROR
        : undefined;

  const lastResult = (() => {
    for (let i = activeTasks.length - 1; i >= 0; i--) {
      const r = activeTasks[i].outputData?.result as string | undefined;
      if (r) return r;
    }
    return undefined;
  })();

  // Fall back to execution-level output if no task had a result
  let subOutput = lastResult;
  if (!subOutput && subExecution.output) {
    const wfOut = subExecution.output;
    const candidate = wfOut.result ?? wfOut.output ?? wfOut.message;
    if (typeof candidate === "string" && candidate.length > 0) {
      subOutput = candidate;
    }
  }

  // Extract initial prompt from execution input
  const subExecInput = subExecution.input as any;
  const subInput: string | undefined =
    typeof subExecInput === "string" ? subExecInput || undefined
    : typeof subExecInput === "object" && subExecInput !== null
      ? (subExecInput.prompt || subExecInput.conversation || subExecInput.message || undefined)
    : undefined;

  const subAgentDef = (subExecution.workflowDefinition?.metadata?.agentDef as Record<string, unknown> | undefined);

  return {
    id: subExecution.workflowId,
    agentName,
    model,
    turns,
    status: mapWorkflowStatus(subExecution.status),
    agentDef: subAgentDef,
    totalTokens: {
      promptTokens: totalPrompt,
      completionTokens: totalCompletion,
      totalTokens: totalPrompt + totalCompletion,
    },
    totalDurationMs: subDuration,
    finishReason: subFinishReason,
    strategy: AgentStrategy.SINGLE,
    input: subInput,
    output: subOutput,
  };
}
