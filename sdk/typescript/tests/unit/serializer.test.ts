import { describe, it, expect } from "vitest";
import { z } from "zod";
import { AgentConfigSerializer } from "../../src/serializer.js";
import { Agent, PromptTemplate, scatterGather } from "../../src/agent.js";
import type { CallbackHandler, TerminationCondition, HandoffCondition } from "../../src/agent.js";
import {
  tool,
  httpTool,
  mcpTool,
  apiTool,
  agentTool,
  humanTool,
  imageTool,
  searchTool,
  indexTool,
} from "../../src/tool.js";

const serializer = new AgentConfigSerializer();

// ── serialize() — full payload ─────────────────────────────

describe("AgentConfigSerializer.serialize()", () => {
  it("produces correct top-level payload", () => {
    const a = new Agent({ name: "test_agent", model: "openai/gpt-4o" });
    const payload = serializer.serialize(a, "Hello world", {
      sessionId: "sess-123",
      media: ["image.png"],
      idempotencyKey: "key-1",
    });

    expect(payload.agentConfig).toBeDefined();
    expect(payload.prompt).toBe("Hello world");
    expect(payload.sessionId).toBe("sess-123");
    expect(payload.media).toEqual(["image.png"]);
    expect(payload.idempotencyKey).toBe("key-1");
  });

  it("defaults sessionId to empty string and media to empty array", () => {
    const a = new Agent({ name: "test" });
    const payload = serializer.serialize(a);

    expect(payload.sessionId).toBe("");
    expect(payload.media).toEqual([]);
    expect(payload.prompt).toBe("");
  });

  it("omits idempotencyKey when not provided", () => {
    const a = new Agent({ name: "test" });
    const payload = serializer.serialize(a);

    expect(payload).not.toHaveProperty("idempotencyKey");
  });
});

// ── serializeAgent() — simple agent ────────────────────────

describe("serializeAgent() — simple agent", () => {
  it("serializes a minimal agent", () => {
    const a = new Agent({ name: "simple", model: "openai/gpt-4o" });
    const config = serializer.serializeAgent(a);

    expect(config.name).toBe("simple");
    expect(config.model).toBe("openai/gpt-4o");
    // Default values are always emitted (matching Python)
    expect(config.maxTurns).toBe(25);
    expect(config.timeoutSeconds).toBe(10);
    expect(config.external).toBe(false);
    // No strategy without agents
    expect(config).not.toHaveProperty("strategy");
    // No tools
    expect(config).not.toHaveProperty("tools");
  });

  it("includes non-default scalar values", () => {
    const a = new Agent({
      name: "agent",
      maxTurns: 10,
      maxTokens: 4096,
      temperature: 0.7,
      timeoutSeconds: 300,
      external: true,
      planner: true,
      includeContents: "none",
      requiredTools: ["search"],
    });
    const config = serializer.serializeAgent(a);

    expect(config.maxTurns).toBe(10);
    expect(config.maxTokens).toBe(4096);
    expect(config.temperature).toBe(0.7);
    expect(config.timeoutSeconds).toBe(300);
    expect(config.external).toBe(true);
    expect(config.planner).toBe(true);
    expect(config.includeContents).toBe("none");
    expect(config.requiredTools).toEqual(["search"]);
  });

  it("omits null/undefined values", () => {
    const a = new Agent({ name: "test" });
    const config = serializer.serializeAgent(a);

    expect(config).not.toHaveProperty("model");
    expect(config).not.toHaveProperty("instructions");
    expect(config).not.toHaveProperty("outputType");
    expect(config).not.toHaveProperty("memory");
    expect(config).not.toHaveProperty("termination");
    expect(config).not.toHaveProperty("allowedTransitions");
    expect(config).not.toHaveProperty("introduction");
    expect(config).not.toHaveProperty("metadata");
    expect(config).not.toHaveProperty("thinkingConfig");
    expect(config).not.toHaveProperty("gate");
    expect(config).not.toHaveProperty("credentials");
  });
});

// ── Instructions serialization ─────────────────────────────

describe("serializeAgent() — instructions", () => {
  it("serializes string instructions as-is", () => {
    const a = new Agent({ name: "test", instructions: "You are helpful." });
    const config = serializer.serializeAgent(a);
    expect(config.instructions).toBe("You are helpful.");
  });

  it("serializes PromptTemplate to wire format", () => {
    const pt = new PromptTemplate("research_prompt", { domain: "tech" }, 2);
    const a = new Agent({ name: "test", instructions: pt });
    const config = serializer.serializeAgent(a);

    expect(config.instructions).toEqual({
      type: "prompt_template",
      name: "research_prompt",
      variables: { domain: "tech" },
      version: 2,
    });
  });

  it("serializes PromptTemplate without version", () => {
    const pt = new PromptTemplate("basic");
    const a = new Agent({ name: "test", instructions: pt });
    const config = serializer.serializeAgent(a);
    const instr = config.instructions as Record<string, unknown>;
    expect(instr.type).toBe("prompt_template");
    expect(instr.name).toBe("basic");
    expect(instr).not.toHaveProperty("version");
    expect(instr).not.toHaveProperty("variables");
  });

  it("serializes function instructions by calling them", () => {
    const a = new Agent({
      name: "test",
      instructions: () => "Dynamic instructions",
    });
    const config = serializer.serializeAgent(a);
    expect(config.instructions).toBe("Dynamic instructions");
  });
});

// ── Tools serialization ────────────────────────────────────

describe("serializeAgent() — tools", () => {
  it("serializes native tools with Zod schema", () => {
    const t = tool(async () => "ok", {
      name: "search",
      description: "Search the web",
      inputSchema: z.object({ query: z.string() }),
    });
    const a = new Agent({ name: "test", tools: [t] });
    const config = serializer.serializeAgent(a);

    expect(config.tools).toHaveLength(1);
    const toolConfig = (config.tools as Record<string, unknown>[])[0];
    expect(toolConfig.name).toBe("search");
    expect(toolConfig.description).toBe("Search the web");
    expect(toolConfig.toolType).toBe("worker");
    const schema = toolConfig.inputSchema as Record<string, unknown>;
    expect(schema.type).toBe("object");
    expect(schema).toHaveProperty("properties");
  });

  it("serializes native tools with JSON Schema", () => {
    const t = tool(async () => "ok", {
      name: "search",
      description: "Search",
      inputSchema: { type: "object", properties: { q: { type: "string" } }, required: ["q"] },
    });
    const a = new Agent({ name: "test", tools: [t] });
    const config = serializer.serializeAgent(a);

    const toolConfig = (config.tools as Record<string, unknown>[])[0];
    expect(toolConfig.inputSchema).toEqual({
      type: "object",
      properties: { q: { type: "string" } },
      required: ["q"],
    });
  });

  it("serializes httpTool", () => {
    const t = httpTool({
      name: "api_call",
      description: "Call API",
      url: "https://api.example.com",
      method: "POST",
      headers: { Authorization: "Bearer ${API_KEY}" },
      credentials: ["API_KEY"],
    });
    const a = new Agent({ name: "test", tools: [t] });
    const config = serializer.serializeAgent(a);

    const toolConfig = (config.tools as Record<string, unknown>[])[0];
    expect(toolConfig.toolType).toBe("http");
    const tc = toolConfig.config as Record<string, unknown>;
    expect(tc.url).toBe("https://api.example.com");
    expect(tc.method).toBe("POST");
    expect(tc.credentials).toEqual(["API_KEY"]);
  });

  it("serializes mcpTool", () => {
    const t = mcpTool({
      serverUrl: "https://mcp.example.com",
      name: "mcp",
      description: "MCP",
    });
    const a = new Agent({ name: "test", tools: [t] });
    const config = serializer.serializeAgent(a);

    const toolConfig = (config.tools as Record<string, unknown>[])[0];
    expect(toolConfig.toolType).toBe("mcp");
  });

  it("serializes tool with all optional fields", () => {
    const t = tool(async () => ({}), {
      name: "full",
      description: "Full tool",
      inputSchema: { type: "object", properties: {} },
      outputSchema: { type: "object", properties: { result: { type: "string" } } },
      approvalRequired: true,
      timeoutSeconds: 120,
    });
    const a = new Agent({ name: "test", tools: [t] });
    const config = serializer.serializeAgent(a);

    const toolConfig = (config.tools as Record<string, unknown>[])[0];
    expect(toolConfig.outputSchema).toEqual({
      type: "object",
      properties: { result: { type: "string" } },
    });
    expect(toolConfig.approvalRequired).toBe(true);
    expect(toolConfig.timeoutSeconds).toBe(120);
  });
});

// ── agent_tool serialization ───────────────────────────────

describe("serializeAgent() — nested agent_tool", () => {
  it("serializes agentTool with nested agentConfig", () => {
    const subAgent = new Agent({
      name: "researcher",
      model: "openai/gpt-4o",
      instructions: "Research things",
    });
    const t = agentTool(subAgent, {
      retryCount: 3,
      retryDelaySeconds: 5,
      optional: true,
    });
    const a = new Agent({ name: "orchestrator", tools: [t] });
    const config = serializer.serializeAgent(a);

    const toolConfig = (config.tools as Record<string, unknown>[])[0];
    expect(toolConfig.toolType).toBe("agent_tool");

    const tc = toolConfig.config as Record<string, unknown>;
    expect(tc.retryCount).toBe(3);
    expect(tc.retryDelaySeconds).toBe(5);
    expect(tc.optional).toBe(true);

    // Nested agent should be serialized
    const nested = tc.agentConfig as Record<string, unknown>;
    expect(nested.name).toBe("researcher");
    expect(nested.model).toBe("openai/gpt-4o");
    expect(nested.instructions).toBe("Research things");

    // Should NOT have 'agent' key (it was extracted)
    expect(tc).not.toHaveProperty("agent");
  });
});

// ── Multi-agent strategies ─────────────────────────────────

describe("serializeAgent() — multi-agent", () => {
  it("serializes sequential pipeline", () => {
    const a = new Agent({ name: "a" });
    const b = new Agent({ name: "b" });
    const pipeline = a.pipe(b);
    const config = serializer.serializeAgent(pipeline);

    expect(config.strategy).toBe("sequential");
    const agents = config.agents as Record<string, unknown>[];
    expect(agents).toHaveLength(2);
    expect(agents[0].name).toBe("a");
    expect(agents[1].name).toBe("b");
  });

  it("serializes parallel strategy", () => {
    const w1 = new Agent({ name: "worker1" });
    const w2 = new Agent({ name: "worker2" });
    const parallel = new Agent({
      name: "team",
      agents: [w1, w2],
      strategy: "parallel",
    });
    const config = serializer.serializeAgent(parallel);

    expect(config.strategy).toBe("parallel");
    expect((config.agents as unknown[]).length).toBe(2);
  });

  it("serializes handoff strategy", () => {
    const agent1 = new Agent({ name: "agent1" });
    const agent2 = new Agent({ name: "agent2" });
    const handoff = new Agent({
      name: "handoff_team",
      agents: [agent1, agent2],
      strategy: "handoff",
    });
    const config = serializer.serializeAgent(handoff);

    expect(config.strategy).toBe("handoff");
  });

  it("serializes router with Agent", () => {
    const routerAgent = new Agent({ name: "router", model: "openai/gpt-4o-mini" });
    const a = new Agent({
      name: "routed",
      agents: [new Agent({ name: "a" }), new Agent({ name: "b" })],
      strategy: "router",
      router: routerAgent,
    });
    const config = serializer.serializeAgent(a);

    const router = config.router as Record<string, unknown>;
    expect(router.name).toBe("router");
    expect(router.model).toBe("openai/gpt-4o-mini");
  });

  it("serializes router with function", () => {
    const a = new Agent({
      name: "routed",
      agents: [new Agent({ name: "a" })],
      strategy: "router",
      router: () => "a",
    });
    const config = serializer.serializeAgent(a);

    expect(config.router).toEqual({ taskName: "routed_router_fn" });
  });

  it("omits strategy when no agents", () => {
    const a = new Agent({ name: "solo", strategy: "sequential" });
    const config = serializer.serializeAgent(a);
    expect(config).not.toHaveProperty("strategy");
    expect(config).not.toHaveProperty("agents");
  });
});

// ── outputType serialization ───────────────────────────────

describe("serializeAgent() — outputType", () => {
  it("serializes Zod outputType", () => {
    const schema = z
      .object({
        title: z.string(),
        score: z.number(),
      })
      .describe("ArticleScore");

    const a = new Agent({ name: "test", outputType: schema });
    const config = serializer.serializeAgent(a);

    const ot = config.outputType as Record<string, unknown>;
    expect(ot.className).toBe("ArticleScore");
    const s = ot.schema as Record<string, unknown>;
    expect(s.type).toBe("object");
    expect(s).toHaveProperty("properties");
  });

  it('uses "Output" as default className for undescribed Zod', () => {
    const schema = z.object({ value: z.string() });
    const a = new Agent({ name: "test", outputType: schema });
    const config = serializer.serializeAgent(a);
    const ot = config.outputType as Record<string, unknown>;
    expect(ot.className).toBe("Output");
  });

  it("serializes JSON Schema outputType", () => {
    const schema = {
      type: "object",
      properties: { result: { type: "string" } },
    };
    const a = new Agent({ name: "test", outputType: schema });
    const config = serializer.serializeAgent(a);
    const ot = config.outputType as Record<string, unknown>;
    expect(ot.schema).toEqual(schema);
    expect(ot.className).toBe("Output");
  });
});

// ── Guardrails serialization ───────────────────────────────

describe("serializeAgent() — guardrails", () => {
  it("serializes guardrails", () => {
    const guard = {
      name: "pii_blocker",
      position: "output",
      onFail: "retry",
      maxRetries: 3,
      guardrailType: "regex",
      patterns: ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
      mode: "block",
      message: "PII detected",
    };
    const a = new Agent({ name: "test", guardrails: [guard] });
    const config = serializer.serializeAgent(a);

    const guards = config.guardrails as Record<string, unknown>[];
    expect(guards).toHaveLength(1);
    expect(guards[0]).toEqual(guard);
  });
});

// ── Termination serialization ──────────────────────────────

describe("serializeAgent() — termination", () => {
  it("serializes simple termination", () => {
    const cond: TerminationCondition = {
      toJSON: () => ({ type: "text_mention", text: "DONE", caseSensitive: false }),
    };
    const a = new Agent({ name: "test", termination: cond });
    const config = serializer.serializeAgent(a);

    expect(config.termination).toEqual({
      type: "text_mention",
      text: "DONE",
      caseSensitive: false,
    });
  });

  it("serializes composed AND/OR termination", () => {
    const composed: TerminationCondition = {
      toJSON: () => ({
        type: "or",
        conditions: [
          { type: "text_mention", text: "PUBLISHED" },
          {
            type: "and",
            conditions: [
              { type: "max_message", maxMessages: 50 },
              { type: "token_usage", maxTotalTokens: 100000 },
            ],
          },
        ],
      }),
    };
    const a = new Agent({ name: "test", termination: composed });
    const config = serializer.serializeAgent(a);

    const term = config.termination as Record<string, unknown>;
    expect(term.type).toBe("or");
    const conditions = term.conditions as Record<string, unknown>[];
    expect(conditions).toHaveLength(2);
    expect(conditions[0].type).toBe("text_mention");
    expect(conditions[1].type).toBe("and");
    const inner = (conditions[1] as Record<string, unknown>).conditions as Record<
      string,
      unknown
    >[];
    expect(inner).toHaveLength(2);
    expect(inner[0].type).toBe("max_message");
    expect(inner[1].type).toBe("token_usage");
  });
});

// ── Handoff serialization ──────────────────────────────────

describe("serializeAgent() — handoffs", () => {
  it("serializes handoff conditions", () => {
    const handoffs: HandoffCondition[] = [
      {
        toJSON: () => ({
          target: "writer",
          type: "on_tool_result",
          toolName: "search",
          resultContains: "found",
        }),
      },
      {
        toJSON: () => ({
          target: "editor",
          type: "on_text_mention",
          text: "TRANSFER",
        }),
      },
    ];
    const a = new Agent({ name: "test", handoffs });
    const config = serializer.serializeAgent(a);

    const h = config.handoffs as Record<string, unknown>[];
    expect(h).toHaveLength(2);
    expect(h[0]).toEqual({
      target: "writer",
      type: "on_tool_result",
      toolName: "search",
      resultContains: "found",
    });
    expect(h[1]).toEqual({
      target: "editor",
      type: "on_text_mention",
      text: "TRANSFER",
    });
  });
});

// ── Callback serialization ─────────────────────────────────

describe("serializeAgent() — callbacks", () => {
  it("serializes callbacks with wire positions", () => {
    const handler: CallbackHandler = {
      async onAgentStart() {},
      async onAgentEnd() {},
      async onToolStart() {},
    };
    const a = new Agent({ name: "my_agent", callbacks: [handler] });
    const config = serializer.serializeAgent(a);

    const callbacks = config.callbacks as Record<string, unknown>[];
    expect(callbacks).toHaveLength(3);

    // Check positions and task names
    const positions = callbacks.map((c) => c.position);
    expect(positions).toContain("before_agent");
    expect(positions).toContain("after_agent");
    expect(positions).toContain("before_tool");

    const taskNames = callbacks.map((c) => c.taskName);
    expect(taskNames).toContain("my_agent_before_agent");
    expect(taskNames).toContain("my_agent_after_agent");
    expect(taskNames).toContain("my_agent_before_tool");
  });

  it("skips unimplemented callback methods", () => {
    const handler: CallbackHandler = {
      async onModelEnd() {},
    };
    const a = new Agent({ name: "agent", callbacks: [handler] });
    const config = serializer.serializeAgent(a);

    const callbacks = config.callbacks as Record<string, unknown>[];
    expect(callbacks).toHaveLength(1);
    expect(callbacks[0].position).toBe("after_model");
    expect(callbacks[0].taskName).toBe("agent_after_model");
  });
});

// ── thinkingBudgetTokens → thinkingConfig ──────────────────

describe("serializeAgent() — thinkingConfig", () => {
  it("converts thinkingBudgetTokens to thinkingConfig", () => {
    const a = new Agent({ name: "test", thinkingBudgetTokens: 2048 });
    const config = serializer.serializeAgent(a);

    expect(config).toHaveProperty("thinkingConfig");
    expect(config.thinkingConfig).toEqual({
      enabled: true,
      budgetTokens: 2048,
    });
    expect(config).not.toHaveProperty("thinkingBudgetTokens");
  });
});

// ── stopWhen ───────────────────────────────────────────────

describe("serializeAgent() — stopWhen", () => {
  it("serializes stopWhen to taskName", () => {
    const a = new Agent({
      name: "my_agent",
      stopWhen: () => false,
    });
    const config = serializer.serializeAgent(a);
    expect(config.stopWhen).toEqual({ taskName: "my_agent_stop_when" });
  });
});

// ── Gate serialization ─────────────────────────────────────

describe("serializeAgent() — gate", () => {
  it("serializes TextGate", () => {
    const a = new Agent({
      name: "test",
      gate: { type: "text_contains", text: "APPROVED", caseSensitive: true },
    });
    const config = serializer.serializeAgent(a);
    expect(config.gate).toEqual({
      type: "text_contains",
      text: "APPROVED",
      caseSensitive: true,
    });
  });

  it("serializes text-based gate without explicit type", () => {
    const a = new Agent({
      name: "test",
      gate: { text: "GO", caseSensitive: false },
    });
    const config = serializer.serializeAgent(a);
    expect(config.gate).toEqual({
      type: "text_contains",
      text: "GO",
      caseSensitive: false,
    });
  });

  it("serializes custom gate as taskName", () => {
    const a = new Agent({
      name: "my_agent",
      gate: { fn: () => true },
    });
    const config = serializer.serializeAgent(a);
    expect(config.gate).toEqual({ taskName: "my_agent_gate" });
  });
});

// ── Memory serialization ───────────────────────────────────

describe("serializeAgent() — memory", () => {
  it("serializes conversation memory", () => {
    const memory = {
      toChatMessages: () => [
        { role: "user", content: "Hello" },
        { role: "assistant", content: "Hi there!" },
      ],
      maxMessages: 50,
    };
    const a = new Agent({ name: "test", memory });
    const config = serializer.serializeAgent(a);

    expect(config.memory).toEqual({
      messages: [
        { role: "user", content: "Hello" },
        { role: "assistant", content: "Hi there!" },
      ],
      maxMessages: 50,
    });
  });
});

// ── Credentials serialization ──────────────────────────────

describe("serializeAgent() — credentials", () => {
  it("serializes agent-level credentials", () => {
    const a = new Agent({
      name: "test",
      credentials: ["GITHUB_TOKEN", { envVar: "KUBECONFIG", relativePath: ".kube/config" }],
    });
    const config = serializer.serializeAgent(a);

    expect(config.credentials).toEqual([
      "GITHUB_TOKEN",
      { envVar: "KUBECONFIG", relativePath: ".kube/config" },
    ]);
  });
});

// ── Code execution + CLI config ────────────────────────────

describe("serializeAgent() — code execution and CLI config", () => {
  it("serializes codeExecution config", () => {
    const a = new Agent({
      name: "test",
      codeExecutionConfig: {
        enabled: true,
        allowedLanguages: ["python", "shell"],
        timeout: 30,
      },
    });
    const config = serializer.serializeAgent(a);

    expect(config.codeExecution).toEqual({
      enabled: true,
      allowedLanguages: ["python", "shell"],
      timeout: 30,
    });
  });

  it("serializes cliConfig", () => {
    const a = new Agent({
      name: "test",
      cliConfig: {
        enabled: true,
        allowedCommands: ["git", "gh"],
        timeout: 30,
        allowShell: false,
      },
    });
    const config = serializer.serializeAgent(a);

    expect(config.cliConfig).toEqual({
      enabled: true,
      allowedCommands: ["git", "gh"],
      timeout: 30,
      allowShell: false,
    });
  });
});

// ── All tool types serialization ───────────────────────────

describe("serializeTool() — all tool types", () => {
  it("serializes humanTool", () => {
    const t = humanTool({ name: "review", description: "Review content" });
    const config = serializer.serializeTool(t);
    expect(config.toolType).toBe("human");
    expect(config.name).toBe("review");
  });

  it("serializes imageTool", () => {
    const t = imageTool({
      name: "gen_img",
      description: "Generate image",
      llmProvider: "openai",
      model: "dall-e-3",
    });
    const config = serializer.serializeTool(t);
    expect(config.toolType).toBe("generate_image");
    const c = config.config as Record<string, unknown>;
    expect(c.llmProvider).toBe("openai");
    expect(c.model).toBe("dall-e-3");
  });

  it("serializes searchTool", () => {
    const t = searchTool({
      name: "search",
      description: "Search docs",
      vectorDb: "pinecone",
      index: "docs",
      embeddingModelProvider: "openai",
      embeddingModel: "text-embedding-3-small",
    });
    const config = serializer.serializeTool(t);
    expect(config.toolType).toBe("rag_search");
    const c = config.config as Record<string, unknown>;
    expect(c.vectorDB).toBe("pinecone");
    expect(c.taskType).toBe("LLM_SEARCH_INDEX");
    expect(c.namespace).toBe("default_ns");
    expect(c.maxResults).toBe(5);
  });

  it("serializes indexTool", () => {
    const t = indexTool({
      name: "index",
      description: "Index docs",
      vectorDb: "weaviate",
      index: "docs",
      embeddingModelProvider: "openai",
      embeddingModel: "text-embedding-3-small",
      chunkSize: 512,
    });
    const config = serializer.serializeTool(t);
    expect(config.toolType).toBe("rag_index");
    const c = config.config as Record<string, unknown>;
    expect(c.taskType).toBe("LLM_INDEX_TEXT");
    expect(c.vectorDB).toBe("weaviate");
    expect(c.chunkSize).toBe(512);
  });

  it("serializes apiTool", () => {
    const t = apiTool({
      url: "https://api.example.com/openapi.json",
      name: "my_api",
      description: "API tool",
    });
    const config = serializer.serializeTool(t);
    expect(config.toolType).toBe("api");
    const c = config.config as Record<string, unknown>;
    expect(c.url).toBe("https://api.example.com/openapi.json");
  });
});

// ── Complex multi-agent wire format ────────────────────────

describe("complex multi-agent wire format", () => {
  it("serializes a full pipeline with nested agents", () => {
    const researcher = new Agent({
      name: "researcher",
      model: "openai/gpt-4o",
      instructions: "Research the topic.",
      tools: [
        tool(async () => ({}), {
          name: "search",
          description: "Web search",
          inputSchema: { type: "object", properties: { q: { type: "string" } } },
        }),
      ],
    });

    const writer = new Agent({
      name: "writer",
      model: "openai/gpt-4o",
      instructions: "Write an article.",
    });

    const editor = new Agent({
      name: "editor",
      model: "anthropic/claude-sonnet-4-5",
      instructions: "Edit the article.",
    });

    const pipeline = researcher.pipe(writer).pipe(editor);
    const payload = serializer.serialize(pipeline, "Write about TypeScript");

    const config = payload.agentConfig as Record<string, unknown>;
    expect(config.strategy).toBe("sequential");
    const agents = config.agents as Record<string, unknown>[];
    expect(agents).toHaveLength(3);

    // Researcher has tools
    expect(agents[0].name).toBe("researcher");
    const tools = agents[0].tools as Record<string, unknown>[];
    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe("search");

    // Editor is anthropic model
    expect(agents[2].name).toBe("editor");
    expect(agents[2].model).toBe("anthropic/claude-sonnet-4-5");
  });

  it("serializes scatterGather correctly", () => {
    const sg = scatterGather({
      name: "research_team",
      model: "openai/gpt-4o",
      workers: [
        new Agent({ name: "w1", model: "openai/gpt-4o" }),
        new Agent({ name: "w2", model: "openai/gpt-4o" }),
      ],
    });
    const config = serializer.serializeAgent(sg);

    // scatterGather creates a flat coordinator with agent_tool tools, not parallel sub-agents
    expect(config.name).toBe("research_team");
    const tools = config.tools as Record<string, unknown>[];
    expect(tools).toHaveLength(2);
    expect(tools[0]).toHaveProperty("toolType", "agent_tool");
    expect(tools[1]).toHaveProperty("toolType", "agent_tool");
  });
});

// ── AllowedTransitions ─────────────────────────────────────

describe("serializeAgent() — allowedTransitions", () => {
  it("serializes transition constraints", () => {
    const a = new Agent({
      name: "team",
      agents: [new Agent({ name: "a" }), new Agent({ name: "b" }), new Agent({ name: "c" })],
      strategy: "handoff",
      allowedTransitions: {
        a: ["b", "c"],
        b: ["c"],
      },
    });
    const config = serializer.serializeAgent(a);
    expect(config.allowedTransitions).toEqual({
      a: ["b", "c"],
      b: ["c"],
    });
  });
});

// ── Mixed tool formats ─────────────────────────────────────

describe("serializer handles mixed tool formats", () => {
  it("serializes agentspan + Vercel AI SDK + raw tools in same array", () => {
    // agentspan native
    const t1 = tool(async () => "ok", {
      name: "native_tool",
      description: "Native",
      inputSchema: { type: "object", properties: {} },
    });

    // Vercel AI SDK shape
    const t2 = {
      description: "AI SDK tool",
      parameters: z.object({ x: z.number() }),
      execute: async () => 42,
    };

    // Raw ToolDef
    const t3 = {
      name: "raw_tool",
      description: "Raw",
      inputSchema: { type: "object", properties: {} },
      toolType: "worker" as const,
    };

    const a = new Agent({ name: "mixed", tools: [t1, t2, t3] });
    const config = serializer.serializeAgent(a);

    const tools = config.tools as Record<string, unknown>[];
    expect(tools).toHaveLength(3);
    expect(tools[0].name).toBe("native_tool");
    expect(tools[1].toolType).toBe("worker");
    expect(tools[2].name).toBe("raw_tool");
  });
});
