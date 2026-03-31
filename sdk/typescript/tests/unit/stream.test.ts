import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AgentStream } from '../../src/stream.js';

// ── Helper: create a ReadableStream from SSE text ───────

function createSSEStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function mockFetch(body: ReadableStream<Uint8Array>, status = 200): void {
  global.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    body,
    text: async () => '',
    headers: new Headers(),
  });
}

// ── SSE Parsing ─────────────────────────────────────────

describe('AgentStream', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('SSE parsing', () => {
    it('parses basic SSE events', async () => {
      const sseChunks = [
        'event:thinking\ndata:{"content":"reasoning..."}\n\n',
        'event:done\ndata:{"output":"finished"}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      expect(events).toHaveLength(2);
      expect(events[0].type).toBe('thinking');
      expect(events[0].content).toBe('reasoning...');
      expect(events[1].type).toBe('done');
    });

    it('handles event type and id fields', async () => {
      const sseChunks = [
        'event:tool_call\nid:ev-1\ndata:{"toolName":"search","args":{"query":"test"}}\n\n',
        'event:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      expect(events[0].type).toBe('tool_call');
      expect(events[0].toolName).toBe('search');
      expect(events[0].args).toEqual({ query: 'test' });
    });

    it('handles multi-line data fields', async () => {
      const sseChunks = [
        'event:message\ndata:{"content":\ndata:"multi-line"}\n\n',
        'event:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      // Multi-line data is concatenated with newlines
      expect(events.length).toBeGreaterThanOrEqual(1);
    });

    it('handles partial chunks across reads', async () => {
      // Split an event across two chunks
      const sseChunks = [
        'event:thinking\nda',
        'ta:{"content":"hello"}\n\nevent:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      expect(events).toHaveLength(2);
      expect(events[0].type).toBe('thinking');
      expect(events[0].content).toBe('hello');
    });

    it('skips heartbeat comments', async () => {
      const sseChunks = [
        ':heartbeat\n\nevent:thinking\ndata:{"content":"hi"}\n\n:ping\n\nevent:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      // Should have thinking and done, not heartbeats
      expect(events).toHaveLength(2);
      expect(events[0].type).toBe('thinking');
      expect(events[1].type).toBe('done');
    });

    it('falls back to data.type when event field is missing', async () => {
      const sseChunks = [
        'data:{"type":"message","content":"hello"}\n\n',
        'event:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      expect(events[0].type).toBe('message');
      expect(events[0].content).toBe('hello');
    });

    it('handles non-JSON data gracefully', async () => {
      const sseChunks = [
        'event:message\ndata:plain text here\n\n',
        'event:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      expect(events[0].type).toBe('message');
      expect(events[0].content).toBe('plain text here');
    });
  });

  describe('event key stripping', () => {
    it('strips _agent_state from event args', async () => {
      const sseChunks = [
        'event:tool_call\ndata:{"toolName":"test","args":{"input":"val","_agent_state":"secret","method":"POST"}}\n\n',
        'event:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      expect(events[0].args).toBeDefined();
      expect(events[0].args!['input']).toBe('val');
      expect(events[0].args).not.toHaveProperty('_agent_state');
      expect(events[0].args).not.toHaveProperty('method');
    });
  });

  describe('events array', () => {
    it('captures all events in the events array', async () => {
      const sseChunks = [
        'event:thinking\ndata:{"content":"a"}\n\n',
        'event:tool_call\ndata:{"toolName":"b"}\n\n',
        'event:done\ndata:{}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      for await (const _event of stream) {
        // drain
      }

      expect(stream.events).toHaveLength(3);
      expect(stream.events[0].type).toBe('thinking');
      expect(stream.events[1].type).toBe('tool_call');
      expect(stream.events[2].type).toBe('done');
    });
  });

  describe('HITL methods', () => {
    it('respond calls respondFn with body', async () => {
      const respondFn = vi.fn().mockResolvedValue(undefined);
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        respondFn,
      );

      await stream.respond({ answer: 'yes' });
      expect(respondFn).toHaveBeenCalledWith({ answer: 'yes' });
    });

    it('approve calls respondFn with approved: true', async () => {
      const respondFn = vi.fn().mockResolvedValue(undefined);
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        respondFn,
      );

      await stream.approve({ extra: 'data' });
      expect(respondFn).toHaveBeenCalledWith({
        approved: true,
        extra: 'data',
      });
    });

    it('approve works without extra output', async () => {
      const respondFn = vi.fn().mockResolvedValue(undefined);
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        respondFn,
      );

      await stream.approve();
      expect(respondFn).toHaveBeenCalledWith({ approved: true });
    });

    it('reject calls respondFn with approved: false', async () => {
      const respondFn = vi.fn().mockResolvedValue(undefined);
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        respondFn,
      );

      await stream.reject('not allowed');
      expect(respondFn).toHaveBeenCalledWith({
        approved: false,
        reason: 'not allowed',
      });
    });

    it('reject works without reason', async () => {
      const respondFn = vi.fn().mockResolvedValue(undefined);
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        respondFn,
      );

      await stream.reject();
      expect(respondFn).toHaveBeenCalledWith({
        approved: false,
        reason: undefined,
      });
    });

    it('send calls respondFn with message', async () => {
      const respondFn = vi.fn().mockResolvedValue(undefined);
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        respondFn,
      );

      await stream.send('hello agent');
      expect(respondFn).toHaveBeenCalledWith({ message: 'hello agent' });
    });
  });

  describe('getResult', () => {
    it('builds AgentResult from done event', async () => {
      const sseChunks = [
        'event:thinking\ndata:{"content":"thinking..."}\n\n',
        'event:done\ndata:{"output":{"answer":42}}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const result = await stream.getResult();
      expect(result.status).toBe('COMPLETED');
      expect(result.executionId).toBe('wf-1');
      expect(result.events.length).toBe(2);
    });

    it('builds FAILED result when no done event but error event exists', async () => {
      const sseChunks = [
        'event:error\ndata:{"content":"something broke"}\n\n',
      ];

      mockFetch(createSSEStream(sseChunks));

      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-1',
        vi.fn(),
      );

      const result = await stream.getResult();
      expect(result.status).toBe('FAILED');
      expect(result.error).toBe('something broke');
    });
  });

  describe('executionId', () => {
    it('exposes executionId', () => {
      const stream = new AgentStream(
        'http://localhost/sse',
        {},
        'wf-123',
        vi.fn(),
      );
      expect(stream.executionId).toBe('wf-123');
    });
  });
});
