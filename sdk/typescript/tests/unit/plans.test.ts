// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

import { describe, it, expect } from "vitest";
import { Generate, Op, Plan, Ref, Step } from "../../src/plans";

describe("Op XOR invariant", () => {
  it("rejects neither args nor generate", () => {
    expect(() => new Op("write_file")).toThrow(/exactly one of args or generate/);
  });

  it("rejects both args and generate", () => {
    expect(
      () =>
        new Op("write_file", {
          args: { path: "x" },
          generate: new Generate({ instructions: "i", outputSchema: '{"x":1}' }),
        }),
    ).toThrow(/exactly one of args or generate/);
  });

  it("accepts args only", () => {
    const op = new Op("write_file", { args: { path: "x" } });
    expect(op.toJSON()).toEqual({ tool: "write_file", args: { path: "x" } });
  });

  it("accepts generate only", () => {
    const op = new Op("write_file", {
      generate: new Generate({ instructions: "i", outputSchema: '{"x":1}' }),
    });
    const j = op.toJSON() as { tool: string; generate: { instructions: string } };
    expect(j.tool).toBe("write_file");
    expect(j.generate.instructions).toBe("i");
  });
});

describe("Plan wire format", () => {
  it("serializes a 2-step plan with a Ref through the dependency edge", () => {
    const p = new Plan({
      steps: [
        new Step("fetch", { operations: [new Op("fetch_data", { args: { url: "u" } })] }),
        new Step("summarize", {
          dependsOn: ["fetch"],
          operations: [new Op("summarize", { args: { document: new Ref("fetch") } })],
        }),
      ],
    });
    const j = p.toJSON() as {
      steps: Array<{ id: string; depends_on?: string[]; operations: Array<Record<string, unknown>> }>;
    };
    expect(j.steps[0].id).toBe("fetch");
    expect(j.steps[1].depends_on).toEqual(["fetch"]);
    const refOp = j.steps[1].operations[0] as { args: { document: { $ref: string } } };
    expect(refOp.args.document).toEqual({ $ref: "fetch" });
  });
});

import { Context } from "../../src/plans";

describe("Context dataclass", () => {
  it("text-only construction", () => {
    const c = new Context({ text: "rule one" });
    expect(c.text).toBe("rule one");
    expect(c.url).toBeUndefined();
  });

  it("url-only construction sets defaults", () => {
    const c = new Context({ url: "https://x.example/y" });
    expect(c.url).toBe("https://x.example/y");
    expect(c.text).toBeUndefined();
    expect(c.required).toBe(true);
    expect(c.maxBytes).toBe(16384);
  });

  it("rejects neither text nor url", () => {
    expect(() => new Context({})).toThrow(/exactly one of text or url/);
  });

  it("rejects both text and url", () => {
    expect(() => new Context({ text: "x", url: "https://y/" })).toThrow(
      /exactly one of text or url/,
    );
  });

  it("rejects non-string url", () => {
    expect(() => new Context({ url: 123 as unknown as string })).toThrow(
      /Context.url must be a string/,
    );
  });

  it("rejects non-string text", () => {
    expect(() => new Context({ text: 42 as unknown as string })).toThrow(
      /Context.text must be a string/,
    );
  });

  it("toJSON text-only is minimal", () => {
    expect(new Context({ text: "rule" }).toJSON()).toEqual({ text: "rule" });
  });

  it("toJSON url-only with defaults is minimal", () => {
    expect(new Context({ url: "https://x/" }).toJSON()).toEqual({
      url: "https://x/",
    });
  });

  it("toJSON url with full options preserves credential placeholder verbatim", () => {
    // Server is responsible for the ${} -> #{} escape; SDK passes through.
    const c = new Context({
      url: "https://confluence.example.com/page",
      headers: { Authorization: "Bearer ${CONFLUENCE_TOKEN}" },
      required: false,
      maxBytes: 8192,
    });
    expect(c.toJSON()).toEqual({
      url: "https://confluence.example.com/page",
      headers: { Authorization: "Bearer ${CONFLUENCE_TOKEN}" },
      required: false,
      maxBytes: 8192,
    });
  });
});
