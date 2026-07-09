// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

/**
 * Typed plan builders for `Strategy.PLAN_EXECUTE`.
 *
 * These types produce the JSON shape PAC (the server's PLAN_AND_COMPILE
 * task) consumes. Use them to construct plans in TypeScript with IDE
 * autocomplete and tsc type-checking, instead of inlining JSON literals.
 *
 * The wire format is identical to the Python SDK's `agentspan.agents.plans`
 * dataclasses: same JSON shape, same field names, same Ref marker
 * (`{"$ref": "step_id"}`). The server compiler is the same path for both
 * SDKs.
 *
 * @example
 *   import { Plan, Step, Op, Ref } from "@conductor-oss/conductor-agent-sdk";
 *
 *   const plan = new Plan({
 *     steps: [
 *       new Step("fetch", { operations: [new Op("fetch_data", { args: { url: URL } })] }),
 *       new Step("summarize", {
 *         dependsOn: ["fetch"],
 *         operations: [new Op("summarize", { args: { document: new Ref("fetch") } })],
 *       }),
 *     ],
 *   });
 *   await runtime.run(harness, prompt, { plan });
 */

// ── Ref ────────────────────────────────────────────────────

/**
 * A reference to a prior step's whole output.
 *
 * Use `new Ref("step_id")` anywhere a literal value would go in an
 * `Op.args` or `Generate.context` to wire one step's output into another
 * step's input — no JSON path, no field selection. The whole result
 * becomes the value at that arg key.
 *
 * The referenced step must be declared in this step's `dependsOn` and
 * must exist in the plan; the server rejects the plan at compile time
 * otherwise (no silent broken refs).
 */
export class Ref {
  readonly stepId: string;

  constructor(stepId: string) {
    if (!stepId || typeof stepId !== "string") {
      throw new Error(`Ref stepId must be a non-empty string, got: ${stepId}`);
    }
    this.stepId = stepId;
  }

  /** Wire format the server's PAC consumes: `{"$ref": "<step_id>"}`. */
  toJSON(): { $ref: string } {
    return { $ref: this.stepId };
  }
}

/**
 * Options for constructing a {@link Context} entry.
 *
 * Exactly one of `text` or `url` must be set. `headers`/`required`/
 * `maxBytes` only apply when `url` is set.
 */
export interface ContextOptions {
  text?: string;
  url?: string;
  headers?: Record<string, string>;
  required?: boolean;
  maxBytes?: number;
}

/**
 * A reference document made available to the PLAN_EXECUTE planner.
 *
 * Appended to the planner's user prompt as a `## Reference Context`
 * block on every planner invocation. Use to ground the planner in
 * domain-specific rules / processes / edge cases that a static
 * `instructions` string can't capture — onboarding playbooks, KYC
 * rules, compliance thresholds, etc.
 *
 * Exactly one of `text` or `url` must be set:
 *
 * * `text`: inlined verbatim — best for short, stable rules.
 * * `url`: HTTP GET on every planner run (no compile-time fetch,
 *   no cache — doc edits go live without recompile). Optional
 *   `headers` carry credential placeholders in the
 *   `${CRED_NAME}` shape; the server escapes them to
 *   `#{CRED_NAME}` so Conductor's templater doesn't consume them
 *   and the runtime credential resolver fills them in at request
 *   time — same auth pipeline as `ToolConfig` HTTP tools.
 *
 * `required=false` substitutes a `[doc unavailable]` marker on
 * fetch failure instead of failing the workflow; `maxBytes`
 * (default 16384) truncates large responses with a
 * `[doc truncated]` marker.
 */
export class Context {
  readonly text?: string;
  readonly url?: string;
  readonly headers?: Record<string, string>;
  readonly required: boolean;
  readonly maxBytes: number;

  constructor(options: ContextOptions) {
    const hasText = options.text !== undefined && options.text !== null;
    const hasUrl = options.url !== undefined && options.url !== null;
    if (hasText === hasUrl) {
      throw new Error("Context: exactly one of text or url must be set");
    }
    if (hasText && typeof options.text !== "string") {
      throw new Error(`Context.text must be a string; got ${typeof options.text}`);
    }
    if (hasUrl && typeof options.url !== "string") {
      throw new Error(`Context.url must be a string; got ${typeof options.url}`);
    }
    this.text = options.text;
    this.url = options.url;
    this.headers = options.headers;
    this.required = options.required ?? true;
    this.maxBytes = options.maxBytes ?? 16384;
  }

  /**
   * Wire format the server's MultiAgentCompiler consumes. Defaults are
   * omitted so the payload stays tight for the common text-only case.
   */
  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    if (this.text !== undefined) {
      out.text = this.text;
    }
    if (this.url !== undefined) {
      out.url = this.url;
      if (this.headers !== undefined && Object.keys(this.headers).length > 0) {
        out.headers = { ...this.headers };
      }
      if (this.required === false) {
        out.required = false;
      }
      if (this.maxBytes !== 16384) {
        out.maxBytes = this.maxBytes;
      }
    }
    return out;
  }
}

/**
 * Walk an arg value tree and replace nested `Ref` objects with their wire
 * form. Lists and dicts are traversed; scalars and `Ref`s themselves are
 * returned as-is via their `toJSON`.
 *
 * Exported for use by other parts of the SDK that need to serialise plan
 * fragments without going through `Plan.toJSON()`.
 */
export function serializePlanValue(v: unknown): unknown {
  if (v instanceof Ref) return v.toJSON();
  if (Array.isArray(v)) return v.map(serializePlanValue);
  if (v !== null && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, sub] of Object.entries(v as Record<string, unknown>)) {
      out[k] = serializePlanValue(sub);
    }
    return out;
  }
  return v;
}

// ── Generate ──────────────────────────────────────────────

/**
 * LLM-generated arguments for a tool call inside a plan step.
 *
 * When an `Op` carries `generate`, the server emits an LLM call at run
 * time that produces the tool's args from these instructions, then runs
 * the tool with the generated args. Use this when arg values aren't
 * known at plan-construction time (e.g., the body of a `write_file` for
 * a section the LLM should write).
 */
export interface GenerateOptions {
  instructions: string;
  /**
   * A JSON-shape string the LLM's output is parsed into; becomes the
   * tool's args. Example: `'{"path": "out/intro.md", "content": "..."}'`.
   */
  outputSchema: string;
  /** Optional cap on the LLM's response token count. */
  maxTokens?: number;
  /**
   * Optional extra text appended to the LLM's user message. Accepts a
   * plain string or a `Ref(...)` — when a `Ref` is passed the server
   * substitutes the upstream step's output at run time.
   */
  context?: unknown;
}

export class Generate {
  readonly instructions: string;
  readonly outputSchema: string;
  readonly maxTokens?: number;
  readonly context?: unknown;

  constructor(opts: GenerateOptions) {
    this.instructions = opts.instructions;
    this.outputSchema = opts.outputSchema;
    this.maxTokens = opts.maxTokens;
    this.context = opts.context;
  }

  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = {
      instructions: this.instructions,
      output_schema: this.outputSchema,
    };
    if (this.maxTokens !== undefined) out.max_tokens = this.maxTokens;
    if (this.context !== undefined) out.context = serializePlanValue(this.context);
    return out;
  }
}

// ── Op ────────────────────────────────────────────────────

export interface OpOptions {
  /** Literal arg map for a deterministic call. */
  args?: Record<string, unknown>;
  /** LLM-generated args (mutually exclusive with `args`). */
  generate?: Generate;
}

/**
 * A single tool invocation within a plan step. Exactly one of `args`
 * or `generate` should be set.
 */
export class Op {
  readonly tool: string;
  readonly args?: Record<string, unknown>;
  readonly generate?: Generate;

  constructor(tool: string, opts: OpOptions = {}) {
    if ((opts.args === undefined) === (opts.generate === undefined)) {
      throw new Error(
        `Op('${tool}'): exactly one of args or generate must be set`,
      );
    }
    this.tool = tool;
    this.args = opts.args;
    this.generate = opts.generate;
  }

  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = { tool: this.tool };
    if (this.args !== undefined) out.args = serializePlanValue(this.args);
    if (this.generate !== undefined) out.generate = this.generate.toJSON();
    return out;
  }
}

// ── Step ──────────────────────────────────────────────────

export interface StepOptions {
  operations?: Op[];
  /** Other step ids this step waits for. */
  dependsOn?: string[];
  /** When true, run `operations` concurrently inside this step. */
  parallel?: boolean;
}

export class Step {
  readonly id: string;
  readonly operations: Op[];
  readonly dependsOn: string[];
  readonly parallel: boolean;

  constructor(id: string, opts: StepOptions = {}) {
    this.id = id;
    this.operations = opts.operations ?? [];
    this.dependsOn = opts.dependsOn ?? [];
    this.parallel = opts.parallel ?? false;
  }

  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = {
      id: this.id,
      operations: this.operations.map((op) => op.toJSON()),
    };
    if (this.dependsOn.length > 0) out.depends_on = [...this.dependsOn];
    if (this.parallel) out.parallel = true;
    return out;
  }
}

// ── Validation ────────────────────────────────────────────

export interface ValidationOptions {
  args?: Record<string, unknown>;
  /**
   * Optional JS expression evaluated against the tool's output (`$` is
   * the parsed output map). Returns truthy on pass.
   */
  successCondition?: string;
}

export class Validation {
  readonly tool: string;
  readonly args?: Record<string, unknown>;
  readonly successCondition?: string;

  constructor(tool: string, opts: ValidationOptions = {}) {
    this.tool = tool;
    this.args = opts.args;
    this.successCondition = opts.successCondition;
  }

  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = { tool: this.tool };
    if (this.args !== undefined) out.args = serializePlanValue(this.args);
    if (this.successCondition !== undefined) out.success_condition = this.successCondition;
    return out;
  }
}

// ── Action (on_success / on_failure) ──────────────────────

export interface ActionOptions {
  args?: Record<string, unknown>;
}

export class Action {
  readonly tool: string;
  readonly args?: Record<string, unknown>;

  constructor(tool: string, opts: ActionOptions = {}) {
    this.tool = tool;
    this.args = opts.args;
  }

  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = { tool: this.tool };
    if (this.args !== undefined) out.args = serializePlanValue(this.args);
    return out;
  }
}

// ── Plan ──────────────────────────────────────────────────

export interface PlanOptions {
  steps?: Step[];
  validation?: Validation[];
  onSuccess?: Action[];
  onFailure?: Action[];
}

/**
 * A compiled plan ready for `Strategy.PLAN_EXECUTE` execution.
 *
 * Construct directly in TypeScript or pass to `runtime.run(harness,
 * prompt, { plan: ... })` to skip the planner LLM and run a fully
 * deterministic pipeline.
 */
export class Plan {
  readonly steps: Step[];
  readonly validation: Validation[];
  readonly onSuccess: Action[];
  readonly onFailure: Action[];

  constructor(opts: PlanOptions = {}) {
    this.steps = opts.steps ?? [];
    this.validation = opts.validation ?? [];
    this.onSuccess = opts.onSuccess ?? [];
    this.onFailure = opts.onFailure ?? [];
  }

  toJSON(): Record<string, unknown> {
    const out: Record<string, unknown> = {
      steps: this.steps.map((s) => s.toJSON()),
    };
    if (this.validation.length > 0) {
      out.validation = this.validation.map((v) => v.toJSON());
    }
    if (this.onSuccess.length > 0) {
      out.on_success = this.onSuccess.map((a) => a.toJSON());
    }
    if (this.onFailure.length > 0) {
      out.on_failure = this.onFailure.map((a) => a.toJSON());
    }
    return out;
  }
}

/**
 * Anything `runtime.run(harness, prompt, { plan })` accepts: a typed
 * `Plan` or a raw JSON-shaped dict.
 */
export type PlanLike = Plan | Record<string, unknown>;

/** Normalise a Plan-or-dict into the JSON dict shape PAC expects. */
export function coercePlan(plan: PlanLike): Record<string, unknown> {
  if (plan instanceof Plan) return plan.toJSON();
  if (plan !== null && typeof plan === "object") return plan as Record<string, unknown>;
  throw new TypeError(`plan must be a Plan or a dict; got ${typeof plan}`);
}
