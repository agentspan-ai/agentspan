// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.execution;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Runs code inside a Docker container for sandboxed execution.
 *
 * <p>Requires Docker to be installed and the Docker daemon to be running.
 *
 * <pre>{@code
 * DockerCodeExecutor executor = new DockerCodeExecutor("python:3.12-slim", "python", 30);
 * ExecutionResult result = executor.execute("import sys; print(sys.version)");
 * }</pre>
 */
public class DockerCodeExecutor extends CodeExecutor {

    private final String image;

    public DockerCodeExecutor(String image) {
        this(image, "python", 30, null);
    }

    public DockerCodeExecutor(String image, String language, int timeout) {
        this(image, language, timeout, null);
    }

    public DockerCodeExecutor(String image, String language, int timeout, String workingDir) {
        super(language, timeout, workingDir);
        this.image = image;
    }

    public String getImage() { return image; }

    @Override
    public ExecutionResult execute(String code) {
        Path tempFile = null;
        try {
            String extension = getExtension(language);
            tempFile = Files.createTempFile("agentspan_code_", extension);
            Files.writeString(tempFile, code);

            String containerPath = "/tmp/code" + extension;
            String interpreter = getInterpreter(language);

            List<String> command = new ArrayList<>(List.of(
                "docker", "run", "--rm",
                "-v", tempFile.toAbsolutePath() + ":" + containerPath + ":ro",
                "--memory", "256m",
                "--cpus", "0.5",
                "--network", "none",
                image,
                interpreter, containerPath
            ));

            ProcessBuilder pb = new ProcessBuilder(command);
            pb.redirectErrorStream(false);
            Process process = pb.start();
            boolean completed = process.waitFor(timeout + 10, TimeUnit.SECONDS);

            if (!completed) {
                process.destroyForcibly();
                return new ExecutionResult("", "Docker execution timed out after " + timeout + "s", 1, true);
            }

            String stdout = new String(process.getInputStream().readAllBytes());
            String stderr = new String(process.getErrorStream().readAllBytes());
            return new ExecutionResult(stdout, stderr, process.exitValue(), false);

        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            return new ExecutionResult("", "Docker execution error: " + e.getMessage(), 1, false);
        } finally {
            if (tempFile != null) {
                try { Files.deleteIfExists(tempFile); } catch (IOException ignored) {}
            }
        }
    }

    private static String getInterpreter(String language) {
        return switch (language.toLowerCase()) {
            case "python" -> "python3";
            case "bash", "sh" -> "bash";
            case "node", "javascript" -> "node";
            case "ruby" -> "ruby";
            default -> language;
        };
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
