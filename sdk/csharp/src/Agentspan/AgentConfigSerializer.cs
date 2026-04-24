// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;

namespace Agentspan;

/// <summary>Serialize an Agent tree to the wire format the server expects.</summary>
internal static class AgentConfigSerializer
{
    public static JsonObject Serialize(Agent agent, string prompt, string sessionId = "")
    {
        return new JsonObject
        {
            ["agentConfig"] = SerializeAgent(agent),
            ["prompt"]      = prompt,
            ["sessionId"]   = sessionId,
            ["media"]       = new JsonArray(),
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
            foreach (var t in agent.Tools) tools.Add(SerializeTool(t));
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

        if (agent.Metadata is not null)
            cfg["metadata"] = JsonNode.Parse(JsonSerializer.Serialize(agent.Metadata, AgentspanJson.Options))!;

        return cfg;
    }

    private static string StrategyToWire(Strategy strategy) => strategy switch
    {
        Strategy.RoundRobin => "round_robin",
        _ => strategy.ToString().ToLowerInvariant(),
    };

    private static JsonObject SerializeTool(ToolDef tool)
    {
        var t = new JsonObject
        {
            ["name"]        = tool.Name,
            ["description"] = tool.Description,
            ["inputSchema"] = JsonNode.Parse(tool.InputSchema.ToJsonString())!,
            ["toolType"]    = tool.External ? "external" : "worker",
        };
        if (tool.ApprovalRequired)      t["approvalRequired"] = true;
        if (tool.TimeoutSeconds.HasValue) t["timeoutSeconds"]  = tool.TimeoutSeconds.Value;
        if (tool.Credentials.Length > 0)
        {
            var creds = new JsonArray();
            foreach (var c in tool.Credentials) creds.Add(c);
            t["credentials"] = creds;
        }
        return t;
    }

    private static JsonObject SerializeGuardrail(GuardrailDef g) => new()
    {
        ["name"]       = g.Name,
        ["position"]   = g.Position == Position.Input ? "input" : "output",
        ["onFail"]     = g.OnFail switch
        {
            OnFail.Retry => "retry",
            OnFail.Fix   => "fix",
            OnFail.Human => "human",
            _            => "raise",
        },
        ["maxRetries"] = g.MaxRetries,
        ["workerName"] = g.Name,  // Conductor task name = guardrail name
    };
}
