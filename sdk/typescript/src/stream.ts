import type { AgentEvent, AgentResult, AgentStatus } from './types.js';
import { stripInternalEventKeys } from './types.js';
import { AgentAPIError, SSETimeoutError, AgentspanError } from './errors.js';
import { makeAgentResult } from './result.js';

// ── Constants ───────────────────────────────────────────

const SSE_TIMEOUT_MS = 15_000;
const MAX_RECONNECT_RETRIES = 5;
const POLL_INTERVAL_MS = 500;

// ── AgentStream ─────────────────────────────────────────

export type RespondFn = (body: unknown) => Promise<void>;

/**
 * SSE-based event stream for agent execution.
 * Implements AsyncIterable<AgentEvent> for use with `for await...of`.
 */
export class AgentStream implements AsyncIterable<AgentEvent> {
  readonly executionId: string;
  readonly events: AgentEvent[] = [];

  private readonly url: string;
  private readonly headers: Record<string, string>;
  private readonly respondFn: RespondFn;
  private readonly serverUrl: string;
  private done = false;

  constructor(
    url: string,
    headers: Record<string, string>,
    executionId: string,
    respondFn: RespondFn,
    serverUrl?: string,
  ) {
    this.url = url;
    this.headers = headers;
    this.executionId = executionId;
    this.respondFn = respondFn;
    this.serverUrl = serverUrl ?? '';
  }

  // ── AsyncIterable implementation ─────────────────────

  [Symbol.asyncIterator](): AsyncIterableIterator<AgentEvent> {
    return this._streamEvents();
  }

  private async *_streamEvents(): AsyncIterableIterator<AgentEvent> {
    let lastEventId = '';
    let retries = 0;

    try {
      while (!this.done && retries <= MAX_RECONNECT_RETRIES) {
        try {
          yield* this._connectAndStream(lastEventId);
          // If _connectAndStream returned without error, we're done
          break;
        } catch (error) {
          if (error instanceof SSETimeoutError) {
            // Fall through to polling
            yield* this._pollForCompletion();
            break;
          }

          retries++;
          if (retries > MAX_RECONNECT_RETRIES) {
            // Exceeded retries, fall through to polling
            yield* this._pollForCompletion();
            break;
          }

          // Exponential backoff: 1s * attempt
          await sleep(1000 * retries);

          // Set lastEventId for reconnection
          if (this.events.length > 0) {
            const lastEvent = this.events[this.events.length - 1];
            if (lastEvent && (lastEvent as unknown as Record<string, unknown>)['_eventId']) {
              lastEventId = String((lastEvent as unknown as Record<string, unknown>)['_eventId']);
            }
          }
        }
      }
    } finally {
      // Mark stream as done once iteration completes
      this.done = true;
    }
  }

  /**
   * Connect to SSE endpoint and stream events.
   */
  private async *_connectAndStream(lastEventId: string): AsyncIterableIterator<AgentEvent> {
    const requestHeaders: Record<string, string> = {
      ...this.headers,
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    };

    if (lastEventId) {
      requestHeaders['Last-Event-ID'] = lastEventId;
    }

    const response = await fetch(this.url, {
      method: 'GET',
      headers: requestHeaders,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new AgentAPIError(
        `SSE connection failed: ${response.status}`,
        response.status,
        body,
      );
    }

    if (!response.body) {
      throw new AgentspanError('SSE response has no body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';
    let currentEventType = '';
    let currentEventId = '';
    let currentData = '';
    let lastRealEventTime = Date.now();

    try {
      while (!this.done) {
        // Check for SSE timeout
        if (Date.now() - lastRealEventTime > SSE_TIMEOUT_MS) {
          throw new SSETimeoutError('No real events received within timeout window');
        }

        const readPromise = reader.read();
        const timeoutMs = Math.max(100, SSE_TIMEOUT_MS - (Date.now() - lastRealEventTime) + 100);

        let timedOut = false;
        const timeoutPromise = sleep(timeoutMs).then(() => {
          timedOut = true;
          return { done: true as const, value: undefined as Uint8Array | undefined };
        });

        const { done: readerDone, value } = await Promise.race([readPromise, timeoutPromise]);

        if (timedOut) {
          // Timeout on read — check if SSE timeout exceeded
          if (Date.now() - lastRealEventTime > SSE_TIMEOUT_MS) {
            throw new SSETimeoutError('No real events received within timeout window');
          }
          continue;
        }

        if (readerDone) {
          // Process any remaining buffer
          if (buffer.trim()) {
            const event = this._parseSSEBlock(currentEventType, currentEventId, currentData);
            if (event) {
              lastRealEventTime = Date.now();
              this.events.push(event);
              yield event;
              if (event.type === 'done') {
                this.done = true;
              }
            }
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        // Keep last incomplete line in buffer
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line === '') {
            // Blank line: dispatch event
            if (currentData || currentEventType) {
              const event = this._parseSSEBlock(currentEventType, currentEventId, currentData);
              if (event) {
                lastRealEventTime = Date.now();
                this.events.push(event);
                yield event;
                if (event.type === 'done') {
                  this.done = true;
                  return;
                }
              }
            }
            currentEventType = '';
            currentEventId = '';
            currentData = '';
          } else if (line.startsWith(':')) {
            // Comment/heartbeat — skip but don't update lastRealEventTime
            continue;
          } else if (line.startsWith('event:')) {
            currentEventType = line.slice(6).trim();
          } else if (line.startsWith('id:')) {
            currentEventId = line.slice(3).trim();
          } else if (line.startsWith('data:')) {
            const dataContent = line.slice(5).trim();
            if (currentData) {
              currentData += '\n' + dataContent;
            } else {
              currentData = dataContent;
            }
          }
        }
      }
    } finally {
      try {
        reader.cancel();
      } catch {
        // Ignore cancel errors
      }
    }
  }

  /**
   * Parse an SSE block into an AgentEvent.
   */
  private _parseSSEBlock(
    eventType: string,
    eventId: string,
    data: string,
  ): AgentEvent | null {
    if (!data && !eventType) return null;

    let parsed: Record<string, unknown> = {};
    if (data) {
      try {
        parsed = JSON.parse(data);
      } catch {
        // Non-JSON data: wrap as content
        parsed = { content: data };
      }
    }

    // Determine type: event field takes priority, then data.type
    const type = eventType || (parsed.type as string) || 'message';

    const event: AgentEvent = {
      type,
      ...parsed,
    };

    // Store event ID internally for reconnection
    if (eventId) {
      (event as unknown as Record<string, unknown>)['_eventId'] = eventId;
    }

    // Strip internal keys from args
    return stripInternalEventKeys(event);
  }

  // ── Polling fallback ─────────────────────────────────

  /**
   * Switch to polling when SSE fails or times out.
   */
  private async *_pollForCompletion(): AsyncIterableIterator<AgentEvent> {
    if (!this.serverUrl) return;

    while (!this.done) {
      try {
        const status = await this._getStatus();
        if (!status) {
          await sleep(POLL_INTERVAL_MS);
          continue;
        }

        if (status.isWaiting) {
          const waitEvent: AgentEvent = {
            type: 'waiting',
            executionId: this.executionId,
            timestamp: Date.now(),
          };
          this.events.push(waitEvent);
          yield waitEvent;
        }

        if (status.isComplete) {
          const doneEvent: AgentEvent = {
            type: 'done',
            output: status.output,
            executionId: this.executionId,
            timestamp: Date.now(),
          };
          this.events.push(doneEvent);
          yield doneEvent;
          this.done = true;
          break;
        }
      } catch {
        // Swallow polling errors
      }

      await sleep(POLL_INTERVAL_MS);
    }
  }

  /**
   * Get agent status for polling fallback.
   */
  private async _getStatus(): Promise<AgentStatus | null> {
    const url = `${this.serverUrl}/agent/${this.executionId}/status`;
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: this.headers,
      });

      if (!response.ok) return null;
      return (await response.json()) as AgentStatus;
    } catch {
      return null;
    }
  }

  // ── HITL methods ─────────────────────────────────────

  /**
   * Send a response to a waiting agent (HITL).
   */
  async respond(output: unknown): Promise<void> {
    await this.respondFn(output);
  }

  /**
   * Approve a HITL request.
   */
  async approve(output?: Record<string, unknown>): Promise<void> {
    await this.respondFn({ approved: true, ...output });
  }

  /**
   * Reject a HITL request.
   */
  async reject(reason?: string): Promise<void> {
    await this.respondFn({ approved: false, reason });
  }

  /**
   * Send a message to a waiting agent.
   */
  async send(message: string): Promise<void> {
    await this.respondFn({ message });
  }

  // ── getResult ────────────────────────────────────────

  /**
   * Drain all remaining events and build an AgentResult.
   */
  async getResult(): Promise<AgentResult> {
    // Drain any remaining events if not already done
    if (!this.done) {
      for await (const _event of this) {
        // Just drain
      }
    }

    // Find the done event
    const doneEvent = this.events.find((e) => e.type === 'done');
    const errorEvent = this.events.findLast((e) => e.type === 'error');

    // Poll the server for the real terminal status — the done SSE event
    // signals stream end, NOT workflow success.
    let serverStatus: Record<string, unknown> | null = null;
    if (this.serverUrl && this.executionId) {
      try {
        const statusUrl = `${this.serverUrl}/agent/${this.executionId}/status`;
        const resp = await fetch(statusUrl, { headers: this.headers });
        if (resp.ok) {
          serverStatus = await resp.json() as Record<string, unknown>;
        }
      } catch {
        // Fall back to stream-based inference
      }
    }

    const status = (serverStatus?.status as string)
      ?? (errorEvent ? 'FAILED' : (doneEvent ? 'COMPLETED' : 'COMPLETED'));
    const output = (serverStatus?.output as unknown) ?? doneEvent?.output ?? null;
    const error = (serverStatus?.reasonForIncompletion as string)
      ?? errorEvent?.content;

    return makeAgentResult({
      output,
      executionId: this.executionId,
      status,
      error,
      events: [...this.events],
    });
  }
}

// ── Helpers ─────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
