/**
 * Example executor — runs examples via subprocess.
 *
 * Spawns `npx tsx <examplePath>` with the given environment variables,
 * captures stdout/stderr, parses output for events and status.
 */

import { spawn } from 'node:child_process';
import * as path from 'node:path';
import type { AgentEvent } from '../src/types.js';

export interface ExecutionResult {
  exampleName: string;
  exitCode: number;
  stdout: string;
  stderr: string;
  duration: number;
  status: 'COMPLETED' | 'FAILED' | 'TIMEOUT' | 'ERROR';
  output: string;
  events: AgentEvent[];
  toolCalls: number;
  executionId?: string;
}

// Regex patterns for parsing stdout
const EXECUTION_ID_RE = /(?:Execution ID|Execution|Workflow ID|Workflow): (\S+)/;
const TOOL_CALLS_RE = /Tool [Cc]alls: (\d+)/;
const STATUS_RE = /Status: (\S+)/;
// Output block: matches "[OK] Agent Result" format with "Output: { ... }" section
// Also matches Python-style box-drawing border format
const AGENT_OUTPUT_RE =
  /(?:[╘└]═+[╛┘]\s*\n(.*?)(?=\n\s*Tool calls:|\n\s*Tokens:|\n\s*Finish reason:|\n\s*Workflow ID:|\n\n\n|$))|(?:Output:\s*(\{[\s\S]*?\})\s*(?:\n\s*Events:|\n\s*Tool [Cc]alls:|\n\s*Messages:|$))/s;
// Simpler fallback: grab Output: or Result: line content
const OUTPUT_LINE_RE = /(?:Output|Result):\s*(.+)/;

/**
 * Parse stdout for structured agent output data.
 */
function parseStdout(stdout: string): {
  output: string;
  toolCalls: number;
  executionId?: string;
  statusFromOutput?: string;
} {
  let output = '';
  let toolCalls = 0;
  let executionId: string | undefined;
  let statusFromOutput: string | undefined;

  // Extract agent output block — try multi-line JSON first, then single line
  const outputMatch = AGENT_OUTPUT_RE.exec(stdout);
  if (outputMatch) {
    output = (outputMatch[1] || outputMatch[2] || '').trim();
  }
  if (!output) {
    // Fallback: grab "Output: ..." single line
    const lineMatch = OUTPUT_LINE_RE.exec(stdout);
    if (lineMatch) {
      output = lineMatch[1].trim();
    }
  }
  if (!output) {
    // Last resort: grab everything after "agent completed with status: COMPLETED"
    const completedIdx = stdout.indexOf('Status: COMPLETED');
    if (completedIdx !== -1) {
      // Look for the Output: block in printResult output
      const afterStatus = stdout.slice(completedIdx);
      const outputIdx = afterStatus.indexOf('Output:');
      if (outputIdx !== -1) {
        const rest = afterStatus.slice(outputIdx + 7).trim();
        // Take until "Events:" or "Tool Calls:" or end
        const endIdx = rest.search(/\n\s*(?:Events|Tool [Cc]alls|Messages):/);
        output = endIdx !== -1 ? rest.slice(0, endIdx).trim() : rest.trim();
      }
    }
  }

  // Extract metadata
  const wfMatch = EXECUTION_ID_RE.exec(stdout);
  if (wfMatch) executionId = wfMatch[1];

  const tcMatch = TOOL_CALLS_RE.exec(stdout);
  if (tcMatch) toolCalls = parseInt(tcMatch[1], 10);

  const statusMatch = STATUS_RE.exec(stdout);
  if (statusMatch) statusFromOutput = statusMatch[1];

  return { output, toolCalls, executionId, statusFromOutput };
}

/**
 * Parse events from stdout JSON lines (events prefixed with `EVENT:` or embedded JSON).
 */
function parseEvents(stdout: string): AgentEvent[] {
  const events: AgentEvent[] = [];

  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();

    // Check for EVENT: prefix
    if (trimmed.startsWith('EVENT:')) {
      try {
        const event = JSON.parse(trimmed.slice(6)) as AgentEvent;
        events.push(event);
      } catch {
        // Skip malformed event lines
      }
      continue;
    }

    // Check for raw JSON event objects
    if (trimmed.startsWith('{"type":')) {
      try {
        const event = JSON.parse(trimmed) as AgentEvent;
        if (event.type) events.push(event);
      } catch {
        // Skip malformed JSON
      }
      continue;
    }

    // Parse human-readable event lines from streaming examples
    if (trimmed.startsWith('[thinking]')) {
      events.push({ type: 'thinking', content: trimmed.slice(10).trim() });
    } else if (trimmed.startsWith('[tool_call]')) {
      const rest = trimmed.slice(11).trim();
      const parenIdx = rest.indexOf('(');
      const toolName = parenIdx > 0 ? rest.slice(0, parenIdx) : rest;
      events.push({ type: 'tool_call', toolName: toolName.trim() });
    } else if (trimmed.startsWith('[tool_result]')) {
      const rest = trimmed.slice(13).trim();
      const arrowIdx = rest.indexOf('->');
      const toolName = arrowIdx > 0 ? rest.slice(0, arrowIdx).trim() : '';
      const result = arrowIdx > 0 ? rest.slice(arrowIdx + 2).trim() : rest;
      events.push({ type: 'tool_result', toolName, result });
    } else if (trimmed.startsWith('[error]')) {
      events.push({ type: 'error', content: trimmed.slice(7).trim() });
    } else if (trimmed.startsWith('[done]') || trimmed.startsWith('Result:')) {
      events.push({ type: 'done' });
    }
  }

  return events;
}

/**
 * Detect errors from stdout/stderr content.
 */
function detectErrors(stdout: string, stderr: string): boolean {
  const combined = stdout + '\n' + stderr;
  return (
    combined.includes('Traceback') ||
    combined.includes('workflow FAILED') ||
    (stderr.trim() !== '' &&
      ['Error', 'Exception', 'Traceback', 'FAILED'].some((kw) => stderr.includes(kw)))
  );
}

/**
 * Execute an example as a subprocess and collect results.
 *
 * @param examplePath - Absolute or relative path to the .ts example file
 * @param env - Environment variables to pass to the subprocess
 * @param timeout - Timeout in seconds
 * @returns ExecutionResult with parsed output, events, and status
 */
export async function executeExample(
  examplePath: string,
  env: Record<string, string>,
  timeout: number,
): Promise<ExecutionResult> {
  const exampleName = path
    .basename(examplePath, '.ts')
    .replace(/^examples\//, '');

  // Derive a friendlier name from the path
  const parts = examplePath.split('/');
  const examplesIdx = parts.indexOf('examples');
  let friendlyName = exampleName;
  if (examplesIdx !== -1) {
    friendlyName = parts
      .slice(examplesIdx + 1)
      .join('/')
      .replace(/\.ts$/, '');
  }

  const startTime = Date.now();

  const resolvedEnv: Record<string, string> = {
    ...process.env as Record<string, string>,
    ...env,
  };

  return new Promise<ExecutionResult>((resolve) => {
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    let settled = false;

    const child = spawn('npx', ['tsx', examplePath], {
      env: resolvedEnv,
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: timeout * 1000,
    });

    // Close stdin immediately — examples shouldn't need interactive input
    child.stdin.end();

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      // Force kill after 5s if still alive
      setTimeout(() => {
        if (!settled) child.kill('SIGKILL');
      }, 5000);
    }, timeout * 1000);

    child.stdout.on('data', (data: Buffer) => {
      stdout += data.toString();
    });

    child.stderr.on('data', (data: Buffer) => {
      stderr += data.toString();
    });

    child.on('close', (code) => {
      settled = true;
      clearTimeout(timer);
      const duration = (Date.now() - startTime) / 1000;
      const exitCode = code ?? 1;

      if (timedOut) {
        resolve({
          exampleName: friendlyName,
          exitCode,
          stdout,
          stderr,
          duration,
          status: 'TIMEOUT',
          output: '',
          events: [],
          toolCalls: 0,
        });
        return;
      }

      const parsed = parseStdout(stdout);
      const events = parseEvents(stdout);
      const hasErrors = detectErrors(stdout, stderr);
      const workflowFailed = stdout.includes('workflow FAILED') || stderr.includes('workflow FAILED');

      let status: ExecutionResult['status'];
      if (workflowFailed) {
        status = 'FAILED';
      } else if (exitCode === 0 && !hasErrors) {
        status = 'COMPLETED';
      } else if (exitCode !== 0) {
        status = 'FAILED';
      } else {
        status = 'ERROR';
      }

      resolve({
        exampleName: friendlyName,
        exitCode,
        stdout,
        stderr,
        duration,
        status,
        output: parsed.output,
        events,
        toolCalls: parsed.toolCalls,
        executionId: parsed.executionId,
      });
    });

    child.on('error', (err) => {
      settled = true;
      clearTimeout(timer);
      const duration = (Date.now() - startTime) / 1000;
      resolve({
        exampleName: friendlyName,
        exitCode: 1,
        stdout,
        stderr: stderr + '\n' + String(err),
        duration,
        status: 'ERROR',
        output: '',
        events: [],
        toolCalls: 0,
      });
    });
  });
}
