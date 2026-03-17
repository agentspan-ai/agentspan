'use strict';

/**
 * @agentspan/sdk — JavaScript SDK for Agentspan
 *
 * @example
 * const { Agent, AgentRuntime, tool } = require('@agentspan/sdk')
 *
 * const getWeather = tool(
 *   async function getWeather({ city }) {
 *     return { city, temperature_f: 72, condition: 'Sunny' }
 *   },
 *   {
 *     description: 'Get current weather for a city.',
 *     inputSchema: { type: 'object', properties: { city: { type: 'string' } }, required: ['city'] },
 *   }
 * )
 *
 * const agent = new Agent({
 *   name: 'weather_agent',
 *   model: 'openai/gpt-4o',
 *   instructions: 'You are a helpful weather assistant.',
 *   tools: [getWeather],
 * })
 *
 * const runtime = new AgentRuntime({ serverUrl: 'http://localhost:8080' })
 * const result = await runtime.run(agent, "What's the weather in SF?")
 * result.printResult()
 * await runtime.shutdown()
 */

const { Agent } = require('./agent');
const { AgentConfig } = require('./config');
const { AgentRuntime } = require('./runtime');
const { makeAgentResult, EventType, Status, FinishReason } = require('./result');
const { tool, getToolDef, httpTool, mcpTool, TOOL_DEF } = require('./tool');
const { AgentConfigSerializer } = require('./serializer');

module.exports = {
  // Core
  Agent,
  AgentConfig,
  AgentRuntime,

  // Tools
  tool,
  getToolDef,
  httpTool,
  mcpTool,
  TOOL_DEF,

  // Results
  makeAgentResult,
  EventType,
  Status,
  FinishReason,

  // Advanced
  AgentConfigSerializer,
};
