// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;

namespace Agentspan.Plans;

/// <summary>
/// Typed plan builders for <c>Strategy.PlanExecute</c>.
///
/// <para>These records produce the JSON shape PAC (the server's
/// PLAN_AND_COMPILE task) consumes. The wire format is identical to the
/// Python SDK's <c>agentspan.agents.plans</c> dataclasses and the
/// TypeScript SDK's <c>Plan</c> class — same JSON shape, same field names,
/// same Ref marker (<c>{"$ref": "step_id"}</c>).</para>
///
/// <para>Example:
/// <code>
/// using Agentspan.Plans;
///
/// var plan = new Plan
/// {
///     Steps = [
///         new Step("fetch") { Operations = [new Op("fetch_data", args: new() {{ "url", URL }})] },
///         new Step("summarize")
///         {
///             DependsOn = ["fetch"],
///             Operations = [new Op("summarize", args: new() {{ "document", new Ref("fetch") }})],
///         },
///     ],
/// };
/// await runtime.RunAsync(harness, prompt, plan: plan);
/// </code>
/// </para>
/// </summary>

// ── Ref ──────────────────────────────────────────────────

/// <summary>
/// A reference to a prior step's whole output. Use <c>new Ref("step_id")</c>
/// anywhere a literal value would go in an <see cref="Op"/>'s args (or a
/// <see cref="Generate"/>'s <c>Context</c>) to wire one step's output into
/// another step's input — no JSON path, no field selection.
///
/// <para>The referenced step must be declared in this step's
/// <c>DependsOn</c> and must exist in the plan; the server rejects the plan
/// at compile time otherwise.</para>
/// </summary>
public sealed class Ref
{
    public string StepId { get; }

    public Ref(string stepId)
    {
        if (string.IsNullOrEmpty(stepId))
            throw new ArgumentException("Ref stepId must be a non-empty string", nameof(stepId));
        StepId = stepId;
    }

    /// <summary>Wire format the server's PAC consumes: <c>{"$ref": "&lt;step_id&gt;"}</c>.</summary>
    public JsonObject ToJson() => new() { ["$ref"] = StepId };

    public override string ToString() => $"Ref({StepId})";
}

/// <summary>
/// A reference document made available to the PLAN_EXECUTE planner.
///
/// <para>Appended to the planner's user prompt as a <c>## Reference Context</c>
/// block on every planner invocation. Use to ground the planner in
/// domain-specific rules / processes / edge cases that a static
/// <c>Instructions</c> string can't capture — onboarding playbooks,
/// KYC rules, compliance thresholds, etc.</para>
///
/// <para>Exactly one of <see cref="Text"/> or <see cref="Url"/> must be set.</para>
///
/// <para>For URL entries, optional <see cref="Headers"/> carry credential
/// placeholders in the <c>${CRED_NAME}</c> shape; the server escapes them
/// to <c>#{CRED_NAME}</c> so Conductor's templater doesn't consume them
/// and the runtime credential resolver fills them in at request time —
/// same auth pipeline as HTTP tool headers.</para>
///
/// <para>Mirrors Python's <c>Context</c> dataclass, TypeScript's
/// <c>Context</c> class, and Java's <c>Context</c> — same wire shape
/// produced by <see cref="ToJson"/>.</para>
/// </summary>
public sealed class Context
{
    public string? Text { get; }
    public string? Url { get; }
    public IDictionary<string, string>? Headers { get; }
    public bool Required { get; }
    public int MaxBytes { get; }

    private Context(string? text, string? url, IDictionary<string, string>? headers, bool required, int maxBytes)
    {
        Text = text;
        Url = url;
        Headers = headers;
        Required = required;
        MaxBytes = maxBytes;
    }

    /// <summary>Inline-text Context entry.</summary>
    public static Context FromText(string text)
    {
        if (string.IsNullOrEmpty(text))
            throw new ArgumentException("Context.Text must be a non-empty string", nameof(text));
        return new Context(text, null, null, true, 16384);
    }

    /// <summary>URL Context entry. Optional headers may contain
    /// <c>${CRED_NAME}</c> placeholders that resolve against the agent's
    /// credential store at request time. <paramref name="required"/>=false
    /// substitutes a <c>[doc unavailable]</c> marker on fetch failure
    /// instead of failing the workflow. <paramref name="maxBytes"/>
    /// truncates large responses with a <c>[doc truncated]</c> marker.</summary>
    public static Context FromUrl(
        string url,
        IDictionary<string, string>? headers = null,
        bool required = true,
        int maxBytes = 16384)
    {
        if (string.IsNullOrEmpty(url))
            throw new ArgumentException("Context.Url must be a non-empty string", nameof(url));
        return new Context(null, url, headers, required, maxBytes);
    }

    /// <summary>
    /// Wire format the server's MultiAgentCompiler consumes. Defaults are
    /// omitted so the payload stays tight for the common text-only /
    /// minimal-URL case.
    /// </summary>
    public JsonObject ToJson()
    {
        var obj = new JsonObject();
        if (Text != null)
        {
            obj["text"] = Text;
        }
        if (Url != null)
        {
            obj["url"] = Url;
            if (Headers != null && Headers.Count > 0)
            {
                var h = new JsonObject();
                foreach (var (k, v) in Headers) h[k] = v;
                obj["headers"] = h;
            }
            if (!Required)
            {
                obj["required"] = false;
            }
            if (MaxBytes != 16384)
            {
                obj["maxBytes"] = MaxBytes;
            }
        }
        return obj;
    }

    public override string ToString() =>
        Text != null ? $"Context(text={Text.Substring(0, Math.Min(Text.Length, 40))}…)" : $"Context(url={Url})";
}

internal static class PlanValues
{
    /// <summary>
    /// Walk an arg value tree and replace nested <see cref="Ref"/> instances
    /// with their wire form. Lists and dicts are traversed in place.
    /// </summary>
    internal static JsonNode? SerializeValue(object? v)
    {
        if (v is null) return null;
        if (v is Ref r) return r.ToJson();
        if (v is JsonNode jn) return jn;
        if (v is IDictionary<string, object?> dict)
        {
            var obj = new JsonObject();
            foreach (var (k, sub) in dict) obj[k] = SerializeValue(sub);
            return obj;
        }
        if (v is System.Collections.IEnumerable enumerable && v is not string)
        {
            var arr = new JsonArray();
            foreach (var item in enumerable) arr.Add(SerializeValue(item));
            return arr;
        }
        // Primitives — wrap via JsonValue
        return JsonValue.Create(v);
    }

    internal static JsonObject SerializeArgs(IDictionary<string, object?> args)
    {
        var obj = new JsonObject();
        foreach (var (k, v) in args) obj[k] = SerializeValue(v);
        return obj;
    }
}

// ── Generate ─────────────────────────────────────────────

/// <summary>
/// LLM-generated arguments for a tool call inside a plan step. When an
/// <see cref="Op"/> carries <c>Generate</c>, the server emits an LLM call
/// at run time that produces the tool's args from these instructions.
/// </summary>
public sealed class Generate
{
    public required string Instructions { get; init; }
    public required string OutputSchema { get; init; }
    public int? MaxTokens { get; init; }
    /// <summary>
    /// Optional extra text appended to the LLM's user message. Accepts a
    /// plain string or a <see cref="Ref"/> — when a Ref is passed, the
    /// server substitutes the upstream step's output at run time.
    /// </summary>
    public object? Context { get; init; }

    public JsonObject ToJson()
    {
        var obj = new JsonObject
        {
            ["instructions"] = Instructions,
            ["output_schema"] = OutputSchema,
        };
        if (MaxTokens.HasValue) obj["max_tokens"] = MaxTokens.Value;
        if (Context is not null) obj["context"] = PlanValues.SerializeValue(Context);
        return obj;
    }
}

// ── Op ───────────────────────────────────────────────────

/// <summary>
/// A single tool invocation within a plan step. Exactly one of
/// <c>Args</c> (literal call) or <c>Generate</c> (LLM-driven args) is
/// set, enforced structurally by the constructor / factory.
///
/// <para>Construct via <c>new Op(tool, args)</c> for a deterministic
/// call, or <c>Op.WithGenerate(tool, generate)</c> for an LLM-driven
/// one. There is no bare <c>new Op(tool)</c> — that loophole let a
/// neither-set Op exist and only fail server-side at PAC compile.</para>
/// </summary>
public sealed class Op
{
    public string Tool { get; }
    public Dictionary<string, object?>? Args { get; }
    public Generate? Generate { get; }

    /// <summary>Op with literal args — runs the tool deterministically.</summary>
    public Op(string tool, Dictionary<string, object?> args)
    {
        if (args is null)
            throw new ArgumentNullException(
                nameof(args),
                $"Op('{tool}'): exactly one of args or generate must be set");
        Tool = tool;
        Args = args;
    }

    private Op(string tool, Generate generate)
    {
        Tool = tool;
        Generate = generate;
    }

    /// <summary>Op whose args are produced at runtime by an LLM call.</summary>
    public static Op WithGenerate(string tool, Generate generate)
    {
        if (generate is null)
            throw new ArgumentNullException(
                nameof(generate),
                $"Op('{tool}'): exactly one of args or generate must be set");
        return new Op(tool, generate);
    }

    public JsonObject ToJson()
    {
        // Invariant: exactly one of Args / Generate set — enforced by ctors.
        var obj = new JsonObject { ["tool"] = Tool };
        if (Args is not null) obj["args"] = PlanValues.SerializeArgs(Args);
        if (Generate is not null) obj["generate"] = Generate.ToJson();
        return obj;
    }
}

// ── Step ─────────────────────────────────────────────────

/// <summary>
/// A node in the plan DAG. Steps run sequentially by default;
/// <c>DependsOn</c> overrides to express cross-step concurrency.
/// <c>Parallel=true</c> runs the step's own <see cref="Op"/>s concurrently.
/// </summary>
public sealed class Step
{
    public string Id { get; }
    public List<Op> Operations { get; init; } = [];
    public List<string> DependsOn { get; init; } = [];
    public bool Parallel { get; init; }

    public Step(string id) { Id = id; }

    public JsonObject ToJson()
    {
        var obj = new JsonObject { ["id"] = Id };
        var ops = new JsonArray();
        foreach (var op in Operations) ops.Add(op.ToJson());
        obj["operations"] = ops;
        if (DependsOn.Count > 0)
        {
            var deps = new JsonArray();
            foreach (var d in DependsOn) deps.Add(d);
            obj["depends_on"] = deps;
        }
        if (Parallel) obj["parallel"] = true;
        return obj;
    }
}

// ── Validation ────────────────────────────────────────────

public sealed class Validation
{
    public string Tool { get; }
    public Dictionary<string, object?>? Args { get; init; }
    /// <summary>
    /// Optional JS expression evaluated against the tool's output
    /// (<c>$</c> is the parsed output map). Returns truthy on pass.
    /// </summary>
    public string? SuccessCondition { get; init; }

    public Validation(string tool) { Tool = tool; }

    public JsonObject ToJson()
    {
        var obj = new JsonObject { ["tool"] = Tool };
        if (Args is not null) obj["args"] = PlanValues.SerializeArgs(Args);
        if (SuccessCondition is not null) obj["success_condition"] = SuccessCondition;
        return obj;
    }
}

// ── Action (on_success / on_failure) ──────────────────────

public sealed class Action
{
    public string Tool { get; }
    public Dictionary<string, object?>? Args { get; init; }

    public Action(string tool) { Tool = tool; }

    public JsonObject ToJson()
    {
        var obj = new JsonObject { ["tool"] = Tool };
        if (Args is not null) obj["args"] = PlanValues.SerializeArgs(Args);
        return obj;
    }
}

// ── Plan ─────────────────────────────────────────────────

/// <summary>
/// A compiled plan ready for <c>Strategy.PlanExecute</c> execution.
/// Pass to <c>runtime.RunAsync(harness, prompt, plan: plan)</c> to skip
/// the planner LLM and run a fully deterministic pipeline.
/// </summary>
public sealed class Plan
{
    public List<Step> Steps { get; init; } = [];
    public List<Validation> Validation { get; init; } = [];
    public List<Action> OnSuccess { get; init; } = [];
    public List<Action> OnFailure { get; init; } = [];

    public JsonObject ToJson()
    {
        var obj = new JsonObject();
        var steps = new JsonArray();
        foreach (var s in Steps) steps.Add(s.ToJson());
        obj["steps"] = steps;
        if (Validation.Count > 0)
        {
            var arr = new JsonArray();
            foreach (var v in Validation) arr.Add(v.ToJson());
            obj["validation"] = arr;
        }
        if (OnSuccess.Count > 0)
        {
            var arr = new JsonArray();
            foreach (var a in OnSuccess) arr.Add(a.ToJson());
            obj["on_success"] = arr;
        }
        if (OnFailure.Count > 0)
        {
            var arr = new JsonArray();
            foreach (var a in OnFailure) arr.Add(a.ToJson());
            obj["on_failure"] = arr;
        }
        return obj;
    }
}
