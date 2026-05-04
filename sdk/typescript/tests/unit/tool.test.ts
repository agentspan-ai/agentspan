import { describe, it, expect } from "vitest";
import { z } from "zod";
import {
  tool,
  getToolDef,
  normalizeToolInput,
  isZodSchema,
  httpTool,
  mcpTool,
  apiTool,
  agentTool,
  humanTool,
  imageTool,
  audioTool,
  videoTool,
  pdfTool,
  searchTool,
  indexTool,
  Tool,
  toolsFrom,
} from "../../src/tool.js";
import { Agent } from "../../src/agent.js";
import { ConfigurationError } from "../../src/errors.js";

// ── isZodSchema ────────────────────────────────────────────

describe("isZodSchema", () => {
  it("returns true for Zod schemas", () => {
    expect(isZodSchema(z.object({ city: z.string() }))).toBe(true);
    expect(isZodSchema(z.string())).toBe(true);
  });

  it("returns false for plain objects", () => {
    expect(isZodSchema({ type: "object", properties: {} })).toBe(false);
    expect(isZodSchema(null)).toBe(false);
    expect(isZodSchema(undefined)).toBe(false);
    expect(isZodSchema("string")).toBe(false);
    expect(isZodSchema(42)).toBe(false);
  });
});

// ── tool() with Zod ────────────────────────────────────────

describe("tool() with Zod schema", () => {
  const zodSchema = z.object({ city: z.string() });

  const myTool = tool(async (args: { city: string }) => `Weather in ${args.city}: 72F`, {
    name: "get_weather",
    description: "Get weather for a city",
    inputSchema: zodSchema,
  });

  it("creates a callable function", async () => {
    const result = await myTool({ city: "NYC" });
    expect(result).toBe("Weather in NYC: 72F");
  });

  it("attaches ToolDef via getToolDef", () => {
    const def = getToolDef(myTool);
    expect(def.name).toBe("get_weather");
    expect(def.description).toBe("Get weather for a city");
    expect(def.toolType).toBe("worker");
    expect(def.func).toBeDefined();
    expect(def.func).not.toBeNull();
  });

  it("converts Zod to JSON Schema in inputSchema", () => {
    const def = getToolDef(myTool);
    const schema = def.inputSchema as Record<string, unknown>;
    expect(schema.type).toBe("object");
    expect(schema).toHaveProperty("properties");
    const props = schema.properties as Record<string, unknown>;
    expect(props).toHaveProperty("city");
  });
});

// ── tool() with JSON Schema ────────────────────────────────

describe("tool() with JSON Schema", () => {
  const jsonSchema = {
    type: "object",
    properties: { city: { type: "string" } },
    required: ["city"],
  };

  const myTool = tool(async (args: { city: string }) => `Weather in ${args.city}: 72F`, {
    name: "get_weather_json",
    description: "Get weather (JSON Schema)",
    inputSchema: jsonSchema,
  });

  it("preserves JSON Schema as-is", () => {
    const def = getToolDef(myTool);
    expect(def.inputSchema).toEqual(jsonSchema);
  });

  it("has worker tool type by default", () => {
    const def = getToolDef(myTool);
    expect(def.toolType).toBe("worker");
  });
});

// ── tool() with options ────────────────────────────────────

describe("tool() options", () => {
  it("uses function name as default name", () => {
    async function calculateSum(args: { a: number; b: number }) {
      return args.a + args.b;
    }
    const t = tool(calculateSum, {
      description: "Add two numbers",
      inputSchema: { type: "object", properties: {} },
    });
    const def = getToolDef(t);
    expect(def.name).toBe("calculateSum");
  });

  it("sets func to null when external is true", () => {
    const t = tool(async () => "noop", {
      name: "external_tool",
      description: "Runs elsewhere",
      inputSchema: { type: "object", properties: {} },
      external: true,
    });
    const def = getToolDef(t);
    expect(def.func).toBeNull();
    expect(def.external).toBe(true);
  });

  it("preserves all optional fields", () => {
    const t = tool(async () => ({}), {
      name: "full_tool",
      description: "All options",
      inputSchema: { type: "object", properties: {} },
      outputSchema: { type: "object", properties: { result: { type: "string" } } },
      approvalRequired: true,
      timeoutSeconds: 60,
      isolated: false,
      credentials: ["API_KEY"],
      guardrails: [{ name: "test_guard" }],
    });
    const def = getToolDef(t);
    expect(def.approvalRequired).toBe(true);
    expect(def.timeoutSeconds).toBe(60);
    expect(def.isolated).toBe(false);
    expect(def.credentials).toEqual(["API_KEY"]);
    expect(def.guardrails).toEqual([{ name: "test_guard" }]);
    expect(def.outputSchema).toEqual({
      type: "object",
      properties: { result: { type: "string" } },
    });
  });
});

// ── getToolDef() with all 3 formats ────────────────────────

describe("getToolDef()", () => {
  it("extracts from agentspan tool() wrapper", () => {
    const t = tool(async () => "ok", {
      name: "test",
      description: "test desc",
      inputSchema: { type: "object", properties: {} },
    });
    const def = getToolDef(t);
    expect(def.name).toBe("test");
  });

  it("extracts from Vercel AI SDK tool shape", () => {
    const aiTool = {
      description: "Weather lookup",
      parameters: z.object({ city: z.string() }),
      execute: async (args: { city: string }) => `Weather in ${args.city}`,
    };
    const def = getToolDef(aiTool);
    expect(def.description).toBe("Weather lookup");
    expect(def.toolType).toBe("worker");
    expect(def.func).toBeDefined();
    const schema = def.inputSchema as Record<string, unknown>;
    expect(schema.type).toBe("object");
  });

  it("extracts from raw ToolDef object", () => {
    const raw = {
      name: "raw_tool",
      description: "A raw tool def",
      inputSchema: { type: "object", properties: {} },
      toolType: "http" as const,
    };
    const def = getToolDef(raw);
    expect(def.name).toBe("raw_tool");
    expect(def.toolType).toBe("http");
  });

  it("throws ConfigurationError for unrecognized format", () => {
    expect(() => getToolDef("not a tool")).toThrow(ConfigurationError);
    expect(() => getToolDef(42)).toThrow(ConfigurationError);
    expect(() => getToolDef(null)).toThrow(ConfigurationError);
  });
});

// ── normalizeToolInput() ───────────────────────────────────

describe("normalizeToolInput()", () => {
  it("normalizes agentspan tool", () => {
    const t = tool(async () => "ok", {
      name: "test",
      description: "desc",
      inputSchema: { type: "object", properties: {} },
    });
    const def = normalizeToolInput(t);
    expect(def.name).toBe("test");
  });

  it("normalizes Vercel AI SDK tool", () => {
    const aiTool = {
      description: "Lookup",
      parameters: z.object({ q: z.string() }),
      execute: async () => "result",
    };
    const def = normalizeToolInput(aiTool);
    expect(def.toolType).toBe("worker");
  });

  it("normalizes raw ToolDef", () => {
    const raw = {
      name: "raw",
      description: "desc",
      inputSchema: { type: "object" },
    };
    const def = normalizeToolInput(raw);
    expect(def.name).toBe("raw");
    expect(def.toolType).toBe("worker"); // default
  });
});

// ── Server-side tool constructors ──────────────────────────

describe("httpTool", () => {
  it("creates HTTP tool with all options", () => {
    const t = httpTool({
      name: "search_api",
      description: "Search via API",
      url: "https://api.example.com/search",
      method: "POST",
      headers: { Authorization: "Bearer ${API_KEY}" },
      accept: ["application/json"],
      contentType: "application/json",
      credentials: ["API_KEY"],
      inputSchema: { type: "object", properties: { q: { type: "string" } } },
    });
    expect(t.name).toBe("search_api");
    expect(t.toolType).toBe("http");
    expect(t.func).toBeNull();
    expect(t.config?.url).toBe("https://api.example.com/search");
    expect(t.config?.method).toBe("POST");
    expect(t.config?.headers).toEqual({ Authorization: "Bearer ${API_KEY}" });
    expect(t.config?.credentials).toEqual(["API_KEY"]);
  });

  it("defaults method to GET", () => {
    const t = httpTool({
      name: "get_api",
      description: "Get",
      url: "https://example.com",
    });
    expect(t.config?.method).toBe("GET");
  });
});

describe("mcpTool", () => {
  it("creates MCP tool with snake_case wire config", () => {
    const t = mcpTool({
      serverUrl: "https://mcp.example.com",
      name: "my_mcp",
      description: "MCP desc",
      toolNames: ["tool_a", "tool_b"],
      maxTools: 10,
    });
    expect(t.toolType).toBe("mcp");
    expect(t.func).toBeNull();
    // Wire format uses snake_case keys (server expects this)
    expect(t.config?.server_url).toBe("https://mcp.example.com");
    expect(t.config?.tool_names).toEqual(["tool_a", "tool_b"]);
    expect(t.config?.max_tools).toBe(10);
  });

  it("uses defaults for name, description, and max_tools", () => {
    const t = mcpTool({ serverUrl: "https://mcp.example.com" });
    expect(t.name).toBe("mcp_tools");
    expect(t.description).toBe("MCP tools from https://mcp.example.com");
    expect(t.config?.max_tools).toBe(64);
  });
});

describe("apiTool", () => {
  it("creates API tool with snake_case wire config", () => {
    const t = apiTool({
      url: "https://api.example.com/openapi.json",
      name: "my_api",
      description: "OpenAPI spec",
      maxTools: 32,
    });
    expect(t.toolType).toBe("api");
    expect(t.func).toBeNull();
    expect(t.config?.url).toBe("https://api.example.com/openapi.json");
    expect(t.config?.max_tools).toBe(32);
  });
});

describe("agentTool", () => {
  it("wraps an Agent as a tool", () => {
    const subAgent = new Agent({
      name: "researcher",
      model: "openai/gpt-4o",
    });
    const t = agentTool(subAgent, {
      retryCount: 3,
      retryDelaySeconds: 5,
      optional: true,
    });
    expect(t.toolType).toBe("agent_tool");
    expect(t.name).toBe("researcher");
    expect(t.description).toBe("Invoke the researcher agent");
    expect(t.func).toBeNull();
    // inputSchema should have request property
    const schema = t.inputSchema as Record<string, unknown>;
    const props = schema.properties as Record<string, unknown>;
    expect(props).toHaveProperty("request");
    expect((schema as any).required).toEqual(["request"]);
    expect(t.config?.agent).toBe(subAgent);
    expect(t.config?.retryCount).toBe(3);
    expect(t.config?.retryDelaySeconds).toBe(5);
    expect(t.config?.optional).toBe(true);
  });

  it("uses custom name and description", () => {
    const a = new Agent({ name: "writer" });
    const t = agentTool(a, { name: "custom_name", description: "Custom desc" });
    expect(t.name).toBe("custom_name");
    expect(t.description).toBe("Custom desc");
  });
});

describe("tool() retry options", () => {
  it("retryLogic EXPONENTIAL_BACKOFF is stored on tool config", () => {
    const t = tool(async () => "ok", {
      name: "t",
      description: "test",
      inputSchema: z.object({ x: z.string() }),
      retryLogic: "EXPONENTIAL_BACKOFF",
    });
    const def = getToolDef(t);
    expect(def.retryLogic).toBe("EXPONENTIAL_BACKOFF");
  });

  it("retryLogic defaults to undefined when not set", () => {
    const t = tool(async () => "ok", {
      name: "t",
      description: "test",
      inputSchema: z.object({ x: z.string() }),
    });
    const def = getToolDef(t);
    expect(def.retryLogic).toBeUndefined();
  });

  it("retryLogic LINEAR_BACKOFF is stored", () => {
    const t = tool(async () => "ok", {
      name: "t",
      description: "test",
      inputSchema: z.object({ x: z.string() }),
      retryLogic: "LINEAR_BACKOFF",
    });
    const def = getToolDef(t);
    expect(def.retryLogic).toBe("LINEAR_BACKOFF");
  });

  it("retryLogic FIXED is stored", () => {
    const t = tool(async () => "ok", {
      name: "t",
      description: "test",
      inputSchema: z.object({ x: z.string() }),
      retryLogic: "FIXED",
    });
    const def = getToolDef(t);
    expect(def.retryLogic).toBe("FIXED");
  });

  it("all retry options are stored together", () => {
    const t = tool(async () => "ok", {
      name: "t",
      description: "test",
      inputSchema: z.object({ x: z.string() }),
      retryCount: 5,
      retryDelaySeconds: 3,
      retryLogic: "LINEAR_BACKOFF",
    });
    const def = getToolDef(t);
    expect(def.retryCount).toBe(5);
    expect(def.retryDelaySeconds).toBe(3);
    expect(def.retryLogic).toBe("LINEAR_BACKOFF");
  });
});

describe("humanTool", () => {
  it("creates human tool", () => {
    const t = humanTool({
      name: "review",
      description: "Human review",
      inputSchema: { type: "object", properties: { content: { type: "string" } } },
    });
    expect(t.toolType).toBe("human");
    expect(t.func).toBeNull();
    expect(t.name).toBe("review");
  });
});

describe("imageTool", () => {
  it("creates image tool", () => {
    const t = imageTool({
      name: "gen_img",
      description: "Generate image",
      llmProvider: "openai",
      model: "dall-e-3",
      style: "natural",
      size: "1024x1024",
    });
    expect(t.toolType).toBe("generate_image");
    expect(t.config?.llmProvider).toBe("openai");
    expect(t.config?.model).toBe("dall-e-3");
    expect(t.config?.style).toBe("natural");
    expect(t.config?.size).toBe("1024x1024");
  });
});

describe("audioTool", () => {
  it("creates audio tool", () => {
    const t = audioTool({
      name: "tts",
      description: "Text to speech",
      llmProvider: "openai",
      model: "tts-1",
      voice: "alloy",
      speed: 1.2,
      format: "mp3",
    });
    expect(t.toolType).toBe("generate_audio");
    expect(t.config?.voice).toBe("alloy");
    expect(t.config?.speed).toBe(1.2);
    expect(t.config?.format).toBe("mp3");
  });
});

describe("videoTool", () => {
  it("creates video tool", () => {
    const t = videoTool({
      name: "gen_video",
      description: "Generate video",
      llmProvider: "runway",
      model: "gen-3",
      duration: 10,
      resolution: "1080p",
      fps: 30,
      style: "cinematic",
      aspectRatio: "16:9",
    });
    expect(t.toolType).toBe("generate_video");
    expect(t.config?.duration).toBe(10);
    expect(t.config?.fps).toBe(30);
    expect(t.config?.aspectRatio).toBe("16:9");
  });
});

describe("pdfTool", () => {
  it("creates PDF tool with defaults", () => {
    const t = pdfTool();
    expect(t.toolType).toBe("generate_pdf");
    expect(t.name).toBe("generate_pdf");
    expect(t.description).toBe("Generate a PDF document from markdown text.");
    expect(t.config?.taskType).toBe("GENERATE_PDF");
    // Default inputSchema has markdown required
    expect(t.inputSchema).toHaveProperty("properties.markdown");
    expect(t.inputSchema).toHaveProperty("properties.pageSize");
    expect(t.inputSchema).toHaveProperty("properties.theme");
    expect(t.inputSchema).toHaveProperty("properties.baseFontSize");
    expect((t.inputSchema as any).required).toEqual(["markdown"]);
  });

  it("creates PDF tool with options", () => {
    const t = pdfTool({
      name: "custom_pdf",
      description: "Custom PDF",
      pageSize: "A4",
      theme: "dark",
      fontSize: 14,
    });
    expect(t.name).toBe("custom_pdf");
    expect(t.config?.taskType).toBe("GENERATE_PDF");
    expect(t.config?.pageSize).toBe("A4");
    expect(t.config?.theme).toBe("dark");
    expect(t.config?.fontSize).toBe(14);
  });
});

describe("searchTool", () => {
  it("creates RAG search tool", () => {
    const t = searchTool({
      name: "search_docs",
      description: "Search documentation",
      vectorDb: "pinecone",
      index: "docs-index",
      embeddingModelProvider: "openai",
      embeddingModel: "text-embedding-3-small",
      maxResults: 10,
      dimensions: 1536,
    });
    expect(t.toolType).toBe("rag_search");
    expect(t.config?.taskType).toBe("LLM_SEARCH_INDEX");
    expect(t.config?.vectorDB).toBe("pinecone");
    expect(t.config?.index).toBe("docs-index");
    expect(t.config?.namespace).toBe("default_ns");
    expect(t.config?.maxResults).toBe(10);
    expect(t.config?.dimensions).toBe(1536);
    // Default inputSchema has query required
    expect(t.inputSchema).toHaveProperty("properties.query");
    expect((t.inputSchema as any).required).toEqual(["query"]);
  });
});

describe("indexTool", () => {
  it("creates RAG index tool", () => {
    const t = indexTool({
      name: "index_docs",
      description: "Index documentation",
      vectorDb: "weaviate",
      index: "docs-index",
      embeddingModelProvider: "openai",
      embeddingModel: "text-embedding-3-small",
      chunkSize: 512,
      chunkOverlap: 50,
    });
    expect(t.toolType).toBe("rag_index");
    expect(t.config?.taskType).toBe("LLM_INDEX_TEXT");
    expect(t.config?.vectorDB).toBe("weaviate");
    expect(t.config?.chunkSize).toBe(512);
    expect(t.config?.chunkOverlap).toBe(50);
    expect(t.config?.namespace).toBe("default_ns");
    // Default inputSchema has text and docId required
    expect(t.inputSchema).toHaveProperty("properties.text");
    expect(t.inputSchema).toHaveProperty("properties.docId");
    expect(t.inputSchema).toHaveProperty("properties.metadata");
    expect((t.inputSchema as any).required).toEqual(["text", "docId"]);
  });
});

// ── @Tool decorator + toolsFrom() ─────────────────────────

describe("@Tool decorator + toolsFrom()", () => {
  class ResearchTools {
    @Tool({ description: "Research database" })
    async researchDatabase(query: string): Promise<Record<string, unknown>> {
      return { query, results: 42 };
    }

    @Tool({ external: true, description: "External aggregator" })
    async externalAggregator(_query: string): Promise<Record<string, unknown>> {
      return {};
    }

    @Tool({ approvalRequired: true, description: "Publish article" })
    async publishArticle(_title: string, _content: string): Promise<Record<string, unknown>> {
      return { status: "published" };
    }

    // Not decorated — should NOT be extracted
    async helperMethod(): Promise<void> {}
  }

  it("extracts decorated methods as tools", () => {
    const tools = toolsFrom(new ResearchTools());
    expect(tools).toHaveLength(3);
  });

  it("respects @Tool options", () => {
    const tools = toolsFrom(new ResearchTools());
    const names = tools.map((t) => getToolDef(t).name);
    expect(names).toContain("researchDatabase");
    expect(names).toContain("externalAggregator");
    expect(names).toContain("publishArticle");
  });

  it("marks external tools correctly", () => {
    const tools = toolsFrom(new ResearchTools());
    const external = tools.find((t) => getToolDef(t).name === "externalAggregator");
    expect(external).toBeDefined();
    const def = getToolDef(external!);
    expect(def.external).toBe(true);
    expect(def.func).toBeNull();
  });

  it("marks approval-required tools correctly", () => {
    const tools = toolsFrom(new ResearchTools());
    const publish = tools.find((t) => getToolDef(t).name === "publishArticle");
    const def = getToolDef(publish!);
    expect(def.approvalRequired).toBe(true);
  });

  it("binds methods to instance", async () => {
    const instance = new ResearchTools();
    const tools = toolsFrom(instance);
    const research = tools.find((t) => getToolDef(t).name === "researchDatabase");
    expect(research).toBeDefined();
    // Call the tool — it should work with the bound instance
    const result = await research!("test query" as unknown, undefined);
    expect(result).toEqual({ query: "test query", results: 42 });
  });
});
