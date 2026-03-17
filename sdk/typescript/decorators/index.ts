/**
 * TypeScript decorator support for Agentspan tools.
 *
 * Usage:
 *   import { AgentTool, toolsFrom } from '@agentspan/sdk/decorators'
 *
 *   class WeatherTools {
 *     @AgentTool({
 *       description: 'Get current weather for a city.',
 *       inputSchema: { type: 'object', properties: { city: { type: 'string' } }, required: ['city'] },
 *     })
 *     async getWeather({ city }: { city: string }) {
 *       return { city, temperature_f: 72, condition: 'Sunny' }
 *     }
 *   }
 *
 *   const tools = toolsFrom(new WeatherTools())
 *   // tools is an array of tool() wrappers, ready to pass to new Agent({ tools })
 *
 * Note: @AgentTool only works on class methods (TypeScript/JS limitation).
 *       For standalone functions, use tool() from '@agentspan/sdk'.
 */

const TOOL_DEF_KEY = '_toolDef';

export interface JsonSchema {
  type: string;
  properties?: Record<string, JsonSchema & { description?: string }>;
  required?: string[];
  description?: string;
  [key: string]: unknown;
}

export interface AgentToolOptions {
  /** Tool name. Defaults to the method name. */
  name?: string;
  /** Description sent to the LLM. Required. */
  description: string;
  /** JSON Schema for the tool's input. Required. */
  inputSchema: JsonSchema;
  /** JSON Schema for the tool's output. Optional. */
  outputSchema?: JsonSchema;
  /** Require human approval before execution. */
  approvalRequired?: boolean;
  /** Max seconds before timeout. */
  timeoutSeconds?: number;
}

export interface ToolDef {
  name: string;
  description: string;
  inputSchema: JsonSchema;
  outputSchema?: JsonSchema;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  func: (...args: any[]) => unknown;
  approvalRequired: boolean;
  timeoutSeconds?: number;
  toolType: 'worker';
  config: Record<string, unknown>;
}

/**
 * Method decorator that registers a class method as an agent tool.
 *
 * @example
 * class Tools {
 *   @AgentTool({ description: '...', inputSchema: { ... } })
 *   async myTool(input: { x: string }) { return { result: input.x } }
 * }
 */
export function AgentTool(options: AgentToolOptions) {
  return function (
    target: object,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ): PropertyDescriptor {
    const originalMethod = descriptor.value;

    const toolDef: ToolDef = {
      name: options.name || propertyKey,
      description: options.description,
      inputSchema: options.inputSchema,
      outputSchema: options.outputSchema,
      func: originalMethod,
      approvalRequired: options.approvalRequired ?? false,
      timeoutSeconds: options.timeoutSeconds,
      toolType: 'worker',
      config: {},
    };

    // Attach the toolDef to the method so toolsFrom() can discover it
    (descriptor.value as Record<string, unknown>)[TOOL_DEF_KEY] = toolDef;

    return descriptor;
  };
}

/**
 * Extract all @AgentTool-decorated methods from an instance as tool() wrappers.
 *
 * The returned functions are bound to the instance and have `._toolDef`
 * attached — compatible with Agent({ tools: [...] }).
 *
 * @example
 * const agent = new Agent({
 *   name: 'weather_agent',
 *   model: 'openai/gpt-4o',
 *   tools: toolsFrom(new WeatherTools()),
 * })
 */
export function toolsFrom(instance: object): Array<(input: unknown) => Promise<unknown>> {
  const tools: Array<(input: unknown) => Promise<unknown>> = [];
  const proto = Object.getPrototypeOf(instance);

  for (const key of Object.getOwnPropertyNames(proto)) {
    if (key === 'constructor') continue;

    const method = (proto as Record<string, unknown>)[key];
    if (typeof method !== 'function') continue;

    const toolDef = (method as Record<string, unknown>)[TOOL_DEF_KEY] as ToolDef | undefined;
    if (!toolDef) continue;

    // Bind to instance so `this` works inside the method
    const boundMethod = (method as Function).bind(instance);

    // Create a wrapper that looks like a tool() result
    async function wrapper(input: unknown) {
      return boundMethod(input);
    }
    Object.defineProperty(wrapper, 'name', { value: toolDef.name, configurable: true });

    // Attach toolDef (compatible with getToolDef() in tool.js)
    const boundToolDef: ToolDef = { ...toolDef, func: boundMethod };
    (wrapper as unknown as Record<string, unknown>)['_toolDef'] = boundToolDef;

    tools.push(wrapper);
  }

  return tools;
}
