// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.execution;

import java.util.Arrays;
import java.util.List;

/**
 * Configuration for agent code execution.
 *
 * <p>Pass to {@code Agent.builder().localCodeExecution(true)} along with
 * {@code .allowedLanguages(...)} and {@code .allowedCommands(...)} for simple use,
 * or use this class for full control over the executor.
 *
 * <pre>{@code
 * // Simple flag-based
 * Agent agent = Agent.builder()
 *     .name("coder")
 *     .model("openai/gpt-4o")
 *     .localCodeExecution(true)
 *     .allowedLanguages(List.of("python"))
 *     .build();
 *
 * // Full control with DockerCodeExecutor
 * CodeExecutionConfig config = new CodeExecutionConfig(
 *     List.of("python"),
 *     List.of("pip"),
 *     new DockerCodeExecutor("python:3.12-slim"),
 *     30
 * );
 * }</pre>
 */
public class CodeExecutionConfig {

    private final List<String> allowedLanguages;
    private final List<String> allowedCommands;
    private final CodeExecutor executor;
    private final int timeout;

    public CodeExecutionConfig(List<String> allowedLanguages, List<String> allowedCommands,
            CodeExecutor executor, int timeout) {
        this.allowedLanguages = allowedLanguages != null ? allowedLanguages : List.of("python");
        this.allowedCommands = allowedCommands != null ? allowedCommands : List.of();
        this.executor = executor;
        this.timeout = timeout > 0 ? timeout : 30;
    }

    public CodeExecutionConfig(List<String> allowedLanguages) {
        this(allowedLanguages, null, null, 30);
    }

    public List<String> getAllowedLanguages() { return allowedLanguages; }
    public List<String> getAllowedCommands() { return allowedCommands; }
    public CodeExecutor getExecutor() { return executor; }
    public int getTimeout() { return timeout; }
}
