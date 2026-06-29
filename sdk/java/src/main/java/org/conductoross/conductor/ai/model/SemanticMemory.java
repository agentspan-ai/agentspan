// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * High-level semantic memory for agents with similarity-based retrieval.
 *
 * <p>Manages long-term memory backed by a {@link MemoryStore} (defaulting to a
 * keyword-overlap {@link InMemoryStore}). Relevant memories can be injected into
 * an agent's prompt via {@link #getContext(String)}.
 *
 * <p>Mirrors the Python ({@code semantic_memory.py}) and C# ({@code SemanticMemory.cs})
 * reference. This is a client-side helper — it is not serialized into the wire
 * {@code AgentConfig}.
 *
 * <pre>{@code
 * SemanticMemory memory = new SemanticMemory();
 * memory.add("User prefers concise answers", Map.of("type", "preference"));
 * memory.add("Project uses Java 17 with Gradle", Map.of("type", "fact"));
 *
 * String context = memory.getContext("How should I answer?");
 * }</pre>
 */
public class SemanticMemory {

    private final MemoryStore store;
    private final int maxResults;
    private final String sessionId;

    /** Default semantic memory: in-memory store, max 5 results, no session scope. */
    public SemanticMemory() {
        this(null, 5, null);
    }

    /**
     * @param store      backend store, or {@code null} for an {@link InMemoryStore}
     * @param maxResults maximum memories to retrieve per query (default 5)
     * @param sessionId  optional session id scoping memories (stored in metadata)
     */
    public SemanticMemory(MemoryStore store, int maxResults, String sessionId) {
        this.store = store != null ? store : new InMemoryStore();
        this.maxResults = maxResults;
        this.sessionId = sessionId;
    }

    /** Add a memory. Returns the entry ID. */
    public String add(String content) {
        return add(content, null);
    }

    /** Add a memory with metadata. Returns the entry ID. */
    public String add(String content, Map<String, Object> metadata) {
        Map<String, Object> meta = metadata != null ? new LinkedHashMap<>(metadata) : new LinkedHashMap<>();
        if (sessionId != null) {
            meta.put("session_id", sessionId);
        }
        return store.add(new MemoryEntry(content, meta));
    }

    /** Search for relevant memories, returning content strings (most relevant first). */
    public List<String> search(String query) {
        return search(query, maxResults);
    }

    /** Search for relevant memories, capped at {@code topK} results. */
    public List<String> search(String query, int topK) {
        return store.search(query, topK).stream().map(MemoryEntry::getContent).collect(Collectors.toList());
    }

    /** Search and return full {@link MemoryEntry} objects. */
    public List<MemoryEntry> searchEntries(String query) {
        return store.search(query, maxResults);
    }

    /** Search and return full {@link MemoryEntry} objects, capped at {@code topK}. */
    public List<MemoryEntry> searchEntries(String query, int topK) {
        return store.search(query, topK);
    }

    /** Delete a memory by ID. */
    public boolean delete(String memoryId) {
        return store.delete(memoryId);
    }

    /** Delete all memories. */
    public void clear() {
        store.clear();
    }

    /** Return all stored memories. */
    public List<MemoryEntry> listAll() {
        return store.listAll();
    }

    public int getMaxResults() {
        return maxResults;
    }

    public String getSessionId() {
        return sessionId;
    }

    /**
     * Return relevant memories formatted for injection into an agent prompt,
     * or an empty string if there are none.
     */
    public String getContext(String query) {
        List<String> memories = search(query);
        if (memories.isEmpty()) {
            return "";
        }
        List<String> lines = new ArrayList<>();
        lines.add("Relevant context from memory:");
        for (int i = 0; i < memories.size(); i++) {
            lines.add("  " + (i + 1) + ". " + memories.get(i));
        }
        return String.join("\n", lines);
    }

    @Override
    public String toString() {
        return "SemanticMemory(entries=" + store.listAll().size() + ", maxResults=" + maxResults + ")";
    }
}
