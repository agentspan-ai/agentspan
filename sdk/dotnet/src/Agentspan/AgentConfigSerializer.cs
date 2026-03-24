using System.Reflection;

namespace Agentspan;

public sealed class AgentConfigSerializer
{
    public Dictionary<string, object?> Serialize(Agent agent) => SerializeAgent(agent);

    private Dictionary<string, object?> SerializeAgent(Agent agent)
    {
        var config = new Dictionary<string, object?>
        {
            ["name"] = agent.Name,
            ["model"] = agent.Model.Length > 0 ? agent.Model : null,
            ["strategy"] = agent.SubAgents.Count > 0 ? StrategyToString(agent.Strategy) : null,
            ["maxTurns"] = agent.MaxTurns,
            ["timeoutSeconds"] = agent.TimeoutSeconds,
            ["external"] = agent.External,
            ["instructions"] = agent.Instructions.Length > 0 ? agent.Instructions : null,
        };

        if (agent.Tools.Count > 0)
            config["tools"] = agent.Tools.Select(SerializeTool).ToList();

        if (agent.SubAgents.Count > 0)
            config["agents"] = agent.SubAgents.Select(SerializeAgent).ToList();

        if (agent.Router != null)
            config["router"] = SerializeAgent(agent.Router);

        if (agent.OutputType != null)
            config["outputType"] = SerializeOutputType(agent.OutputType);

        if (agent.Guardrails.Count > 0)
            config["guardrails"] = agent.Guardrails.Select(SerializeGuardrail).ToList();

        if (agent.MaxTokens.HasValue)
            config["maxTokens"] = agent.MaxTokens.Value;

        if (agent.Temperature.HasValue)
            config["temperature"] = agent.Temperature.Value;

        // Remove nulls
        return config.Where(kv => kv.Value != null).ToDictionary(kv => kv.Key, kv => kv.Value);
    }

    private static Dictionary<string, object?> SerializeTool(ToolDef tool)
    {
        var result = new Dictionary<string, object?>
        {
            ["name"] = tool.Name,
            ["description"] = tool.Description,
            ["inputSchema"] = tool.InputSchema,
            ["toolType"] = tool.ToolType,
        };
        if (tool.ApprovalRequired) result["approvalRequired"] = true;
        if (tool.TimeoutSeconds.HasValue) result["timeoutSeconds"] = tool.TimeoutSeconds.Value;
        if (tool.Config?.Count > 0) result["config"] = tool.Config;
        return result;
    }

    private static Dictionary<string, object?> SerializeGuardrail(Guardrail g) => new()
    {
        ["name"] = g.Name,
        ["position"] = g.Position == GuardrailPosition.Input ? "input" : "output",
        ["onFail"] = g.OnFail switch
        {
            GuardrailOnFail.Retry => "retry",
            GuardrailOnFail.Raise => "raise",
            GuardrailOnFail.Fix => "fix",
            GuardrailOnFail.Human => "human",
            _ => "retry"
        },
        ["maxRetries"] = g.MaxRetries,
        ["guardrailType"] = "custom",
        ["taskName"] = g.Name,
    };

    private static Dictionary<string, object?> SerializeOutputType(Type t) => new()
    {
        ["schema"] = GenerateSchema(t),
        ["className"] = t.Name,
    };

    private static Dictionary<string, object?> GenerateSchema(Type t)
    {
        var props = t.GetProperties(BindingFlags.Public | BindingFlags.Instance);
        var properties = new Dictionary<string, object?>();
        foreach (var prop in props)
        {
            properties[ToCamelCase(prop.Name)] = new Dictionary<string, object?> { ["type"] = JsonTypeFor(prop.PropertyType) };
        }
        return new Dictionary<string, object?> { ["type"] = "object", ["properties"] = properties };
    }

    private static string JsonTypeFor(Type t)
    {
        // Unwrap nullable
        var underlying = Nullable.GetUnderlyingType(t);
        if (underlying != null) return JsonTypeFor(underlying);

        if (t == typeof(string)) return "string";
        if (t == typeof(bool)) return "boolean";
        if (t == typeof(int) || t == typeof(long) || t == typeof(short) || t == typeof(byte)) return "integer";
        if (t == typeof(double) || t == typeof(float) || t == typeof(decimal)) return "number";
        if (t.IsArray || (t.IsGenericType && t.GetGenericTypeDefinition() == typeof(List<>))) return "array";
        return "object";
    }

    private static string ToCamelCase(string s) =>
        s.Length == 0 ? s : char.ToLowerInvariant(s[0]) + s[1..];

    private static string StrategyToString(Strategy s) => s switch
    {
        Strategy.Handoff => "handoff",
        Strategy.Sequential => "sequential",
        Strategy.Parallel => "parallel",
        Strategy.Router => "router",
        Strategy.RoundRobin => "round_robin",
        Strategy.Random => "random",
        Strategy.Swarm => "swarm",
        Strategy.Manual => "manual",
        _ => "handoff"
    };
}
