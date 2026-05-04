// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * An agent that acts as a stand-in for a human user.
 *
 * <p>When it is this agent's turn in a multi-agent conversation, the workflow pauses with a
 * {@code HumanTask} and waits for real human input. The human's response becomes the agent's output.
 *
 * <pre>{@code
 * Agent user = UserProxyAgent.create("human");
 * Agent assistant = Agent.builder().name("assistant").model("openai/gpt-4o").build();
 *
 * Agent team = Agent.builder()
 *     .name("chat")
 *     .model("openai/gpt-4o")
 *     .agents(user, assistant)
 *     .strategy(Strategy.ROUND_ROBIN)
 *     .maxTurns(6)
 *     .build();
 * }</pre>
 */
public class UserProxyAgent {

    /** Valid values for {@code humanInputMode}. */
    public static final String ALWAYS = "ALWAYS";
    public static final String TERMINATE = "TERMINATE";
    public static final String NEVER = "NEVER";

    private UserProxyAgent() {}

    /** Create a UserProxyAgent that always pauses for human input. */
    public static Agent create() {
        return create("user", ALWAYS, "Continue.", "openai/gpt-4o");
    }

    /** Create a UserProxyAgent with a custom name that always pauses for human input. */
    public static Agent create(String name) {
        return create(name, ALWAYS, "Continue.", "openai/gpt-4o");
    }

    /**
     * Create a UserProxyAgent.
     *
     * @param name            agent name
     * @param humanInputMode  {@code "ALWAYS"}, {@code "TERMINATE"}, or {@code "NEVER"}
     * @param defaultResponse response used when {@code humanInputMode="NEVER"}
     * @param model           LLM model (used as fallback when no human input is available)
     */
    public static Agent create(String name, String humanInputMode,
            String defaultResponse, String model) {
        if (!ALWAYS.equals(humanInputMode)
                && !TERMINATE.equals(humanInputMode)
                && !NEVER.equals(humanInputMode)) {
            throw new IllegalArgumentException(
                "Invalid humanInputMode '" + humanInputMode + "'. Must be ALWAYS, TERMINATE, or NEVER");
        }
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("_agent_type", "user_proxy");
        metadata.put("_human_input_mode", humanInputMode);
        metadata.put("_default_response", defaultResponse);

        return Agent.builder()
                .name(name)
                .model(model)
                .instructions("You represent the human user in this conversation. "
                    + "Relay the human's input exactly as provided.")
                .metadata(metadata)
                .build();
    }
}
