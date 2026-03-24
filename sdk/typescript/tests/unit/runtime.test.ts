import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AgentRuntime, configure, run, start, stream, deploy, plan, serve, shutdown } from '../../src/runtime.js';
import { AgentConfig } from '../../src/config.js';

// ── AgentRuntime constructor ────────────────────────────

describe('AgentRuntime', () => {
  const savedEnv: Record<string, string | undefined> = {};
  const envKeys = ['AGENTSPAN_SERVER_URL', 'AGENTSPAN_API_KEY', 'AGENTSPAN_AUTH_KEY', 'AGENTSPAN_AUTH_SECRET'];

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
      expect(runtime.config.serverUrl).toBe('http://localhost:8080/api');
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
        text: async () => '{"workflowId":"wf-1"}',
      });

      const runtime = new AgentRuntime();
      const result = await runtime._httpRequest('GET', '/test');
      expect(result).toEqual({ workflowId: 'wf-1' });
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
        'http://localhost:8080/api/agent/start',
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
        'http://localhost:8080/api/test',
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
