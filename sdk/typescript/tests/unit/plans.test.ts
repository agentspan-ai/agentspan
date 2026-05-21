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
