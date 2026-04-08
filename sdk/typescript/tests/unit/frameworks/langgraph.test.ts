import { describe, it, expect } from "vitest";
import { serializeLangGraph } from "../../../src/frameworks/langgraph-serializer.js";

describe("serializeLangGraph", () => {
  describe("full extraction (createReactAgent-style)", () => {
    it("extracts model and tools from graph with ToolNode", () => {
      function searchWeb(query: string) {
        return `results for ${query}`;
      }
      function calculate(expr: string) {
        return eval(expr);
      }

      const mockGraph = {
        name: "research_agent",
        invoke: () => {},
        getGraph: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          [
            "agent",
            {
              bound: {
                first: {
                  model_name: "gpt-4o",
                  constructor: { name: "ChatOpenAI" },
                },
              },
            },
          ],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  search_web: {
                    name: "search_web",
                    description: "Search the web",
                    func: searchWeb,
                    params_json_schema: {
                      type: "object",
                      properties: { query: { type: "string" } },
                    },
                  },
                  calculate: {
                    name: "calculate",
                    description: "Evaluate a math expression",
                    func: calculate,
                    params_json_schema: {
                      type: "object",
                      properties: { expr: { type: "string" } },
                    },
                  },
                },
              },
            },
          ],
          ["__end__", {}],
        ]),
      };

      const [config, workers] = serializeLangGraph(mockGraph);

      // Config should have model and tools
      expect(config.name).toBe("research_agent");
      expect(config.model).toBe("openai/gpt-4o");
      expect(Array.isArray(config.tools)).toBe(true);
      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(2);
      expect(tools[0]._worker_ref).toBe("search_web");
      expect(tools[0].description).toBe("Search the web");
      expect(tools[1]._worker_ref).toBe("calculate");

      // Workers should contain the extracted tool functions
      expect(workers).toHaveLength(2);
      expect(workers[0].name).toBe("search_web");
      expect(workers[0].func).toBe(searchWeb);
      expect(workers[1].name).toBe("calculate");
      expect(workers[1].func).toBe(calculate);
    });

    it("extracts model with provider inference from class name", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          [
            "agent",
            {
              bound: {
                first: {
                  model_name: "claude-3-sonnet",
                  constructor: { name: "ChatAnthropic" },
                },
              },
            },
          ],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  my_tool: {
                    name: "my_tool",
                    description: "A tool",
                    func: () => {},
                    params_json_schema: { type: "object", properties: {} },
                  },
                },
              },
            },
          ],
          ["__end__", {}],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      expect(config.model).toBe("anthropic/claude-3-sonnet");
    });

    it("uses model name as-is when it already includes provider", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          [
            "agent",
            {
              bound: {
                model: "google/gemini-2.0-flash",
              },
            },
          ],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  t: {
                    name: "t",
                    description: "d",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      expect(config.model).toBe("google/gemini-2.0-flash");
    });
  });

  describe("graph-structure (custom StateGraph)", () => {
    it("extracts nodes and edges from a custom graph", () => {
      function planStep(_state: any) {
        return _state;
      }
      function executeStep(_state: any) {
        return _state;
      }

      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          [
            "plan",
            {
              bound: { func: planStep },
            },
          ],
          [
            "execute",
            {
              bound: { func: executeStep },
            },
          ],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "plan"],
            ["plan", "execute"],
            ["execute", "__end__"],
          ]),
        },
      };

      const [config, workers] = serializeLangGraph(mockGraph);

      // Should produce graph-structure config
      expect(config._graph).toBeDefined();
      const graph = config._graph as Record<string, unknown>;
      expect(Array.isArray(graph.nodes)).toBe(true);
      expect(Array.isArray(graph.edges)).toBe(true);

      const nodes = graph.nodes as Record<string, unknown>[];
      expect(nodes).toHaveLength(2);
      expect(nodes[0].name).toBe("plan");
      expect(nodes[1].name).toBe("execute");

      const edges = graph.edges as Record<string, string>[];
      expect(edges.length).toBeGreaterThanOrEqual(2);

      // Workers for each node (wrapped by makeNodeWorker)
      expect(workers).toHaveLength(2);
      expect(typeof workers[0].func).toBe("function");
      expect(typeof workers[1].func).toBe("function");
    });

    it("extracts conditional edges with router workers", () => {
      function processStep(_state: any) {
        return _state;
      }
      function routeDecision(_state: any) {
        return "approve";
      }

      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          [
            "process",
            {
              bound: { func: processStep },
            },
          ],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([["__start__", "process"]]),
          branches: {
            process: {
              default: {
                path: { func: routeDecision },
                ends: { approve: "__end__", reject: "process" },
              },
            },
          },
        },
      };

      const [config, workers] = serializeLangGraph(mockGraph);

      const graph = config._graph as Record<string, unknown>;
      const conditionalEdges = graph.conditional_edges as Record<string, unknown>[];
      expect(conditionalEdges).toHaveLength(1);
      expect(conditionalEdges[0].source).toBe("process");
      expect(conditionalEdges[0]._router_ref).toContain("router");

      // Workers include the node + the router (router is wrapped in makeRouterWorker)
      expect(workers).toHaveLength(2);
      const routerWorker = workers.find((w) => w.name.includes("router"));
      expect(routerWorker).toBeDefined();
      expect(typeof routerWorker!.func).toBe("function");
    });
  });

  describe("LLM interception with model option", () => {
    it("passes LLM object to prep/finish workers when model option is an object", () => {
      // Simulate a custom StateGraph where the node function calls llm.invoke()
      // but the LLM is in a closure (not reachable from graph tree).
      // The function source must contain '.invoke(' to trigger LLM detection.
      const mockLLM = {
        model: "gpt-4o-mini",
        constructor: { name: "ChatOpenAI" },
        invoke: async (_messages: any[]) => ({ content: "mock" }),
      };

      // Use a function whose toString() contains '.invoke(' and Message patterns
      function agentNode(_state: any) {
        // This references llm.invoke() and SystemMessage — triggers LLM detection
        return mockLLM.invoke([{ role: "system", content: "test" }]);
      }

      const mockGraph = {
        name: "debate_agents",
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["agent", { bound: { func: agentNode } }],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "agent"],
            ["agent", "__end__"],
          ]),
        },
        _agentspan: { model: "openai/gpt-4o-mini" },
      };

      // Without model option: LLM detected but no object → inferred (passthrough)
      const [config1, workers1] = serializeLangGraph(mockGraph);
      expect(config1._graph).toBeDefined();
      const nodes1 = (config1._graph as any).nodes as any[];
      const agentNode1 = nodes1.find((n: any) => n.name === "agent");
      expect(agentNode1._llm_node).toBe(true);
      // Prep worker exists but will run as passthrough (llmObj is null)
      const prep1 = workers1.find((w) => w.name.includes("_prep"));
      expect(prep1).toBeDefined();

      // With model option: LLM object wired through → can monkey-patch
      const [config2, workers2] = serializeLangGraph(mockGraph, { model: mockLLM });
      expect(config2._graph).toBeDefined();
      const nodes2 = (config2._graph as any).nodes as any[];
      const agentNode2 = nodes2.find((n: any) => n.name === "agent");
      expect(agentNode2._llm_node).toBe(true);
      expect(agentNode2._llm_prep_ref).toContain("prep");
      expect(agentNode2._llm_finish_ref).toContain("finish");
      // Both prep and finish workers should exist
      const prep2 = workers2.find((w) => w.name.includes("_prep"));
      const finish2 = workers2.find((w) => w.name.includes("_finish"));
      expect(prep2).toBeDefined();
      expect(finish2).toBeDefined();
    });

    it("prep worker captures messages when LLM object is provided", async () => {
      // This test verifies the prep worker actually monkey-patches .invoke()
      // and captures messages (not passthrough) when the LLM object is available.
      const mockLLM = {
        model: "gpt-4o-mini",
        constructor: { name: "ChatOpenAI" },
        invoke: async (_messages: any[]) => ({ content: "real response" }),
      };

      function debateNode(_state: any) {
        return mockLLM.invoke([{ role: "system", content: "You are a debater" }]);
      }

      const mockGraph = {
        name: "debate",
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["pro", { bound: { func: debateNode } }],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "pro"],
            ["pro", "__end__"],
          ]),
        },
        _agentspan: { model: "openai/gpt-4o-mini" },
      };

      // With LLM object: prep worker should capture messages
      const [, workers] = serializeLangGraph(mockGraph, { model: mockLLM });
      const prepWorker = workers.find((w) => w.name.includes("_prep"));
      expect(prepWorker).toBeDefined();

      // Call the prep worker — should intercept llm.invoke and return messages
      const result = await (prepWorker!.func as any)({ state: { topic: "AI" } });
      expect(result.messages).toBeDefined();
      expect(result.messages.length).toBeGreaterThan(0);
      // _skip_llm should NOT be set (messages captured → server does LLM_CHAT_COMPLETE)
      expect(result._skip_llm).toBeUndefined();

      // Without LLM object but mock is a plain object (not BaseChatModel):
      // prototype patching won't intercept it — falls through to passthrough
      const [, workers2] = serializeLangGraph(mockGraph);
      const prepWorker2 = workers2.find((w) => w.name.includes("_prep"));
      const result2 = await (prepWorker2!.func as any)({ state: { topic: "AI" } });
      // Plain object mock → prototype patch doesn't apply → passthrough
      expect(result2._skip_llm).toBe(true);
    });

    it("prep worker uses prototype patching when LLM is in closure (BaseChatModel)", async () => {
      // Simulate a real LangGraph scenario: the node function captures an LLM
      // that extends BaseChatModel in its closure. Without the LLM object reference,
      // the prep worker uses BaseChatModel.prototype.invoke patching.
      let BaseChatModel: any;
      try {
        const mod = await import("@langchain/core/language_models/chat_models");
        BaseChatModel = mod.BaseChatModel;
      } catch {
        // @langchain/core not installed — skip test
        return;
      }

      // Create a minimal BaseChatModel subclass that simulates ChatOpenAI
      class MockChatModel extends BaseChatModel {
        _llmType() {
          return "mock";
        }
        async _generate() {
          return { generations: [] };
        }
      }
      const closureLLM = new MockChatModel({});

      // Node function captures closureLLM via closure — just like user code
      function proNode(_state: any) {
        return closureLLM.invoke([{ role: "system", content: "debate prompt" }]);
      }

      const mockGraph = {
        name: "debate",
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["pro", { bound: { func: proNode } }],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "pro"],
            ["pro", "__end__"],
          ]),
        },
        _agentspan: { model: "openai/gpt-4o-mini" },
      };

      // NO model option passed — LLM is in closure, not accessible
      const [, workers] = serializeLangGraph(mockGraph);
      const prepWorker = workers.find((w) => w.name.includes("_prep"));
      expect(prepWorker).toBeDefined();

      // Call the prep worker — should intercept via BaseChatModel prototype
      const result = await (prepWorker!.func as any)({ state: { topic: "AI" } });
      expect(result.messages).toBeDefined();
      expect(result.messages.length).toBeGreaterThan(0);
      // _skip_llm should NOT be set — messages were captured
      expect(result._skip_llm).toBeUndefined();
    });

    it("prep worker captures messages via fetch interception when prototype patching fails", async () => {
      // Simulate a closure-captured LLM that makes a real fetch call.
      // The fetch interceptor should capture messages from the HTTP request body.
      const _origFetch = globalThis.fetch;

      // Create a fake LLM that calls fetch (simulating OpenAI SDK behavior)
      function makeFakeLLM() {
        return {
          async invoke(messages: any[]) {
            const response = await fetch("https://api.openai.com/v1/chat/completions", {
              method: "POST",
              headers: { "content-type": "application/json", authorization: "Bearer fake" },
              body: JSON.stringify({
                model: "gpt-4o-mini",
                messages: messages.map((m: any) => ({
                  role: m.role || "user",
                  content: m.content || String(m),
                })),
              }),
            });
            const data = await response.json();
            return { content: data.choices?.[0]?.message?.content || "" };
          },
        };
      }

      const closureLLM = makeFakeLLM();

      // Node function uses closure-captured LLM (no prototype chain to patch)
      async function nodeFunc(state: any) {
        const resp = await closureLLM.invoke([
          { role: "system", content: "test system prompt" },
          { role: "user", content: `topic: ${state.topic}` },
        ]);
        return { result: resp.content };
      }

      const mockGraph = {
        name: "fetch_test",
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["agent", { bound: { func: nodeFunc } }],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "agent"],
            ["agent", "__end__"],
          ]),
        },
        _agentspan: { model: "openai/gpt-4o-mini" },
      };

      const [, workers] = serializeLangGraph(mockGraph);
      const prepWorker = workers.find((w) => w.name.includes("_prep"));
      expect(prepWorker).toBeDefined();

      const result = await (prepWorker!.func as any)({ state: { topic: "AI" } });
      expect(result.messages).toBeDefined();
      expect(result.messages.length).toBe(2);
      expect(result.messages[0].role).toBe("system");
      expect(result._skip_llm).toBeUndefined();

      // Verify fetch was restored
      // (The persistent interceptor stays but is in passthrough mode)
    });

    it("finish worker returns mock content via fetch interception", async () => {
      function makeFakeLLM() {
        return {
          async invoke(messages: any[]) {
            const response = await fetch("https://api.openai.com/v1/chat/completions", {
              method: "POST",
              headers: { "content-type": "application/json", authorization: "Bearer fake" },
              body: JSON.stringify({ model: "gpt-4o-mini", messages }),
            });
            const data = await response.json();
            return { content: data.choices?.[0]?.message?.content || "" };
          },
        };
      }

      const closureLLM = makeFakeLLM();

      async function nodeFunc(state: any) {
        const resp = await closureLLM.invoke([{ role: "user", content: state.topic }]);
        return { result: resp.content };
      }

      const mockGraph = {
        name: "fetch_mock_test",
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["agent", { bound: { func: nodeFunc } }],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "agent"],
            ["agent", "__end__"],
          ]),
        },
        _agentspan: { model: "openai/gpt-4o-mini" },
      };

      const [, workers] = serializeLangGraph(mockGraph);
      const finishWorker = workers.find((w) => w.name.includes("_finish"));
      expect(finishWorker).toBeDefined();

      const mockContent = "This is the server-generated LLM response.";
      const result = await (finishWorker!.func as any)({
        state: { topic: "test" },
        llm_result: mockContent,
      });
      expect(result.result).toBe(mockContent);
    });

    it("supports LLM object via _agentspan.llm metadata", () => {
      const mockLLM = {
        model: "gpt-4o-mini",
        constructor: { name: "ChatOpenAI" },
        invoke: async (_messages: any[]) => ({ content: "mock" }),
      };

      function llmNode(_state: any) {
        return mockLLM.invoke([{ role: "system", content: "prompt" }]);
      }

      const mockGraph = {
        name: "test_agent",
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["agent", { bound: { func: llmNode } }],
          ["__end__", {}],
        ]),
        builder: {
          edges: new Set([
            ["__start__", "agent"],
            ["agent", "__end__"],
          ]),
        },
        _agentspan: { model: "openai/gpt-4o-mini", llm: mockLLM },
      };

      const [config, workers] = serializeLangGraph(mockGraph);
      expect(config._graph).toBeDefined();
      // Prep and finish workers should exist (LLM object from metadata)
      const prep = workers.find((w) => w.name.includes("_prep"));
      const finish = workers.find((w) => w.name.includes("_finish"));
      expect(prep).toBeDefined();
      expect(finish).toBeDefined();
    });
  });

  describe("model-only (no tools)", () => {
    it("produces config with model but no tools array", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          [
            "agent",
            {
              bound: {
                first: {
                  model_name: "gpt-4o-mini",
                  constructor: { name: "ChatOpenAI" },
                },
              },
            },
          ],
          ["__end__", {}],
        ]),
      };

      const [config, workers] = serializeLangGraph(mockGraph);
      expect(config.model).toBe("openai/gpt-4o-mini");
      expect(config.tools).toEqual([]);
      expect(workers).toHaveLength(0);
    });
  });

  describe("fallback cases", () => {
    it("falls through to passthrough when no model or tools found", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["__start__", {}],
          ["__end__", {}],
        ]),
      };

      const [config, workers] = serializeLangGraph(mockGraph);
      expect(config._worker_name).toBeDefined();
      expect(workers).toHaveLength(1);
    });

    it("falls through to passthrough for empty graph", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>(),
      };

      const [config, workers] = serializeLangGraph(mockGraph);
      expect(config._worker_name).toBeDefined();
      expect(workers).toHaveLength(1);
    });

    it("handles plain object nodes (not just Map)", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: { agent: {} },
      };

      const [config, workers] = serializeLangGraph(mockGraph);
      expect(config._worker_name).toBeDefined();
      expect(workers).toHaveLength(1);
    });
  });

  describe("JS tools array detection", () => {
    it("extracts tools from bound.tools array (JS ToolNode pattern)", () => {
      function calculate(expr: string) {
        return eval(expr);
      }

      const mockGraph = {
        invoke: () => {},
        nodes: {
          agent: {
            bound: { model: "gpt-4o" },
          },
          tools: {
            bound: {
              tools: [
                {
                  name: "calculate",
                  description: "Evaluate a math expression",
                  func: calculate,
                  schema: { _def: { typeName: "ZodObject" } },
                },
              ],
            },
          },
        },
      };

      const [config, workers] = serializeLangGraph(mockGraph);
      expect(config.model).toBe("openai/gpt-4o");
      expect(Array.isArray(config.tools)).toBe(true);
      const tools = config.tools as Record<string, unknown>[];
      expect(tools).toHaveLength(1);
      expect(tools[0]._worker_ref).toBe("calculate");
      expect(workers).toHaveLength(1);
      expect(workers[0].name).toBe("calculate");
    });

    it("falls through to graph-structure when tools found but model is null", () => {
      // Simulates real JS compiled createReactAgent where model is in closure.
      // Without model, full-extraction is unsafe (server crashes on null model).
      // Should fall through to graph-structure instead.
      const mockGraph = {
        name: "my_agent",
        invoke: () => {},
        nodes: {
          agent: {
            bound: { func: () => {} }, // model hidden in closure
          },
          tools: {
            bound: {
              tools: [
                {
                  name: "search",
                  description: "Search the web",
                  func: () => {},
                },
              ],
            },
          },
        },
        builder: {
          edges: new Set([
            ["__start__", "agent"],
            ["agent", "tools"],
            ["tools", "__end__"],
          ]),
        },
      };

      const [config] = serializeLangGraph(mockGraph);
      // Without model, should produce graph-structure (not full-extraction)
      expect(config.name).toBe("my_agent");
      expect(config._graph).toBeDefined();
    });

    it("triggers full extraction when model is passed via options", () => {
      // Simulates: runtime.run(graph, prompt, { model: llm })
      const mockGraph = {
        name: "my_agent",
        invoke: () => {},
        nodes: {
          agent: {
            bound: { func: () => {} }, // model hidden in closure
          },
          tools: {
            bound: {
              tools: [
                {
                  name: "search",
                  description: "Search the web",
                  func: () => {},
                },
              ],
            },
          },
        },
      };

      // Pass model as LLM-like object (same as ChatOpenAI instance)
      const mockLLM = { model: "gpt-4o-mini", constructor: { name: "ChatOpenAI" } };
      const [config, workers] = serializeLangGraph(mockGraph, { model: mockLLM });
      expect(config.name).toBe("my_agent");
      expect(config.model).toBe("openai/gpt-4o-mini");
      expect(config._graph).toBeUndefined(); // full extraction = no _graph
      expect(Array.isArray(config.tools)).toBe(true);
      expect(workers).toHaveLength(1);
    });

    it("triggers full extraction when model string is passed via options", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: {
          agent: { bound: { func: () => {} } },
          tools: {
            bound: {
              tools: [{ name: "calc", description: "Calculate", func: () => {} }],
            },
          },
        },
      };

      const [config] = serializeLangGraph(mockGraph, {
        model: "anthropic/claude-sonnet-4-20250514",
      });
      expect(config.model).toBe("anthropic/claude-sonnet-4-20250514");
      expect(config._graph).toBeUndefined(); // full extraction
    });
  });

  describe("tool schema extraction", () => {
    it("extracts schema from params_json_schema", () => {
      const schema = { type: "object", properties: { q: { type: "string" } } };
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["agent", { bound: { model: "gpt-4o" } }],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  search: {
                    name: "search",
                    description: "Search",
                    func: () => {},
                    params_json_schema: schema,
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      const tools = config.tools as Record<string, unknown>[];
      expect(tools[0].parameters).toEqual(schema);
    });

    it("falls back to empty schema when no schema property exists", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map<string, unknown>([
          ["agent", { bound: { model: "gpt-4o" } }],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  bare_tool: {
                    name: "bare_tool",
                    description: "No schema",
                    func: () => {},
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      const tools = config.tools as Record<string, unknown>[];
      expect(tools[0].parameters).toEqual({ type: "object", properties: {} });
    });
  });

  describe("name derivation", () => {
    it("uses graph.name when available", () => {
      const mockGraph = {
        name: "my_custom_graph",
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
                    description: "",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      expect(config.name).toBe("my_custom_graph");
    });

    it("defaults to langgraph_agent when no name", () => {
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
                    description: "",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      expect(config.name).toBe("langgraph_agent");
    });

    it('filters out generic "LangGraph" from getName()', () => {
      const mockGraph = {
        invoke: () => {},
        getName: () => "LangGraph",
        nodes: new Map<string, unknown>([
          ["agent", { bound: { model: "gpt-4o" } }],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  t: {
                    name: "t",
                    description: "",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      // "LangGraph" is the generic default, should fall through to _DEFAULT_NAME
      expect(config.name).toBe("langgraph_agent");
    });

    it("uses custom name from getName() when not generic", () => {
      const mockGraph = {
        invoke: () => {},
        getName: () => "my_agent",
        nodes: new Map<string, unknown>([
          ["agent", { bound: { model: "gpt-4o" } }],
          [
            "tools",
            {
              bound: {
                tools_by_name: {
                  t: {
                    name: "t",
                    description: "",
                    func: () => {},
                    params_json_schema: { type: "object" },
                  },
                },
              },
            },
          ],
        ]),
      };

      const [config] = serializeLangGraph(mockGraph);
      expect(config.name).toBe("my_agent");
    });
  });
});
