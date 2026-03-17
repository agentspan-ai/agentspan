'use strict';

/**
 * Result types — AgentResult, AgentHandle, AgentEvent.
 */

const EventType = Object.freeze({
  THINKING: 'thinking',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  GUARDRAIL_PASS: 'guardrail_pass',
  GUARDRAIL_FAIL: 'guardrail_fail',
  WAITING: 'waiting',
  ERROR: 'error',
  DONE: 'done',
});

const Status = Object.freeze({
  COMPLETED: 'COMPLETED',
  FAILED: 'FAILED',
  TERMINATED: 'TERMINATED',
  TIMED_OUT: 'TIMED_OUT',
});

const FinishReason = Object.freeze({
  STOP: 'stop',
  LENGTH: 'LENGTH',
  TOOL_CALLS: 'tool_calls',
  ERROR: 'error',
  CANCELLED: 'cancelled',
  TIMEOUT: 'timeout',
  GUARDRAIL: 'guardrail',
  REJECTED: 'rejected',
});

const TERMINAL_STATUSES = new Set(['COMPLETED', 'FAILED', 'TERMINATED', 'TIMED_OUT']);

function makeAgentResult({ workflowId, output, status, messages, toolCalls, finishReason, error, tokenUsage, subResults }) {
  const result = {
    workflowId,
    output: output || null,
    status: (status || 'COMPLETED').toUpperCase(),
    messages: messages || [],
    toolCalls: toolCalls || [],
    finishReason: finishReason || null,
    error: error || null,
    tokenUsage: tokenUsage || null,
    subResults: subResults || {},

    get isSuccess() { return result.status === 'COMPLETED'; },
    get isFailed() { return TERMINAL_STATUSES.has(result.status) && result.status !== 'COMPLETED'; },

    printResult() {
      const sep = '═'.repeat(50);
      console.log(`\n╒${sep}╕`);
      console.log(`│ ${'Agent Output'.padEnd(49)}│`);
      console.log(`╘${sep}╛\n`);

      if (result.isFailed && result.error) {
        console.log(`ERROR: ${result.error}\n`);
      } else if (result.output && typeof result.output === 'object') {
        const out = result.output;
        if (out.result !== undefined && out.result !== null) {
          console.log(out.result);
          console.log();
        } else {
          for (const [k, v] of Object.entries(out)) {
            console.log(`--- ${k} ---`);
            console.log(v);
            console.log();
          }
        }
      } else {
        console.log(result.output);
        console.log();
      }

      if (Object.keys(result.subResults).length > 0) {
        console.log('--- Per-agent results ---');
        for (const [name, out] of Object.entries(result.subResults)) {
          console.log(`  [${name}]: ${out}`);
        }
        console.log();
      }

      if (result.toolCalls.length > 0) console.log(`Tool calls: ${result.toolCalls.length}`);
      if (result.tokenUsage) {
        const u = result.tokenUsage;
        console.log(
          `Tokens: ${u.totalTokens || u.total_tokens || 0} total ` +
          `(${u.promptTokens || u.prompt_tokens || 0} prompt, ` +
          `${u.completionTokens || u.completion_tokens || 0} completion)`
        );
      }
      if (result.finishReason) console.log(`Finish reason: ${result.finishReason}`);
      console.log(`Workflow ID: ${result.workflowId}\n`);
    },
  };

  return result;
}

module.exports = { makeAgentResult, EventType, Status, FinishReason, TERMINAL_STATUSES };
