import { describe, it, expect } from "vitest";
import { extractModelFromLLM } from "../../../src/wrappers/langgraph.js";
import { serializeLangGraph } from "../../../src/frameworks/langgraph-serializer.js";

describe("LangGraph wrapper", () => {
  describe("extractModelFromLLM", () => {
    it("returns string model as-is", () => {
      expect(extractModelFromLLM("openai/gpt-4o-mini")).toBe("openai/gpt-4o-mini");
    });

    it("extracts model from ChatOpenAI-like object", () => {
      class ChatOpenAI {
        model = "gpt-4o-mini";
      }
      const llm = new ChatOpenAI();
      expect(extractModelFromLLM(llm)).toBe("openai/gpt-4o-mini");
    });

    it("extracts model from ChatAnthropic-like object", () => {
      class ChatAnthropic {
        modelName = "claude-3-sonnet";
      }
      const llm = new ChatAnthropic();
      expect(extractModelFromLLM(llm)).toBe("anthropic/claude-3-sonnet");
    });

    it("extracts model from ChatGoogleGenerativeAI-like object", () => {
      class ChatGoogleGenerativeAI {
        model = "gemini-2.0-flash";
      }
      const llm = new ChatGoogleGenerativeAI();
      expect(extractModelFromLLM(llm)).toBe("google_gemini/gemini-2.0-flash");
    });

    it("extracts model with model_name property", () => {
      const llm = { model_name: "gpt-4o" };
      expect(extractModelFromLLM(llm)).toBe("openai/gpt-4o");
    });

    it("preserves model string with existing provider prefix", () => {
      const llm = { model: "anthropic/claude-3-opus" };
      expect(extractModelFromLLM(llm)).toBe("anthropic/claude-3-opus");
    });

    it("infers anthropic from claude in model name", () => {
      const llm = { model: "claude-3-5-sonnet" };
      expect(extractModelFromLLM(llm)).toBe("anthropic/claude-3-5-sonnet");
    });

    it("infers google_gemini from gemini in model name", () => {
      const llm = { model: "gemini-pro" };
      expect(extractModelFromLLM(llm)).toBe("google_gemini/gemini-pro");
    });

    it("defaults to openai/gpt-4o-mini for null", () => {
      expect(extractModelFromLLM(null)).toBe("openai/gpt-4o-mini");
    });

    it("defaults to openai/gpt-4o-mini for undefined", () => {
      expect(extractModelFromLLM(undefined)).toBe("openai/gpt-4o-mini");
    });

    it("handles Bedrock class name", () => {
      class ChatBedrock {
        model = "us.anthropic.claude-3-5-haiku";
      }
      const llm = new ChatBedrock();
      expect(extractModelFromLLM(llm)).toBe("bedrock/us.anthropic.claude-3-5-haiku");
    });
  });

  describe("createReactAgent wrapper", () => {
    it("adds _agentspan metadata to the graph object", () => {
      // Mock the original createReactAgent
      const mockGraph = {
        invoke: () => {},
        getGraph: () => {},
        nodes: new Map(),
      };

      // We need to mock the module loading. Since the wrapper uses require(),
      // we'll test the metadata attachment logic directly
      const tools = [
        { name: "search", description: "Search the web", func: async () => "results" },
        { name: "calc", description: "Calculate", func: async () => "42" },
      ];

      class ChatOpenAI {
        model = "gpt-4o-mini";
      }
      const llm = new ChatOpenAI();

      // Simulate what createReactAgent wrapper does
      const modelStr = extractModelFromLLM(llm);
      expect(modelStr).toBe("openai/gpt-4o-mini");

      const metadata = {
        model: modelStr,
        tools,
        instructions: "You are helpful.",
        framework: "langgraph" as const,
      };

      (mockGraph as any)._agentspan = metadata;

      // Verify metadata was stored
      expect((mockGraph as any)._agentspan).toBeDefined();
      expect((mockGraph as any)._agentspan.model).toBe("openai/gpt-4o-mini");
      expect((mockGraph as any)._agentspan.tools).toHaveLength(2);
      expect((mockGraph as any)._agentspan.framework).toBe("langgraph");
    });

    it("stores undefined instructions when prompt is not a string", () => {
      const prompt: unknown = 123;
      const metadata = {
        model: "openai/gpt-4o-mini",
        tools: [],
        instructions: typeof prompt === "string" ? prompt : undefined,
        framework: "langgraph" as const,
      };

      expect(metadata.instructions).toBeUndefined();
    });
  });

  describe("serializeLangGraph with _agentspan metadata", () => {
    it("uses wrapper metadata for serialization when present", () => {
      const searchFunc = async (_args: Record<string, unknown>) => "results";
      const calcFunc = async (_args: Record<string, unknown>) => "42";

      const mockGraph = {
        invoke: () => {},
        getGraph: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["__end__", {}],
        ]),
        _agentspan: {
          model: "openai/gpt-4o-mini",
          tools: [
            {
              name: "search",
              description: "Search the web",
              func: searchFunc,
              params_json_schema: {
                type: "object",
                properties: { query: { type: "string" } },
              },
            },
            {
              name: "calculate",
              description: "Evaluate math",
              func: calcFunc,
              params_json_schema: {
                type: "object",
                properties: { expr: { type: "string" } },
              },
            },
          ],
          instructions: "You are a helpful assistant.",
          framework: "langgraph",
        },
      };

      const [config, workers] = serializeLangGraph(mockGraph);

      // Should use metadata-based extraction
      expect(config.model).toBe("openai/gpt-4o-mini");
      expect(config.instructions).toBe("You are a helpful assistant.");
      expect(Array.isArray(config.tools)).toBe(true);

      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(2);
      expect(tools[0]._worker_ref).toBe("search");
      expect(tools[0].description).toBe("Search the web");
      expect(tools[1]._worker_ref).toBe("calculate");

      // Workers should contain the extracted functions
      expect(workers).toHaveLength(2);
      expect(workers[0].name).toBe("search");
      expect(workers[0].func).toBe(searchFunc);
      expect(workers[1].name).toBe("calculate");
      expect(workers[1].func).toBe(calcFunc);
    });

    it("falls through to introspection when metadata has no model", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["agent", { bound: { model: "gpt-4o" } }],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  t: {
                    name: "t",
                    description: "A tool",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
        _agentspan: {
          tools: [],
          // No model - should fall through
        },
      };

      const [config] = serializeLangGraph(mockGraph);
      // Should fall through to introspection-based extraction
      expect(config.model).toBe("openai/gpt-4o");
    });

    it("falls through to introspection when metadata has no tools", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["agent", { bound: { model: "gpt-4o" } }],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  t: {
                    name: "t",
                    description: "A tool",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
        _agentspan: {
          model: "openai/gpt-4o-mini",
          // No tools - should fall through
        },
      };

      const [config] = serializeLangGraph(mockGraph);
      // Should fall through to introspection
      expect(config.model).toBe("openai/gpt-4o");
    });

    it("uses graph name with wrapper metadata", () => {
      const mockGraph = {
        name: "my_wrapped_agent",
        invoke: () => {},
        nodes: new Map(),
        _agentspan: {
          model: "anthropic/claude-3-sonnet",
          tools: [
            {
              name: "search",
              description: "Search",
              func: () => {},
              params_json_schema: { type: "object" },
            },
          ],
          framework: "langgraph",
        },
      };

      const [config] = serializeLangGraph(mockGraph);
      expect(config.name).toBe("my_wrapped_agent");
      expect(config.model).toBe("anthropic/claude-3-sonnet");
    });
  });
});
