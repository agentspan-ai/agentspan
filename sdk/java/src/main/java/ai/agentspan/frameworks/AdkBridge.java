// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.frameworks;

import ai.agentspan.Agent;
import ai.agentspan.CallbackHandler;
import ai.agentspan.model.ToolDef;

import com.google.adk.agents.BaseAgent;
import com.google.adk.agents.Callbacks;
import com.google.adk.agents.Instruction;
import com.google.adk.agents.LlmAgent;
import com.google.adk.agents.LoopAgent;
import com.google.adk.models.LlmRequest;
import com.google.adk.models.LlmResponse;
import com.google.adk.tools.AgentTool;
import com.google.adk.tools.Annotations;
import com.google.adk.tools.BaseTool;
import com.google.adk.tools.BaseToolset;
import com.google.adk.tools.BuiltInCodeExecutionTool;
import com.google.adk.tools.FunctionTool;
import com.google.adk.tools.GoogleSearchTool;
import com.google.genai.types.Content;
import com.google.genai.types.FunctionDeclaration;
import com.google.genai.types.GenerateContentConfig;
import com.google.genai.types.Part;
import com.google.genai.types.Schema;
import com.google.genai.types.ThinkingConfig;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Adapter that takes a native Google ADK {@link BaseAgent} and produces an
 * Agentspan {@link Agent} configured so the durable Agentspan runtime can
 * execute the agent server-side.
 *
 * <p>This bridge extracts every field the server's
 * {@code GoogleADKNormalizer} consumes:
 * <ul>
 *   <li>Identity: {@code name}, {@code description}, {@code model}</li>
 *   <li>Prompts: {@code instruction} (Static + Provider), {@code globalInstruction}</li>
 *   <li>Tools: {@code FunctionTool}, {@code AgentTool}; preserves
 *       {@code @Schema(name=...)} param naming</li>
 *   <li>Sub-agents: recursive — sub-agent tools, callbacks, and nested
 *       sub-agents all round-trip</li>
 *   <li>Composite-agent types: {@code SequentialAgent}, {@code ParallelAgent},
 *       {@code LoopAgent} (with {@code max_iterations}) — emitted via
 *       {@code _type} so the server picks the right strategy</li>
 *   <li>Generation config: {@code temperature}, {@code maxOutputTokens},
 *       {@code thinkingConfig}</li>
 *   <li>Output: {@code outputSchema}, {@code outputKey}</li>
 *   <li>Control: {@code planning}, {@code includeContents},
 *       {@code disallowTransferToParent}, {@code disallowTransferToPeers}</li>
 *   <li>Callbacks: all six positions (before/after × agent/model/tool) —
 *       emitted as {@code _worker_ref} placeholders so the server compiles
 *       hook tasks; runtime invocation is best-effort (ADK contexts are
 *       not reconstructable server-side)</li>
 * </ul>
 *
 * <p>Symmetry with the Python {@code google.adk} serializer in
 * {@code sdk/python/src/agentspan/agents/frameworks/serializer.py} — both walk
 * the native agent tree and emit the same wire shape consumed by the server's
 * {@code GoogleADKNormalizer}.
 */
public final class AdkBridge {

    private static final Logger log = LoggerFactory.getLogger(AdkBridge.class);

    /** Map from ADK callback wire-field name to LlmAgent getter method. */
    private static final String[][] CALLBACK_FIELDS = {
            {"before_agent_callback", "beforeAgentCallback"},
            {"after_agent_callback",  "afterAgentCallback"},
            {"before_model_callback", "beforeModelCallback"},
            {"after_model_callback",  "afterModelCallback"},
            {"before_tool_callback",  "beforeToolCallback"},
            {"after_tool_callback",   "afterToolCallback"},
    };

    private AdkBridge() {}

    // ── Public entry ─────────────────────────────────────────────────────────

    /**
     * Convert any native ADK {@link BaseAgent} ({@code LlmAgent},
     * {@code SequentialAgent}, {@code ParallelAgent}, {@code LoopAgent}, …)
     * into an Agentspan {@link Agent} ready for {@code Agentspan.run(...)}.
     */
    public static Agent toAgentspan(BaseAgent adk) {
        return agentBuilder(adk).build();
    }

    /**
     * Same as {@link #toAgentspan} but returns the populated
     * {@link Agent.Builder} so callers can attach Agentspan-only features
     * (guardrails, gate, termination conditions, callbacks, …) on top of a
     * native ADK agent before building.
     *
     * <pre>{@code
     * Agent decorated = AdkBridge.agentBuilder(llmAgent)
     *     .guardrails(piiGuard)
     *     .build();
     * Agentspan.run(decorated, "...");
     * }</pre>
     */
    public static Agent.Builder agentBuilder(BaseAgent adk) {
        if (adk == null) {
            throw new IllegalArgumentException("AdkBridge.agentBuilder: agent is null");
        }
        return agentBuilder(adk, new java.util.IdentityHashMap<>());
    }

    private static Agent toAgentspan(BaseAgent adk, java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        return agentBuilder(adk, visited).build();
    }

    private static Agent.Builder agentBuilder(BaseAgent adk, java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        if (visited.putIfAbsent(adk, Boolean.TRUE) != null) {
            throw new IllegalArgumentException(
                    "AdkBridge: cycle detected in subAgents/AgentTool graph at agent '"
                    + adk.name() + "'");
        }

        Agent.Builder b = Agent.builder()
                .name(adk.name())
                .framework("google_adk");

        // Model + instruction live at the Agentspan top level so the
        // worker poller / debug tools see them directly. Everything else
        // goes into frameworkConfig (flattened by AgentConfigSerializer into
        // the rawConfig the server consumes).
        if (adk instanceof LlmAgent llm) {
            llm.model().ifPresent(m -> m.modelName().ifPresent(b::model));
            String inst = extractInstruction(llm.instruction());
            if (inst != null && !inst.isEmpty()) b.instructions(inst);

            List<ToolDef> tools = extractTopLevelTools(llm, visited);
            if (!tools.isEmpty()) b.tools(tools.toArray(new ToolDef[0]));
        }

        // Sub-agents register their worker handlers via prepareWorkers walking
        // agent.getAgents(); the wire format is built separately into the raw
        // sub_agents Map list below.
        List<Agent> subAgentChildren = new ArrayList<>();
        for (BaseAgent sub : safeSubAgents(adk)) {
            subAgentChildren.add(toAgentspan(sub, visited));
        }
        if (!subAgentChildren.isEmpty()) {
            b.agents(subAgentChildren.toArray(new Agent[0]));
        }

        // Callbacks: wrap ADK callbacks as an Agentspan CallbackHandler so the
        // runtime registers worker handlers and the server schedules hook tasks
        // at the right positions. Best-effort — contexts are stubbed; see
        // wrapCallbacks() for the constraint matrix.
        if (adk instanceof LlmAgent llmCb) {
            CallbackHandler handler = wrapCallbacks(llmCb);
            if (handler != null) b.callbacks(handler);
        }

        Map<String, Object> frameworkConfig = buildRawConfig(adk, /*topLevel=*/ true,
                new java.util.IdentityHashMap<>());
        // Strip the simple scalars already set on the Agent.Builder — the
        // serializer emits them at the top level and frameworkConfig.putAll
        // would just overwrite with the same value.
        frameworkConfig.remove("name");
        frameworkConfig.remove("model");
        frameworkConfig.remove("instruction");
        // Intentionally keep `tools` in frameworkConfig: it contains the full
        // wire-shape including built-in tools (GoogleSearchTool, code
        // execution) that have no ToolDef representation, so it must override
        // the serializer's worker-only list via map.putAll(cfg).
        if (!frameworkConfig.isEmpty()) b.frameworkConfig(frameworkConfig);

        return b;
    }

    // ── Raw-config builder (used for top-level + every nested sub-agent) ─────

    /**
     * Serialize a single ADK {@link BaseAgent} into the wire Map shape the
     * server's {@code GoogleADKNormalizer.normalize(raw)} consumes. Recursive:
     * nested sub-agents are serialized via the same path. The {@code visited}
     * set guards against cycles in the {@code subAgents} / {@code AgentTool}
     * graph that would otherwise blow the stack.
     */
    private static Map<String, Object> buildRawConfig(
            BaseAgent adk, boolean topLevel,
            java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        if (visited.putIfAbsent(adk, Boolean.TRUE) != null) {
            throw new IllegalArgumentException(
                    "AdkBridge: cycle detected in subAgents/AgentTool graph at agent '"
                    + adk.name() + "'");
        }
        Map<String, Object> raw = new LinkedHashMap<>();

        // Identity
        raw.put("name", adk.name());
        String desc = adk.description();
        if (desc != null && !desc.isEmpty()) raw.put("description", desc);

        // Composite-agent class detection (SequentialAgent / ParallelAgent /
        // LoopAgent). Server reads `_type` to set strategy; without this the
        // normalizer defaults to "handoff" and our pipelines run wrong.
        String typeName = adk.getClass().getSimpleName();
        if ("SequentialAgent".equals(typeName)
                || "ParallelAgent".equals(typeName)
                || "LoopAgent".equals(typeName)) {
            raw.put("_type", typeName);
        }

        // LoopAgent.maxIterations → server's `max_iterations`
        if (adk instanceof LoopAgent loop) {
            Integer mi = loop.maxIterations();
            if (mi != null && mi > 0) raw.put("max_iterations", mi);
        }

        // LlmAgent-specific fields
        if (adk instanceof LlmAgent llm) {
            llm.model().ifPresent(m -> m.modelName().ifPresent(name -> raw.put("model", name)));

            String inst = extractInstruction(llm.instruction());
            if (inst != null && !inst.isEmpty()) raw.put("instruction", inst);

            String gi = extractInstruction(llm.globalInstruction());
            if (gi != null && !gi.isEmpty()) raw.put("global_instruction", gi);

            // Output schema (genai Schema → JSON-schema-shaped Map)
            llm.outputSchema().ifPresent(s -> raw.put("output_schema", schemaToMap(s)));
            llm.outputKey().ifPresent(k -> raw.put("output_key", k));

            // include_contents — only emit when not default (server defaults match)
            LlmAgent.IncludeContents inc = llm.includeContents();
            if (inc != null && inc != LlmAgent.IncludeContents.DEFAULT) {
                raw.put("include_contents", inc.name().toLowerCase());
            }

            // Planning (BuiltInPlanner)
            if (llm.planning()) {
                raw.put("planner", Map.of("_type", "BuiltInPlanner"));
            }

            // Transfer restrictions (consumed by parent normalizer when this
            // agent appears as a sub_agent — see GoogleADKNormalizer line ~134)
            if (llm.disallowTransferToParent()) raw.put("disallow_transfer_to_parent", true);
            if (llm.disallowTransferToPeers())  raw.put("disallow_transfer_to_peers",  true);

            // GenerateContentConfig → server's `generate_content_config`
            llm.generateContentConfig().ifPresent(gc -> {
                Map<String, Object> gcMap = new LinkedHashMap<>();
                gc.temperature().ifPresent(t -> gcMap.put("temperature", t));
                gc.maxOutputTokens().ifPresent(m -> gcMap.put("max_output_tokens", m));
                gc.thinkingConfig().ifPresent(tc -> {
                    Map<String, Object> tcMap = new LinkedHashMap<>();
                    tc.includeThoughts().ifPresent(it -> tcMap.put("include_thoughts", it));
                    tc.thinkingBudget().ifPresent(b -> tcMap.put("thinking_budget", b));
                    if (!tcMap.isEmpty()) gcMap.put("thinking_config", tcMap);
                });
                if (!gcMap.isEmpty()) raw.put("generate_content_config", gcMap);
            });

            // Tools — full dispatch on BaseTool subclass.
            List<Map<String, Object>> toolMaps = buildToolMaps(llm.tools().blockingGet(), visited);
            if (!toolMaps.isEmpty()) raw.put("tools", toolMaps);

            // Callbacks: emit `_worker_ref` placeholders for each non-empty
            // callback list. The matching CallbackHandler attached on the
            // Agent.Builder (see toAgentspan) registers the local worker so
            // any server-scheduled hook task lands somewhere.
            //
            // KNOWN SERVER LIMITATION (matches Python — see python ADK
            // examples/14_callbacks.py): the server-side compiler currently
            // does NOT translate `before_*/after_*_callback._worker_ref`
            // into Conductor hook tasks. The wire field is recognized by
            // GoogleADKNormalizer (CallbackConfig is built), but downstream
            // workflow compilation drops it for the simple-LLM agent shape.
            // Bridge stays ready: the moment the server emits the hook
            // task, the registered worker dispatches the user's callback.
            //
            // Callback context limitations even when server fires hooks:
            // CallbackContext/InvocationContext are passed as null. Callbacks
            // that read session state / save artifacts will NPE (caught and
            // logged). Inspection-only callbacks (the common case) work fine.
            attachCallbackRefs(llm, raw);
        }

        // Sub-agents — full recursive serialization.
        List<? extends BaseAgent> subs = safeSubAgents(adk);
        if (subs != null && !subs.isEmpty()) {
            List<Map<String, Object>> subMaps = new ArrayList<>();
            for (BaseAgent s : subs) {
                subMaps.add(buildRawConfig(s, /*topLevel=*/ false, visited));
            }
            raw.put("sub_agents", subMaps);
        }

        return raw;
    }

    // ── Instruction extraction ───────────────────────────────────────────────

    private static String extractInstruction(Instruction inst) {
        if (inst == null) return null;
        if (inst instanceof Instruction.Static s) {
            return s.instruction();
        }
        if (inst instanceof Instruction.Provider p) {
            try {
                // Resolve with a null context. Many providers don't actually
                // touch the context; for those that do, the user must rely on
                // server-side state via output_key / globalInstruction. We log
                // any failure but never break the run.
                return p.getInstruction().apply(null).blockingGet();
            } catch (Throwable t) {
                log.warn("AdkBridge: Instruction.Provider for '{}' threw during static "
                        + "resolution; falling back to empty instruction. {}",
                        t.getClass().getSimpleName(), t.getMessage());
                return null;
            }
        }
        return null;
    }

    // ── Tool extraction ──────────────────────────────────────────────────────

    /**
     * Top-level tools — extracted from {@code LlmAgent.tools()} and wrapped as
     * {@link ToolDef} so the Agentspan worker poller registers handlers AND
     * the serializer emits the expected {@code _worker_ref} / {@code _type:
     * AgentTool} wire shape.
     */
    private static List<ToolDef> extractTopLevelTools(
            LlmAgent llm, java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        List<ToolDef> out = new ArrayList<>();
        for (BaseTool t : llm.tools().blockingGet()) {
            ToolDef d = toToolDef(t, visited);
            if (d != null) out.add(d);
        }
        return out;
    }

    /**
     * Tool wire-maps for nested sub-agents. Same shape as the serializer would
     * emit for top-level tools — the server's recursive normalizer pulls them
     * from each sub_agent's {@code tools} array.
     */
    private static List<Map<String, Object>> buildToolMaps(
            List<BaseTool> tools, java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        List<Map<String, Object>> out = new ArrayList<>();
        if (tools == null) return out;

        for (BaseTool t : tools) {
            addToolMap(t, out, visited);
        }
        return out;
    }

    private static void addToolMap(
            BaseTool t, List<Map<String, Object>> out,
            java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        if (t instanceof FunctionTool ft) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("_worker_ref", ft.name());
            m.put("description", nullToEmpty(ft.description()));
            m.put("parameters", buildInputSchema(ft));
            out.add(m);
        } else if (t instanceof AgentTool at) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("_type", "AgentTool");
            m.put("name", at.name());
            m.put("description", nullToEmpty(at.description()));
            m.put("agent", buildRawConfig(at.getAgent(), /*topLevel=*/ false, visited));
            out.add(m);
        } else if (t instanceof GoogleSearchTool) {
            // Server normalizer recognizes _type: GoogleSearchTool (line 279)
            // and wires it as a builtin HTTP tool with config {builtin: google_search}.
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("_type", "GoogleSearchTool");
            m.put("name", "google_search");
            m.put("description", "Search the web using Google.");
            out.add(m);
        } else if (t instanceof BuiltInCodeExecutionTool) {
            // Server normalizer recognizes _type: CodeExecutionTool (line 100,
            // 288) and enables setCodeExecution(enabled=true) on the config.
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("_type", "CodeExecutionTool");
            m.put("name", "code_execution");
            m.put("description", "Execute code in a sandboxed environment.");
            out.add(m);
        } else if (t instanceof BaseToolset bts) {
            // A toolset is a lazy bundle of BaseTools. Resolve, emit each, then
            // close — many toolsets (e.g. McpToolset) hold a network/process
            // resource that we MUST release after extraction. Failure to
            // expand is logged at error level so the user notices they lost
            // tools rather than silently degrading the LLM's tool list.
            try {
                for (BaseTool inner : bts.getTools(null).blockingIterable()) {
                    addToolMap(inner, out, visited);
                }
            } catch (Throwable th) {
                log.error("AdkBridge: BaseToolset '{}' expansion failed; tools from this "
                        + "toolset will NOT be available to the agent. Cause: {}",
                        t.getClass().getName(), th.toString());
            } finally {
                try { bts.close(); }
                catch (Throwable th) {
                    log.debug("AdkBridge: BaseToolset.close() threw: {}", th.toString());
                }
            }
        } else {
            log.warn("AdkBridge: dropping unsupported BaseTool subclass '{}'", t.getClass().getName());
        }
    }

    private static ToolDef toToolDef(BaseTool t, java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        if (t instanceof FunctionTool ft) return functionToolToDef(ft);
        if (t instanceof AgentTool at)    return agentToolToDef(at, visited);
        // GoogleSearchTool / BuiltInCodeExecutionTool / BaseToolset: server-side
        // builtin tools that don't need a local worker. Returning null is
        // intentional — extractTopLevelTools drops nulls and these still get
        // emitted into the wire format via buildToolMaps (frameworkConfig.tools).
        if (t instanceof GoogleSearchTool
                || t instanceof BuiltInCodeExecutionTool
                || t instanceof BaseToolset) {
            return null;
        }
        log.warn("AdkBridge: dropping unsupported BaseTool subclass '{}'", t.getClass().getName());
        return null;
    }

    private static ToolDef functionToolToDef(FunctionTool ft) {
        Method method = ft.func();
        method.setAccessible(true);

        Map<String, Object> inputSchema = buildInputSchema(ft);
        Map<String, Object> outputSchema = Map.of("type", "object");

        final Method finalMethod = method;
        final String name = ft.name();
        Function<Map<String, Object>, Object> func = inputData -> {
            try {
                Object[] args = buildArgs(finalMethod, inputData);
                return finalMethod.invoke(null, args);
            } catch (java.lang.reflect.InvocationTargetException ite) {
                // Unwrap so the user sees their own exception, not a confusing
                // double-wrapped stack trace.
                Throwable cause = ite.getCause() != null ? ite.getCause() : ite;
                if (cause instanceof RuntimeException re) throw re;
                throw new RuntimeException("ADK FunctionTool '" + name + "' threw: "
                        + cause.getMessage(), cause);
            } catch (IllegalAccessException | IllegalArgumentException ex) {
                throw new RuntimeException("ADK FunctionTool '" + name
                        + "' invocation failed (check parameter types and the -parameters "
                        + "compiler flag): " + ex.getMessage(), ex);
            }
        };

        return new ToolDef.Builder()
                .name(ft.name())
                .description(nullToEmpty(ft.description()))
                .inputSchema(inputSchema)
                .outputSchema(outputSchema)
                .func(func)
                .toolType("worker")
                .build();
    }

    private static ToolDef agentToolToDef(AgentTool at, java.util.IdentityHashMap<BaseAgent, Boolean> visited) {
        BaseAgent inner = at.getAgent();
        Agent childAgent = toAgentspan(inner, visited);
        // AgentTool produces an empty input schema in ADK by default; the
        // Agentspan serializer's AgentTool path builds a stock {request:
        // string} schema for us.
        return new ToolDef.Builder()
                .name(at.name())
                .description(nullToEmpty(at.description()))
                .toolType("agent_tool")
                .agentRef(childAgent)
                .build();
    }

    // ── Schema / parameter extraction (with @Schema name fix) ───────────────

    private static Map<String, Object> buildInputSchema(FunctionTool ft) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");

        Map<String, Object> properties = new LinkedHashMap<>();
        List<String> required = new ArrayList<>();

        // First try ADK's own FunctionDeclaration — that's the schema the LLM
        // will see, so we mirror exactly the same property names.
        try {
            FunctionDeclaration decl = ft.declaration().orElse(null);
            if (decl != null) {
                Schema params = decl.parameters().orElse(null);
                if (params != null) {
                    params.properties().ifPresent(p -> {
                        for (Map.Entry<String, Schema> e : p.entrySet()) {
                            properties.put(e.getKey(), schemaToMap(e.getValue()));
                        }
                    });
                    params.required().ifPresent(required::addAll);
                }
            }
        } catch (Throwable t) {
            log.debug("AdkBridge: FunctionDeclaration parse failed for {}: {}",
                    ft.name(), t.getMessage());
        }

        // Reflection fallback when the declaration doesn't expose properties.
        if (properties.isEmpty()) {
            for (Parameter p : ft.func().getParameters()) {
                String pn = paramName(p);
                Map<String, Object> propSchema = new LinkedHashMap<>();
                propSchema.put("type", jsonTypeOf(p.getType()));
                schemaAnnotationDescription(p).ifPresent(d -> propSchema.put("description", d));
                properties.put(pn, propSchema);
                required.add(pn);
            }
        }

        schema.put("properties", properties);
        if (!required.isEmpty()) schema.put("required", required);
        return schema;
    }

    /**
     * The reason {@link com.google.adk.tools.Annotations.Schema} exists on the
     * parameter is so the LLM sees {@code customer_id} while the Java method
     * keeps idiomatic {@code customerId}. Prior bridge versions used
     * {@link Parameter#getName()} and lost this rename, causing NPEs when the
     * server invoked the tool with the schema name. Honor {@code @Schema.name}
     * first.
     */
    private static final java.util.Set<String> WARNED_ARG_METHODS =
            java.util.concurrent.ConcurrentHashMap.newKeySet();

    private static String paramName(Parameter p) {
        Annotations.Schema ann = p.getAnnotation(Annotations.Schema.class);
        if (ann != null && ann.name() != null && !ann.name().isEmpty()) {
            return ann.name();
        }
        String name = p.getName();
        // Compiler-retained parameter names require -parameters at javac time.
        // Without it, getName() returns "arg0" / "arg1" / ... which the LLM
        // then sees in the function schema — guaranteed garbage tool calls.
        // Warn loudly once per method so the user notices and either adds
        // -parameters or switches to @Schema(name=...).
        if (name != null && name.matches("arg\\d+")) {
            String key = p.getDeclaringExecutable().getDeclaringClass().getName()
                    + "#" + p.getDeclaringExecutable().getName();
            if (WARNED_ARG_METHODS.add(key)) {
                log.warn("AdkBridge: method '{}' parameter names are not preserved "
                        + "(got '{}'). The LLM will see meaningless parameter names. "
                        + "Compile with javac -parameters, or use "
                        + "@Schema(name=\"...\") on each parameter.", key, name);
            }
        }
        return name;
    }

    private static java.util.Optional<String> schemaAnnotationDescription(Parameter p) {
        Annotations.Schema ann = p.getAnnotation(Annotations.Schema.class);
        if (ann == null || ann.description() == null || ann.description().isEmpty()) {
            return java.util.Optional.empty();
        }
        return java.util.Optional.of(ann.description());
    }

    private static Map<String, Object> schemaToMap(Schema s) {
        Map<String, Object> m = new LinkedHashMap<>();
        s.type().ifPresent(t -> m.put("type", t.toString().toLowerCase()));
        s.description().ifPresent(d -> m.put("description", d));
        s.enum_().ifPresent(e -> m.put("enum", e));
        s.format().ifPresent(f -> m.put("format", f));
        s.items().ifPresent(it -> m.put("items", schemaToMap(it)));
        s.properties().ifPresent(p -> {
            Map<String, Object> propsOut = new LinkedHashMap<>();
            for (Map.Entry<String, Schema> e : p.entrySet()) {
                propsOut.put(e.getKey(), schemaToMap(e.getValue()));
            }
            m.put("properties", propsOut);
        });
        s.required().ifPresent(r -> m.put("required", r));
        return m;
    }

    private static String jsonTypeOf(Class<?> type) {
        if (type == String.class) return "string";
        if (type == int.class || type == Integer.class
            || type == long.class || type == Long.class) return "integer";
        if (type == double.class || type == Double.class
            || type == float.class || type == Float.class) return "number";
        if (type == boolean.class || type == Boolean.class) return "boolean";
        if (type.isArray() || List.class.isAssignableFrom(type)) return "array";
        return "object";
    }

    // ── Method invocation helpers ────────────────────────────────────────────

    private static Object[] buildArgs(Method method, Map<String, Object> inputData) {
        Parameter[] params = method.getParameters();
        Object[] args = new Object[params.length];
        for (int i = 0; i < params.length; i++) {
            String pn = paramName(params[i]);
            Object raw = inputData != null ? inputData.get(pn) : null;
            // Share ToolRegistry's coercion table: handles primitives, String,
            // java.time.*, enums, Optional, List<X>, Map, arrays via Jackson
            // and the generic type. Keeps the bridge in lockstep with the
            // @Tool fix from #236.
            args[i] = ai.agentspan.internal.ToolRegistry.coerceArgument(
                    raw, params[i].getType(), params[i].getParameterizedType());
        }
        return args;
    }

    // ── Callback wiring ──────────────────────────────────────────────────────

    /**
     * Emit a {@code _worker_ref} placeholder for every callback position that
     * has at least one registered ADK callback. The matching
     * {@link CallbackHandler} attached on the {@code Agent.Builder} registers
     * the local worker handler.
     */
    private static void attachCallbackRefs(LlmAgent llm, Map<String, Object> raw) {
        String agentName = llm.name();
        for (String[] pair : CALLBACK_FIELDS) {
            String field = pair[0];
            String getter = pair[1];
            if (callbackListIsNonEmpty(llm, getter)) {
                String position = field.replace("_callback", "");
                Map<String, Object> ref = new LinkedHashMap<>();
                ref.put("_worker_ref", agentName + "_" + position);
                raw.put(field, ref);
            }
        }
    }

    private static boolean callbackListIsNonEmpty(LlmAgent llm, String getter) {
        return !callbackList(llm, getter).isEmpty();
    }

    /**
     * Wrap any ADK callbacks attached to {@code llm} as a single
     * {@link CallbackHandler} that the Agentspan runtime can dispatch to.
     *
     * <p>Returns {@code null} if no callbacks are attached.
     *
     * <p><b>Limitations:</b> the {@link com.google.adk.agents.CallbackContext}
     * / {@link com.google.adk.agents.InvocationContext} passed to the user's
     * callback is {@code null}. Callbacks that read session state, invoke
     * {@code state()}, or call {@code saveArtifact} / {@code loadArtifact}
     * will throw NPE — caught and logged. Callbacks that <em>inspect</em>
     * the request/response shape (the common safety/guardrail / logging
     * use case) work fine.
     */
    @SuppressWarnings("unchecked")
    private static CallbackHandler wrapCallbacks(LlmAgent llm) {
        List<Callbacks.BeforeAgentCallback> beforeAgent = callbackList(llm, "beforeAgentCallback");
        List<Callbacks.AfterAgentCallback>  afterAgent  = callbackList(llm, "afterAgentCallback");
        List<Callbacks.BeforeModelCallback> beforeModel = callbackList(llm, "beforeModelCallback");
        List<Callbacks.AfterModelCallback>  afterModel  = callbackList(llm, "afterModelCallback");
        List<Callbacks.BeforeToolCallback>  beforeTool  = callbackList(llm, "beforeToolCallback");
        List<Callbacks.AfterToolCallback>   afterTool   = callbackList(llm, "afterToolCallback");

        if (beforeAgent.isEmpty() && afterAgent.isEmpty()
                && beforeModel.isEmpty() && afterModel.isEmpty()
                && beforeTool.isEmpty() && afterTool.isEmpty()) {
            return null;
        }

        return new CallbackHandler() {
            @Override public Map<String, Object> onAgentStart(Map<String, Object> in) {
                for (var cb : beforeAgent) {
                    try {
                        Content out = cb.call(null).blockingGet();
                        if (out != null) return Map.of("content", textOf(out));
                    } catch (Throwable t) {
                        log.warn("ADK beforeAgentCallback failed: {}", t.getMessage());
                    }
                }
                return Map.of();
            }
            @Override public Map<String, Object> onAgentEnd(Map<String, Object> in) {
                for (var cb : afterAgent) {
                    try {
                        Content out = cb.call(null).blockingGet();
                        if (out != null) return Map.of("content", textOf(out));
                    } catch (Throwable t) {
                        log.warn("ADK afterAgentCallback failed: {}", t.getMessage());
                    }
                }
                return Map.of();
            }
            @Override public Map<String, Object> onModelStart(Map<String, Object> in) {
                LlmRequest.Builder req = reconstructLlmRequest(in);
                for (var cb : beforeModel) {
                    try {
                        LlmResponse resp = cb.call(null, req).blockingGet();
                        if (resp != null) {
                            return Map.of("content", resp.content().map(AdkBridge::textOf).orElse(""));
                        }
                    } catch (Throwable t) {
                        log.warn("ADK beforeModelCallback failed: {}", t.getMessage());
                    }
                }
                return Map.of();
            }
            @Override public Map<String, Object> onModelEnd(Map<String, Object> in) {
                LlmResponse resp = reconstructLlmResponse(in);
                for (var cb : afterModel) {
                    try {
                        LlmResponse rewritten = cb.call(null, resp).blockingGet();
                        if (rewritten != null) {
                            return Map.of("content", rewritten.content().map(AdkBridge::textOf).orElse(""));
                        }
                    } catch (Throwable t) {
                        log.warn("ADK afterModelCallback failed: {}", t.getMessage());
                    }
                }
                return Map.of();
            }
            @Override public Map<String, Object> onToolStart(Map<String, Object> in) {
                String toolName = (String) in.getOrDefault("tool_name", "");
                Map<String, Object> args = (Map<String, Object>) in.getOrDefault("args", Map.of());
                for (var cb : beforeTool) {
                    try {
                        // BaseTool/ToolContext are null — user callbacks should
                        // base decisions on the args/toolName they get here.
                        Map<String, Object> out = cb.call(null, null, args, null).blockingGet();
                        if (out != null) return out;
                    } catch (Throwable t) {
                        log.warn("ADK beforeToolCallback failed for '{}': {}", toolName, t.getMessage());
                    }
                }
                return Map.of();
            }
            @Override public Map<String, Object> onToolEnd(Map<String, Object> in) {
                String toolName = (String) in.getOrDefault("tool_name", "");
                Map<String, Object> args = (Map<String, Object>) in.getOrDefault("args", Map.of());
                Object result = in.get("result");
                for (var cb : afterTool) {
                    try {
                        Map<String, Object> out = cb.call(null, null, args, null, result).blockingGet();
                        if (out != null) return out;
                    } catch (Throwable t) {
                        log.warn("ADK afterToolCallback failed for '{}': {}", toolName, t.getMessage());
                    }
                }
                return Map.of();
            }
        };
    }

    /**
     * Read a callback list getter on {@link LlmAgent}. The static return type
     * declares {@code Optional<List<...>>} but, depending on the ADK build,
     * runtime sometimes returns the {@link List} directly (e.g. an
     * {@code ImmutableList}). Handle both shapes — and an empty/null Optional —
     * uniformly.
     */
    @SuppressWarnings("unchecked")
    private static <T> List<T> callbackList(LlmAgent llm, String getter) {
        try {
            Method m = LlmAgent.class.getMethod(getter);
            Object v = m.invoke(llm);
            if (v == null) return List.of();
            if (v instanceof java.util.Optional<?> opt) {
                if (!opt.isPresent()) return List.of();
                v = opt.get();
            }
            if (v instanceof List<?> list) return (List<T>) list;
        } catch (Throwable ignored) {}
        return List.of();
    }

    /**
     * Best-effort reconstruction of an {@link LlmRequest.Builder} from the
     * hook task's input map. Server hook payload format may vary — we look
     * for the common keys ({@code messages}, {@code prompt}). Empty contents
     * are still safe: most safety callbacks call {@code req.contents()} just
     * to inspect text and will see an empty list rather than NPE.
     */
    @SuppressWarnings("unchecked")
    private static LlmRequest.Builder reconstructLlmRequest(Map<String, Object> in) {
        LlmRequest.Builder b = LlmRequest.builder();
        List<Content> contents = new ArrayList<>();

        Object messagesObj = in.get("messages");
        if (messagesObj instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?>) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> msg = (Map<String, Object>) item;
                    String role = String.valueOf(msg.getOrDefault("role", "user"));
                    String text = String.valueOf(msg.getOrDefault("content", ""));
                    contents.add(Content.builder()
                            .role(role)
                            .parts(List.of(Part.builder().text(text).build()))
                            .build());
                }
            }
        } else if (in.get("prompt") instanceof String s && !s.isEmpty()) {
            contents.add(Content.builder()
                    .role("user")
                    .parts(List.of(Part.builder().text(s).build()))
                    .build());
        }
        b.contents(contents);
        return b;
    }

    /**
     * Best-effort reconstruction of an {@link LlmResponse} from the
     * after-model hook task input. Server typically posts the LLM's text
     * output under {@code content} or {@code result}.
     */
    private static LlmResponse reconstructLlmResponse(Map<String, Object> in) {
        Object text = in.get("content");
        if (text == null) text = in.get("result");
        if (text == null) text = "";

        // LlmResponse.builder() is package-private in some ADK builds. Fall
        // back to a minimal Content if direct construction isn't available.
        try {
            Method builder = LlmResponse.class.getMethod("builder");
            Object b = builder.invoke(null);
            Method content = b.getClass().getMethod("content", java.util.Optional.class);
            Content c = Content.builder()
                    .role("model")
                    .parts(List.of(Part.builder().text(String.valueOf(text)).build()))
                    .build();
            content.invoke(b, java.util.Optional.of(c));
            Method build = b.getClass().getMethod("build");
            return (LlmResponse) build.invoke(b);
        } catch (Throwable t) {
            log.debug("AdkBridge: LlmResponse reconstruction failed, returning null. {}",
                    t.getMessage());
            return null;
        }
    }

    private static String textOf(Content c) {
        try {
            return c.text();
        } catch (Throwable t) {
            return "";
        }
    }

    // ── Misc helpers ─────────────────────────────────────────────────────────

    private static List<? extends BaseAgent> safeSubAgents(BaseAgent adk) {
        try {
            List<? extends BaseAgent> s = adk.subAgents();
            return s == null ? List.of() : s;
        } catch (Throwable t) {
            return List.of();
        }
    }

    private static String nullToEmpty(String s) {
        return s == null ? "" : s;
    }
}
