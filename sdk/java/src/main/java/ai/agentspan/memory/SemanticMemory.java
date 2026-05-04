// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.memory;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Long-term memory with similarity-based retrieval.
 *
 * <p>Uses keyword overlap (Jaccard similarity) by default. Plug in a custom {@link MemoryStore}
 * for production use with real vector databases.
 *
 * <pre>{@code
 * SemanticMemory memory = new SemanticMemory();
 * memory.add("User prefers concise answers");
 * memory.add("Project uses Java 17 with Spring Boot");
 *
 * List<MemoryEntry> relevant = memory.search("what language is the project in?", 3);
 * }</pre>
 */
public class SemanticMemory {

    private final MemoryStore store;

    public SemanticMemory() {
        this.store = new InMemoryStore();
    }

    public SemanticMemory(MemoryStore store) {
        this.store = store;
    }

    /** Add a memory entry with the given content. Returns the entry ID. */
    public String add(String content) {
        return add(content, null);
    }

    /** Add a memory entry with content and metadata. Returns the entry ID. */
    public String add(String content, Map<String, Object> metadata) {
        MemoryEntry entry = new MemoryEntry(content, metadata);
        return store.add(entry);
    }

    /** Search for memories relevant to the query. Returns up to {@code topK} results. */
    public List<MemoryEntry> search(String query, int topK) {
        return store.search(query, topK);
    }

    /** Delete a memory entry by ID. */
    public boolean delete(String memoryId) {
        return store.delete(memoryId);
    }

    /** Remove all memories. */
    public void clear() {
        store.clear();
    }

    /** Return all stored memories. */
    public List<MemoryEntry> listAll() {
        return store.listAll();
    }

    /** Format relevant memories as a system prompt injection block. */
    public String formatForPrompt(String query, int topK) {
        List<MemoryEntry> results = search(query, topK);
        if (results.isEmpty()) return "";
        StringBuilder sb = new StringBuilder("[Relevant Memories]\n");
        for (MemoryEntry entry : results) {
            sb.append("- ").append(entry.getContent()).append("\n");
        }
        return sb.toString();
    }

    // ── Default in-memory store using keyword overlap ──────────────────

    static class InMemoryStore extends MemoryStore {
        private final Map<String, MemoryEntry> memories = new LinkedHashMap<>();

        @Override
        public String add(MemoryEntry entry) {
            if (entry.getId() == null || entry.getId().isEmpty()) {
                entry.setId(sha256Short(entry.getContent() + System.currentTimeMillis()));
            }
            if (entry.getCreatedAt() == 0.0) {
                entry.setCreatedAt(System.currentTimeMillis() / 1000.0);
            }
            memories.put(entry.getId(), entry);
            return entry.getId();
        }

        @Override
        public List<MemoryEntry> search(String query, int topK) {
            if (memories.isEmpty()) return new ArrayList<>();
            Set<String> queryWords = tokenize(query);
            List<double[]> scored = new ArrayList<>();
            List<MemoryEntry> entries = new ArrayList<>(memories.values());
            for (int i = 0; i < entries.size(); i++) {
                Set<String> entryWords = tokenize(entries.get(i).getContent());
                double score = jaccard(queryWords, entryWords);
                scored.add(new double[]{score, i});
            }
            scored.sort((a, b) -> Double.compare(b[0], a[0]));
            List<MemoryEntry> result = new ArrayList<>();
            for (int i = 0; i < Math.min(topK, scored.size()); i++) {
                result.add(entries.get((int) scored.get(i)[1]));
            }
            return result;
        }

        @Override
        public boolean delete(String id) {
            return memories.remove(id) != null;
        }

        @Override
        public void clear() {
            memories.clear();
        }

        @Override
        public List<MemoryEntry> listAll() {
            return new ArrayList<>(memories.values());
        }

        private static Set<String> tokenize(String text) {
            if (text == null || text.isEmpty()) return new HashSet<>();
            return new HashSet<>(Arrays.asList(text.toLowerCase().split("\\s+")));
        }

        private static double jaccard(Set<String> a, Set<String> b) {
            if (a.isEmpty() || b.isEmpty()) return 0.0;
            Set<String> intersection = new HashSet<>(a);
            intersection.retainAll(b);
            Set<String> union = new HashSet<>(a);
            union.addAll(b);
            return (double) intersection.size() / union.size();
        }

        private static String sha256Short(String input) {
            try {
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                byte[] hash = md.digest(input.getBytes());
                StringBuilder hex = new StringBuilder();
                for (int i = 0; i < 8; i++) {
                    hex.append(String.format("%02x", hash[i]));
                }
                return hex.toString();
            } catch (Exception e) {
                return Long.toHexString(System.nanoTime());
            }
        }
    }
}
