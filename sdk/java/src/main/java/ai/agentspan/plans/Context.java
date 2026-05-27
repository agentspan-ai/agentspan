// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.plans;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A reference document made available to the PLAN_EXECUTE planner.
 *
 * <p>Appended to the planner's user prompt as a {@code ## Reference Context}
 * block on every planner invocation. Use to ground the planner in
 * domain-specific rules / processes / edge cases that a static
 * {@code instructions} string can't capture — onboarding playbooks,
 * KYC rules, compliance thresholds, etc.
 *
 * <p>Exactly one of {@code text} or {@code url} must be set:
 *
 * <ul>
 *   <li>{@code text}: inlined verbatim — best for short, stable rules.</li>
 *   <li>{@code url}: HTTP GET on every planner run (no compile-time fetch,
 *       no cache — doc edits go live without recompile). Optional
 *       {@code headers} carry credential placeholders in the
 *       {@code ${CRED_NAME}} shape; the server escapes them to
 *       {@code #{CRED_NAME}} so Conductor's templater doesn't consume
 *       them and the runtime credential resolver fills them in at
 *       request time — same auth pipeline as HTTP tool headers.</li>
 * </ul>
 *
 * <p>{@code required=false} substitutes a {@code [doc unavailable]} marker
 * on fetch failure instead of failing the workflow; {@code maxBytes}
 * (default 16384) truncates large responses with a
 * {@code [doc truncated]} marker.
 *
 * <p>Mirrors the Python {@code Context} dataclass and TypeScript
 * {@code Context} class; same wire shape produced by {@link #toJson()}.
 */
public final class Context {
    private final String text;
    private final String url;
    private final Map<String, String> headers;
    private final boolean required;
    private final int maxBytes;

    private Context(Builder b) {
        if ((b.text == null) == (b.url == null)) {
            throw new IllegalArgumentException("Context: exactly one of text or url must be set");
        }
        this.text = b.text;
        this.url = b.url;
        this.headers = b.headers;
        this.required = b.required;
        this.maxBytes = b.maxBytes;
    }

    /** Shorthand: inline-text entry. */
    public static Context text(String text) {
        return builder().text(text).build();
    }

    /** Shorthand: URL entry with all defaults (required=true, maxBytes=16384). */
    public static Context url(String url) {
        return builder().url(url).build();
    }

    public static Builder builder() {
        return new Builder();
    }

    public String getText() {
        return text;
    }

    public String getUrl() {
        return url;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    public boolean isRequired() {
        return required;
    }

    public int getMaxBytes() {
        return maxBytes;
    }

    /**
     * Wire format the server's MultiAgentCompiler consumes. Defaults
     * are omitted so the payload stays tight for the common
     * text-only / minimal-URL case.
     */
    public Map<String, Object> toJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        if (text != null) {
            out.put("text", text);
        }
        if (url != null) {
            out.put("url", url);
            if (headers != null && !headers.isEmpty()) {
                out.put("headers", new LinkedHashMap<>(headers));
            }
            if (!required) {
                out.put("required", false);
            }
            if (maxBytes != 16384) {
                out.put("maxBytes", maxBytes);
            }
        }
        return out;
    }

    public static final class Builder {
        private String text;
        private String url;
        private Map<String, String> headers;
        private boolean required = true;
        private int maxBytes = 16384;

        public Builder text(String text) {
            this.text = text;
            return this;
        }

        public Builder url(String url) {
            this.url = url;
            return this;
        }

        public Builder headers(Map<String, String> headers) {
            this.headers = headers != null ? new LinkedHashMap<>(headers) : null;
            return this;
        }

        public Builder header(String name, String value) {
            if (this.headers == null) {
                this.headers = new LinkedHashMap<>();
            }
            this.headers.put(name, value);
            return this;
        }

        public Builder required(boolean required) {
            this.required = required;
            return this;
        }

        public Builder maxBytes(int maxBytes) {
            this.maxBytes = maxBytes;
            return this;
        }

        public Context build() {
            return new Context(this);
        }
    }
}
