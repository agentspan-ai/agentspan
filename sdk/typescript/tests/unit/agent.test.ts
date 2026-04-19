import { describe, it, expect } from "vitest";
import {
  Agent,
  PromptTemplate,
  scatterGather,
  AgentDec,
  agentsFrom,
  agent,
} from "../../src/agent.js";

// ── Agent construction ─────────────────────────────────────

describe("Agent", () => {
  describe("construction", () => {
    it("creates a simple agent with only name", () => {
      const a = new Agent({ name: "test" });
      expect(a.name).toBe("test");
      expect(a.tools).toEqual([]);
      expect(a.agents).toEqual([]);
      expect(a.maxTurns).toBe(25);
      expect(a.timeoutSeconds).toBe(10);
      expect(a.external).toBe(false);
      expect(a.planner).toBe(false);
      expect(a.guardrails).toEqual([]);
      expect(a.handoffs).toEqual([]);
      expect(a.callbacks).toEqual([]);
    });

    it("creates an agent with all options", () => {
      const subAgent = new Agent({ name: "sub" });
      const memory = {
        toChatMessages: () => [{ role: "user", content: "Hello" }],
        maxMessages: 50,
      };

      const a = new Agent({
        name: "full_agent",
        model: "openai/gpt-4o",
        instructions: "You are helpful.",
        tools: ["tool_ref"],
        agents: [subAgent],
        strategy: "handoff",
        outputType: { type: "object" },
        guardrails: [{ name: "guard1" }],
        memory,
        maxTurns: 10,
        maxTokens: 4096,
        temperature: 0.7,
        timeoutSeconds: 300,
        external: false,
        termination: { toJSON: () => ({ type: "text_mention", text: "DONE" }) },
        handoffs: [
          { toJSON: () => ({ target: "sub", type: "on_text_mention", text: "TRANSFER" }) },
        ],
        allowedTransitions: { full_agent: ["sub"] },
        introduction: "I am the full agent.",
        metadata: { version: "1.0" },
        planner: true,
        includeContents: "default",
        thinkingBudgetTokens: 1024,
        requiredTools: ["tool_a"],
        codeExecutionConfig: { enabled: true, allowedLanguages: ["python"] },
        cliConfig: { enabled: true, allowedCommands: ["git"] },
        credentials: ["OPENAI_API_KEY"],
      });

      expect(a.name).toBe("full_agent");
      expect(a.model).toBe("openai/gpt-4o");
      expect(a.instructions).toBe("You are helpful.");
      expect(a.agents).toHaveLength(1);
      expect(a.strategy).toBe("handoff");
      expect(a.maxTurns).toBe(10);
      expect(a.maxTokens).toBe(4096);
      expect(a.temperature).toBe(0.7);
      expect(a.timeoutSeconds).toBe(300);
      expect(a.planner).toBe(true);
      expect(a.includeContents).toBe("default");
      expect(a.thinkingBudgetTokens).toBe(1024);
      expect(a.requiredTools).toEqual(["tool_a"]);
      expect(a.credentials).toEqual(["OPENAI_API_KEY"]);
    });

    it("supports function-based instructions", () => {
      const a = new Agent({
        name: "dynamic",
        instructions: () => `The date is ${new Date().toISOString().slice(0, 10)}`,
      });
      expect(typeof a.instructions).toBe("function");
    });

    it("supports PromptTemplate instructions", () => {
      const pt = new PromptTemplate("research_prompt", { domain: "tech" }, 2);
      const a = new Agent({
        name: "template_agent",
        instructions: pt,
      });
      expect(a.instructions).toBeInstanceOf(PromptTemplate);
    });
  });

  // ── .pipe() ──────────────────────────────────────────────

  describe(".pipe()", () => {
    it("creates sequential pipeline from two agents", () => {
      const a = new Agent({ name: "a", model: "openai/gpt-4o" });
      const b = new Agent({ name: "b", model: "openai/gpt-4o" });
      const pipeline = a.pipe(b);

      expect(pipeline.strategy).toBe("sequential");
      expect(pipeline.agents).toHaveLength(2);
      expect(pipeline.agents[0]).toBe(a);
      expect(pipeline.agents[1]).toBe(b);
      expect(pipeline.name).toBe("a_b");
      // Model propagated from left-hand side (matching Python >>)
      expect(pipeline.model).toBe("openai/gpt-4o");
    });

    it("flattens sequential pipeline (base spec §14.14)", () => {
      const a = new Agent({ name: "a" });
      const b = new Agent({ name: "b" });
      const c = new Agent({ name: "c" });

      const pipeline = a.pipe(b).pipe(c);

      // Must be flat: [a, b, c], NOT nested
      expect(pipeline.strategy).toBe("sequential");
      expect(pipeline.agents).toHaveLength(3);
      expect(pipeline.agents[0]).toBe(a);
      expect(pipeline.agents[1]).toBe(b);
      expect(pipeline.agents[2]).toBe(c);
      expect(pipeline.name).toBe("a_b_c");
    });

    it("flattens deeply chained pipelines", () => {
      const a = new Agent({ name: "a" });
      const b = new Agent({ name: "b" });
      const c = new Agent({ name: "c" });
      const d = new Agent({ name: "d" });

      const pipeline = a.pipe(b).pipe(c).pipe(d);

      expect(pipeline.agents).toHaveLength(4);
      expect(pipeline.agents.map((ag) => ag.name)).toEqual(["a", "b", "c", "d"]);
    });

    it("does not flatten non-sequential agents", () => {
      const a = new Agent({
        name: "a",
        agents: [new Agent({ name: "sub" })],
        strategy: "parallel",
      });
      const b = new Agent({ name: "b" });

      const pipeline = a.pipe(b);

      // a is parallel, not sequential, so pipe creates new sequential with [a, b]
      expect(pipeline.agents).toHaveLength(2);
      expect(pipeline.agents[0]).toBe(a);
      expect(pipeline.agents[1]).toBe(b);
    });
  });
});

// ── PromptTemplate ─────────────────────────────────────────

describe("PromptTemplate", () => {
  it("creates with name only", () => {
    const pt = new PromptTemplate("my_template");
    expect(pt.name).toBe("my_template");
    expect(pt.variables).toBeUndefined();
    expect(pt.version).toBeUndefined();
  });

  it("creates with all fields", () => {
    const pt = new PromptTemplate("my_template", { domain: "tech", tone: "formal" }, 3);
    expect(pt.name).toBe("my_template");
    expect(pt.variables).toEqual({ domain: "tech", tone: "formal" });
    expect(pt.version).toBe(3);
  });
});

// ── scatterGather ──────────────────────────────────────────

describe("scatterGather()", () => {
  it("creates coordinator with worker agent_tools", () => {
    const worker1 = new Agent({ name: "worker1", model: "openai/gpt-4o" });
    const worker2 = new Agent({ name: "worker2", model: "openai/gpt-4o" });

    const sg = scatterGather({
      name: "research_team",
      model: "openai/gpt-4o",
      instructions: "Research team",
      workers: [worker1, worker2],
    });

    expect(sg.name).toBe("research_team");
    // Workers are tools, not sub-agents
    expect(sg.agents).toHaveLength(0);
    expect(sg.tools).toHaveLength(2);
    expect(sg.tools[0]).toHaveProperty("toolType", "agent_tool");
    expect(sg.tools[1]).toHaveProperty("toolType", "agent_tool");
  });

  it("includes scatter-gather prefix in instructions", () => {
    const sg = scatterGather({
      name: "team",
      model: "openai/gpt-4o",
      workers: [new Agent({ name: "w1" })],
      instructions: "Focus on depth.",
    });
    expect(sg.instructions).toContain("coordinator that decomposes");
    expect(sg.instructions).toContain("MULTIPLE TIMES IN PARALLEL");
    expect(sg.instructions).toContain("Focus on depth.");
  });

  it("defaults model to worker model", () => {
    const sg = scatterGather({
      name: "team",
      workers: [new Agent({ name: "w1", model: "anthropic/claude-sonnet-4-5" })],
    });
    expect(sg.model).toBe("anthropic/claude-sonnet-4-5");
  });

  it("defaults timeout to 300 seconds", () => {
    const sg = scatterGather({
      name: "team",
      workers: [new Agent({ name: "w1" })],
    });
    expect(sg.timeoutSeconds).toBe(300);
  });
});

// ── @AgentDec decorator + agentsFrom() ─────────────────────

describe("@AgentDec decorator + agentsFrom()", () => {
  class Classifiers {
    @AgentDec({ name: "tech_classifier", model: "openai/gpt-4o" })
    techClassifier(_prompt: string): string {
      return "";
    }

    @AgentDec({ name: "business_classifier", model: "anthropic/claude-sonnet-4-5" })
    businessClassifier(_prompt: string): string {
      return "";
    }

    // Not decorated
    helperMethod(): void {}
  }

  it("extracts decorated methods as Agent instances", () => {
    const agents = agentsFrom(new Classifiers());
    expect(agents).toHaveLength(2);
  });

  it("preserves agent options from decorator", () => {
    const agents = agentsFrom(new Classifiers());
    const names = agents.map((a) => a.name);
    expect(names).toContain("tech_classifier");
    expect(names).toContain("business_classifier");

    const tech = agents.find((a) => a.name === "tech_classifier");
    expect(tech?.model).toBe("openai/gpt-4o");

    const biz = agents.find((a) => a.name === "business_classifier");
    expect(biz?.model).toBe("anthropic/claude-sonnet-4-5");
  });
});

// ── agent() functional wrapper ─────────────────────────────

describe("agent() functional wrapper", () => {
  it("creates agent from function", () => {
    const myAgent = agent(() => "You are a researcher.", {
      name: "researcher",
      model: "openai/gpt-4o",
    });

    expect(myAgent).toBeInstanceOf(Agent);
    expect(myAgent.name).toBe("researcher");
    expect(myAgent.model).toBe("openai/gpt-4o");
    expect(typeof myAgent.instructions).toBe("function");
  });
});
