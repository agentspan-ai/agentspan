import { describe, it, expect } from "vitest";
import {
  extractModelFromLLM,
  createAgentExecutor,
  createRunnableWithMetadata,
} from "../../../src/wrappers/langchain.js";
import { serializeLangChain } from "../../../src/frameworks/langchain-serializer.js";

describe("LangChain wrapper", () => {
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

    it("extracts model with model_name property", () => {
      const llm = { model_name: "gpt-4o" };
      expect(extractModelFromLLM(llm)).toBe("openai/gpt-4o");
    });

    it("preserves model with existing provider prefix", () => {
      const llm = { model: "anthropic/claude-3-opus" };
      expect(extractModelFromLLM(llm)).toBe("anthropic/claude-3-opus");
    });

    it("defaults to openai/gpt-4o-mini for null", () => {
      expect(extractModelFromLLM(null)).toBe("openai/gpt-4o-mini");
    });
  });

  describe("createAgentExecutor", () => {
    it("attaches _agentspan metadata to executor", () => {
      class ChatOpenAI {
        model = "gpt-4o-mini";
      }
      const llm = new ChatOpenAI();
      const tools = [
        { name: "search", description: "Search the web", func: async () => "results" },
      ];

      const executor = createAgentExecutor({
        agent: { llm },
        tools,
        llm,
      }) as Record<string, unknown>;

      expect(executor._agentspan).toBeDefined();
      const metadata = executor._agentspan as Record<string, unknown>;
      expect(metadata.model).toBe("openai/gpt-4o-mini");
      expect(metadata.tools).toBe(tools);
      expect(metadata.framework).toBe("langchain");
    });

    it("extracts LLM from agent when not provided directly", () => {
      class ChatOpenAI {
        model = "gpt-4o";
      }
      const llm = new ChatOpenAI();
      const tools = [{ name: "calc", description: "Calculate", func: async () => "42" }];

      const executor = createAgentExecutor({
        agent: { llm },
        tools,
      }) as Record<string, unknown>;

      const metadata = executor._agentspan as Record<string, unknown>;
      expect(metadata.model).toBe("openai/gpt-4o");
    });
  });

  describe("createRunnableWithMetadata", () => {
    it("creates a runnable-like object with _agentspan metadata", () => {
      class ChatOpenAI {
        model = "gpt-4o-mini";
      }
      const llm = new ChatOpenAI();
      const myFunc = async (_input: { input: string }) => ({ output: "result" });
      const tools = [{ name: "search", description: "Search", func: async () => "results" }];

      const runnable = createRunnableWithMetadata({
        func: myFunc,
        llm,
        tools,
        instructions: "You are helpful.",
      }) as Record<string, unknown>;

      expect(runnable.invoke).toBe(myFunc);
      expect(runnable.lc_namespace).toEqual(["langchain", "schema", "runnable"]);
      expect(runnable._agentspan).toBeDefined();

      const metadata = runnable._agentspan as Record<string, unknown>;
      expect(metadata.model).toBe("openai/gpt-4o-mini");
      expect(metadata.tools).toBe(tools);
      expect(metadata.instructions).toBe("You are helpful.");
      expect(metadata.framework).toBe("langchain");
    });
  });

  describe("serializeLangChain with _agentspan metadata", () => {
    it("uses wrapper metadata for serialization when present", () => {
      const searchFunc = async (_args: Record<string, unknown>) => "results";

      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ["langchain", "agents"],
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
        ],
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
          ],
          instructions: "You are a search assistant.",
          framework: "langchain",
        },
      };

      const [config, workers] = serializeLangChain(mockExecutor);

      expect(config.model).toBe("openai/gpt-4o-mini");
      expect(config.instructions).toBe("You are a search assistant.");
      expect(Array.isArray(config.tools)).toBe(true);

      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(1);
      expect(tools[0]._worker_ref).toBe("search");

      expect(workers).toHaveLength(1);
      expect(workers[0].name).toBe("search");
      expect(workers[0].func).toBe(searchFunc);
    });

    it("falls through to introspection when metadata has no model", () => {
      class ChatOpenAI {
        model_name = "gpt-4o";
        constructor() {}
      }
      Object.defineProperty(ChatOpenAI, "name", { value: "ChatOpenAI" });

      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ["langchain", "agents"],
        agent: {
          llm: new ChatOpenAI(),
        },
        tools: [
          {
            name: "calc",
            description: "Calculate",
            func: () => {},
            params_json_schema: { type: "object" },
          },
        ],
        _agentspan: {
          // No model - should fall through
          tools: [],
        },
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.model).toBe("openai/gpt-4o");
    });

    it("uses executor name with wrapper metadata", () => {
      const mockExecutor = {
        name: "my_custom_agent",
        invoke: () => {},
        _agentspan: {
          model: "anthropic/claude-3-sonnet",
          tools: [
            {
              name: "tool1",
              description: "A tool",
              func: () => {},
              params_json_schema: { type: "object" },
            },
          ],
          framework: "langchain",
        },
      };

      const [config] = serializeLangChain(mockExecutor);
      expect(config.name).toBe("my_custom_agent");
      expect(config.model).toBe("anthropic/claude-3-sonnet");
    });
  });
});
