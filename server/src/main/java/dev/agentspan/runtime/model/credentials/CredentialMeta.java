/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.model.credentials;

import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonProperty;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Credential metadata returned in list and single-item responses.
 * The plaintext value is NEVER included — only a partial display.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CredentialMeta {
    @JsonProperty("name")
    private String name;

    @JsonProperty("partial")
    private String partial; // first4 + "..." + last4

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;
}
