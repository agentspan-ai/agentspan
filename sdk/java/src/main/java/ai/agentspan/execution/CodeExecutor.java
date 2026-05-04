// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.execution;

import ai.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Base class for code execution environments.
 *
 * <pre>{@code
 * CodeExecutor executor = new LocalCodeExecutor("python", 30);
 * ExecutionResult result = executor.execute("print('hello')");
 * ToolDef tool = executor.asTool();
 * }</pre>
 */
public abstract class CodeExecutor {

    protected final String language;
    protected final int timeout;
    protected final String workingDir;

    public CodeExecutor(String language, int timeout, String workingDir) {
        this.language = language != null ? language : "python";
        this.timeout = timeout > 0 ? timeout : 30;
        this.workingDir = workingDir;
    }

    /** Execute code and return the result. */
    public abstract ExecutionResult execute(String code);

    /**
     * Create a worker ToolDef for this executor that can be passed to {@code Agent.builder().tools(...)}.
     */
    public ToolDef asTool() {
        return asTool("execute_code", null);
    }

    public ToolDef asTool(String name, String description) {
        if (name == null) name = "execute_code";
        if (description == null) {
            description = "Execute " + language + " code. Returns stdout, stderr, and exit code. "
                + "Timeout: " + timeout + "s.";
        }
        Map<String, Object> codeProp = new LinkedHashMap<>();
        codeProp.put("type", "string");
        codeProp.put("description", "The code to execute.");
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("code", codeProp);
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        schema.put("properties", props);
        schema.put("required", List.of("code"));
        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(schema)
                .func(input -> {
                    String code = (String) input.get("code");
                    if (code == null || code.isEmpty()) {
                        return Map.of("status", "success", "output", "", "error", "", "exitCode", 0);
                    }
                    ExecutionResult result = execute(code);
                    return Map.of(
                        "status", result.isSuccess() ? "success" : "error",
                        "output", result.getOutput(),
                        "error", result.getError(),
                        "exitCode", result.getExitCode(),
                        "timedOut", result.isTimedOut()
                    );
                })
                .build();
    }

    public String getLanguage() { return language; }
    public int getTimeout() { return timeout; }
    public String getWorkingDir() { return workingDir; }
}
