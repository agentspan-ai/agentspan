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
  workflowId?: string;
}

// Regex patterns for parsing stdout (mirroring Python's parsing.py)
const WORKFLOW_ID_RE = /Workflow ID: (\S+)/;
const TOOL_CALLS_RE = /Tool calls: (\d+)/;
const STATUS_RE = /Status: (\S+)/;
// Output block between the box-drawing border and metadata lines
const AGENT_OUTPUT_RE =
  /[╘└]═+[╛┘]\s*\n(.*?)(?=\nTool calls:|\nTokens:|\nFinish reason:|\nWorkflow ID:|\n\n\n|$)/s;

/**
 * Parse stdout for structured agent output data.
 */
function parseStdout(stdout: string): {
  output: string;
  toolCalls: number;
  workflowId?: string;
  statusFromOutput?: string;
} {
  let output = '';
  let toolCalls = 0;
  let workflowId: string | undefined;
  let statusFromOutput: string | undefined;

  // Extract agent output block
  const outputMatch = AGENT_OUTPUT_RE.exec(stdout);
  if (outputMatch) {
    output = outputMatch[1].trim();
  }

  // Extract metadata
  const wfMatch = WORKFLOW_ID_RE.exec(stdout);
  if (wfMatch) workflowId = wfMatch[1];

  const tcMatch = TOOL_CALLS_RE.exec(stdout);
  if (tcMatch) toolCalls = parseInt(tcMatch[1], 10);

  const statusMatch = STATUS_RE.exec(stdout);
  if (statusMatch) statusFromOutput = statusMatch[1];

  return { output, toolCalls, workflowId, statusFromOutput };
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
 * @param native - If true, set AGENTSPAN_NATIVE_MODE=1
 * @returns ExecutionResult with parsed output, events, and status
 */
export async function executeExample(
  examplePath: string,
  env: Record<string, string>,
  timeout: number,
  native?: boolean,
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

  if (native) {
    resolvedEnv['AGENTSPAN_NATIVE_MODE'] = '1';
  }

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
        workflowId: parsed.workflowId,
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
