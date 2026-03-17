'use strict';

/**
 * tool() — register a JS function as an agent tool.
 *
 * Attaches a ._toolDef property to the wrapper function containing the
 * resolved tool definition. The function retains its original call signature.
 *
 * @example
 * const getWeather = tool(
 *   async function getWeather({ city }) {
 *     return { city, temperature_f: 72, condition: 'Sunny' }
 *   },
 *   {
 *     description: 'Get current weather for a city.',
 *     inputSchema: {
 *       type: 'object',
 *       properties: { city: { type: 'string' } },
 *       required: ['city'],
 *     },
 *   }
 * )
 */

const TOOL_DEF = Symbol('toolDef');

function tool(fn, options) {
  if (typeof fn !== 'function') {
    throw new TypeError('tool(): first argument must be a function');
  }
  if (!options || !options.description || !options.inputSchema) {
    throw new TypeError('tool(): options must include { description, inputSchema }');
  }

  const toolDef = {
    name: options.name || fn.name || 'unnamed_tool',
    description: options.description,
    inputSchema: options.inputSchema,
    outputSchema: options.outputSchema || null,
    func: fn,
    approvalRequired: options.approvalRequired || false,
    timeoutSeconds: options.timeoutSeconds || null,
    toolType: 'worker',
    config: {},
  };

  async function wrapper(input) {
    return fn(input);
  }

  Object.defineProperty(wrapper, 'name', { value: toolDef.name, configurable: true });
  wrapper[TOOL_DEF] = toolDef;
  wrapper._toolDef = toolDef; // convenience alias for plain JS (no Symbol support needed)

  return wrapper;
}

/**
 * Extract a ToolDef from a tool() wrapper or a raw ToolDef object.
 */
function getToolDef(toolObj) {
  if (typeof toolObj === 'function') {
    const td = toolObj[TOOL_DEF] || toolObj._toolDef;
    if (td) return td;
    throw new TypeError(
      `Function "${toolObj.name || 'unknown'}" is not a registered tool. Wrap it with tool() first.`
    );
  }
  if (toolObj && typeof toolObj === 'object' && toolObj.name && toolObj.toolType) {
    return toolObj; // already a ToolDef
  }
  throw new TypeError(`Invalid tool: ${JSON.stringify(toolObj)}`);
}

/**
 * httpTool() — tool backed by an HTTP endpoint (no local worker needed).
 */
function httpTool({ name, description, url, method = 'GET', headers = {}, inputSchema = {}, accept = ['application/json'], contentType = 'application/json' }) {
  return {
    name,
    description,
    inputSchema,
    outputSchema: null,
    func: null,
    approvalRequired: false,
    timeoutSeconds: null,
    toolType: 'http',
    config: {
      url,
      method: method.toUpperCase(),
      headers,
      accept,
      contentType,
    },
  };
}

/**
 * mcpTool() — tool backed by an MCP server (no local worker needed).
 */
function mcpTool({ name, description, serverUrl, headers = {}, inputSchema = {} }) {
  return {
    name,
    description,
    inputSchema,
    outputSchema: null,
    func: null,
    approvalRequired: false,
    timeoutSeconds: null,
    toolType: 'mcp',
    config: {
      serverUrl,
      headers,
    },
  };
}

module.exports = { tool, getToolDef, httpTool, mcpTool, TOOL_DEF };
