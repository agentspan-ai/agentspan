// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * Thin wrapper over the conductor client's `workflowResource` for workflow
 * reads. Mirrors the Java/C#/Python SDK split where workflow-execution reads
 * (status, tasks, token usage) go through a dedicated client built on the
 * shared Conductor client rather than ad-hoc HTTP on the runtime.
 */

import type { ConductorClient } from "./agent-client.js";

/** Conductor workflow shape (subset we read). */
export interface WorkflowExecution {
  workflowId?: string;
  status?: string;
  output?: Record<string, unknown>;
  input?: Record<string, unknown>;
  variables?: Record<string, unknown>;
  tasks?: Record<string, unknown>[];
  reasonForIncompletion?: string;
  [key: string]: unknown;
}

/** Aggregated token usage across a workflow execution tree. */
export interface WorkflowTokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

/**
 * Read-only client for Conductor workflow executions.
 *
 * Built on a (lazily-resolved) {@link ConductorClient}; the runtime shares a
 * single Conductor client between this, the {@link AgentClient}, and the
 * worker poller.
 */
export class WorkflowClient {
  /**
   * @param getClient resolver for the shared Conductor client.
   * @param fetchAgentExecution optional fallback that reads an Agentspan agent
   *   execution (`GET /agent/execution/{id}`). Agent executions are not stored
   *   in Conductor's workflow index, so `getExecutionStatus` 404s for them;
   *   when this fallback is provided, {@link getWorkflow} uses it.
   */
  constructor(
    private readonly getClient: () => Promise<ConductorClient>,
    private readonly fetchAgentExecution?: (
      executionId: string,
    ) => Promise<Record<string, unknown> | null>,
  ) {}

  /**
   * Fetch a workflow execution by id (with tasks).
   *
   * Tries Conductor's `getExecutionStatus` first; for agent executions (which
   * Conductor's workflow index doesn't hold) falls back to the Agentspan
   * agent-execution endpoint when available.
   *
   * @param executionId Conductor workflow id or agent execution id.
   * @param includeTasks Include the task list (default true).
   */
  async getWorkflow(executionId: string, includeTasks = true): Promise<WorkflowExecution> {
    try {
      const client = await this.getClient();
      return (await client.workflowResource.getExecutionStatus(
        executionId,
        includeTasks,
      )) as unknown as WorkflowExecution;
    } catch (e) {
      // Only fall back to the agent-execution endpoint when Conductor genuinely
      // doesn't have the workflow (404). A transient 5xx must propagate with its
      // real status, not be masked by the fallback.
      const status =
        (e as { status?: number; statusCode?: number }).status ??
        (e as { statusCode?: number }).statusCode;
      const notFound = status === 404 || /\b404\b|not found/i.test((e as Error).message ?? "");
      if (notFound && this.fetchAgentExecution) {
        const exec = await this.fetchAgentExecution(executionId);
        if (exec) {
          // Agent executions key on `executionId`; surface it as `workflowId`
          // so the shape matches a Conductor workflow.
          return {
            workflowId: (exec.workflowId as string) ?? (exec.executionId as string),
            ...exec,
          } as WorkflowExecution;
        }
      }
      throw e;
    }
  }

  /** Workflow status string (RUNNING/COMPLETED/FAILED/...), or "" if unknown. */
  async getStatus(executionId: string): Promise<string> {
    const wf = await this.getWorkflow(executionId, false);
    return wf.status ?? "";
  }

  /**
   * Aggregate token usage across the execution tree.
   *
   * Reads `tokenUsage` at each level and recurses into SUB_WORKFLOW tasks,
   * mirroring the Python SDK's `_extract_token_usage`.
   */
  async extractTokenUsage(executionId: string): Promise<WorkflowTokenUsage | null> {
    if (!executionId) return null;
    const { prompt, completion, total, found } = await this._collect(executionId, new Set());
    if (!found) return null;
    const finalTotal = total === 0 && (prompt > 0 || completion > 0) ? prompt + completion : total;
    return { promptTokens: prompt, completionTokens: completion, totalTokens: finalTotal };
  }

  private async _collect(
    executionId: string,
    visited: Set<string>,
  ): Promise<{ prompt: number; completion: number; total: number; found: boolean }> {
    if (visited.has(executionId)) return { prompt: 0, completion: 0, total: 0, found: false };
    visited.add(executionId);

    let data: WorkflowExecution;
    try {
      data = await this.getWorkflow(executionId, true);
    } catch (e) {
      // Token accounting is best-effort; surface at debug so a zeroed total is diagnosable.
      console.debug(`token-usage read failed for ${executionId}: ${(e as Error).message}`);
      return { prompt: 0, completion: 0, total: 0, found: false };
    }

    let totalPrompt = 0;
    let totalCompletion = 0;
    let totalTotal = 0;
    let foundAny = false;

    const tokenUsage = data.tokenUsage as Record<string, unknown> | undefined;
    if (tokenUsage) {
      const p = Number(tokenUsage.promptTokens ?? 0);
      const c = Number(tokenUsage.completionTokens ?? 0);
      const t = Number(tokenUsage.totalTokens ?? 0);
      if (p || c || t) {
        foundAny = true;
        totalPrompt += p;
        totalCompletion += c;
        totalTotal += t;
      }
    }

    for (const task of data.tasks ?? []) {
      const taskType = String(task.taskType ?? "").toUpperCase();
      if (taskType.includes("SUB_WORKFLOW")) {
        const subId = task.subWorkflowId as string | undefined;
        if (subId && !visited.has(subId)) {
          const sub = await this._collect(subId, visited);
          if (sub.found) {
            foundAny = true;
            totalPrompt += sub.prompt;
            totalCompletion += sub.completion;
            totalTotal += sub.total;
          }
        }
      }
    }

    return { prompt: totalPrompt, completion: totalCompletion, total: totalTotal, found: foundAny };
  }
}
