/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Single authority for credential resolution across all call paths.
 *
 * <p>Two forms of name accepted:
 * <ul>
 *   <li><strong>Flat:</strong> {@code GITHUB_TOKEN} — direct store lookup.</li>
 *   <li><strong>Dotted (JSONPath):</strong> {@code GCP_SVC.project_id}, {@code BLOB.auth.oauth.client_id} —
 *       resolves the base name ({@code GCP_SVC}), parses the stored value as JSON,
 *       and walks the remaining dotted path to extract a field. Mirrors Conductor's
 *       {@code ${workflow.secrets.NAME.path}} convention.</li>
 * </ul>
 *
 * <p>Returns {@code null} when (a) the base credential isn't in the store, (b) the base
 * value isn't valid JSON when a dotted path was requested, or (c) the path doesn't
 * resolve to a field. Non-string leaves (numbers, booleans, nested objects) are
 * returned in their JSON representation so callers (HTTP placeholder substitution,
 * MCP header rewriting) can interpolate them as strings.</p>
 *
 * <p><strong>Constraint:</strong> dotted resolution always splits on the first
 * {@code .}. If a credential name itself contains a dot, dotted resolution will not
 * find it — store such secrets under dot-free names.</p>
 *
 * <p>No env-var fallback — the store is the source of truth. The SDK applies its
 * own {@code os.environ} fallback when {@code secret_strict_mode=false}.</p>
 */
@Service
public class CredentialResolutionService {

    private static final Logger log = LoggerFactory.getLogger(CredentialResolutionService.class);

    private final CredentialStoreProvider storeProvider;
    private final ObjectMapper mapper = new ObjectMapper();

    public CredentialResolutionService(CredentialStoreProvider storeProvider) {
        this.storeProvider = storeProvider;
    }

    /**
     * Resolve a credential name for a user. Supports dotted JSONPath into JSON-valued
     * secrets — see class javadoc.
     *
     * @return the value (extracted scalar or full JSON), or null if not found
     */
    public String resolve(String userId, String name) {
        int dot = name.indexOf('.');
        if (dot < 0) {
            String value = storeProvider.get(userId, name);
            if (value == null) log.debug("Credential '{}' not found for user '{}'", name, userId);
            return value;
        }

        String base = name.substring(0, dot);
        String path = name.substring(dot + 1);
        String json = storeProvider.get(userId, base);
        if (json == null) {
            log.debug("Base credential '{}' for path '{}' not found for user '{}'", base, path, userId);
            return null;
        }
        return extractByDottedPath(json, path);
    }

    /**
     * Walk a dotted path through a JSON document. Returns the leaf as a string
     * (text nodes unquoted; everything else as compact JSON). Returns null if the
     * input isn't valid JSON or the path doesn't resolve.
     */
    private String extractByDottedPath(String json, String dottedPath) {
        JsonNode node;
        try {
            node = mapper.readTree(json);
        } catch (Exception e) {
            log.debug("Credential value is not JSON; cannot extract path '{}': {}", dottedPath, e.toString());
            return null;
        }
        for (String segment : dottedPath.split("\\.")) {
            if (node == null) return null;
            node = node.get(segment);
        }
        if (node == null || node.isMissingNode()) return null;
        return node.isTextual() ? node.asText() : node.toString();
    }

    public static class CredentialNotFoundException extends RuntimeException {
        public CredentialNotFoundException(String name) {
            super("Secret not found: " + name);
        }
    }
}
