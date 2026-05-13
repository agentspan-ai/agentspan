// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.execution;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Runs code in a local subprocess (no sandbox).
 *
 * <pre>{@code
 * LocalCodeExecutor executor = new LocalCodeExecutor("python", 30);
 * ExecutionResult result = executor.execute("print('hello world')");
 * System.out.println(result.getOutput()); // "hello world"
 * }</pre>
 */
public class LocalCodeExecutor extends CodeExecutor {

    private static final Map<String, String> INTERPRETERS = Map.of(
        "python", "python3",
        "bash", "bash",
        "sh", "bash",
        "node", "node",
        "javascript", "node",
        "ruby", "ruby"
    );

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
        String interpreter = INTERPRETERS.getOrDefault(language.toLowerCase(), language);
        Path tempFile = null;
        try {
            String extension = getExtension(language);
            tempFile = Files.createTempFile("agentspan_code_", extension);
            Files.writeString(tempFile, code);

            List<String> command = new ArrayList<>();
            command.add(interpreter);
            command.add(tempFile.toAbsolutePath().toString());

            ProcessBuilder pb = new ProcessBuilder(command);
            pb.redirectErrorStream(false);
            if (workingDir != null) pb.directory(new File(workingDir));

            Process process = pb.start();
            boolean completed = process.waitFor(timeout, TimeUnit.SECONDS);

            if (!completed) {
                process.destroyForcibly();
                return new ExecutionResult("", "Execution timed out after " + timeout + "s", 1, true);
            }

            String stdout = new String(process.getInputStream().readAllBytes());
            String stderr = new String(process.getErrorStream().readAllBytes());
            int exitCode = process.exitValue();
            return new ExecutionResult(stdout, stderr, exitCode, false);

        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            return new ExecutionResult("", "Execution error: " + e.getMessage(), 1, false);
        } finally {
            if (tempFile != null) {
                try { Files.deleteIfExists(tempFile); } catch (IOException ignored) {}
            }
        }
    }

    private static String getExtension(String language) {
        return switch (language.toLowerCase()) {
            case "python" -> ".py";
            case "bash", "sh" -> ".sh";
            case "node", "javascript" -> ".js";
            case "ruby" -> ".rb";
            default -> ".tmp";
        };
    }
}
