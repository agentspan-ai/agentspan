import { describe, it, expect } from "vitest";
import { detectFramework } from "../../../src/frameworks/detect.js";
import { Agent } from "../../../src/agent.js";

// ── detectFramework ──────────────────────────────────────

describe("detectFramework", () => {
  describe("native Agent", () => {
    it("returns null for a native Agent instance", () => {
      const agent = new Agent({ name: "test" });
      expect(detectFramework(agent)).toBeNull();
    });

    it("returns null for an Agent with tools and sub-agents", () => {
      const sub = new Agent({ name: "sub" });
      const agent = new Agent({
        name: "parent",
        agents: [sub],
        tools: [],
      });
      expect(detectFramework(agent)).toBeNull();
    });
  });

  describe("LangGraph detection", () => {
    it("detects object with invoke() and getGraph()", () => {
      const mockGraph = {
        invoke: () => {},
        getGraph: () => {},
      };
      expect(detectFramework(mockGraph)).toBe("langgraph");
    });

    it("detects object with invoke() and nodes Map", () => {
      const mockGraph = {
        invoke: () => {},
        nodes: new Map([["node1", {}]]),
      };
      expect(detectFramework(mockGraph)).toBe("langgraph");
    });

    it("does not detect when invoke is missing", () => {
      const mock = {
        getGraph: () => {},
        nodes: new Map(),
      };
      expect(detectFramework(mock)).not.toBe("langgraph");
    });

    it("does not detect when neither getGraph nor nodes exist", () => {
      const mock = {
        invoke: () => {},
      };
      expect(detectFramework(mock)).not.toBe("langgraph");
    });

    it("does not detect when nodes is a plain object (not a Map)", () => {
      const mock = {
        invoke: () => {},
        nodes: { node1: {} },
      };
      // nodes must be a Map, not a plain object
      expect(detectFramework(mock)).not.toBe("langgraph");
    });
  });

  describe("LangChain detection", () => {
    it("detects object with invoke() and lc_namespace array", () => {
      const mockExecutor = {
        invoke: () => {},
        lc_namespace: ["langchain", "agents"],
      };
      expect(detectFramework(mockExecutor)).toBe("langchain");
    });

    it("does not detect when lc_namespace is not an array", () => {
      const mock = {
        invoke: () => {},
        lc_namespace: "langchain",
      };
      expect(detectFramework(mock)).not.toBe("langchain");
    });

    it("does not detect when invoke is missing", () => {
      const mock = {
        lc_namespace: ["langchain"],
      };
      expect(detectFramework(mock)).not.toBe("langchain");
    });
  });

  describe("OpenAI Agents SDK detection", () => {
    it("detects Agent with name, instructions, model, tools, handoffs", () => {
      const mockAgent = {
        name: "test",
        instructions: "You are helpful.",
        model: "gpt-4o",
        tools: [],
        handoffs: [],
      };
      expect(detectFramework(mockAgent)).toBe("openai");
    });

    it("detects Agent with inputGuardrails/outputGuardrails", () => {
      const mockAgent = {
        name: "test",
        instructions: "hi",
        model: "gpt-4o-mini",
        tools: [],
        inputGuardrails: [],
        outputGuardrails: [],
      };
      expect(detectFramework(mockAgent)).toBe("openai");
    });

    it("detects Agent with asTool method", () => {
      const mockAgent = {
        name: "test",
        instructions: "hi",
        model: "gpt-4",
        tools: [{ name: "search" }],
        asTool: () => {},
      };
      expect(detectFramework(mockAgent)).toBe("openai");
    });

    it("does not detect when instructions is missing", () => {
      const mock = {
        name: "test",
        model: "gpt-4",
        tools: [],
        handoffs: [],
      };
      expect(detectFramework(mock)).not.toBe("openai");
    });
  });

  describe("Google ADK detection", () => {
    it("detects object with model and beforeModelCallback", () => {
      const mockAgent = {
        model: "gemini-pro",
        beforeModelCallback: () => {},
      };
      expect(detectFramework(mockAgent)).toBe("google_adk");
    });

    it("detects object with model and afterModelCallback", () => {
      const mockAgent = {
        model: "gemini-pro",
        afterModelCallback: () => {},
      };
      expect(detectFramework(mockAgent)).toBe("google_adk");
    });

    it("detects object with model and instruction string", () => {
      const mockAgent = {
        model: "gemini-pro",
        instruction: "You are a helpful assistant",
      };
      expect(detectFramework(mockAgent)).toBe("google_adk");
    });

    it("detects object with model and generateContentConfig", () => {
      const mockAgent = {
        model: "gemini-2.0-flash",
        generateContentConfig: { temperature: 0.5 },
      };
      expect(detectFramework(mockAgent)).toBe("google_adk");
    });

    it("detects object with model and outputKey", () => {
      const mockAgent = {
        model: "models/gemini-pro",
        outputKey: "result",
      };
      expect(detectFramework(mockAgent)).toBe("google_adk");
    });

    it("does not detect when model is missing", () => {
      const mock = {
        instruction: "You are helpful",
        beforeModelCallback: () => {},
      };
      expect(detectFramework(mock)).not.toBe("google_adk");
    });
  });

  describe("unknown objects", () => {
    it("returns null for null", () => {
      expect(detectFramework(null)).toBeNull();
    });

    it("returns null for undefined", () => {
      expect(detectFramework(undefined)).toBeNull();
    });

    it("returns null for a plain object", () => {
      expect(detectFramework({})).toBeNull();
    });

    it("returns null for a string", () => {
      expect(detectFramework("hello")).toBeNull();
    });

    it("returns null for a number", () => {
      expect(detectFramework(42)).toBeNull();
    });

    it("returns null for an object with unrelated methods", () => {
      const mock = {
        execute: () => {},
        configure: () => {},
      };
      expect(detectFramework(mock)).toBeNull();
    });
  });

  describe("priority ordering", () => {
    it("LangGraph takes priority over LangChain when both shapes match", () => {
      // An object that has invoke/getGraph AND lc_namespace
      const mock = {
        invoke: () => {},
        getGraph: () => {},
        lc_namespace: ["langchain"],
      };
      expect(detectFramework(mock)).toBe("langgraph");
    });

    it("LangChain takes priority over OpenAI when both shapes match", () => {
      // An object that has invoke/lc_namespace AND name/instructions/tools/model/handoffs
      const mock = {
        invoke: () => {},
        lc_namespace: ["langchain"],
        name: "test",
        instructions: "hi",
        tools: [],
        model: "gpt-4",
        handoffs: [],
      };
      expect(detectFramework(mock)).toBe("langchain");
    });
  });
});
