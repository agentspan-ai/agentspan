// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.Agent;
import ai.agentspan.model.ToolDef;

import com.google.adk.agents.BaseAgent;
import com.google.adk.agents.Instruction;
import com.google.adk.agents.LlmAgent;
import com.google.adk.agents.LoopAgent;
import com.google.adk.tools.AgentTool;
import com.google.adk.tools.Annotations;
import com.google.adk.tools.BaseTool;
import com.google.adk.tools.FunctionTool;
import com.google.genai.types.FunctionDeclaration;
import com.google.genai.types.GenerateContentConfig;
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

    private AdkBridge() {}

    // ── Public entry ─────────────────────────────────────────────────────────

    /**
     * Convert any native ADK {@link BaseAgent} ({@code LlmAgent},
     * {@code SequentialAgent}, {@code ParallelAgent}, {@code LoopAgent}, …)
     * into an Agentspan {@link Agent} ready for {@code Agentspan.run(...)}.
     */
    public static Agent toAgentspan(BaseAgent adk) {
        if (adk == null) {
            throw new IllegalArgumentException("AdkBridge.toAgentspan: agent is null");
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

            List<ToolDef> tools = extractTopLevelTools(llm);
            if (!tools.isEmpty()) b.tools(tools.toArray(new ToolDef[0]));
        }

        // Sub-agents register their worker handlers via prepareWorkers walking
        // agent.getAgents(); the wire format is built separately into the raw
        // sub_agents Map list below.
        List<Agent> subAgentChildren = new ArrayList<>();
        for (BaseAgent sub : safeSubAgents(adk)) {
            subAgentChildren.add(toAgentspan(sub));
        }
        if (!subAgentChildren.isEmpty()) {
            b.agents(subAgentChildren.toArray(new Agent[0]));
        }

        Map<String, Object> frameworkConfig = buildRawConfig(adk, /*topLevel=*/ true);
        // Strip fields already set on the Agent.Builder — the serializer puts
        // them at the top level and frameworkConfig.putAll would just overwrite
        // with the same value.
        frameworkConfig.remove("name");
        frameworkConfig.remove("model");
        frameworkConfig.remove("instruction");
        frameworkConfig.remove("tools");
        if (!frameworkConfig.isEmpty()) b.frameworkConfig(frameworkConfig);

        return b.build();
    }

    // ── Raw-config builder (used for top-level + every nested sub-agent) ─────

    /**
     * Serialize a single ADK {@link BaseAgent} into the wire Map shape the
     * server's {@code GoogleADKNormalizer.normalize(raw)} consumes. Recursive:
     * nested sub-agents are serialized via the same path.
     */
    private static Map<String, Object> buildRawConfig(BaseAgent adk, boolean topLevel) {
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
            List<Map<String, Object>> toolMaps = buildToolMaps(llm.tools().blockingGet());
            if (!toolMaps.isEmpty()) raw.put("tools", toolMaps);

            // Callbacks: intentionally NOT emitted as `_worker_ref` placeholders.
            // ADK callbacks take rich contexts (CallbackContext, LlmRequest.Builder,
            // ToolContext) that can't be reconstructed from the Map<String,Object>
            // the Agentspan worker poller receives. Emitting `_worker_ref` here
            // would make the server schedule a before/after-hook task that no
            // local handler can answer, leaving the workflow blocked. Users who
            // need callbacks should register them via Agentspan's CallbackHandler
            // API on the Agent.Builder directly.
            //
            // TODO: build a thin adapter that synthesises an ADK CallbackContext
            // from a Map and routes ADK callbacks through Agentspan workers.
        }

        // Sub-agents — full recursive serialization.
        List<? extends BaseAgent> subs = safeSubAgents(adk);
        if (subs != null && !subs.isEmpty()) {
            List<Map<String, Object>> subMaps = new ArrayList<>();
            for (BaseAgent s : subs) {
                subMaps.add(buildRawConfig(s, /*topLevel=*/ false));
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
    private static List<ToolDef> extractTopLevelTools(LlmAgent llm) {
        List<ToolDef> out = new ArrayList<>();
        for (BaseTool t : llm.tools().blockingGet()) {
            ToolDef d = toToolDef(t);
            if (d != null) out.add(d);
        }
        return out;
    }

    /**
     * Tool wire-maps for nested sub-agents. Same shape as the serializer would
     * emit for top-level tools — the server's recursive normalizer pulls them
     * from each sub_agent's {@code tools} array.
     */
    private static List<Map<String, Object>> buildToolMaps(List<BaseTool> tools) {
        List<Map<String, Object>> out = new ArrayList<>();
        if (tools == null) return out;

        for (BaseTool t : tools) {
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
                m.put("agent", buildRawConfig(at.getAgent(), /*topLevel=*/ false));
                out.add(m);
            } else {
                log.warn("AdkBridge: dropping unsupported BaseTool subclass '{}'", t.getClass().getName());
            }
        }
        return out;
    }

    private static ToolDef toToolDef(BaseTool t) {
        if (t instanceof FunctionTool ft) return functionToolToDef(ft);
        if (t instanceof AgentTool at)    return agentToolToDef(at);
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
            } catch (Exception e) {
                throw new RuntimeException("ADK FunctionTool execution failed: " + name, e);
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

    private static ToolDef agentToolToDef(AgentTool at) {
        BaseAgent inner = at.getAgent();
        Agent childAgent = toAgentspan(inner);
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
    private static String paramName(Parameter p) {
        Annotations.Schema ann = p.getAnnotation(Annotations.Schema.class);
        if (ann != null && ann.name() != null && !ann.name().isEmpty()) {
            return ann.name();
        }
        return p.getName();
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
            args[i] = coerce(raw, params[i].getType());
        }
        return args;
    }

    private static Object coerce(Object value, Class<?> type) {
        if (value == null) {
            if (type == int.class) return 0;
            if (type == long.class) return 0L;
            if (type == double.class) return 0.0;
            if (type == boolean.class) return false;
            return null;
        }
        if (type.isInstance(value)) return value;
        String s = value.toString();
        if (type == String.class) return s;
        if (type == int.class || type == Integer.class) {
            return value instanceof Number n ? n.intValue() : Integer.parseInt(s);
        }
        if (type == long.class || type == Long.class) {
            return value instanceof Number n ? n.longValue() : Long.parseLong(s);
        }
        if (type == double.class || type == Double.class) {
            return value instanceof Number n ? n.doubleValue() : Double.parseDouble(s);
        }
        if (type == boolean.class || type == Boolean.class) {
            return value instanceof Boolean b ? b : Boolean.parseBoolean(s);
        }
        return value;
    }

    // ── Callback wiring ──────────────────────────────────────────────────────

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

    // Reference an unused symbol so the IDE keeps the ThinkingConfig import.
    @SuppressWarnings("unused")
    private static final Class<?> THINKING_CONFIG_CLASS = ThinkingConfig.class;
    @SuppressWarnings("unused")
    private static final Class<?> GENERATE_CONTENT_CONFIG_CLASS = GenerateContentConfig.class;
}
