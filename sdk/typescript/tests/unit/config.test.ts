import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AgentConfig, normalizeServerUrl } from '../../src/config.js';

describe('normalizeServerUrl', () => {
  it('appends /api when missing', () => {
    expect(normalizeServerUrl('http://localhost:6767')).toBe(
      'http://localhost:6767/api',
    );
  });

  it('does not double-append /api', () => {
    expect(normalizeServerUrl('http://localhost:6767/api')).toBe(
      'http://localhost:6767/api',
    );
  });

  it('strips trailing slashes before appending', () => {
    expect(normalizeServerUrl('http://localhost:6767/')).toBe(
      'http://localhost:6767/api',
    );
    expect(normalizeServerUrl('http://localhost:6767///')).toBe(
      'http://localhost:6767/api',
    );
  });

  it('strips trailing slash after /api', () => {
    expect(normalizeServerUrl('http://localhost:6767/api/')).toBe(
      'http://localhost:6767/api',
    );
  });

  it('handles custom paths before /api', () => {
    expect(normalizeServerUrl('https://cloud.example.com/v1/api')).toBe(
      'https://cloud.example.com/v1/api',
    );
  });

  it('appends /api to custom base paths', () => {
    expect(normalizeServerUrl('https://cloud.example.com/v1')).toBe(
      'https://cloud.example.com/v1/api',
    );
  });
});

describe('AgentConfig', () => {
  // Save and restore env vars to avoid test pollution
  const savedEnv: Record<string, string | undefined> = {};
  const envKeys = [
    'AGENTSPAN_SERVER_URL',
    'AGENTSPAN_API_KEY',
    'AGENTSPAN_AUTH_KEY',
    'AGENTSPAN_AUTH_SECRET',
    'AGENTSPAN_WORKER_POLL_INTERVAL',
    'AGENTSPAN_WORKER_THREADS',
    'AGENTSPAN_AUTO_START_WORKERS',
    'AGENTSPAN_AUTO_START_SERVER',
    'AGENTSPAN_DAEMON_WORKERS',
    'AGENTSPAN_STREAMING_ENABLED',
    'AGENTSPAN_CREDENTIAL_STRICT_MODE',
    'AGENTSPAN_LOG_LEVEL',
    'AGENTSPAN_LLM_RETRY_COUNT',
  ];

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

  describe('defaults', () => {
    it('uses default values when no options or env vars', () => {
      const config = new AgentConfig();

      expect(config.serverUrl).toBe('http://localhost:6767/api');
      expect(config.apiKey).toBe('');
      expect(config.authKey).toBe('');
      expect(config.authSecret).toBe('');
      expect(config.workerPollIntervalMs).toBe(100);
      expect(config.workerThreads).toBe(1);
      expect(config.autoStartWorkers).toBe(true);
      expect(config.autoStartServer).toBe(true);
      expect(config.daemonWorkers).toBe(true);
      expect(config.streamingEnabled).toBe(true);
      expect(config.credentialStrictMode).toBe(false);
      expect(config.logLevel).toBe('INFO');
      expect(config.llmRetryCount).toBe(3);
    });
  });

  describe('constructor overrides', () => {
    it('accepts all options', () => {
      const config = new AgentConfig({
        serverUrl: 'https://my-server.com',
        apiKey: 'key-123',
        authKey: 'auth-key',
        authSecret: 'auth-secret',
        workerPollIntervalMs: 500,
        workerThreads: 4,
        autoStartWorkers: false,
        autoStartServer: false,
        daemonWorkers: false,
        streamingEnabled: false,
        credentialStrictMode: true,
        logLevel: 'DEBUG',
        llmRetryCount: 5,
      });

      expect(config.serverUrl).toBe('https://my-server.com/api');
      expect(config.apiKey).toBe('key-123');
      expect(config.authKey).toBe('auth-key');
      expect(config.authSecret).toBe('auth-secret');
      expect(config.workerPollIntervalMs).toBe(500);
      expect(config.workerThreads).toBe(4);
      expect(config.autoStartWorkers).toBe(false);
      expect(config.autoStartServer).toBe(false);
      expect(config.daemonWorkers).toBe(false);
      expect(config.streamingEnabled).toBe(false);
      expect(config.credentialStrictMode).toBe(true);
      expect(config.logLevel).toBe('DEBUG');
      expect(config.llmRetryCount).toBe(5);
    });

    it('normalizes serverUrl from options', () => {
      const config = new AgentConfig({ serverUrl: 'http://example.com:9090/' });
      expect(config.serverUrl).toBe('http://example.com:9090/api');
    });

    it('does not double-append /api from options', () => {
      const config = new AgentConfig({
        serverUrl: 'http://example.com:9090/api',
      });
      expect(config.serverUrl).toBe('http://example.com:9090/api');
    });
  });

  describe('env var loading', () => {
    it('reads all AGENTSPAN_ env vars', () => {
      process.env.AGENTSPAN_SERVER_URL = 'https://env-server.com';
      process.env.AGENTSPAN_API_KEY = 'env-api-key';
      process.env.AGENTSPAN_AUTH_KEY = 'env-auth-key';
      process.env.AGENTSPAN_AUTH_SECRET = 'env-auth-secret';
      process.env.AGENTSPAN_WORKER_POLL_INTERVAL = '200';
      process.env.AGENTSPAN_WORKER_THREADS = '2';
      process.env.AGENTSPAN_AUTO_START_WORKERS = 'false';
      process.env.AGENTSPAN_AUTO_START_SERVER = 'false';
      process.env.AGENTSPAN_DAEMON_WORKERS = 'false';
      process.env.AGENTSPAN_STREAMING_ENABLED = 'false';
      process.env.AGENTSPAN_CREDENTIAL_STRICT_MODE = 'true';
      process.env.AGENTSPAN_LOG_LEVEL = 'ERROR';
      process.env.AGENTSPAN_LLM_RETRY_COUNT = '5';

      const config = new AgentConfig();

      expect(config.serverUrl).toBe('https://env-server.com/api');
      expect(config.apiKey).toBe('env-api-key');
      expect(config.authKey).toBe('env-auth-key');
      expect(config.authSecret).toBe('env-auth-secret');
      expect(config.workerPollIntervalMs).toBe(200);
      expect(config.workerThreads).toBe(2);
      expect(config.autoStartWorkers).toBe(false);
      expect(config.autoStartServer).toBe(false);
      expect(config.daemonWorkers).toBe(false);
      expect(config.streamingEnabled).toBe(false);
      expect(config.credentialStrictMode).toBe(true);
      expect(config.logLevel).toBe('ERROR');
      expect(config.llmRetryCount).toBe(5);
    });

    it('options override env vars', () => {
      process.env.AGENTSPAN_SERVER_URL = 'https://env-server.com';
      process.env.AGENTSPAN_API_KEY = 'env-api-key';

      const config = new AgentConfig({
        serverUrl: 'https://override.com/api',
        apiKey: 'override-key',
      });

      expect(config.serverUrl).toBe('https://override.com/api');
      expect(config.apiKey).toBe('override-key');
    });

    it('handles boolean env var variations', () => {
      process.env.AGENTSPAN_AUTO_START_WORKERS = '1';
      process.env.AGENTSPAN_AUTO_START_SERVER = 'yes';
      process.env.AGENTSPAN_DAEMON_WORKERS = 'TRUE';
      process.env.AGENTSPAN_STREAMING_ENABLED = 'no';

      const config = new AgentConfig();

      expect(config.autoStartWorkers).toBe(true);
      expect(config.autoStartServer).toBe(true);
      expect(config.daemonWorkers).toBe(true);
      expect(config.streamingEnabled).toBe(false);
    });

    it('handles invalid numeric env vars gracefully', () => {
      process.env.AGENTSPAN_WORKER_POLL_INTERVAL = 'not-a-number';
      process.env.AGENTSPAN_WORKER_THREADS = '';

      const config = new AgentConfig();

      expect(config.workerPollIntervalMs).toBe(100);
      expect(config.workerThreads).toBe(1);
    });
  });

  describe('fromEnv', () => {
    it('creates config from env vars only', () => {
      process.env.AGENTSPAN_SERVER_URL = 'https://fromenv.com/api';
      process.env.AGENTSPAN_API_KEY = 'fromenv-key';

      const config = AgentConfig.fromEnv();

      expect(config.serverUrl).toBe('https://fromenv.com/api');
      expect(config.apiKey).toBe('fromenv-key');
    });

    it('uses defaults when no env vars set', () => {
      const config = AgentConfig.fromEnv();

      expect(config.serverUrl).toBe('http://localhost:6767/api');
      expect(config.apiKey).toBe('');
      expect(config.logLevel).toBe('INFO');
    });
  });
});
