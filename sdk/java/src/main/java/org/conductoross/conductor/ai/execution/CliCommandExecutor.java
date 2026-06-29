// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.execution;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/**
 * Local executor for the auto-injected {@code run_command} CLI tool.
 *
 * <p>Mirrors the Python ({@code cli_config.py}), TypeScript ({@code cli-config.ts})
 * and C# ({@code CliTool}) implementations: tokenize the command line, validate
 * the executable against the whitelist, then run it via {@link ProcessBuilder}.
 *
 * <p>LLMs routinely pack the whole command line into the {@code command} field
 * (e.g. {@code "gh repo list --limit 5"}). {@link #tokenize(String)} splits it so
 * validation keys off the executable and execution gets a proper argv.
 *
 * <p>Failures (whitelist rejection, timeout, command-not-found, non-zero exit)
 * are returned as an error result map rather than thrown — matching the Java
 * code-execution worker and the C# {@code CliTool}.
 */
public final class CliCommandExecutor {

    private CliCommandExecutor() {}

    // ── Tokenization ──────────────────────────────────────────────────────

    /**
     * Tokenize a command line into argv, honoring single and double quotes.
     * Falls back to plain whitespace splitting if quotes are unbalanced.
     */
    public static List<String> tokenize(String command) {
        List<String> tokens = new ArrayList<>();
        if (command == null) return tokens;

        StringBuilder current = new StringBuilder();
        boolean hasCurrent = false;
        char quote = 0;

        for (int i = 0; i < command.length(); i++) {
            char ch = command.charAt(i);
            if (quote != 0) {
                if (ch == quote) {
                    quote = 0;
                } else {
                    current.append(ch);
                }
            } else if (ch == '"' || ch == '\'') {
                quote = ch;
                hasCurrent = true;
            } else if (Character.isWhitespace(ch)) {
                if (hasCurrent) {
                    tokens.add(current.toString());
                    current.setLength(0);
                    hasCurrent = false;
                }
            } else {
                current.append(ch);
                hasCurrent = true;
            }
        }

        if (quote != 0) {
            // Unbalanced quotes — fall back to naive whitespace split.
            tokens.clear();
            for (String t : command.trim().split("\\s+")) {
                if (!t.isEmpty()) tokens.add(t);
            }
            return tokens;
        }
        if (hasCurrent) tokens.add(current.toString());
        return tokens;
    }

    // ── Validation ────────────────────────────────────────────────────────

    /** Basename of the executable (strip {@code /usr/bin/git} → {@code git}). */
    private static String basename(String exe) {
        int idx = Math.max(exe.lastIndexOf('/'), exe.lastIndexOf('\\'));
        return idx >= 0 ? exe.substring(idx + 1) : exe;
    }

    /**
     * Validate the executable against the whitelist. Empty whitelist permits all.
     *
     * @throws IllegalArgumentException if the executable is not in the whitelist
     */
    static void validate(String executable, List<String> allowedCommands) {
        if (allowedCommands == null || allowedCommands.isEmpty()) {
            return; // no restrictions
        }
        String base = basename(executable);
        if (!allowedCommands.contains(base)) {
            List<String> sorted = new ArrayList<>(allowedCommands);
            Collections.sort(sorted);
            throw new IllegalArgumentException(
                    "Command '" + base + "' is not allowed. Allowed commands: " + String.join(", ", sorted));
        }
    }

    // ── Execution ─────────────────────────────────────────────────────────

    /** Convenience overload: extract fields from the worker input map. */
    public static Map<String, Object> run(Map<String, Object> input, CliConfig config) {
        String command = asString(input.get("command"));
        List<String> args = asStringList(input.get("args"));
        String cwd = asString(input.get("cwd"));
        boolean shell = Boolean.TRUE.equals(input.get("shell"));
        return run(
                command,
                args,
                cwd,
                shell,
                config.getAllowedCommands(),
                config.getTimeout(),
                config.getWorkingDir(),
                config.isAllowShell());
    }

    /**
     * Execute a command. Returns a map with {@code status}, {@code exit_code},
     * {@code stdout} and {@code stderr}.
     */
    public static Map<String, Object> run(
            String command,
            List<String> args,
            String cwd,
            boolean shell,
            List<String> allowedCommands,
            int timeout,
            String workingDir,
            boolean allowShell) {

        if (command == null || command.isBlank()) {
            return error("No command provided.");
        }

        // Models frequently pass the entire command line as `command`
        // (e.g. "gh repo list --limit 5") rather than splitting executable/args.
        List<String> tokens = tokenize(command);
        if (tokens.isEmpty()) {
            return error("No command provided.");
        }
        String executable = tokens.get(0);

        // Validate against whitelist (on the executable).
        try {
            validate(executable, allowedCommands);
        } catch (IllegalArgumentException e) {
            return error(e.getMessage());
        }

        // Shell gate.
        if (shell && !allowShell) {
            return error("Shell mode is disabled for this agent. Do not set shell=true.");
        }

        int effectiveTimeout = timeout > 0 ? timeout : 30;

        // Merge any args embedded in the command line with the explicit args list.
        List<String> argv = new ArrayList<>(tokens.subList(1, tokens.size()));
        if (args != null) {
            for (String a : args) argv.add(a);
        }

        String effectiveCwd = (cwd != null && !cwd.isEmpty())
                ? cwd
                : (workingDir != null && !workingDir.isEmpty() ? workingDir : null);

        // Build the process command.
        List<String> fullCmd = new ArrayList<>();
        if (shell) {
            StringBuilder cmdStr = new StringBuilder(shellQuote(executable));
            for (String a : argv) cmdStr.append(' ').append(shellQuote(a));
            if (isWindows()) {
                fullCmd.add("cmd.exe");
                fullCmd.add("/c");
            } else {
                fullCmd.add("/bin/sh");
                fullCmd.add("-c");
            }
            fullCmd.add(cmdStr.toString());
        } else {
            fullCmd.add(executable);
            fullCmd.addAll(argv);
        }

        ProcessBuilder pb = new ProcessBuilder(fullCmd);
        if (effectiveCwd != null) pb.directory(new File(effectiveCwd));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Process process;
            try {
                process = pb.start();
            } catch (IOException e) {
                // ProcessBuilder.start throws IOException when the executable
                // cannot be found (e.g. "error=2, No such file or directory").
                return error("Command not found: " + executable);
            }

            Future<String> stdoutF = pool.submit(() -> readStream(process.getInputStream()));
            Future<String> stderrF = pool.submit(() -> readStream(process.getErrorStream()));

            boolean finished = process.waitFor(effectiveTimeout, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                return error("Command timed out after " + effectiveTimeout + "s");
            }

            String stdout = stdoutF.get(2, TimeUnit.SECONDS);
            String stderr = stderrF.get(2, TimeUnit.SECONDS);
            int code = process.exitValue();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", code == 0 ? "success" : "error");
            result.put("exit_code", code);
            result.put("stdout", stdout);
            result.put("stderr", stderr);
            return result;
        } catch (Exception e) {
            return error(e.getMessage() != null ? e.getMessage() : e.toString());
        } finally {
            pool.shutdownNow();
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private static Map<String, Object> error(String stderr) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("status", "error");
        m.put("stdout", "");
        m.put("stderr", stderr);
        return m;
    }

    private static String readStream(InputStream is) {
        try {
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        }
    }

    /** Shell-quote a token (mirrors Python {@code shlex.quote}). */
    private static String shellQuote(String s) {
        if (s.isEmpty()) return "''";
        // Safe characters need no quoting.
        if (s.matches("[a-zA-Z0-9_@%+=:,./-]+")) return s;
        return "'" + s.replace("'", "'\\''") + "'";
    }

    private static boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase().contains("win");
    }

    private static String asString(Object v) {
        return v instanceof String ? (String) v : null;
    }

    private static List<String> asStringList(Object v) {
        if (v == null) return Collections.emptyList();
        if (v instanceof List<?> list) {
            List<String> out = new ArrayList<>(list.size());
            for (Object o : list) out.add(String.valueOf(o));
            return out;
        }
        return List.of(String.valueOf(v));
    }
}
