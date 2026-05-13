// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

/**
 * Configuration for {@code Agent(model=ClaudeCode(...))} or the short string {@code "claude-code/opus"}.
 *
 * <pre>{@code
 * Agent reviewer = Agent.builder()
 *     .name("reviewer")
 *     .model(new ClaudeCode("opus", ClaudeCode.PermissionMode.ACCEPT_EDITS).toModelString())
 *     .instructions("Review code quality")
 *     .build();
 * }</pre>
 */
public class ClaudeCode {

    public enum PermissionMode {
        DEFAULT("default"),
        ACCEPT_EDITS("acceptEdits"),
        PLAN("plan"),
        BYPASS("bypassPermissions");

        private final String value;
        PermissionMode(String value) { this.value = value; }
        public String getValue() { return value; }
    }

    private static final java.util.Map<String, String> MODEL_ALIASES = new java.util.HashMap<>();
    static {
        MODEL_ALIASES.put("opus", "claude-opus-4-6");
        MODEL_ALIASES.put("sonnet", "claude-sonnet-4-6");
        MODEL_ALIASES.put("haiku", "claude-haiku-4-5");
    }

    private final String modelName;
    private final PermissionMode permissionMode;

    public ClaudeCode() {
        this("", PermissionMode.ACCEPT_EDITS);
    }

    public ClaudeCode(String modelName) {
        this(modelName, PermissionMode.ACCEPT_EDITS);
    }

    public ClaudeCode(String modelName, PermissionMode permissionMode) {
        this.modelName = modelName != null ? modelName : "";
        this.permissionMode = permissionMode != null ? permissionMode : PermissionMode.ACCEPT_EDITS;
    }

    /** Convert to the model string format used by {@code Agent.builder().model(...)}. */
    public String toModelString() {
        if (modelName == null || modelName.isEmpty()) return "claude-code";
        return "claude-code/" + modelName;
    }

    /** Resolve a short alias (opus, sonnet, haiku) to the full model ID. */
    public static String resolveModel(String alias) {
        if (alias == null || alias.isEmpty()) return null;
        return MODEL_ALIASES.getOrDefault(alias, alias);
    }

    public String getModelName() { return modelName; }
    public PermissionMode getPermissionMode() { return permissionMode; }

    @Override
    public String toString() {
        return "ClaudeCode{model=" + toModelString() + ", mode=" + permissionMode.getValue() + "}";
    }
}
