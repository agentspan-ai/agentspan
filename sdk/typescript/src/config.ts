import { config as dotenvConfig } from 'dotenv';

// Load .env file on import (no-op if file doesn't exist)
dotenvConfig();

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

/**
 * Normalize server URL: ensures it ends with `/api`.
 * - Strips trailing slashes first
 * - Appends `/api` if the path does not already end with `/api`
 */
export function normalizeServerUrl(url: string): string {
  // Strip trailing slashes
  let normalized = url.replace(/\/+$/, '');

  // Append /api if not already present
  if (!normalized.endsWith('/api')) {
    normalized += '/api';
  }

  return normalized;
}

/**
 * Parse a boolean from an environment variable string.
 * Recognizes 'true', '1', 'yes' as true; everything else as false.
 */
function parseBoolEnv(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined || value === '') return defaultValue;
  return ['true', '1', 'yes'].includes(value.toLowerCase());
}

/**
 * Parse an integer from an environment variable string.
 */
function parseIntEnv(value: string | undefined, defaultValue: number): number {
  if (value === undefined || value === '') return defaultValue;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? defaultValue : parsed;
}

export interface AgentConfigOptions {
  serverUrl?: string;
  apiKey?: string;
  authKey?: string;
  authSecret?: string;
  workerPollIntervalMs?: number;
  workerThreads?: number;
  autoStartWorkers?: boolean;
  autoStartServer?: boolean;
  daemonWorkers?: boolean;
  streamingEnabled?: boolean;
  credentialStrictMode?: boolean;
  logLevel?: LogLevel;
  llmRetryCount?: number;
}

/**
 * SDK configuration with env var fallback and URL normalization.
 */
export class AgentConfig {
  readonly serverUrl: string;
  readonly apiKey: string;
  readonly authKey: string;
  readonly authSecret: string;
  readonly workerPollIntervalMs: number;
  readonly workerThreads: number;
  readonly autoStartWorkers: boolean;
  readonly autoStartServer: boolean;
  readonly daemonWorkers: boolean;
  readonly streamingEnabled: boolean;
  readonly credentialStrictMode: boolean;
  readonly logLevel: LogLevel;
  readonly llmRetryCount: number;

  constructor(options?: AgentConfigOptions) {
    const env = process.env;

    const rawUrl =
      options?.serverUrl ??
      env.AGENTSPAN_SERVER_URL ??
      'http://localhost:6767/api';

    this.serverUrl = normalizeServerUrl(rawUrl);

    this.apiKey = options?.apiKey ?? env.AGENTSPAN_API_KEY ?? '';
    this.authKey = options?.authKey ?? env.AGENTSPAN_AUTH_KEY ?? '';
    this.authSecret = options?.authSecret ?? env.AGENTSPAN_AUTH_SECRET ?? '';

    this.workerPollIntervalMs =
      options?.workerPollIntervalMs ??
      parseIntEnv(env.AGENTSPAN_WORKER_POLL_INTERVAL, 100);

    this.workerThreads =
      options?.workerThreads ??
      parseIntEnv(env.AGENTSPAN_WORKER_THREADS, 1);

    this.autoStartWorkers =
      options?.autoStartWorkers ??
      parseBoolEnv(env.AGENTSPAN_AUTO_START_WORKERS, true);

    this.autoStartServer =
      options?.autoStartServer ??
      parseBoolEnv(env.AGENTSPAN_AUTO_START_SERVER, true);

    this.daemonWorkers =
      options?.daemonWorkers ??
      parseBoolEnv(env.AGENTSPAN_DAEMON_WORKERS, true);

    this.streamingEnabled =
      options?.streamingEnabled ??
      parseBoolEnv(env.AGENTSPAN_STREAMING_ENABLED, true);

    this.credentialStrictMode =
      options?.credentialStrictMode ??
      parseBoolEnv(env.AGENTSPAN_CREDENTIAL_STRICT_MODE, false);

    this.logLevel =
      options?.logLevel ??
      ((env.AGENTSPAN_LOG_LEVEL as LogLevel) || 'INFO');

    this.llmRetryCount =
      options?.llmRetryCount ??
      parseIntEnv(env.AGENTSPAN_LLM_RETRY_COUNT, 3);
  }

  /**
   * Create an AgentConfig from environment variables only (no overrides).
   */
  static fromEnv(): AgentConfig {
    return new AgentConfig();
  }
}
