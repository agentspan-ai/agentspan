// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.execution;

import static org.junit.jupiter.api.Assertions.*;

import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.Test;

/**
 * {@link CodeExecutor#asTool()} must propagate the executor's timeout onto the
 * generated {@link ToolDef}, so worker registration sizes the Conductor task
 * def's responseTimeout to the handler's blocking duration. Building the tool
 * does not execute anything — no Docker required.
 */
class CodeExecutorAsToolTest {

    @Test
    void asTool_propagates_executor_timeout_to_toolDef() {
        DockerCodeExecutor executor = new DockerCodeExecutor("python:3.12-slim", "python", 420);
        ToolDef tool = executor.asTool("py_docker_exec", "run python in docker");

        assertEquals(
                420,
                tool.getTimeoutSeconds(),
                "asTool() must carry the executor's 420s timeout onto the ToolDef so a "
                        + "long-running container exec isn't reclaimed at the 300s default. "
                        + "COUNTERFACTUAL: if timeout isn't propagated, getTimeoutSeconds()==0.");
        assertEquals("worker", tool.getToolType());
    }
}
