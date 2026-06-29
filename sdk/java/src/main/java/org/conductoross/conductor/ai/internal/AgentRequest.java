// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.enums.Framework;
import org.conductoross.conductor.ai.plans.Plan;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

/**
 * Request payload for {@code POST /api/agent/compile}, {@code /deploy}, and {@code /start}.
 *
 * <p>All three endpoints share the same server-side {@code StartRequest} DTO. A single
 * {@link Agent} field carries the agent definition. The {@link Serializer} writes it
 * under either {@code "agentConfig"} (native agents) or {@code "framework"} +
 * {@code "rawConfig"} (framework-backed agents) — no duplication.
 *
 * <p>Build via {@link #nativeAgent(Agent)} or {@link #frameworkAgent(Framework, Agent)},
 * then chain builder methods for execution-specific fields.
 */
@JsonSerialize(using = AgentRequest.Serializer.class)
public final class AgentRequest {

    // ── Agent definition ────────────────────────────────────────────────
    /** The agent to compile / deploy / start. Always present. */
    final Agent agent;

    /**
     * Non-null for framework-backed agents; {@code null} for native agents.
     * Determines whether {@link Serializer} writes {@code "agentConfig"} or
     * {@code "framework"} + {@code "rawConfig"}.
     */
    final Framework framework;

    // ── Execution fields (only meaningful for /start) ────────────────────
    final String prompt;
    final String sessionId;
    final String runId;
    final Plan staticPlan;

    // ── Optional fields ──────────────────────────────────────────────────
    final List<String> media;
    final Map<String, Object> context;
    final String idempotencyKey;
    final List<String> credentials;
    final Integer timeoutSeconds;

    private AgentRequest(Builder b) {
        this.agent = b.agent;
        this.framework = b.framework;
        this.prompt = b.prompt;
        this.sessionId = b.sessionId;
        this.runId = b.runId;
        this.staticPlan = b.staticPlan;
        this.media = b.media;
        this.context = b.context;
        this.idempotencyKey = b.idempotencyKey;
        this.credentials = b.credentials;
        this.timeoutSeconds = b.timeoutSeconds;
    }

    /** Build a request for a native (non-framework) agent. */
    public static Builder nativeAgent(Agent agent) {
        return new Builder(agent, null);
    }

    /** Build a request for a framework-backed agent (OpenAI, ADK, Skill). */
    public static Builder frameworkAgent(Framework framework, Agent agent) {
        return new Builder(agent, framework);
    }

    // ── Builder ──────────────────────────────────────────────────────────

    public static final class Builder {
        private final Agent agent;
        private final Framework framework;
        private String prompt;
        private String sessionId;
        private String runId;
        private Plan staticPlan;
        private List<String> media;
        private Map<String, Object> context;
        private String idempotencyKey;
        private List<String> credentials;
        private Integer timeoutSeconds;

        private Builder(Agent agent, Framework framework) {
            this.agent = agent;
            this.framework = framework;
        }

        public Builder prompt(String v) {
            this.prompt = v;
            return this;
        }

        public Builder sessionId(String v) {
            this.sessionId = v;
            return this;
        }

        public Builder runId(String v) {
            this.runId = v;
            return this;
        }

        public Builder staticPlan(Plan v) {
            this.staticPlan = v;
            return this;
        }

        public Builder media(List<String> v) {
            this.media = v;
            return this;
        }

        public Builder context(Map<String, Object> v) {
            this.context = v;
            return this;
        }

        public Builder idempotencyKey(String v) {
            this.idempotencyKey = v;
            return this;
        }

        public Builder credentials(List<String> v) {
            this.credentials = v;
            return this;
        }

        public Builder timeoutSeconds(Integer v) {
            this.timeoutSeconds = v;
            return this;
        }

        public AgentRequest build() {
            return new AgentRequest(this);
        }
    }

    // ── Jackson serializer ───────────────────────────────────────────────

    /**
     * Writes the correct JSON shape based on whether a {@link Framework} is set:
     * <ul>
     *   <li>Native: {@code "agentConfig": serialize(agent)}</li>
     *   <li>Framework: {@code "framework": "openai", "rawConfig": serialize(agent)}</li>
     * </ul>
     * All other fields are written with explicit null-checks so no field is emitted
     * when not set ({@code @JsonInclude(NON_NULL)} is not needed on the class).
     */
    static final class Serializer extends JsonSerializer<AgentRequest> {
        private static final AgentConfigSerializer AGENT_SERIALIZER = new AgentConfigSerializer();

        @Override
        public void serialize(AgentRequest r, JsonGenerator gen, SerializerProvider provider) throws IOException {
            gen.writeStartObject();

            // Agent definition — mutually exclusive key based on framework
            if (r.framework == null) {
                gen.writeObjectField("agentConfig", AGENT_SERIALIZER.serialize(r.agent));
            } else {
                gen.writeStringField("framework", r.framework.wireValue());
                gen.writeObjectField("rawConfig", AGENT_SERIALIZER.serialize(r.agent));
            }

            // Execution fields
            if (r.prompt != null) gen.writeStringField("prompt", r.prompt);
            if (r.sessionId != null) gen.writeStringField("sessionId", r.sessionId);
            if (r.runId != null) gen.writeStringField("runId", r.runId);
            if (r.staticPlan != null) gen.writeObjectField("static_plan", r.staticPlan.toJson());

            // Optional fields
            if (r.media != null) {
                gen.writeFieldName("media");
                provider.defaultSerializeValue(r.media, gen);
            }
            if (r.context != null) {
                gen.writeFieldName("context");
                provider.defaultSerializeValue(r.context, gen);
            }
            if (r.idempotencyKey != null) gen.writeStringField("idempotencyKey", r.idempotencyKey);
            if (r.credentials != null) {
                gen.writeFieldName("credentials");
                provider.defaultSerializeValue(r.credentials, gen);
            }
            if (r.timeoutSeconds != null) gen.writeNumberField("timeoutSeconds", r.timeoutSeconds);

            gen.writeEndObject();
        }
    }
}
