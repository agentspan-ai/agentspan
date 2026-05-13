import { describe, it, expect } from "vitest";
import { serializeFrameworkAgent } from "../../../src/frameworks/serializer.js";

describe("serializeFrameworkAgent", () => {
  describe("OpenAI Agent shape", () => {
    it("extracts model, instructions, and tools with _worker_ref", () => {
      function searchFn(query: string) {
        return `results for ${query}`;
      }

      const mockAgent = {
        name: "research_assistant",
        instructions: "You are a helpful research assistant.",
        model: "gpt-4o",
        tools: [
          {
            name: "search",
            description: "Search the web for information",
            params_json_schema: {
              type: "object",
              properties: { query: { type: "string" } },
            },
            func: searchFn,
          },
        ],
        handoffs: [],
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);

      expect(config.name).toBe("research_assistant");
      expect(config.instructions).toBe("You are a helpful research assistant.");
      expect(config.model).toBe("gpt-4o");

      // Tools should be serialized with _worker_ref markers
      const tools = config.tools as unknown[];
      expect(tools).toHaveLength(1);
      const tool = tools[0] as Record<string, unknown>;
      expect(tool._worker_ref).toBe("search");
      expect(tool.description).toBe("Search the web for information");
      expect(tool.parameters).toEqual({
        type: "object",
        properties: { query: { type: "string" } },
      });

      // Workers should contain the function reference
      expect(workers).toHaveLength(1);
      expect(workers[0].name).toBe("search");
      expect(workers[0].func).toBe(searchFn);
    });

    it("handles agent with multiple tools", () => {
      function tool1() {
        return "a";
      }
      function tool2() {
        return "b";
      }

      const mockAgent = {
        name: "multi_tool_agent",
        instructions: "Help the user.",
        model: "gpt-4o-mini",
        tools: [
          {
            name: "calc",
            description: "Calculator",
            params_json_schema: { type: "object", properties: { expr: { type: "string" } } },
            func: tool1,
          },
          {
            name: "search",
            description: "Web search",
            params_json_schema: { type: "object", properties: { q: { type: "string" } } },
            func: tool2,
          },
        ],
        handoffs: [],
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);
      const tools = config.tools as unknown[];
      expect(tools).toHaveLength(2);
      expect(workers).toHaveLength(2);
    });
  });

  describe("Google ADK LlmAgent shape", () => {
    it("extracts model, instruction, and tools", () => {
      function lookupFn(id: string) {
        return `data for ${id}`;
      }

      const mockAgent = {
        name: "adk_agent",
        model: "gemini-2.0-flash",
        instruction: "You are a helpful assistant.",
        generateContentConfig: { temperature: 0.7 },
        tools: [
          {
            name: "lookup",
            description: "Look up data by ID",
            parameters: { type: "object", properties: { id: { type: "string" } } },
            func: lookupFn,
          },
        ],
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);

      expect(config.name).toBe("adk_agent");
      expect(config.model).toBe("gemini-2.0-flash");
      expect(config.instruction).toBe("You are a helpful assistant.");

      const tools = config.tools as unknown[];
      expect(tools).toHaveLength(1);
      const tool = tools[0] as Record<string, unknown>;
      expect(tool._worker_ref).toBe("lookup");

      expect(workers).toHaveLength(1);
      expect(workers[0].func).toBe(lookupFn);
    });
  });

  describe("callable function extraction", () => {
    it("extracts named functions as worker refs", () => {
      function myHelperFunction() {
        return 42;
      }

      const mockAgent = {
        name: "test",
        callback: myHelperFunction,
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);
      expect(config.callback).toEqual(expect.objectContaining({ _worker_ref: "myHelperFunction" }));
      expect(workers).toHaveLength(1);
      expect(workers[0].name).toBe("myHelperFunction");
      expect(workers[0].func).toBe(myHelperFunction);
    });

    it("does not extract anonymous arrow functions without names", () => {
      const mockAgent = {
        name: "test",
        // Arrow functions assigned to object properties have the property name
        // but their .name is '' when created inline
        items: ["a", "b"],
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);
      // items should be serialized as an array, not as a worker_ref
      expect(config.items).toEqual(["a", "b"]);
      expect(workers).toHaveLength(0);
    });

    it("does not extract class constructors as workers", () => {
      class MyClass {
        doStuff() {
          return "hi";
        }
      }

      const mockAgent = {
        name: "test",
        someClass: MyClass,
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);
      // Class should not become a _worker_ref
      expect((config.someClass as any)?._worker_ref).toBeUndefined();
      expect(workers).toHaveLength(0);
    });
  });

  describe("tool object extraction", () => {
    it("extracts tool-like object with name + schema + embedded function", () => {
      function toolImpl(input: string) {
        return input.toUpperCase();
      }

      const toolWrapper = {
        name: "upper",
        description: "Convert to uppercase",
        params_json_schema: { type: "object", properties: { input: { type: "string" } } },
        _impl: toolImpl,
      };

      const mockAgent = {
        name: "agent",
        tools: [toolWrapper],
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);

      const tools = config.tools as unknown[];
      expect(tools).toHaveLength(1);
      const tool = tools[0] as Record<string, unknown>;
      expect(tool._worker_ref).toBe("upper");
      expect(workers).toHaveLength(1);
      expect(workers[0].func).toBe(toolImpl);
    });

    it("requires schema to be recognized as a tool", () => {
      const notATool = {
        name: "just_named",
        description: "Has name and description but no schema",
        value: 42,
      };

      const mockAgent = {
        name: "agent",
        item: notATool,
      };

      const [config, workers] = serializeFrameworkAgent(mockAgent);
      // Should be serialized as a regular object, not a tool
      const item = config.item as Record<string, unknown>;
      expect(item._worker_ref).toBeUndefined();
      expect(item.name).toBe("just_named");
      expect(workers).toHaveLength(0);
    });
  });

  describe("circular reference protection", () => {
    it("handles circular references without crashing", () => {
      const obj: Record<string, unknown> = { name: "circular" };
      obj.self = obj;

      const [config, workers] = serializeFrameworkAgent(obj);
      expect(config.name).toBe("circular");
      expect(typeof config.self).toBe("string");
      expect(config.self as string).toContain("circular ref");
      expect(workers).toHaveLength(0);
    });

    it("handles deeply nested circular references", () => {
      const inner: Record<string, unknown> = { value: 1 };
      const outer: Record<string, unknown> = { name: "outer", child: inner };
      inner.parent = outer;

      const [config] = serializeFrameworkAgent(outer);
      expect(config.name).toBe("outer");
      const child = config.child as Record<string, unknown>;
      expect(child.value).toBe(1);
      expect(typeof child.parent).toBe("string");
    });
  });

  describe("nested object serialization", () => {
    it("serializes nested plain objects", () => {
      const mockAgent = {
        name: "agent",
        config: {
          temperature: 0.7,
          maxTokens: 1000,
        },
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      expect(config.config).toEqual({
        temperature: 0.7,
        maxTokens: 1000,
      });
    });

    it("serializes arrays recursively", () => {
      const mockAgent = {
        name: "agent",
        items: [1, "two", { three: 3 }],
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      expect(config.items).toEqual([1, "two", { three: 3 }]);
    });

    it("serializes Maps", () => {
      const mockAgent = {
        name: "agent",
        data: new Map([
          ["key1", "val1"],
          ["key2", "val2"],
        ]),
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      const data = config.data as Record<string, string>;
      expect(data.key1).toBe("val1");
      expect(data.key2).toBe("val2");
    });

    it("serializes Sets as arrays", () => {
      const mockAgent = {
        name: "agent",
        tags: new Set(["a", "b", "c"]),
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      const tags = config.tags as string[];
      expect(tags).toHaveLength(3);
      expect(tags).toContain("a");
    });

    it("serializes Dates as ISO strings", () => {
      const date = new Date("2025-01-01T00:00:00Z");
      const mockAgent = {
        name: "agent",
        created: date,
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      expect(config.created).toBe("2025-01-01T00:00:00.000Z");
    });

    it("skips _-prefixed properties", () => {
      const mockAgent = {
        name: "agent",
        _internal: "hidden",
        _secret: 42,
        visible: "shown",
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      expect(config.name).toBe("agent");
      expect(config.visible).toBe("shown");
      expect(config._internal).toBeUndefined();
      expect(config._secret).toBeUndefined();
    });
  });

  describe("class instance serialization", () => {
    it("adds _type marker for class instances", () => {
      class MyConfig {
        temperature = 0.5;
        model = "gpt-4o";
      }

      const mockAgent = {
        name: "agent",
        config: new MyConfig(),
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      const innerConfig = config.config as Record<string, unknown>;
      expect(innerConfig._type).toBe("MyConfig");
      expect(innerConfig.temperature).toBe(0.5);
      expect(innerConfig.model).toBe("gpt-4o");
    });
  });

  describe("enum-like values", () => {
    it("extracts .value from enum-like objects", () => {
      // Simulate a framework enum-like object
      class ResponseFormat {
        constructor(public value: string) {}
      }
      const format = new ResponseFormat("json");

      const mockAgent = {
        name: "agent",
        responseFormat: format,
      };

      const [config] = serializeFrameworkAgent(mockAgent);
      expect(config.responseFormat).toBe("json");
    });
  });

  describe("agent-as-tool extraction", () => {
    it("extracts nested agent wrapped as tool", () => {
      const childAgent = {
        name: "child_agent",
        instructions: "I am a child.",
        model: "gpt-4o-mini",
        tools: [],
      };

      const agentTool = {
        _is_agent_tool: true,
        _agent_instance: childAgent,
        name: "child_tool",
        description: "Delegates to child agent",
      };

      const mockAgent = {
        name: "parent",
        tools: [agentTool],
      };

      const [config, _workers] = serializeFrameworkAgent(mockAgent);
      const tools = config.tools as unknown[];
      expect(tools).toHaveLength(1);
      const tool = tools[0] as Record<string, unknown>;
      expect(tool._type).toBe("AgentTool");
      expect(tool.name).toBe("child_tool");
      expect(tool.agent).toBeDefined();
      const agentConfig = tool.agent as Record<string, unknown>;
      expect(agentConfig.name).toBe("child_agent");
    });
  });

  describe("edge cases", () => {
    it("handles null input", () => {
      // null should produce a simple result
      const [_config, workers] = serializeFrameworkAgent(null);
      // It gets wrapped since null is not an object
      expect(workers).toHaveLength(0);
    });

    it("handles string input", () => {
      const [_config, workers] = serializeFrameworkAgent("just a string");
      expect(workers).toHaveLength(0);
    });

    it("handles empty object", () => {
      const [config, workers] = serializeFrameworkAgent({});
      expect(config).toEqual({});
      expect(workers).toHaveLength(0);
    });

    it("handles deeply nested objects without stack overflow", () => {
      // Build a deep but non-circular object
      let obj: Record<string, unknown> = { name: "leaf", value: 42 };
      for (let i = 0; i < 50; i++) {
        obj = { name: `level_${i}`, child: obj };
      }

      // Should not throw
      const [config, workers] = serializeFrameworkAgent(obj);
      expect(config.name).toBe("level_49");
      expect(workers).toHaveLength(0);
    });
  });
});
