// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Schema;

namespace Agentspan;

/// <summary>Serialize an Agent tree to the wire format the server expects.</summary>
internal static class AgentConfigSerializer
{
    public static JsonObject Serialize(Agent agent, string prompt, string sessionId = "",
        IEnumerable<string>? media = null)
    {
        var mediaArr = new JsonArray();
        if (media is not null)
            foreach (var url in media) mediaArr.Add(url);

        return new JsonObject
        {
            ["agentConfig"] = SerializeAgent(agent),
            ["prompt"]      = prompt,
            ["sessionId"]   = sessionId,
            ["media"]       = mediaArr,
        };
    }

    internal static JsonObject SerializeAgent(Agent agent)
    {
        var cfg = new JsonObject { ["name"] = agent.Name };

        if (agent.Model            is not null) cfg["model"]            = agent.Model;
        if (agent.Instructions     is not null) cfg["instructions"]     = agent.Instructions;
        if (agent.MaxTurns         .HasValue)   cfg["maxTurns"]         = agent.MaxTurns.Value;
        if (agent.MaxTokens        .HasValue)   cfg["maxTokens"]        = agent.MaxTokens.Value;
        if (agent.Temperature      .HasValue)   cfg["temperature"]      = agent.Temperature.Value;
        if (agent.TimeoutSeconds   .HasValue)   cfg["timeoutSeconds"]   = agent.TimeoutSeconds.Value;
        if (agent.ThinkingBudgetTokens.HasValue)cfg["thinkingBudgetTokens"] = agent.ThinkingBudgetTokens.Value;
        if (agent.IncludeContents  is not null) cfg["includeContents"]  = agent.IncludeContents;
        if (agent.Introduction     is not null) cfg["introduction"]     = agent.Introduction;
        if (agent.External)                     cfg["external"]         = true;
        if (agent.Planner)                      cfg["planner"]          = true;

        if (agent.LocalCodeExecution || agent.CodeExecution is not null
            || agent.AllowedLanguages is not null || agent.AllowedCommands is not null)
        {
            var ce = new JsonObject { ["enabled"] = true };
            var langs = agent.CodeExecution?.AllowedLanguages ?? agent.AllowedLanguages;
            var cmds  = agent.CodeExecution?.AllowedCommands  ?? agent.AllowedCommands;
            var timeout = agent.CodeExecution?.Timeout;
            if (langs is not null && langs.Count > 0)
            {
                var arr = new JsonArray();
                foreach (var l in langs) arr.Add(l);
                ce["allowedLanguages"] = arr;
            }
            if (cmds is not null && cmds.Count > 0)
            {
                var arr = new JsonArray();
                foreach (var c in cmds) arr.Add(c);
                ce["allowedCommands"] = arr;
            }
            if (timeout.HasValue) ce["timeout"] = timeout.Value;
            cfg["codeExecution"] = ce;
        }

        if (agent.OutputType is not null)
        {
            cfg["outputType"] = new JsonObject
            {
                ["schema"]    = GenerateSchema(agent.OutputType),
                ["className"] = agent.OutputType.Name,
            };
        }

        if (agent.RequiredTools?.Count > 0)
        {
            var arr = new JsonArray();
            foreach (var t in agent.RequiredTools) arr.Add(t);
            cfg["requiredTools"] = arr;
        }

        if (agent.PromptTemplateInstructions is not null)
        {
            var pt = new JsonObject { ["name"] = agent.PromptTemplateInstructions.Name };
            if (agent.PromptTemplateInstructions.Version.HasValue)
                pt["version"] = agent.PromptTemplateInstructions.Version.Value;
            if (agent.PromptTemplateInstructions.Variables is not null)
            {
                var vars = new JsonObject();
                foreach (var (k, v) in agent.PromptTemplateInstructions.Variables)
                    vars[k] = v;
                pt["variables"] = vars;
            }
            cfg["promptTemplate"] = pt;
        }

        if (agent.Tools.Count > 0)
        {
            var tools = new JsonArray();
            foreach (var t in agent.Tools) tools.Add(SerializeTool(t, agent.Stateful));
            cfg["tools"] = tools;
        }

        if (agent.Guardrails.Count > 0)
        {
            var guardrails = new JsonArray();
            foreach (var g in agent.Guardrails) guardrails.Add(SerializeGuardrail(g));
            cfg["guardrails"] = guardrails;
        }

        if (agent.Agents.Count > 0)
        {
            var agents = new JsonArray();
            foreach (var a in agent.Agents) agents.Add(SerializeAgent(a));
            cfg["agents"] = agents;
        }

        if (agent.Strategy.HasValue)
            cfg["strategy"] = StrategyToWire(agent.Strategy.Value);

        if (agent.Router is not null)
            cfg["router"] = SerializeAgent(agent.Router);

        if (agent.Termination is not null)
            cfg["termination"] = SerializeTermination(agent.Termination);

        if (agent.AllowedTransitions is not null)
        {
            var at = new JsonObject();
            foreach (var (key, targets) in agent.AllowedTransitions)
            {
                var arr = new JsonArray();
                foreach (var t in targets) arr.Add(t);
                at[key] = arr;
            }
            cfg["allowedTransitions"] = at;
        }

        if (agent.Metadata is not null)
            cfg["metadata"] = JsonNode.Parse(JsonSerializer.Serialize(agent.Metadata, AgentspanJson.Options))!;

        // Lifecycle callbacks — emit position + taskName pairs
        var callbackArr = new JsonArray();
        if (agent.BeforeModelCallback is not null)
            callbackArr.Add(new JsonObject { ["position"] = "before_model", ["taskName"] = $"{agent.Name}_before_model" });
        if (agent.AfterModelCallback is not null)
            callbackArr.Add(new JsonObject { ["position"] = "after_model",  ["taskName"] = $"{agent.Name}_after_model" });
        if (callbackArr.Count > 0)
            cfg["callbacks"] = callbackArr;

        return cfg;
    }

    private static JsonNode GenerateSchema(Type type)
    {
        var opts = new JsonSerializerOptions(AgentspanJson.Options);
        opts.MakeReadOnly(populateMissingResolver: true);
        return JsonSchemaExporter.GetJsonSchemaAsNode(opts, type);
    }

    private static string StrategyToWire(Strategy strategy) => strategy switch
    {
        Strategy.RoundRobin => "round_robin",
        _ => strategy.ToString().ToLowerInvariant(),
    };

    private static JsonObject SerializeTool(ToolDef tool, bool agentStateful = false)
    {
        var toolType = tool.ToolType
            ?? (tool.External ? "external" : "worker");

        var t = new JsonObject
        {
            ["name"]        = tool.Name,
            ["description"] = tool.Description,
            ["inputSchema"] = JsonNode.Parse(tool.InputSchema.ToJsonString())!,
            ["toolType"]    = toolType,
        };

        // Stateful routing: propagate agent.Stateful to worker tools
        if (agentStateful && toolType is "worker" or "external")
            t["stateful"] = true;

        if (tool.ApprovalRequired)        t["approvalRequired"] = true;
        if (tool.TimeoutSeconds.HasValue)  t["timeoutSeconds"]   = tool.TimeoutSeconds.Value;

        // For worker/external tools, credentials go at top level.
        // For all other tool types (http, mcp, media, rag), they go inside config.
        bool isWorkerTool = toolType is "worker" or "external";
        if (tool.Credentials.Length > 0 && isWorkerTool)
        {
            var creds = new JsonArray();
            foreach (var c in tool.Credentials) creds.Add(c);
            t["credentials"] = creds;
        }

        // For agent_tool, embed the child agent config
        if (toolType == "agent_tool" && tool.WrappedAgent is not null)
        {
            var config = new JsonObject
            {
                ["agentConfig"] = SerializeAgent(tool.WrappedAgent),
            };
            if (tool.AgentToolRetryCount.HasValue)
                config["retryCount"] = tool.AgentToolRetryCount.Value;
            if (tool.AgentToolRetryDelaySeconds.HasValue)
                config["retryDelaySeconds"] = tool.AgentToolRetryDelaySeconds.Value;
            if (tool.AgentToolOptional.HasValue)
                config["optional"] = tool.AgentToolOptional.Value;
            t["config"] = config;
        }

        // For server-side tools (http, mcp, media, pdf, rag), emit the static config object.
        // Also embed credentials inside config (server requirement for non-worker tools).
        if (tool.Config is not null && toolType != "agent_tool")
        {
            // Merge credentials into config if present
            var configCopy = new Dictionary<string, object>(tool.Config);
            if (!isWorkerTool && tool.Credentials.Length > 0)
                configCopy["credentials"] = tool.Credentials.ToList();
            t["config"] = JsonNode.Parse(JsonSerializer.Serialize(configCopy, AgentspanJson.Options))!;
        }
        else if (!isWorkerTool && tool.Credentials.Length > 0)
        {
            // No config dict yet — create one just for credentials
            t["config"] = JsonNode.Parse(JsonSerializer.Serialize(
                new Dictionary<string, object> { ["credentials"] = tool.Credentials.ToList() },
                AgentspanJson.Options))!;
        }

        return t;
    }

    private static JsonNode SerializeTermination(TerminationCondition condition) => condition switch
    {
        TextMentionTermination t => new JsonObject
        {
            ["type"]          = "text_mention",
            ["text"]          = t.Text,
            ["caseSensitive"] = t.CaseSensitive,
        },
        StopMessageTermination s => new JsonObject
        {
            ["type"]        = "stop_message",
            ["stopMessage"] = s.StopMessage,
        },
        MaxMessageTermination m => new JsonObject
        {
            ["type"]        = "max_message",
            ["maxMessages"] = m.MaxMessages,
        },
        TokenUsageTermination tok => SerializeTokenUsageTermination(tok),
        AndTermination and => new JsonObject
        {
            ["type"]       = "and",
            ["conditions"] = SerializeTerminationList(and.Conditions),
        },
        OrTermination or => new JsonObject
        {
            ["type"]       = "or",
            ["conditions"] = SerializeTerminationList(or.Conditions),
        },
        _ => new JsonObject { ["type"] = "unknown" },
    };

    private static JsonObject SerializeTokenUsageTermination(TokenUsageTermination tok)
    {
        var obj = new JsonObject { ["type"] = "token_usage" };
        if (tok.MaxTotalTokens      is not null) obj["maxTotalTokens"]      = tok.MaxTotalTokens.Value;
        if (tok.MaxPromptTokens     is not null) obj["maxPromptTokens"]     = tok.MaxPromptTokens.Value;
        if (tok.MaxCompletionTokens is not null) obj["maxCompletionTokens"] = tok.MaxCompletionTokens.Value;
        return obj;
    }

    private static JsonArray SerializeTerminationList(IReadOnlyList<TerminationCondition> conditions)
    {
        var arr = new JsonArray();
        foreach (var c in conditions) arr.Add(SerializeTermination(c));
        return arr;
    }

    private static JsonObject SerializeGuardrail(GuardrailDef g) => new()
    {
        ["name"]          = g.Name,
        ["position"]      = g.Position == Position.Input ? "input" : "output",
        ["onFail"]        = g.OnFail switch
        {
            OnFail.Retry => "retry",
            OnFail.Fix   => "fix",
            OnFail.Human => "human",
            _            => "raise",
        },
        ["maxRetries"]    = g.MaxRetries,
        ["guardrailType"] = "custom",
        ["taskName"]      = g.Name,  // Conductor task name = guardrail name
    };
}
