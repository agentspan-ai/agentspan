// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.execution;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Execute code in a local subprocess.
 *
 * <p><strong>No sandboxing</strong> — the code runs with the same permissions as
 * the host JVM process. Use {@link DockerCodeExecutor} for untrusted code.
 *
 * <p>Mirrors Python's {@code LocalCodeExecutor}: it writes the snippet to a temp
 * file, invokes the matching interpreter, captures stdout/stderr, enforces a
 * timeout, and always cleans up the temp file. It never throws — failures (bad
 * language, missing interpreter, timeout, non-zero exit) are reported as a
 * structured {@link ExecutionResult}.
 *
 * <pre>{@code
 * LocalCodeExecutor executor = new LocalCodeExecutor("python", 10);
 * ExecutionResult result = executor.execute("print('hello')");
 * assert result.getOutput().strip().equals("hello");
 * }</pre>
 */
public class LocalCodeExecutor extends CodeExecutor {

    /** Map language names to interpreter argv prefixes (parity with Python's _INTERPRETERS). */
    private static final Map<String, List<String>> INTERPRETERS = Map.of(
            "python", List.of("python3"),
            "python3", List.of("python3"),
            "bash", List.of("bash"),
            "sh", List.of("sh"),
            "node", List.of("node"),
            "javascript", List.of("node"),
            "ruby", List.of("ruby"));

    public LocalCodeExecutor() {
        this("python", 30, null);
    }

    public LocalCodeExecutor(String language, int timeout) {
        this(language, timeout, null);
    }

    public LocalCodeExecutor(String language, int timeout, String workingDir) {
        super(language, timeout, workingDir);
    }

    @Override
    public ExecutionResult execute(String code) {
        if (code == null || code.isEmpty()) {
            return new ExecutionResult("No code provided. Nothing to execute.", "", 0, false);
        }

        List<String> interpreter = INTERPRETERS.get(language.toLowerCase());
        if (interpreter == null) {
            return new ExecutionResult("", "Unsupported language: " + language, 1, false);
        }

        Path tempFile = null;
        try {
            tempFile = Files.createTempFile("agentspan_code_", fileExtension(language));
            Files.writeString(tempFile, code);

            List<String> command = new ArrayList<>(interpreter);
            command.add(tempFile.toAbsolutePath().toString());

            ProcessBuilder pb = new ProcessBuilder(command);
            pb.redirectErrorStream(false);
            if (workingDir != null) {
                pb.directory(new java.io.File(workingDir));
            }

            Process process = pb.start();
            boolean completed = process.waitFor(timeout, TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                return new ExecutionResult("", "Execution timed out after " + timeout + "s", -1, true);
            }

            String stdout = new String(process.getInputStream().readAllBytes());
            String stderr = new String(process.getErrorStream().readAllBytes());
            return new ExecutionResult(stdout, stderr, process.exitValue(), false);

        } catch (IOException e) {
            // Most commonly: interpreter binary not on PATH.
            String msg = e.getMessage() != null ? e.getMessage() : e.toString();
            if (msg.toLowerCase().contains("cannot run program") || msg.toLowerCase().contains("no such file")) {
                return new ExecutionResult("", "Interpreter not found: " + interpreter.get(0), 127, false);
            }
            return new ExecutionResult("", msg, 1, false);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new ExecutionResult("", "Execution interrupted: " + e.getMessage(), 1, false);
        } finally {
            if (tempFile != null) {
                try {
                    Files.deleteIfExists(tempFile);
                } catch (IOException ignored) {
                    // best-effort cleanup
                }
            }
        }
    }

    private static String fileExtension(String language) {
        return switch (language.toLowerCase()) {
            case "python", "python3" -> ".py";
            case "bash", "sh" -> ".sh";
            case "node", "javascript" -> ".js";
            case "ruby" -> ".rb";
            default -> ".txt";
        };
    }
}
