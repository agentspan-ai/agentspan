// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.execution;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;

/**
 * Unit tests for {@link CliCommandExecutor} — the local executor + tokenizer
 * behind the auto-injected {@code run_command} tool. No LLM, no server.
 *
 * Parity target: Python {@code cli_config.py} (shlex), TypeScript
 * {@code cli-config.ts} and C# {@code CliTool.Tokenize}.
 *
 * The execution tests run harmless real commands ({@code echo}, {@code false})
 * and are disabled on Windows where those binaries differ.
 */
class CliCommandExecutorTest {

    // ── Tokenization ──────────────────────────────────────────────────────

    @Test
    void tokenize_bareExecutable() {
        assertEquals(List.of("git"), CliCommandExecutor.tokenize("git"));
    }

    @Test
    void tokenize_fullCommandLine() {
        assertEquals(
                List.of("gh", "repo", "list", "--limit", "5"), CliCommandExecutor.tokenize("gh repo list --limit 5"));
    }

    @Test
    void tokenize_collapsesRepeatedWhitespace() {
        assertEquals(List.of("git", "status", "-s"), CliCommandExecutor.tokenize("git   status\t-s"));
    }

    @Test
    void tokenize_honorsDoubleQuotes() {
        // Naive whitespace split would yield ["git","commit","-m","\"hello","world\""].
        assertEquals(
                List.of("git", "commit", "-m", "hello world"),
                CliCommandExecutor.tokenize("git commit -m \"hello world\""));
    }

    @Test
    void tokenize_honorsSingleQuotes() {
        assertEquals(List.of("echo", "hello world"), CliCommandExecutor.tokenize("echo 'hello world'"));
    }

    @Test
    void tokenize_unbalancedQuotesFallBackToWhitespaceSplit() {
        assertEquals(List.of("echo", "\"oops"), CliCommandExecutor.tokenize("echo \"oops"));
    }

    @Test
    void tokenize_emptyAndNull() {
        assertTrue(CliCommandExecutor.tokenize("").isEmpty());
        assertTrue(CliCommandExecutor.tokenize(null).isEmpty());
    }

    // ── Validation (no execution) ─────────────────────────────────────────

    @Test
    void run_rejectsDisallowedFullCommandLineKeyedOnExecutable() {
        Map<String, Object> result =
                CliCommandExecutor.run("rm -rf /", null, null, false, List.of("git"), 30, null, false);
        assertEquals("error", result.get("status"));
        assertTrue(
                ((String) result.get("stderr")).contains("Command 'rm' is not allowed"),
                "stderr should name the rejected executable: " + result.get("stderr"));
        assertNull(result.get("exit_code"), "no process should have run");
    }

    @Test
    void run_shellGateBlocksWhenDisabled() {
        Map<String, Object> result = CliCommandExecutor.run("echo hi", null, null, true, List.of(), 30, null, false);
        assertEquals("error", result.get("status"));
        assertTrue(((String) result.get("stderr")).contains("Shell mode is disabled"));
    }

    @Test
    void run_emptyCommand() {
        Map<String, Object> result = CliCommandExecutor.run("  ", null, null, false, List.of(), 30, null, false);
        assertEquals("error", result.get("status"));
        assertEquals("No command provided.", result.get("stderr"));
    }

    // ── Execution ─────────────────────────────────────────────────────────

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_executesFullCommandLine() {
        Map<String, Object> result =
                CliCommandExecutor.run("echo hello world", null, null, false, List.of("echo"), 30, null, false);
        assertEquals("success", result.get("status"));
        assertEquals(0, result.get("exit_code"));
        assertEquals("hello world", ((String) result.get("stdout")).trim());
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_stripsPathPrefixBeforeWhitelistCheck() {
        Map<String, Object> result =
                CliCommandExecutor.run("/bin/echo ok", null, null, false, List.of("echo"), 30, null, false);
        assertEquals("success", result.get("status"));
        assertEquals("ok", ((String) result.get("stdout")).trim());
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_mergesEmbeddedAndExplicitArgs() {
        Map<String, Object> result = CliCommandExecutor.run(
                "echo foo", List.of("bar", "baz"), null, false, List.of("echo"), 30, null, false);
        assertEquals("success", result.get("status"));
        assertEquals("foo bar baz", ((String) result.get("stdout")).trim());
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_honorsQuotedArgInCommandLine() {
        // The quoted phrase must arrive as a SINGLE argv element, so echo prints
        // it once with a single internal space (not as separate quoted tokens).
        Map<String, Object> result =
                CliCommandExecutor.run("echo \"hello   world\"", null, null, false, List.of("echo"), 30, null, false);
        assertEquals("success", result.get("status"));
        assertEquals("hello   world", ((String) result.get("stdout")).trim());
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_nonZeroExitReportsError() {
        Map<String, Object> result = CliCommandExecutor.run("false", null, null, false, List.of(), 30, null, false);
        assertEquals("error", result.get("status"));
        assertNotEquals(0, result.get("exit_code"));
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_commandNotFound() {
        Map<String, Object> result =
                CliCommandExecutor.run("agentspan_no_such_binary_xyz", null, null, false, List.of(), 30, null, false);
        assertEquals("error", result.get("status"));
        assertTrue(((String) result.get("stderr")).contains("Command not found"), "stderr: " + result.get("stderr"));
    }

    @Test
    @DisabledOnOs(OS.WINDOWS)
    void run_viaInputMapAndConfigOverload() {
        CliConfig cfg = CliConfig.builder().allowedCommands(List.of("echo")).build();
        Map<String, Object> input = Map.of("command", "echo hi there");
        Map<String, Object> result = CliCommandExecutor.run(input, cfg);
        assertEquals("success", result.get("status"));
        assertEquals("hi there", ((String) result.get("stdout")).trim());
    }
}
