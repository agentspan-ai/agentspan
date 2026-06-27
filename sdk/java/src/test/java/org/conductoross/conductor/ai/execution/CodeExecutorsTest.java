// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.execution;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;

/**
 * Deterministic unit tests for the local / Jupyter / serverless code executors.
 *
 * <p>Parity target: Python {@code code_executor.py}
 * ({@code LocalCodeExecutor} / {@code JupyterCodeExecutor} /
 * {@code ServerlessCodeExecutor}).
 *
 * <p>No LLM and no live server: {@link LocalCodeExecutor} runs harmless real
 * snippets ({@code echo} / {@code print}), and the Jupyter/Serverless tests only
 * exercise the config surface and the structured-error path when the
 * kernel/endpoint is unavailable.
 */
class CodeExecutorsTest {

    // ── LocalCodeExecutor — real execution (deterministic) ────────────────

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void local_bashEcho_runsAndCapturesStdout() {
        LocalCodeExecutor exec = new LocalCodeExecutor("bash", 10);
        ExecutionResult result = exec.execute("echo hello-local");
        assertTrue(result.isSuccess(), "bash echo should succeed: " + result.getError());
        assertEquals(0, result.getExitCode());
        assertEquals("hello-local", result.getOutput().strip());
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void local_pythonPrint_runsAndCapturesStdout() {
        LocalCodeExecutor exec = new LocalCodeExecutor("python", 10);
        ExecutionResult result = exec.execute("print('hi-py')");
        // python3 may be absent on minimal CI; only assert output when it ran.
        if (result.getExitCode() == 127) return;
        assertTrue(result.isSuccess(), "python print should succeed: " + result.getError());
        assertEquals("hi-py", result.getOutput().strip());
    }

    @Test
    void local_emptyCode_returnsSuccessNoThrow() {
        LocalCodeExecutor exec = new LocalCodeExecutor("python", 10);
        ExecutionResult result = exec.execute("");
        assertTrue(result.isSuccess());
    }

    @Test
    void local_unsupportedLanguage_returnsStructuredError() {
        LocalCodeExecutor exec = new LocalCodeExecutor("cobol", 10);
        ExecutionResult result = exec.execute("DISPLAY 'X'.");
        assertFalse(result.isSuccess());
        assertEquals(1, result.getExitCode());
        assertTrue(result.getError().toLowerCase().contains("unsupported"), result.getError());
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void local_nonZeroExit_isNotSuccessButDoesNotThrow() {
        LocalCodeExecutor exec = new LocalCodeExecutor("bash", 10);
        ExecutionResult result = exec.execute("exit 3");
        assertFalse(result.isSuccess());
        assertEquals(3, result.getExitCode());
    }

    @Test
    void local_asTool_buildsToolDef() {
        LocalCodeExecutor exec = new LocalCodeExecutor("python", 7);
        assertNotNull(exec.asTool());
        assertEquals(7, exec.getTimeout());
        assertEquals("python", exec.getLanguage());
    }

    // ── JupyterCodeExecutor — config surface + error path ─────────────────

    @Test
    void jupyter_configSurface() {
        JupyterCodeExecutor exec =
                new JupyterCodeExecutor("http://127.0.0.1:1/", "python3", 12);
        // trailing slash is normalized away
        assertEquals("http://127.0.0.1:1", exec.getUrl());
        assertEquals("python3", exec.getKernelName());
        assertEquals(12, exec.getTimeout());
        assertEquals("python", exec.getLanguage());
        assertNotNull(exec.asTool());
    }

    @Test
    void jupyter_unavailableGateway_returnsStructuredErrorNoThrow() {
        // Port 1 / 127.0.0.1 is not a Jupyter gateway: must produce a structured
        // error result, never throw.
        JupyterCodeExecutor exec =
                new JupyterCodeExecutor("http://127.0.0.1:1/", "python3", 2);
        ExecutionResult result = exec.execute("print('x')");
        assertFalse(result.isSuccess());
        assertEquals(1, result.getExitCode());
        assertNotNull(result.getError());
        assertFalse(result.getError().isEmpty());
    }

    // ── ServerlessCodeExecutor — config surface + error path ──────────────

    @Test
    void serverless_configSurface() {
        java.util.Map<String, String> headers = java.util.Map.of("X-Env", "prod");
        ServerlessCodeExecutor exec =
                new ServerlessCodeExecutor("https://example.invalid/exec", "tok", "python", 9, headers);
        assertEquals("https://example.invalid/exec", exec.getEndpoint());
        assertEquals(9, exec.getTimeout());
        assertEquals("python", exec.getLanguage());
        assertEquals("prod", exec.getHeaders().get("X-Env"));
        assertNotNull(exec.asTool());
    }

    @Test
    void serverless_unreachableEndpoint_returnsStructuredErrorNoThrow() {
        // .invalid never resolves (RFC 6761): must produce a structured error,
        // never throw.
        ServerlessCodeExecutor exec =
                new ServerlessCodeExecutor("https://nonexistent.invalid/exec", null, "python", 2, null);
        ExecutionResult result = exec.execute("print('x')");
        assertFalse(result.isSuccess());
        assertEquals(1, result.getExitCode());
        assertNotNull(result.getError());
        assertFalse(result.getError().isEmpty());
    }
}
