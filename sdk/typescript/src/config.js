'use strict';

/**
 * AgentConfig — runtime configuration loaded from environment variables.
 *
 * All variables are prefixed with AGENTSPAN_:
 *   AGENTSPAN_SERVER_URL            (default: http://localhost:8080/api)
 *   AGENTSPAN_AUTH_KEY              (optional)
 *   AGENTSPAN_AUTH_SECRET           (optional)
 *   AGENTSPAN_WORKER_POLL_INTERVAL  (default: 100 ms)
 *   AGENTSPAN_LOG_LEVEL             (default: INFO)
 */

class AgentConfig {
  constructor(options = {}) {
    const env = (key) => process.env[key];
    const envInt = (key, def) => {
      const v = env(key);
      if (!v) return def;
      const n = parseInt(v, 10);
      return isNaN(n) ? def : n;
    };

    let serverUrl =
      options.serverUrl ||
      env('AGENTSPAN_SERVER_URL') ||
      'http://localhost:8080/api';

    // Auto-append /api if missing
    serverUrl = serverUrl.replace(/\/$/, '');
    if (!serverUrl.endsWith('/api')) {
      serverUrl = serverUrl + '/api';
    }

    this.serverUrl = serverUrl;
    this.authKey = options.authKey || env('AGENTSPAN_AUTH_KEY') || undefined;
    this.authSecret = options.authSecret || env('AGENTSPAN_AUTH_SECRET') || undefined;
    this.workerPollIntervalMs =
      options.workerPollIntervalMs || envInt('AGENTSPAN_WORKER_POLL_INTERVAL', 100);
    this.logLevel = options.logLevel || env('AGENTSPAN_LOG_LEVEL') || 'INFO';
  }

  static fromEnv() {
    return new AgentConfig();
  }
}

module.exports = { AgentConfig };
