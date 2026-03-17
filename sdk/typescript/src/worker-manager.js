'use strict';

/**
 * WorkerManager — registers @tool JS functions as Conductor task workers.
 *
 * Uses @io-orkes/conductor-javascript TaskManager for polling.
 * Each tool() function becomes a Conductor SIMPLE task worker.
 */

const { orkesConductorClient, TaskManager } = require('@io-orkes/conductor-javascript');

class WorkerManager {
  constructor({ serverUrl, authKey, authSecret, pollIntervalMs = 100 }) {
    this._serverUrl = serverUrl; // already has /api suffix
    this._authKey = authKey;
    this._authSecret = authSecret;
    this._pollIntervalMs = pollIntervalMs;
    this._client = null;
    this._taskManager = null;
    this._workers = [];
    this._started = false;
  }

  async _ensureClient() {
    if (this._client) return this._client;

    const clientOptions = {
      serverUrl: this._serverUrl,
    };
    if (this._authKey) clientOptions.keyId = this._authKey;
    if (this._authSecret) clientOptions.keySecret = this._authSecret;

    // Suppress conductor SDK internal noise (auth warnings, worker init logs)
    const origWarn = console.warn;
    const origLog = console.log;
    const sdkNoise = (msg) =>
      typeof msg === 'string' &&
      (msg.includes('CONDUCTOR_AUTH') || msg.includes('TaskWorker'));
    console.warn = (...args) => { if (!sdkNoise(args[0])) origWarn.apply(console, args); };
    console.log  = (...args) => { if (!sdkNoise(args[0])) origLog.apply(console, args); };
    this._client = await orkesConductorClient(clientOptions);
    console.warn = origWarn;
    console.log  = origLog;

    return this._client;
  }

  /**
   * Add a tool worker definition before polling starts.
   * @param {string} taskDefName - Conductor task type name (matches tool name)
   * @param {Function} fn - The tool function to execute
   */
  addWorker(taskDefName, fn) {
    this._workers.push({
      taskDefName,
      execute: async (task) => {
        const inputData = task.inputData || {};
        // Strip internal fields injected by the server
        const { _agent_state, ...args } = inputData;
        try {
          const output = await fn(args);
          const outputData =
            output !== null && typeof output === 'object'
              ? output
              : { result: output };
          return { outputData, status: 'COMPLETED' };
        } catch (err) {
          return {
            status: 'FAILED',
            reasonForIncompletion: err instanceof Error ? err.message : String(err),
          };
        }
      },
      // How often to poll (ms)
      pollInterval: this._pollIntervalMs,
    });
  }

  /**
   * Register a task definition on the Conductor server.
   * Non-fatal if the task def already exists.
   */
  async registerTaskDef(name) {
    try {
      const baseUrl = this._serverUrl.replace(/\/api$/, '');
      const headers = { 'Content-Type': 'application/json' };
      if (this._authKey) headers['X-Auth-Key'] = this._authKey;
      if (this._authSecret) headers['X-Auth-Secret'] = this._authSecret;

      await fetch(`${baseUrl}/api/metadata/taskdefs`, {
        method: 'POST',
        headers,
        body: JSON.stringify([
          {
            name,
            retryCount: 2,
            retryLogic: 'LINEAR_BACKOFF',
            retryDelaySeconds: 2,
            timeoutSeconds: 120,
            responseTimeoutSeconds: 120,
          },
        ]),
      });
    } catch {
      // Non-fatal — task def may already exist
    }
  }

  async startPolling() {
    if (this._started) return;
    if (this._workers.length === 0) return;

    const client = await this._ensureClient();
    // Pass a silent logger so the conductor SDK doesn't emit its own INFO lines
    const silentLogger = {
      debug: () => {},
      info:  () => {},
      warn:  () => {},
      error: (...a) => console.error('[conductor]', ...a),
      log:   () => {},
    };

    this._taskManager = new TaskManager(client, this._workers, {
      options: { pollInterval: this._pollIntervalMs },
      logger: silentLogger,
    });
    this._taskManager.startPolling();
    this._started = true;
  }

  async stopPolling() {
    if (this._taskManager && this._started) {
      await this._taskManager.stopPolling();
      this._started = false;
    }
  }
}

module.exports = { WorkerManager };
