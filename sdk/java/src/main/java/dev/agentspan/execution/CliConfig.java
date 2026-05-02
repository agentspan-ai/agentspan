// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.execution;

import java.util.ArrayList;
import java.util.List;

/**
 * Configuration for first-class CLI command execution on an Agent.
 *
 * <p>When set on an agent, a {@code run_command} worker tool is injected automatically,
 * allowing the LLM to execute shell commands within the configured constraints.
 *
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("ops")
 *     .model("openai/gpt-4o")
 *     .cliConfig(new CliConfig.Builder()
 *         .allowedCommands(List.of("git", "gh", "curl"))
 *         .timeout(60)
 *         .build())
 *     .build();
 * }</pre>
 */
public class CliConfig {

    private final boolean enabled;
    private final List<String> allowedCommands;
    private final int timeout;
    private final String workingDir;
    private final boolean allowShell;

    private CliConfig(Builder builder) {
        this.enabled = builder.enabled;
        this.allowedCommands = builder.allowedCommands != null ? new ArrayList<>(builder.allowedCommands) : new ArrayList<>();
        this.timeout = builder.timeout > 0 ? builder.timeout : 30;
        this.workingDir = builder.workingDir;
        this.allowShell = builder.allowShell;
    }

    public boolean isEnabled() { return enabled; }
    public List<String> getAllowedCommands() { return allowedCommands; }
    public int getTimeout() { return timeout; }
    public String getWorkingDir() { return workingDir; }
    public boolean isAllowShell() { return allowShell; }

    public static Builder builder() { return new Builder(); }

    public static class Builder {
        private boolean enabled = true;
        private List<String> allowedCommands;
        private int timeout = 30;
        private String workingDir;
        private boolean allowShell = false;

        public Builder enabled(boolean enabled) { this.enabled = enabled; return this; }
        public Builder allowedCommands(List<String> allowedCommands) { this.allowedCommands = allowedCommands; return this; }
        public Builder timeout(int timeout) { this.timeout = timeout; return this; }
        public Builder workingDir(String workingDir) { this.workingDir = workingDir; return this; }
        public Builder allowShell(boolean allowShell) { this.allowShell = allowShell; return this; }

        public CliConfig build() { return new CliConfig(this); }
    }
}
