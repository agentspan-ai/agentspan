// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.memory;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** A single semantic memory entry. */
public class MemoryEntry {

    private String id;
    private String content;
    private Map<String, Object> metadata;
    private List<Double> embedding;
    private double createdAt;

    public MemoryEntry() {
        this.metadata = new HashMap<>();
        this.createdAt = System.currentTimeMillis() / 1000.0;
    }

    public MemoryEntry(String content) {
        this();
        this.content = content;
    }

    public MemoryEntry(String content, Map<String, Object> metadata) {
        this();
        this.content = content;
        this.metadata = metadata != null ? metadata : new HashMap<>();
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }

    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }

    public List<Double> getEmbedding() { return embedding; }
    public void setEmbedding(List<Double> embedding) { this.embedding = embedding; }

    public double getCreatedAt() { return createdAt; }
    public void setCreatedAt(double createdAt) { this.createdAt = createdAt; }
}
