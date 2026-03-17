'use strict';

/**
 * AgentConfigSerializer — converts an Agent tree to the AgentConfig JSON
 * expected by POST /api/agent/start and /api/agent/compile.
 *
 * Mirrors Python's AgentConfigSerializer exactly.
 */

const { getToolDef } = require('./tool');

class AgentConfigSerializer {
  serialize(agent) {
    return this._serializeAgent(agent);
  }

  _serializeAgent(agent) {
    const config = {
      name: agent.name,
      model: agent.model || null,
      maxTurns: agent.maxTurns,
    };

    // Strategy only relevant when sub-agents exist
    if (agent.agents && agent.agents.length > 0) {
      config.strategy = agent.strategy || null;
    }

    // Instructions
    if (typeof agent.instructions === 'function') {
      config.instructions = agent.instructions();
    } else if (agent.instructions) {
      config.instructions = agent.instructions;
    }

    // Tools
    if (agent.tools && agent.tools.length > 0) {
      config.tools = agent.tools.map((t) => this._serializeTool(t));
    }

    // Sub-agents (recursive)
    if (agent.agents && agent.agents.length > 0) {
      config.agents = agent.agents.map((a) => this._serializeAgent(a));
    }

    // Optional fields
    if (agent.maxTokens != null) config.maxTokens = agent.maxTokens;
    if (agent.temperature != null) config.temperature = agent.temperature;
    if (agent.timeoutSeconds != null) config.timeoutSeconds = agent.timeoutSeconds;
    if (agent.external) config.external = agent.external;
    if (agent.metadata && Object.keys(agent.metadata).length > 0) {
      config.metadata = agent.metadata;
    }

    // Remove null/undefined for cleaner JSON
    return Object.fromEntries(
      Object.entries(config).filter(([, v]) => v !== null && v !== undefined)
    );
  }

  _serializeTool(toolObj) {
    const td = getToolDef(toolObj);
    const result = {
      name: td.name,
      description: td.description,
      inputSchema: td.inputSchema,
      toolType: td.toolType,
    };

    if (td.outputSchema) result.outputSchema = td.outputSchema;
    if (td.approvalRequired) result.approvalRequired = true;
    if (td.timeoutSeconds != null) result.timeoutSeconds = td.timeoutSeconds;
    if (td.config && Object.keys(td.config).length > 0) result.config = td.config;

    return result;
  }
}

module.exports = { AgentConfigSerializer };
