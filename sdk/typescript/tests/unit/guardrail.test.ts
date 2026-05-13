import { describe, it, expect } from "vitest";
import {
  guardrail,
  RegexGuardrail,
  LLMGuardrail,
  Guardrail,
  guardrailsFrom,
} from "../../src/guardrail.js";
import type { GuardrailResult } from "../../src/types.js";

// ── guardrail() ──────────────────────────────────────────

describe("guardrail()", () => {
  it("creates a custom guardrail def with defaults", () => {
    const fn = (content: string): GuardrailResult => ({
      passed: !content.includes("bad"),
    });

    const def = guardrail(fn, { name: "my_guard" });

    expect(def.name).toBe("my_guard");
    expect(def.guardrailType).toBe("custom");
    expect(def.position).toBe("output"); // default
    expect(def.onFail).toBe("raise"); // default
    expect(def.taskName).toBe("my_guard");
    expect(def.func).toBe(fn);
    expect(def.maxRetries).toBeUndefined();
  });

  it("creates a custom guardrail def with explicit options", () => {
    const fn = async (content: string): Promise<GuardrailResult> => ({
      passed: true,
      message: `Checked: ${content}`,
    });

    const def = guardrail(fn, {
      name: "checker",
      position: "input",
      onFail: "retry",
      maxRetries: 5,
    });

    expect(def.name).toBe("checker");
    expect(def.guardrailType).toBe("custom");
    expect(def.position).toBe("input");
    expect(def.onFail).toBe("retry");
    expect(def.maxRetries).toBe(5);
    expect(def.taskName).toBe("checker");
    expect(def.func).toBe(fn);
  });

  it("the attached function is callable", async () => {
    const fn = async (content: string): Promise<GuardrailResult> => ({
      passed: content.length > 0,
      message: content.length > 0 ? undefined : "Empty content",
    });

    const def = guardrail(fn, { name: "length_check" });
    const result = await def.func!("hello");
    expect(result.passed).toBe(true);

    const failResult = await def.func!("");
    expect(failResult.passed).toBe(false);
    expect(failResult.message).toBe("Empty content");
  });
});

// ── guardrail.external() ─────────────────────────────────

describe("guardrail.external()", () => {
  it("creates an external guardrail def with defaults", () => {
    const def = guardrail.external({ name: "remote_guard" });

    expect(def.name).toBe("remote_guard");
    expect(def.guardrailType).toBe("external");
    expect(def.position).toBe("output"); // default
    expect(def.onFail).toBe("raise"); // default
    expect(def.taskName).toBe("remote_guard");
    expect(def.func).toBeNull();
  });

  it("creates an external guardrail def with explicit options", () => {
    const def = guardrail.external({
      name: "ext_guard",
      position: "input",
      onFail: "human",
    });

    expect(def.name).toBe("ext_guard");
    expect(def.guardrailType).toBe("external");
    expect(def.position).toBe("input");
    expect(def.onFail).toBe("human");
    expect(def.taskName).toBe("ext_guard");
    expect(def.func).toBeNull();
  });
});

// ── RegexGuardrail ───────────────────────────────────────

describe("RegexGuardrail", () => {
  it("constructs with all options", () => {
    const g = new RegexGuardrail({
      name: "pii_blocker",
      patterns: ["\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\b"],
      mode: "block",
      position: "output",
      onFail: "retry",
      message: "PII detected in output",
    });

    expect(g.name).toBe("pii_blocker");
    expect(g.patterns).toEqual(["\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\b"]);
    expect(g.mode).toBe("block");
    expect(g.position).toBe("output");
    expect(g.onFail).toBe("retry");
    expect(g.message).toBe("PII detected in output");
  });

  it("applies defaults for optional fields", () => {
    const g = new RegexGuardrail({
      name: "url_check",
      patterns: ["https?://"],
      mode: "allow",
    });

    expect(g.position).toBe("output");
    expect(g.onFail).toBe("raise");
    expect(g.message).toBeUndefined();
  });

  it("serializes to GuardrailDef", () => {
    const g = new RegexGuardrail({
      name: "pii_blocker",
      patterns: ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
      mode: "block",
      position: "output",
      onFail: "retry",
      message: "PII detected",
    });

    const def = g.toGuardrailDef();
    expect(def).toEqual({
      name: "pii_blocker",
      position: "output",
      onFail: "retry",
      guardrailType: "regex",
      patterns: ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
      mode: "block",
      message: "PII detected",
      maxRetries: 3,
    });
  });

  it("serializes without optional message", () => {
    const g = new RegexGuardrail({
      name: "check",
      patterns: ["test"],
      mode: "allow",
    });

    const def = g.toGuardrailDef();
    expect(def.message).toBeUndefined();
    expect(def.guardrailType).toBe("regex");
    expect(def.patterns).toEqual(["test"]);
    expect(def.mode).toBe("allow");
  });
});

// ── LLMGuardrail ─────────────────────────────────────────

describe("LLMGuardrail", () => {
  it("constructs with all options", () => {
    const g = new LLMGuardrail({
      name: "bias_checker",
      model: "openai/gpt-4o",
      policy: "Check if the output contains biased language",
      position: "output",
      onFail: "fix",
      maxTokens: 200,
    });

    expect(g.name).toBe("bias_checker");
    expect(g.model).toBe("openai/gpt-4o");
    expect(g.policy).toBe("Check if the output contains biased language");
    expect(g.position).toBe("output");
    expect(g.onFail).toBe("fix");
    expect(g.maxTokens).toBe(200);
  });

  it("applies defaults for optional fields", () => {
    const g = new LLMGuardrail({
      name: "safety",
      model: "anthropic/claude-3-haiku",
      policy: "Is this safe?",
    });

    expect(g.position).toBe("output");
    expect(g.onFail).toBe("raise");
    expect(g.maxTokens).toBeUndefined();
  });

  it("serializes to GuardrailDef", () => {
    const g = new LLMGuardrail({
      name: "bias_checker",
      model: "openai/gpt-4o",
      policy: "Check bias",
      position: "output",
      onFail: "fix",
      maxTokens: 100,
    });

    const def = g.toGuardrailDef();
    expect(def).toEqual({
      name: "bias_checker",
      position: "output",
      onFail: "fix",
      guardrailType: "llm",
      model: "openai/gpt-4o",
      policy: "Check bias",
      maxRetries: 3,
      maxTokens: 100,
    });
  });

  it("serializes without optional maxTokens", () => {
    const g = new LLMGuardrail({
      name: "safety",
      model: "anthropic/claude-3-haiku",
      policy: "Is this safe?",
    });

    const def = g.toGuardrailDef();
    expect(def.maxTokens).toBeUndefined();
    expect(def.guardrailType).toBe("llm");
    expect(def.model).toBe("anthropic/claude-3-haiku");
    expect(def.policy).toBe("Is this safe?");
  });
});

// ── @Guardrail decorator + guardrailsFrom ────────────────

describe("@Guardrail decorator", () => {
  it("extracts decorated methods as GuardrailDef[]", () => {
    class SafetyGuardrails {
      @Guardrail({ position: "output", onFail: "human" })
      factValidator(content: string): GuardrailResult {
        const redFlags = ["the best", "always", "never"];
        const found = redFlags.filter((rf) => content.toLowerCase().includes(rf));
        return found.length > 0
          ? { passed: false, message: `Unverifiable claims: ${found.join(", ")}` }
          : { passed: true };
      }

      @Guardrail({ name: "pii_check", position: "input", onFail: "raise", maxRetries: 2 })
      piiDetector(content: string): GuardrailResult {
        const hasPII = /\b\d{3}-\d{2}-\d{4}\b/.test(content);
        return hasPII ? { passed: false, message: "SSN detected" } : { passed: true };
      }

      // Non-decorated method should be ignored
      helperMethod(): string {
        return "not a guardrail";
      }
    }

    const instance = new SafetyGuardrails();
    const defs = guardrailsFrom(instance);

    expect(defs).toHaveLength(2);

    // factValidator — uses method name as guardrail name
    const factDef = defs.find((d) => d.name === "factValidator");
    expect(factDef).toBeDefined();
    expect(factDef!.guardrailType).toBe("custom");
    expect(factDef!.position).toBe("output");
    expect(factDef!.onFail).toBe("human");
    expect(factDef!.taskName).toBe("factValidator");
    expect(factDef!.func).toBeTypeOf("function");

    // piiDetector — uses explicit name
    const piiDef = defs.find((d) => d.name === "pii_check");
    expect(piiDef).toBeDefined();
    expect(piiDef!.guardrailType).toBe("custom");
    expect(piiDef!.position).toBe("input");
    expect(piiDef!.onFail).toBe("raise");
    expect(piiDef!.maxRetries).toBe(2);
    expect(piiDef!.taskName).toBe("pii_check");
  });

  it("decorated guardrail functions are callable and bound to instance", async () => {
    class MyGuardrails {
      private threshold = 10;

      @Guardrail()
      lengthCheck(content: string): GuardrailResult {
        return content.length >= this.threshold
          ? { passed: true }
          : { passed: false, message: `Too short (min: ${this.threshold})` };
      }
    }

    const instance = new MyGuardrails();
    const defs = guardrailsFrom(instance);
    expect(defs).toHaveLength(1);

    const fn = defs[0].func!;

    // Uses `this.threshold` — proves binding works
    const passResult = await fn("This is long enough content");
    expect(passResult.passed).toBe(true);

    const failResult = await fn("short");
    expect(failResult.passed).toBe(false);
    expect(failResult.message).toBe("Too short (min: 10)");
  });

  it("applies defaults when no options are provided to @Guardrail()", () => {
    class Defaults {
      @Guardrail()
      myGuard(_content: string): GuardrailResult {
        return { passed: true };
      }
    }

    const defs = guardrailsFrom(new Defaults());
    expect(defs).toHaveLength(1);
    expect(defs[0].name).toBe("myGuard");
    expect(defs[0].position).toBe("output");
    expect(defs[0].onFail).toBe("raise");
    expect(defs[0].guardrailType).toBe("custom");
  });

  it("returns empty array for class with no decorated methods", () => {
    class NoGuardrails {
      someMethod(): string {
        return "not a guardrail";
      }
    }

    const defs = guardrailsFrom(new NoGuardrails());
    expect(defs).toHaveLength(0);
  });
});
