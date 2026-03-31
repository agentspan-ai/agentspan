// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Example 16 — Credentials on Tools
 *
 * <p>Demonstrates the {@code credentials} field on {@code @Tool}. Declared
 * credential names are resolved by the server before each tool call and
 * injected as environment variables into the worker. This keeps secrets
 * out of the agent config and parent process environment.
 *
 * <p>Setup (one-time, via CLI):
 * <pre>
 *   agentspan credentials set --name GITHUB_TOKEN
 * </pre>
 *
 * <p>Without credentials the tool falls back to unauthenticated GitHub API
 * calls (rate-limited to 60 req/hr but functional for demos).
 */
public class Example16CredentialsTool {

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();

    static class GithubTools {

        @Tool(
            name = "list_github_repos",
            description = "List public repositories for a GitHub username (most recently updated)",
            credentials = {"GITHUB_TOKEN"}
        )
        public Map<String, Object> listGithubRepos(String username, int limit) {
            try {
                int n = limit > 0 ? Math.min(limit, 10) : 5;
                // GITHUB_TOKEN is injected as an env var by the server when credentials are set
                String token = System.getenv("GITHUB_TOKEN");
                HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                    .uri(URI.create("https://api.github.com/users/" + username
                        + "/repos?per_page=" + n + "&sort=updated"))
                    .timeout(Duration.ofSeconds(10))
                    .header("Accept", "application/vnd.github+json")
                    .header("User-Agent", "agentspan-java-example/1.0");
                if (token != null && !token.isEmpty()) {
                    reqBuilder.header("Authorization", "Bearer " + token);
                }
                String body = HTTP_CLIENT.send(reqBuilder.build(),
                    HttpResponse.BodyHandlers.ofString()).body();

                // Parse minimally: count repos and extract names
                int count = countOccurrences(body, "\"full_name\"");
                String preview = body.length() > 300 ? body.substring(0, 300) + "..." : body;
                return Map.of(
                    "username", username,
                    "repos_found", count,
                    "authenticated", token != null && !token.isEmpty(),
                    "preview", preview
                );
            } catch (IOException | InterruptedException e) {
                return Map.of("username", username, "error", e.getMessage());
            }
        }

        @Tool(
            name = "get_github_user",
            description = "Get profile information for a GitHub user",
            credentials = {"GITHUB_TOKEN"}
        )
        public Map<String, Object> getGithubUser(String username) {
            try {
                String token = System.getenv("GITHUB_TOKEN");
                HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                    .uri(URI.create("https://api.github.com/users/" + username))
                    .timeout(Duration.ofSeconds(10))
                    .header("Accept", "application/vnd.github+json")
                    .header("User-Agent", "agentspan-java-example/1.0");
                if (token != null && !token.isEmpty()) {
                    reqBuilder.header("Authorization", "Bearer " + token);
                }
                String body = HTTP_CLIENT.send(reqBuilder.build(),
                    HttpResponse.BodyHandlers.ofString()).body();

                // Extract a few key fields
                String name = extractField(body, "\"name\":");
                String login = extractField(body, "\"login\":");
                String publicRepos = extractField(body, "\"public_repos\":");
                String followers = extractField(body, "\"followers\":");

                return Map.of(
                    "login", login,
                    "name", name,
                    "public_repos", publicRepos,
                    "followers", followers,
                    "authenticated", token != null && !token.isEmpty()
                );
            } catch (IOException | InterruptedException e) {
                return Map.of("username", username, "error", e.getMessage());
            }
        }
    }

    private static String extractField(String json, String key) {
        int idx = json.indexOf(key);
        if (idx < 0) return "unknown";
        String after = json.substring(idx + key.length()).trim();
        if (after.startsWith("\"")) {
            int end = after.indexOf("\"", 1);
            return end > 0 ? after.substring(1, end) : "unknown";
        }
        return after.split("[,}\\]]")[0].trim();
    }

    private static int countOccurrences(String text, String pattern) {
        int count = 0, idx = 0;
        while ((idx = text.indexOf(pattern, idx)) >= 0) { count++; idx += pattern.length(); }
        return count;
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new GithubTools());

        Agent agent = Agent.builder()
            .name("github_agent")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions(
                "You are a GitHub assistant. You can look up GitHub users and list "
                + "their repositories. Use the available tools to answer questions.")
            .build();

        AgentResult result = Agentspan.run(agent,
            "Look up the GitHub user 'torvalds' and show their most recent 3 repositories.");
        result.printResult();

        Agentspan.shutdown();
    }
}
