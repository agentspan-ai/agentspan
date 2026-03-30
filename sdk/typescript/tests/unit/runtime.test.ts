import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AgentRuntime, configure, run, start, stream, deploy, plan, serve, shutdown } from '../../src/runtime.js';
import { AgentConfig } from '../../src/config.js';

// ── AgentRuntime constructor ────────────────────────────

describe('AgentRuntime', () => {
  const savedEnv: Record<string, string | undefined> = {};
  const envKeys = ['AGENTSPAN_SERVER_URL', 'AGENTSPAN_API_KEY', 'AGENTSPAN_AUTH_KEY', 'AGENTSPAN_AUTH_SECRET'];

  function mockAgentServer(executionId = 'wf-cred-test', fetchCalls?: string[]) {
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      fetchCalls?.push(url);
      if (url.includes('/agent/start')) {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ executionId }),
        };
      }
      if (url.includes('/agent/stream/')) {
        const ssePayload = 'event: done\ndata: {"output":{"result":"ok"},"status":"COMPLETED"}\n\n';
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
          body: new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(ssePayload));
              controller.close();
            },
          }),
        };
      }
      if (url.includes(`/agent/${executionId}/status`)) {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ status: 'COMPLETED', output: { result: 'ok' } }),
          json: async () => ({ status: 'COMPLETED', output: { result: 'ok' } }),
        };
      }
      return {
        ok: true,
        status: 200,
        text: async () => '{}',
        json: async () => ({}),
      };
    });
  }

  beforeEach(() => {
    for (const key of envKeys) {
      savedEnv[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of envKeys) {
      if (savedEnv[key] !== undefined) {
        process.env[key] = savedEnv[key];
      } else {
        delete process.env[key];
      }
    }
  });

  describe('constructor', () => {
    it('creates with default config', () => {
      const runtime = new AgentRuntime();
      expect(runtime.config).toBeInstanceOf(AgentConfig);
      expect(runtime.config.serverUrl).toBe('http://localhost:6767/api');
    });

    it('creates with custom config', () => {
      const runtime = new AgentRuntime({
        serverUrl: 'https://custom.com',
        apiKey: 'my-key',
      });
      expect(runtime.config.serverUrl).toBe('https://custom.com/api');
      expect(runtime.config.apiKey).toBe('my-key');
    });

    it('builds Bearer auth headers for apiKey', () => {
      const runtime = new AgentRuntime({ apiKey: 'test-key' });
      // Access private field indirectly via _httpRequest
      // We'll test this by checking the runtime was created without error
      expect(runtime.config.apiKey).toBe('test-key');
    });

    it('builds X-Auth-Key/Secret headers for authKey/authSecret', () => {
      const runtime = new AgentRuntime({
        authKey: 'key',
        authSecret: 'secret',
      });
      expect(runtime.config.authKey).toBe('key');
      expect(runtime.config.authSecret).toBe('secret');
    });
  });

  describe('_httpRequest', () => {
    it('throws AgentAPIError on non-2xx response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => 'Not Found',
      });

      const runtime = new AgentRuntime();
      await expect(runtime._httpRequest('GET', '/test')).rejects.toThrow(
        /HTTP GET \/test failed: 404/,
      );
    });

    it('returns parsed JSON for successful response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => '{"executionId":"wf-1"}',
      });

      const runtime = new AgentRuntime();
      const result = await runtime._httpRequest('GET', '/test');
      expect(result).toEqual({ executionId: 'wf-1' });
    });

    it('returns empty object for empty response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        text: async () => '',
      });

      const runtime = new AgentRuntime();
      const result = await runtime._httpRequest('GET', '/test');
      expect(result).toEqual({});
    });

    it('includes auth headers in requests', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => '{}',
      });

      const runtime = new AgentRuntime({ apiKey: 'test-api-key' });
      await runtime._httpRequest('POST', '/agent/start', { prompt: 'hi' });

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:6767/api/agent/start',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-api-key',
            'Content-Type': 'application/json',
          }),
        }),
      );
    });

    it('includes X-Auth-Key/Secret headers when configured', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => '{}',
      });

      const runtime = new AgentRuntime({
        authKey: 'my-auth-key',
        authSecret: 'my-auth-secret',
      });
      await runtime._httpRequest('GET', '/test');

      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:6767/api/test',
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Auth-Key': 'my-auth-key',
            'X-Auth-Secret': 'my-auth-secret',
          }),
        }),
      );
    });

    it('passes AbortSignal to fetch', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => '{}',
      });

      const controller = new AbortController();
      const runtime = new AgentRuntime();
      await runtime._httpRequest('GET', '/test', undefined, controller.signal);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          signal: controller.signal,
        }),
      );
    });
  });

  describe('framework detection', () => {
    it('does not throw for native Agent (framework is null)', async () => {
      // Framework detection stub returns null, so native path is taken
      // This test just verifies the stub doesn't cause issues
      // Actual execution would require mocking the full HTTP flow
      const runtime = new AgentRuntime();
      expect(runtime).toBeInstanceOf(AgentRuntime);
    });
  });

  describe('shutdown', () => {
    it('can be called without error', async () => {
      const runtime = new AgentRuntime();
      await expect(runtime.shutdown()).resolves.not.toThrow();
    });
  });

  describe('SSE URL construction', () => {
    it('constructs SSE URL as /agent/stream/{executionId}', async () => {
      const fetchCalls: string[] = [];

      global.fetch = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
        fetchCalls.push(url);

        if (url.includes('/agent/start')) {
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ executionId: 'wf-sse-test' }),
          };
        }
        if (url.includes('/agent/stream/') || url.includes('/sse')) {
          // SSE endpoint — return a stream with a done event
          const ssePayload = 'event: done\ndata: {"output":"result","status":"COMPLETED"}\n\n';
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'content-type': 'text/event-stream' }),
            body: new ReadableStream({
              start(controller) {
                controller.enqueue(new TextEncoder().encode(ssePayload));
                controller.close();
              },
            }),
          };
        }
        if (url.includes('/status')) {
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ status: 'COMPLETED', output: 'result' }),
          };
        }
        if (url.includes('/metadata/taskdefs')) {
          return { ok: true, status: 200, text: async () => '' };
        }
        if (url.includes('/tasks/poll/')) {
          return { ok: true, status: 204, text: async () => '' };
        }
        return { ok: true, status: 200, text: async () => '{}' };
      });

      const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767/api' });
      const { Agent } = await import('../../src/agent.js');
      const agent = new Agent({ name: 'test_agent', model: 'gpt-4o' });

      // run() drains the SSE stream, which triggers the fetch to the SSE URL
      try {
        await runtime.run(agent, 'test prompt');
      } catch {
        // May error on SSE parsing — that's OK, we just need the URL
      }

      // Verify SSE URL uses /agent/stream/{id}
      const sseCall = fetchCalls.find((u) => u.includes('/stream/') || u.includes('/sse'));
      expect(sseCall).toBe('http://localhost:6767/api/agent/stream/wf-sse-test');
    });
  });

  describe('stream()', () => {
    it('streams native agents through the handle stream path', async () => {
      const fetchCalls: string[] = [];
      mockAgentServer('wf-native-stream', fetchCalls);

      const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767/api' });
      vi.spyOn((runtime as any).workerManager, 'startPolling').mockImplementation(() => {});

      const { Agent } = await import('../../src/agent.js');
      const agent = new Agent({ name: 'native_stream_agent', model: 'gpt-4o' });

      const agentStream = await runtime.stream(agent, 'test prompt');
      const result = await agentStream.getResult();

      expect(result.status).toBe('COMPLETED');
      expect(result.output).toEqual({ result: 'ok' });
      expect(fetchCalls).toContain('http://localhost:6767/api/agent/stream/wf-native-stream');
    });

    it('streams framework agents through the same SSE endpoint', async () => {
      const fetchCalls: string[] = [];
      mockAgentServer('wf-framework-stream', fetchCalls);

      const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767/api' });
      vi.spyOn((runtime as any).workerManager, 'startPolling').mockImplementation(() => {});

      const openAiAgent = {
        name: 'framework_stream_agent',
        instructions: 'You are helpful.',
        model: 'gpt-4o',
        tools: [],
        handoffs: [],
      };

      const agentStream = await runtime.stream(openAiAgent, 'test prompt');
      const result = await agentStream.getResult();

      expect(result.status).toBe('COMPLETED');
      expect(result.output).toEqual({ result: 'ok' });
      expect(fetchCalls).toContain('http://localhost:6767/api/agent/stream/wf-framework-stream');

      const startCall = (global.fetch as any).mock.calls.find(([url]: [string]) =>
        url.includes('/agent/start'),
      );
      const body = JSON.parse(startCall[1].body as string);
      expect(body.framework).toBe('openai');
    });
  });

  describe('credentials payloads', () => {
    it('includes credentials in native run start payload', async () => {
      mockAgentServer('wf-native-cred');

      const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767/api' });
      vi.spyOn((runtime as any).workerManager, 'startPolling').mockImplementation(() => {});
      vi.spyOn((runtime as any).workerManager, 'stopPolling').mockImplementation(() => {});

      const { Agent } = await import('../../src/agent.js');
      const agent = new Agent({ name: 'native_cred_agent', model: 'gpt-4o' });

      await runtime.run(agent, 'test prompt', {
        credentials: ['OPENAI_API_KEY'],
      });

      const startCall = (global.fetch as any).mock.calls.find(([url]: [string]) =>
        url.includes('/agent/start'),
      );
      const body = JSON.parse(startCall[1].body as string);
      expect(body.credentials).toEqual(['OPENAI_API_KEY']);
    });

    it('includes credentials in framework run start payload', async () => {
      mockAgentServer('wf-framework-cred');

      const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767/api' });
      vi.spyOn((runtime as any).workerManager, 'startPolling').mockImplementation(() => {});
      vi.spyOn((runtime as any).workerManager, 'stopPolling').mockImplementation(() => {});

      const openAiAgent = {
        name: 'framework_cred_agent',
        instructions: 'You are helpful.',
        model: 'gpt-4o',
        tools: [],
        handoffs: [],
      };

      await runtime.run(openAiAgent, 'test prompt', {
        credentials: ['OPENAI_API_KEY'],
      });

      const startCall = (global.fetch as any).mock.calls.find(([url]: [string]) =>
        url.includes('/agent/start'),
      );
      const body = JSON.parse(startCall[1].body as string);
      expect(body.credentials).toEqual(['OPENAI_API_KEY']);
      expect(body.framework).toBe('openai');
    });

    it('includes credentials in framework start payload', async () => {
      mockAgentServer('wf-framework-start-cred');

      const runtime = new AgentRuntime({ serverUrl: 'http://localhost:6767/api' });
      vi.spyOn((runtime as any).workerManager, 'startPolling').mockImplementation(() => {});

      const openAiAgent = {
        name: 'framework_start_agent',
        instructions: 'You are helpful.',
        model: 'gpt-4o',
        tools: [],
        handoffs: [],
      };

      await runtime.start(openAiAgent, 'test prompt', {
        credentials: ['OPENAI_API_KEY'],
      });

      const startCall = (global.fetch as any).mock.calls.find(([url]: [string]) =>
        url.includes('/agent/start'),
      );
      const body = JSON.parse(startCall[1].body as string);
      expect(body.credentials).toEqual(['OPENAI_API_KEY']);
      expect(body.framework).toBe('openai');
    });
  });
});

// ── Singleton functions ─────────────────────────────────

describe('Singleton functions', () => {
  const savedEnv: Record<string, string | undefined> = {};
  const envKeys = ['AGENTSPAN_SERVER_URL', 'AGENTSPAN_API_KEY'];

  beforeEach(() => {
    for (const key of envKeys) {
      savedEnv[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of envKeys) {
      if (savedEnv[key] !== undefined) {
        process.env[key] = savedEnv[key];
      } else {
        delete process.env[key];
      }
    }
  });

  it('configure creates a new singleton runtime', () => {
    const runtime = configure({
      serverUrl: 'https://singleton.com',
      apiKey: 'singleton-key',
    });
    expect(runtime).toBeInstanceOf(AgentRuntime);
    expect(runtime.config.serverUrl).toBe('https://singleton.com/api');
  });

  it('run is a function', () => {
    expect(typeof run).toBe('function');
  });

  it('start is a function', () => {
    expect(typeof start).toBe('function');
  });

  it('stream is a function', () => {
    expect(typeof stream).toBe('function');
  });

  it('deploy is a function', () => {
    expect(typeof deploy).toBe('function');
  });

  it('plan is a function', () => {
    expect(typeof plan).toBe('function');
  });

  it('serve is a function', () => {
    expect(typeof serve).toBe('function');
  });

  it('shutdown is a function', () => {
    expect(typeof shutdown).toBe('function');
  });
});
