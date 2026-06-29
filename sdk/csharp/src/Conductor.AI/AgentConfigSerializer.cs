// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Schema;

namespace Conductor.AI;

/// <summary>Serialize an Agent tree to the wire format the server expects.</summary>
internal static class AgentConfigSerializer
{
    public static JsonObject Serialize(Agent agent, string prompt, string sessionId = "",
        IEnumerable<string>? media = null)
    {
        var mediaArr = new JsonArray();
        if (media is not null)
            foreach (var url in media) mediaArr.Add(url);

        // Framework shape-adapter agents go through a different wire envelope:
        // {framework, rawConfig, prompt, sessionId}. The server routes these to
        // OpenAINormalizer / GoogleADKNormalizer based on `framework`. Mirrors
        // Java's HttpApi.startFrameworkAgent (POST /api/agent/start with framework).
        if (agent.Framework is "openai" or "google_adk" or "skill")
        {
            var env = new JsonObject
            {
                ["framework"] = agent.Framework,
                ["rawConfig"] = SerializeAgent(agent),
                ["prompt"]    = prompt,
            };
            if (!string.IsNullOrEmpty(sessionId)) env["sessionId"] = sessionId;
            return env;
        }

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
        // Framework shape-adapter path: server normalizers (OpenAINormalizer,
        // GoogleADKNormalizer) consume a different wire shape than the default.
        // Tools are emitted as {_worker_ref, description, parameters}; raw
        // framework config (handoffs, sub_agents, output_type) is folded in.
        if (agent.Framework == "skill")
        {
            var skill = new JsonObject
            {
                ["name"] = agent.Name,
                ["model"] = agent.Model,
                ["_framework"] = "skill",
            };
            if (agent.FrameworkConfig is not null)
            {
                foreach (var (k, v) in agent.FrameworkConfig)
                    skill[k] = JsonNode.Parse(JsonSerializer.Serialize(v, AgentspanJson.Options));
            }
            return skill;
        }

        if (agent.Framework is "openai" or "google_adk")
        {
            return SerializeFrameworkAgent(agent);
        }

        var cfg = new JsonObject { ["name"] = agent.Name };

        // Resolve dynamic instructions (InstructionsFn) at serialize time — matches Python/Java.
        var resolvedInstructions = agent.ResolveInstructions();

        if (agent.Model            is not null) cfg["model"]            = agent.Model;
        if (resolvedInstructions   is not null) cfg["instructions"]     = resolvedInstructions;
        if (agent.MaxTurns         .HasValue)   cfg["maxTurns"]         = agent.MaxTurns.Value;
        if (agent.MaxTokens        .HasValue)   cfg["maxTokens"]        = agent.MaxTokens.Value;
        if (agent.Temperature      .HasValue)   cfg["temperature"]      = agent.Temperature.Value;
        if (agent.TimeoutSeconds   .HasValue)   cfg["timeoutSeconds"]   = agent.TimeoutSeconds.Value;
        // Thinking budget nests under `thinkingConfig` — the server only reads
        // the nested {enabled, budgetTokens} object (AgentConfig#thinkingConfig).
        // Matches Python/Java/TS. The flat `thinkingBudgetTokens` key is dropped.
        if (agent.ThinkingBudgetTokens.HasValue)
            cfg["thinkingConfig"] = new JsonObject
            {
                ["enabled"]     = true,
                ["budgetTokens"] = agent.ThinkingBudgetTokens.Value,
            };
        if (agent.IncludeContents  is not null) cfg["includeContents"]  = agent.IncludeContents;
        if (agent.Introduction     is not null) cfg["introduction"]     = agent.Introduction;
        if (agent.External)                     cfg["external"]         = true;
        // Legacy "plan-first preamble" flag — server expects `enablePlanning`
        // (Boolean) since the `planner` JSON key was repurposed for the
        // PAC/PAE sub-agent slot below.
        if (agent.EnablePlanning)               cfg["enablePlanning"]   = true;

        // PLAN_EXECUTE named slots: planner (required when Strategy=PlanExecute)
        // + fallback (optional). Both serialize as nested AgentConfig objects.
        if (agent.Planner  is not null)         cfg["planner"]  = SerializeAgent(agent.Planner);
        if (agent.Fallback is not null)         cfg["fallback"] = SerializeAgent(agent.Fallback);
        if (agent.FallbackMaxTurns.HasValue)    cfg["fallbackMaxTurns"] = agent.FallbackMaxTurns.Value;

        // Planner context (PLAN_EXECUTE strategy) — text snippets + URLs
        // injected into the planner's prompt. Reject if set on a non-
        // PLAN_EXECUTE strategy to match the Python/TS/Java SDK guard
        // shape (caught at build time elsewhere; serialization is the
        // last line of defence).
        if (agent.PlannerContext is { Count: > 0 })
        {
            if (agent.Strategy != Strategy.PlanExecute)
            {
                throw new InvalidOperationException(
                    "PlannerContext is only valid with Strategy.PlanExecute. " +
                    $"Got Strategy={agent.Strategy}. The context block is appended " +
                    "to the planner's user prompt at runtime, which only exists in PLAN_EXECUTE.");
            }
            var arr = new JsonArray();
            foreach (var entry in agent.PlannerContext) arr.Add(entry.ToJson());
            cfg["plannerContext"] = arr;
        }

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

        // Prompt template nests under `instructions` as a typed object — the
        // server reads prompt templates only from `instructions`
        // ({type: prompt_template, name, variables?, version?}). Matches
        // Python/Java/TS; the top-level `promptTemplate` key is dropped. This
        // overwrites any string `instructions` set above.
        if (agent.PromptTemplateInstructions is not null)
        {
            var pt = new JsonObject
            {
                ["type"] = "prompt_template",
                ["name"] = agent.PromptTemplateInstructions.Name,
            };
            if (agent.PromptTemplateInstructions.Variables is { Count: > 0 })
            {
                var vars = new JsonObject();
                foreach (var (k, v) in agent.PromptTemplateInstructions.Variables)
                    vars[k] = v;
                pt["variables"] = vars;
            }
            if (agent.PromptTemplateInstructions.Version.HasValue)
                pt["version"] = agent.PromptTemplateInstructions.Version.Value;
            cfg["instructions"] = pt;
        }

        // Inject execute_code worker tool when local code execution is on, so
        // the LLM sees it as a callable function. Mirrors Python's
        // Agent._attach_code_execution_tool and Java's serializer block.
        // The tool name is {agent_name}_execute_code to avoid multi-agent
        // collisions and to match what AgentRuntime.RegisterLocalCodeExecutionWorker
        // registers locally.
        var injectedTools = new JsonArray();
        if (agent.Tools.Count > 0)
        {
            foreach (var t in agent.Tools) injectedTools.Add(SerializeTool(t, agent.Stateful));
        }
        if (agent.LocalCodeExecution || agent.CodeExecution is not null)
        {
            var langs = agent.CodeExecution?.AllowedLanguages ?? agent.AllowedLanguages
                        ?? new List<string> { "python" };
            if (langs.Count == 0) langs = ["python"];
            var langArr = new JsonArray();
            foreach (var l in langs) langArr.Add(l);

            var langDesc = string.Join(", ", langs);
            var properties = new JsonObject
            {
                ["language"] = new JsonObject
                {
                    ["type"]        = "string",
                    ["description"] = "The programming language to use. One of: " + langDesc,
                    ["enum"]        = new JsonArray(langs.Select(l => (JsonNode?)l).ToArray()),
                },
                ["code"] = new JsonObject
                {
                    ["type"]        = "string",
                    ["description"] = "The code to execute.",
                },
            };

            var execTool = new JsonObject
            {
                ["name"] = $"{agent.Name}_execute_code",
                ["description"] =
                    "Execute code in the specified language. Supported languages: " + langDesc +
                    ". Each execution runs in an isolated environment — no state, variables, " +
                    "or imports persist between calls.",
                ["inputSchema"] = new JsonObject
                {
                    ["type"]       = "object",
                    ["properties"] = properties,
                    ["required"]   = new JsonArray { "language", "code" },
                },
                ["outputSchema"] = new JsonObject
                {
                    ["type"] = "object",
                    ["additionalProperties"] = new JsonObject(),
                },
                ["toolType"] = "worker",
            };
            injectedTools.Add(execTool);
        }
        if (injectedTools.Count > 0)
        {
            cfg["tools"] = injectedTools;
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

        // Condition-based handoffs (SWARM triggers)
        if (agent.Handoffs.Count > 0)
        {
            var handoffs = new JsonArray();
            foreach (var h in agent.Handoffs) handoffs.Add(SerializeHandoff(h, agent.Name));
            cfg["handoffs"] = handoffs;
        }

        // Gate — stop a sequential pipeline when output contains the sentinel text
        if (agent.Gate is not null)
        {
            cfg["gate"] = new JsonObject
            {
                ["type"]          = "text_contains",
                ["text"]          = agent.Gate.Text,
                ["caseSensitive"] = agent.Gate.CaseSensitive,
            };
        }

        // Lifecycle callbacks — emit one {position, taskName} entry per active position.
        // Sources: the function-typed callbacks AND the CallbackHandler list (a handler
        // contributes a position only if it overrides that hook). Positions are emitted
        // at most once, in server order.
        var callbackArr = new JsonArray();
        var seenPositions = new HashSet<string>(StringComparer.Ordinal);

        void AddCallback(string position)
        {
            if (seenPositions.Add(position))
                callbackArr.Add(new JsonObject
                {
                    ["position"] = position,
                    ["taskName"] = $"{agent.Name}_{position}",
                });
        }

        if (agent.BeforeAgentCallback is not null) AddCallback("before_agent");
        if (agent.AfterAgentCallback  is not null) AddCallback("after_agent");
        if (agent.BeforeModelCallback is not null) AddCallback("before_model");
        if (agent.AfterModelCallback  is not null) AddCallback("after_model");
        if (agent.BeforeToolCallback  is not null) AddCallback("before_tool");
        if (agent.AfterToolCallback   is not null) AddCallback("after_tool");

        foreach (var (position, method) in CallbackHandler.Positions)
            if (agent.Callbacks.Any(h => h.Overrides(method)))
                AddCallback(position);

        if (callbackArr.Count > 0)
            cfg["callbacks"] = callbackArr;

        // ── Cross-SDK parity fields (match Python/Java wire keys & shapes) ──

        // reasoningEffort (string) — OpenAI reasoning models
        if (!string.IsNullOrEmpty(agent.ReasoningEffort))
            cfg["reasoningEffort"] = agent.ReasoningEffort;

        // contextWindowBudget (int) — proactive context condensation
        if (agent.ContextWindowBudget.HasValue)
            cfg["contextWindowBudget"] = agent.ContextWindowBudget.Value;

        // maskedFields (list of strings) — redacted in history/UI. NOTE: the
        // server does not currently apply this (known no-op); emitted anyway for
        // wire parity with Python/Java.
        if (agent.MaskedFields is { Count: > 0 })
        {
            var arr = new JsonArray();
            foreach (var f in agent.MaskedFields) arr.Add(f);
            cfg["maskedFields"] = arr;
        }

        // synthesize (bool) — only emit when explicitly disabled (true = server default)
        if (!agent.Synthesize)
            cfg["synthesize"] = false;

        // prefillTools — [{toolName, arguments}] executed before the first LLM turn
        if (agent.PrefillTools is { Count: > 0 })
        {
            var arr = new JsonArray();
            foreach (var pt in agent.PrefillTools)
            {
                arr.Add(new JsonObject
                {
                    ["toolName"]  = pt.ToolName,
                    ["arguments"] = JsonNode.Parse(
                        JsonSerializer.Serialize(pt.Arguments, AgentspanJson.Options))!,
                });
            }
            cfg["prefillTools"] = arr;
        }

        // cliConfig — {enabled, allowedCommands, timeout, allowShell, workingDir?}
        if (agent.CliConfig is not null)
        {
            var c = agent.CliConfig;
            var cmds = new JsonArray();
            if (c.AllowedCommands is not null)
                foreach (var cmd in c.AllowedCommands) cmds.Add(cmd);
            var cli = new JsonObject
            {
                ["enabled"]         = c.Enabled,
                ["allowedCommands"] = cmds,
                ["timeout"]         = c.Timeout,
                ["allowShell"]      = c.AllowShell,
            };
            if (c.WorkingDir is not null) cli["workingDir"] = c.WorkingDir;
            cfg["cliConfig"] = cli;
        }

        return cfg;
    }

    private static JsonObject SerializeFrameworkAgent(Agent agent)
    {
        var fw = agent.Framework!;
        var map = new JsonObject { ["name"] = agent.Name };

        if (!string.IsNullOrEmpty(agent.Model)) map["model"] = agent.Model;

        // OpenAI uses `instructions`; ADK uses `instruction` (singular).
        var fwInstructions = agent.ResolveInstructions();
        if (!string.IsNullOrEmpty(fwInstructions))
        {
            map[fw == "google_adk" ? "instruction" : "instructions"] = fwInstructions;
        }

        // Framework normalizers expect the `_worker_ref` shape:
        //   { _worker_ref, description, parameters }
        // The default tool shape (name + inputSchema + toolType) is silently
        // dropped by these normalizers, so the LLM would see a paramless tool.
        if (agent.Tools.Count > 0)
        {
            var tools = new JsonArray();
            foreach (var t in agent.Tools)
            {
                // Agent-as-tool: emit `{_type: "AgentTool", name, description, agent}`
                // so the framework normalizer compiles this as a SUB_WORKFLOW task.
                if (t.ToolType == "agent_tool" && t.WrappedAgent is not null)
                {
                    tools.Add(new JsonObject
                    {
                        ["_type"]       = "AgentTool",
                        ["name"]        = t.Name,
                        ["description"] = t.Description ?? "",
                        ["agent"]       = SerializeAgent(t.WrappedAgent),
                    });
                    continue;
                }
                var entry = new JsonObject
                {
                    ["_worker_ref"] = t.Name,
                    ["description"] = t.Description ?? "",
                };
                // InputSchema is itself a JsonObject — clone via DeepClone to avoid
                // re-parenting the same node (a JsonNode can only have one parent).
                entry["parameters"] = t.InputSchema.DeepClone();
                tools.Add(entry);
            }
            map["tools"] = tools;
        }

        if (agent.FrameworkConfig is not null)
        {
            foreach (var (k, v) in agent.FrameworkConfig)
            {
                map[k] = JsonNode.Parse(JsonSerializer.Serialize(v, AgentspanJson.Options));
            }
        }

        return map;
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
        Strategy.PlanExecute => "plan_execute",
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

        // Stateful routing: emit stateful=true if the agent is stateful OR the
        // tool itself is marked stateful (mirrors Python @tool(stateful=True)).
        if ((agentStateful || tool.Stateful) && toolType is "worker" or "external")
            t["stateful"] = true;

        if (tool.ApprovalRequired)        t["approvalRequired"] = true;
        if (tool.TimeoutSeconds.HasValue)  t["timeoutSeconds"]   = tool.TimeoutSeconds.Value;
        if (tool.RetryCount.HasValue && tool.RetryCount.Value != 2)
            t["retryCount"] = tool.RetryCount.Value;
        if (tool.RetryDelaySeconds.HasValue && tool.RetryDelaySeconds.Value != 2)
            t["retryDelaySeconds"] = tool.RetryDelaySeconds.Value;
        if (!string.IsNullOrEmpty(tool.RetryPolicy) && tool.RetryPolicy != "linear_backoff")
            t["retryPolicy"] = tool.RetryPolicy;

        // Credentials must land inside config.credentials for all tool types.
        // The server's AgentService.extractDeclaredCredentials reads
        // tool.getConfig().get("credentials") — top-level t["credentials"]
        // is not consulted.  Worker / external tools previously put them at
        // top level only, which meant declared_names was always empty and
        // Bug #4's empty-declared block-all path fired on every resolve call.
        bool isWorkerTool = toolType is "worker" or "external";

        // Tool-level guardrails (mirror Python's @tool(guardrails=[...]))
        if (tool.Guardrails.Count > 0)
        {
            var gArr = new JsonArray();
            foreach (var g in tool.Guardrails) gArr.Add(SerializeGuardrail(g));
            t["guardrails"] = gArr;
        }

        // For agent_tool, embed the child agent config
        if (toolType == "agent_tool" && tool.WrappedAgent is not null)
        {
            var config = new JsonObject
            {
                ["agentConfig"] = SerializeAgent(tool.WrappedAgent),
            };
            if (tool.WrappedAgent.Framework == "skill")
            {
                config["workerNames"] = new JsonArray(
                    Skill.CreateSkillWorkers(tool.WrappedAgent)
                        .Select(w => (JsonNode?)w.Name)
                        .ToArray());
            }
            if (tool.AgentToolRetryCount.HasValue)
                config["retryCount"] = tool.AgentToolRetryCount.Value;
            if (tool.AgentToolRetryDelaySeconds.HasValue)
                config["retryDelaySeconds"] = tool.AgentToolRetryDelaySeconds.Value;
            if (tool.AgentToolOptional.HasValue)
                config["optional"] = tool.AgentToolOptional.Value;
            t["config"] = config;
        }

        // Emit config object, always merging credentials inside it (all tool types).
        if (tool.Config is not null && toolType != "agent_tool")
        {
            var configCopy = new Dictionary<string, object>(tool.Config);
            if (tool.Credentials.Length > 0)
                configCopy["credentials"] = tool.Credentials.ToList();
            t["config"] = JsonNode.Parse(JsonSerializer.Serialize(configCopy, AgentspanJson.Options))!;
        }
        else if (tool.Credentials.Length > 0)
        {
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

    private static JsonObject SerializeHandoff(Handoff h, string agentName)
    {
        var hMap = new JsonObject { ["target"] = h.Target };
        switch (h)
        {
            case OnTextMention otm:
                hMap["type"] = "on_text_mention";
                hMap["text"] = otm.Text;
                break;
            case OnToolResult otr:
                hMap["type"]     = "on_tool_result";
                hMap["toolName"] = otr.ToolName;
                if (otr.ResultContains is not null) hMap["resultContains"] = otr.ResultContains;
                break;
            case OnCondition:
                hMap["type"]     = "on_condition";
                hMap["taskName"] = $"{agentName}_handoff_{h.Target}";
                break;
            default:
                hMap["type"] = "unknown";
                break;
        }
        return hMap;
    }

    internal static JsonObject SerializeGuardrail(GuardrailDef g) => new()
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
        // External guardrails reference a remote worker by name. Regex/LLM/custom
        // guardrails run as locally-registered worker tasks, so they serialize as
        // "custom" (the server treats them identically — a named task).
        ["guardrailType"] = g.External ? "external" : "custom",
        ["taskName"]      = g.Name,  // Conductor task name = guardrail name
    };
}
