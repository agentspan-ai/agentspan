// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A single memory entry stored in a {@link MemoryStore}.
 *
 * <p>Mirrors the Python ({@code MemoryEntry}) and C# ({@code MemoryEntry}) reference types.
 */
public class MemoryEntry {

    private String id;
    private final String content;
    private final Map<String, Object> metadata;
    private long createdAt;

    public MemoryEntry(String content) {
        this(content, new LinkedHashMap<>());
    }

    public MemoryEntry(String content, Map<String, Object> metadata) {
        this.id = "";
        this.content = content != null ? content : "";
        this.metadata = metadata != null ? metadata : new LinkedHashMap<>();
        this.createdAt = 0L;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getContent() {
        return content;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    /** Unix timestamp (millis) when the memory was created, or {@code 0} if unset. */
    public long getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(long createdAt) {
        this.createdAt = createdAt;
    }
}
