'use strict';

/**
 * AgentRuntime — the execution engine.
 *
 * 1. Serialize Agent → AgentConfig JSON
 * 2. POST /api/agent/start  → workflowId
 * 3. Register JS tool workers with Conductor TaskManager
 * 4. Poll /api/agent/{id}/status until complete  (or stream SSE)
 * 5. Return AgentResult
 */

const { AgentConfig } = require('./config');
const { AgentConfigSerializer } = require('./serializer');
const { WorkerManager } = require('./worker-manager');
const { makeAgentResult, TERMINAL_STATUSES } = require('./result');
const { getToolDef } = require('./tool');

function log(config, level, ...args) {
  const levels = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };
  const threshold = levels[(config.logLevel || 'INFO').toUpperCase()] ?? 1;
  if ((levels[level] ?? 1) >= threshold) {
    const prefix = `[agentspan:${level.toLowerCase()}]`;
    if (level === 'ERROR') console.error(prefix, ...args);
    else if (level === 'WARN') console.warn(prefix, ...args);
    else console.log(prefix, ...args);
  }
}

class AgentRuntime {
  constructor(options = {}) {
    this._config = options instanceof AgentConfig ? options : new AgentConfig(options);
    this._serializer = new AgentConfigSerializer();
    this._workerManager = new WorkerManager({
      serverUrl: this._config.serverUrl,
      authKey: this._config.authKey,
      authSecret: this._config.authSecret,
      pollIntervalMs: this._config.workerPollIntervalMs,
    });
    this._registeredTools = new Set();
    this._workersStarted = false;

    this._headers = { 'Content-Type': 'application/json' };
    if (this._config.authKey) this._headers['X-Auth-Key'] = this._config.authKey;
    if (this._config.authSecret) this._headers['X-Auth-Secret'] = this._config.authSecret;
  }

  // ── Public API ────────────────────────────────────────────────────────

  /** Run an agent and await the result. */
  async run(agent, prompt, options = {}) {
    await this._prepareWorkers(agent);
    const workflowId = await this._startAgent(agent, prompt, options);
    log(this._config, 'INFO', `Agent '${agent.name}' started (workflowId=${workflowId})`);
    return this._waitForResult(workflowId);
  }

  /** Start an agent and return a handle for polling / HITL approval. */
  async start(agent, prompt, options = {}) {
    await this._prepareWorkers(agent);
    const workflowId = await this._startAgent(agent, prompt, options);
    log(this._config, 'INFO', `Agent '${agent.name}' started (workflowId=${workflowId})`);
    return this._makeHandle(workflowId);
  }

  /** Start an agent and stream events as an async iterable. */
  async *stream(agent, prompt, options = {}) {
    await this._prepareWorkers(agent);
    const workflowId = await this._startAgent(agent, prompt, options);
    log(this._config, 'INFO', `Agent '${agent.name}' streaming (workflowId=${workflowId})`);
    yield* this._streamSse(workflowId);
  }

  /** Compile an agent to a Conductor workflow definition without executing. */
  async plan(agent) {
    const configJson = this._serializer.serialize(agent);
    const url = `${this._config.serverUrl}/agent/compile`;
    const resp = await fetch(url, {
      method: 'POST',
      headers: this._headers,
      body: JSON.stringify({ agentConfig: configJson }),
    });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Compile failed (${resp.status}): ${body}`);
    }
    const data = await resp.json();
    return data.workflowDef || data;
  }

  /** Stop all workers and release resources. */
  async shutdown() {
    await this._workerManager.stopPolling();
    log(this._config, 'INFO', 'AgentRuntime shut down');
  }

  // ── Internal: start ───────────────────────────────────────────────────

  async _startAgent(agent, prompt, options) {
    const configJson = this._serializer.serialize(agent);
    const payload = {
      agentConfig: configJson,
      prompt,
      sessionId: options.sessionId || '',
      media: [],
    };
    if (options.timeoutSeconds != null) payload.timeoutSeconds = options.timeoutSeconds;

    const url = `${this._config.serverUrl}/agent/start`;
    log(this._config, 'DEBUG', 'POST', url, JSON.stringify(payload, null, 2));

    const resp = await fetch(url, {
      method: 'POST',
      headers: this._headers,
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Failed to start agent (${resp.status}): ${body}`);
    }

    const data = await resp.json();
    return data.workflowId;
  }

  // ── Internal: workers ─────────────────────────────────────────────────

  async _prepareWorkers(agent) {
    const toolDefs = this._collectWorkerTools(agent);
    const newDefs = toolDefs.filter((td) => !this._registeredTools.has(td.name));

    for (const td of newDefs) {
      await this._workerManager.registerTaskDef(td.name);
      this._registeredTools.add(td.name);
      this._workerManager.addWorker(td.name, td.func);
      log(this._config, 'DEBUG', `Registered worker for tool '${td.name}'`);
    }

    if (newDefs.length > 0 || (toolDefs.length > 0 && !this._workersStarted)) {
      await this._workerManager.startPolling();
      this._workersStarted = true;
    }
  }

  _collectWorkerTools(agent) {
    const defs = [];
    for (const t of agent.tools || []) {
      try {
        const td = getToolDef(t);
        if (td.toolType === 'worker' && td.func !== null) {
          defs.push(td);
        }
      } catch {
        /* skip invalid entries */
      }
    }
    for (const sub of agent.agents || []) {
      defs.push(...this._collectWorkerTools(sub));
    }
    return defs;
  }

  // ── Internal: polling ─────────────────────────────────────────────────

  async _waitForResult(workflowId, pollIntervalMs = 500) {
    while (true) {
      await new Promise((r) => setTimeout(r, pollIntervalMs));
      const data = await this._getStatus(workflowId);
      const status = (data.status || '').toUpperCase();
      if (TERMINAL_STATUSES.has(status)) {
        return this._toResult(workflowId, data);
      }
    }
  }

  async _getStatus(workflowId) {
    const url = `${this._config.serverUrl}/agent/${workflowId}/status`;
    const resp = await fetch(url, { headers: this._headers });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Status check failed (${resp.status}): ${body}`);
    }
    return resp.json();
  }

  _toResult(workflowId, data) {
    const output = data.output || data.result || null;
    return makeAgentResult({
      workflowId,
      output,
      status: (data.status || 'COMPLETED').toUpperCase(),
      messages: data.messages || [],
      toolCalls: data.toolCalls || [],
      finishReason: data.finishReason,
      error: data.error,
      tokenUsage: data.tokenUsage,
      subResults: data.subResults || {},
    });
  }

  // ── Internal: handle ──────────────────────────────────────────────────

  _makeHandle(workflowId) {
    const self = this;
    return {
      workflowId,

      async getStatus() {
        const data = await self._getStatus(workflowId);
        const status = (data.status || '').toUpperCase();
        return {
          workflowId,
          isComplete: TERMINAL_STATUSES.has(status),
          isRunning: !TERMINAL_STATUSES.has(status) && status !== 'PAUSED',
          isWaiting: status === 'PAUSED' || data.isWaiting === true,
          output: data.output || null,
          status,
          reason: data.reason,
          currentTask: data.currentTask,
          messages: data.messages || [],
        };
      },

      async wait(pollIntervalMs = 500) {
        return self._waitForResult(workflowId, pollIntervalMs);
      },

      async approve(output = {}) {
        const url = `${self._config.serverUrl}/agent/${workflowId}/respond`;
        await fetch(url, {
          method: 'POST',
          headers: self._headers,
          body: JSON.stringify({ approved: true, output }),
        });
      },

      async reject(reason = 'Rejected') {
        const url = `${self._config.serverUrl}/agent/${workflowId}/respond`;
        await fetch(url, {
          method: 'POST',
          headers: self._headers,
          body: JSON.stringify({ approved: false, reason }),
        });
      },
    };
  }

  // ── Internal: SSE streaming ───────────────────────────────────────────

  async *_streamSse(workflowId) {
    const url = `${this._config.serverUrl}/agent/stream/${workflowId}`;
    const headers = { ...this._headers, Accept: 'text/event-stream' };
    delete headers['Content-Type'];

    try {
      const resp = await fetch(url, { headers });

      if (!resp.ok || !resp.body) {
        yield* this._streamByPolling(workflowId);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let eventType;
      let eventId;
      const dataLines = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const raw of lines) {
          const line = raw.replace(/\r$/, '');

          if (line.startsWith(':')) continue; // heartbeat

          if (line === '') {
            if (dataLines.length > 0) {
              const dataStr = dataLines.join('\n');
              let data;
              try { data = JSON.parse(dataStr); }
              catch { data = { content: dataStr }; }

              const event = this._parseEvent(eventType || '', data);
              if (event) {
                yield event;
                if (event.type === 'done') { await reader.cancel(); return; }
              }
            }
            eventType = undefined;
            eventId = undefined;
            dataLines.length = 0;
          } else if (line.startsWith('event:')) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith('id:')) {
            eventId = line.slice(3).trim();
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trim());
          }
        }
      }
    } catch {
      yield* this._streamByPolling(workflowId);
    }
  }

  _parseEvent(type, data) {
    const t = type || data.type || '';
    if (t === 'thinking') return { type: 'thinking', content: data.content, raw: data };
    if (t === 'tool_call') return { type: 'tool_call', toolName: data.toolName, args: data.args, raw: data };
    if (t === 'tool_result') return { type: 'tool_result', toolName: data.toolName, result: data.result, raw: data };
    if (t === 'waiting') return { type: 'waiting', raw: data };
    if (t === 'error') return { type: 'error', error: data.error, raw: data };
    if (t === 'done') return { type: 'done', output: data.output || null, raw: data };
    if (t === 'guardrail_pass') return { type: 'guardrail_pass', raw: data };
    if (t === 'guardrail_fail') return { type: 'guardrail_fail', raw: data };
    return null;
  }

  async *_streamByPolling(workflowId) {
    const result = await this._waitForResult(workflowId);
    yield { type: 'done', output: result.output, raw: {} };
  }
}

module.exports = { AgentRuntime };
