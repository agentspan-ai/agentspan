/**
 * Generic agent serializer — zero framework-specific code.
 *
 * Provides:
 * - Deep serialization of any agent object to JSON-compatible dict
 * - Callable extraction with schema generation
 * - Tool object extraction with embedded function discovery
 *
 * Output format matches the Python SDK's serializer.py:
 * - Callables → { "_worker_ref": "name", "description": "...", "parameters": {...} }
 * - Objects → { "_type": "ClassName", ...serialized properties }
 * - Enums → raw value
 * - Circular references → "<circular ref: ClassName>"
 */

// ── WorkerInfo ──────────────────────────────────────────

/**
 * Extracted callable info for worker registration.
 */
export interface WorkerInfo {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  func: Function | null;
  /** True if the worker function is already wrapped as a Task→TaskResult handler. */
  _pre_wrapped?: boolean;
  /** Extra metadata (e.g. llm_role, subgraph_role, is_dynamic_fanout). */
  _extra?: Record<string, unknown>;
}

// ── Public API ──────────────────────────────────────────

/**
 * Generic deep serialization of any framework agent object.
 *
 * Walks the object tree using standard JS introspection.
 * Callables are replaced with `{ "_worker_ref": "name", ... }` markers.
 * Non-callable objects are serialized with `{ "_type": "ClassName", ... }`.
 *
 * @returns A tuple of [json_dict, extracted_workers].
 */
export function serializeFrameworkAgent(
  agentObj: unknown,
): [Record<string, unknown>, WorkerInfo[]] {
  const workers: WorkerInfo[] = [];
  const seen = new WeakSet<object>();

  function serialize(obj: unknown): unknown {
    // Primitives
    if (obj === null || obj === undefined) return obj;
    if (typeof obj === "string" || typeof obj === "number" || typeof obj === "boolean") {
      return obj;
    }

    // Enum-like: object with a .value primitive property and a constructor name ending in enum patterns
    if (typeof obj === "object" && obj !== null && !Array.isArray(obj)) {
      const asAny = obj as Record<string, unknown>;
      if (_isEnumLike(asAny)) {
        return asAny.value;
      }
    }

    // Pydantic-like model class (used as output_type) → JSON Schema
    if (typeof obj === "function" && typeof (obj as any).model_json_schema === "function") {
      try {
        return (obj as any).model_json_schema();
      } catch {
        return { _type: (obj as any).name ?? "UnknownClass" };
      }
    }

    // Callable function with meaningful name → extract as worker
    if (_isToolCallable(obj)) {
      const worker = _extractCallable(obj as Function);
      workers.push(worker);
      return {
        _worker_ref: worker.name,
        description: worker.description,
        parameters: worker.inputSchema,
      };
    }

    // Agent-as-tool: framework tool wrapping a nested agent
    const agentToolResult = _tryExtractAgentTool(obj, workers);
    if (agentToolResult !== null) {
      return agentToolResult;
    }

    // Tool-like object (has name + description/schema + embedded callable)
    const toolWorker = _tryExtractToolObject(obj);
    if (toolWorker !== null) {
      workers.push(toolWorker);
      return {
        _worker_ref: toolWorker.name,
        description: toolWorker.description,
        parameters: toolWorker.inputSchema,
      };
    }

    // Circular reference protection (only for objects, not primitives)
    if (typeof obj === "object" && obj !== null) {
      if (seen.has(obj)) {
        return `<circular ref: ${obj.constructor?.name ?? "Object"}>`;
      }
      seen.add(obj);
    }

    try {
      // Map
      if (obj instanceof Map) {
        const result: Record<string, unknown> = {};
        for (const [k, v] of obj) {
          result[String(k)] = serialize(v);
        }
        return result;
      }

      // Set
      if (obj instanceof Set) {
        return Array.from(obj).map((v) => serialize(v));
      }

      // Array
      if (Array.isArray(obj)) {
        return obj.map((v) => serialize(v));
      }

      // Date
      if (obj instanceof Date) {
        return obj.toISOString();
      }

      // RegExp
      if (obj instanceof RegExp) {
        return obj.toString();
      }

      // Buffer / Uint8Array
      if (obj instanceof Uint8Array) {
        return new TextDecoder().decode(obj);
      }

      // Plain object or class instance
      if (typeof obj === "object" && obj !== null) {
        const result: Record<string, unknown> = {};
        const className = obj.constructor?.name;
        if (className && className !== "Object") {
          result._type = className;
        }

        // Try Zod schema → JSON Schema
        if (_isZodSchema(obj)) {
          try {
            const jsonSchema = _zodToJsonSchema(obj);
            if (jsonSchema) return jsonSchema;
          } catch {
            // Fall through to property enumeration
          }
        }

        // Enumerate properties
        const keys = _getSerializableKeys(obj);
        for (const key of keys) {
          if (key.startsWith("_")) continue;
          try {
            const val = (obj as Record<string, unknown>)[key];
            result[key] = serialize(val);
          } catch {
            // Skip unreadable properties
          }
        }
        return result;
      }

      // Fallback — string representation
      return String(obj);
    } finally {
      if (typeof obj === "object" && obj !== null) {
        seen.delete(obj);
      }
    }
  }

  const config = serialize(agentObj);
  if (typeof config !== "object" || config === null || Array.isArray(config)) {
    return [{ _type: "unknown", value: config } as Record<string, unknown>, workers];
  }
  return [config as Record<string, unknown>, workers];
}

// ── Private helpers ─────────────────────────────────────

/**
 * Check if an object looks like an enum value (has .value + constructor is not Object).
 */
function _isEnumLike(obj: Record<string, unknown>): boolean {
  if (!("value" in obj)) return false;
  const val = obj.value;
  if (typeof val !== "string" && typeof val !== "number") return false;
  const ctorName = obj.constructor?.name ?? "";
  // Must not be a plain Object
  return ctorName !== "" && ctorName !== "Object";
}

/**
 * Check if an object is a callable function that should be extracted as a worker.
 */
function _isToolCallable(obj: unknown): boolean {
  if (typeof obj !== "function") return false;
  // Skip classes (constructors)
  if (_isClass(obj)) return false;
  // Must have a meaningful name
  const name = (obj as any).name ?? "";
  if (!name || name === "" || name === "anonymous") return false;
  return true;
}

/**
 * Heuristic to check if a function is actually a class constructor.
 */
function _isClass(fn: unknown): boolean {
  if (typeof fn !== "function") return false;
  const str = Function.prototype.toString.call(fn);
  return str.startsWith("class ");
}

/**
 * Extract name, description, and schema from a callable function.
 */
function _extractCallable(func: Function): WorkerInfo {
  const name = (func as any).toolName ?? (func as any).name ?? func.name ?? "unknown_tool";

  const description = (func as any).description ?? "";

  // Try to extract schema from function metadata
  const schema = _extractFunctionSchema(func);

  return {
    name,
    description: typeof description === "string" ? description.trim().split("\n")[0] : "",
    inputSchema: schema,
    func,
  };
}

/**
 * Extract JSON schema from function metadata if available.
 * Falls back to empty schema since TypeScript doesn't have runtime type hints.
 */
function _extractFunctionSchema(func: Function): Record<string, unknown> {
  // Check for explicit schema properties (common in framework tools)
  const schema =
    (func as any).params_json_schema ??
    (func as any).input_schema ??
    (func as any).parameters ??
    (func as any).schema;

  if (schema && typeof schema === "object") {
    // If it's a Zod schema, try to convert
    if (_isZodSchema(schema)) {
      const jsonSchema = _zodToJsonSchema(schema);
      if (jsonSchema) return jsonSchema;
    }
    return schema;
  }

  return { type: "object", properties: {} };
}

/**
 * Try to detect and extract an agent-as-tool wrapper.
 * Returns serialized config dict or null.
 */
function _tryExtractAgentTool(obj: unknown, workers: WorkerInfo[]): Record<string, unknown> | null {
  if (typeof obj !== "object" || obj === null) return null;
  const asAny = obj as Record<string, unknown>;

  if (!asAny._is_agent_tool && !asAny._agent_instance) return null;

  const childAgent = asAny._agent_instance;
  if (!childAgent) return null;

  const [childConfig, childWorkers] = serializeFrameworkAgent(childAgent);
  workers.push(...childWorkers);

  return {
    _type: "AgentTool",
    name: (asAny.name as string) ?? (childAgent as any).name ?? "agent_tool",
    description: (asAny.description as string) ?? "",
    agent: childConfig,
  };
}

/**
 * Try to recognize a tool-like wrapper object and extract its callable.
 *
 * Many frameworks wrap tool functions in objects that have:
 * - A `name` attribute
 * - A `description` or docstring
 * - A JSON schema (`params_json_schema`, `input_schema`, `parameters`, etc.)
 * - An embedded callable
 */
function _tryExtractToolObject(obj: unknown): WorkerInfo | null {
  if (typeof obj !== "object" || obj === null) return null;
  if (typeof obj === "function") return null;
  const asAny = obj as Record<string, unknown>;

  // Must have a name
  const name = asAny.name;
  if (!name || typeof name !== "string") return null;

  // Must have some kind of schema (indicates it's a tool definition)
  let schema: Record<string, unknown> | null = null;
  for (const schemaKey of ["params_json_schema", "input_schema", "parameters", "schema"]) {
    const val = asAny[schemaKey];
    if (val && typeof val === "object" && !Array.isArray(val)) {
      // Might be a Zod schema
      if (_isZodSchema(val)) {
        const jsonSchema = _zodToJsonSchema(val);
        if (jsonSchema) {
          schema = jsonSchema;
          break;
        }
      }
      schema = val as Record<string, unknown>;
      break;
    }
  }
  if (!schema) return null;

  const description = typeof asAny.description === "string" ? asAny.description : "";

  // Find the embedded callable
  const originalFunc = _findEmbeddedFunction(obj, 2);
  if (originalFunc === null) return null;

  return {
    name,
    description: description.trim().split("\n")[0],
    inputSchema: schema,
    func: originalFunc,
  };
}

/**
 * Walk an object's attributes to find an embedded plain function.
 * Searches up to `maxDepth` levels deep.
 */
function _findEmbeddedFunction(obj: unknown, maxDepth: number): Function | null {
  if (maxDepth <= 0) return null;
  if (typeof obj !== "object" || obj === null) return null;

  const asAny = obj as Record<string, unknown>;

  // Check direct properties for function values
  for (const key of Object.keys(asAny)) {
    const val = asAny[key];
    if (val === null || val === undefined) continue;

    if (typeof val === "function" && !_isClass(val)) {
      return val as Function;
    }

    // Nested object — recurse
    if (typeof val === "object" && val !== null && !Array.isArray(val)) {
      const result = _findEmbeddedFunction(val, maxDepth - 1);
      if (result !== null) return result;
    }
  }

  return null;
}

/**
 * Get serializable keys from an object.
 * Uses Object.keys for plain objects, and Object.getOwnPropertyNames for class instances.
 */
function _getSerializableKeys(obj: object): string[] {
  const keys = new Set<string>();
  // Enumerable own properties
  for (const key of Object.keys(obj)) {
    keys.add(key);
  }
  return Array.from(keys);
}

/**
 * Check if an object is a Zod schema.
 */
function _isZodSchema(obj: unknown): boolean {
  if (typeof obj !== "object" || obj === null) return false;
  const asAny = obj as Record<string, unknown>;
  // Zod schemas have _def property with typeName
  return (
    typeof asAny._def === "object" &&
    asAny._def !== null &&
    typeof (asAny._def as Record<string, unknown>).typeName === "string"
  );
}

/**
 * Convert a Zod schema to JSON Schema.
 * Uses zod-to-json-schema if available, falls back to null.
 */
function _zodToJsonSchema(zodSchema: unknown): Record<string, unknown> | null {
  try {
    // Try dynamic import of zod-to-json-schema

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { zodToJsonSchema: convert } = require("zod-to-json-schema");
    return convert(zodSchema) as Record<string, unknown>;
  } catch {
    return null;
  }
}
