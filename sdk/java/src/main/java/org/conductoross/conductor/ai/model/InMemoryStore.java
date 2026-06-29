// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Simple in-memory store using Jaccard keyword overlap for similarity.
 *
 * <p>This is a lightweight fallback when no vector database is available.
 * For production use, plug in a real vector store via {@link MemoryStore}.
 * Mirrors the Python ({@code InMemoryStore}) and C# ({@code InMemoryStore}) reference.
 */
public class InMemoryStore implements MemoryStore {

    private final Map<String, MemoryEntry> memories = new LinkedHashMap<>();

    @Override
    public String add(MemoryEntry entry) {
        if (entry.getId() == null || entry.getId().isEmpty()) {
            entry.setId(generateId(entry.getContent()));
        }
        if (entry.getCreatedAt() == 0L) {
            entry.setCreatedAt(System.currentTimeMillis());
        }
        memories.put(entry.getId(), entry);
        return entry.getId();
    }

    @Override
    public List<MemoryEntry> search(String query, int topK) {
        if (memories.isEmpty()) {
            return new ArrayList<>();
        }
        Set<String> queryWords = tokenize(query);

        List<MemoryEntry> scoredEntries = new ArrayList<>(memories.values());
        Map<String, Double> scores = new LinkedHashMap<>();
        for (MemoryEntry entry : scoredEntries) {
            scores.put(entry.getId(), jaccard(queryWords, tokenize(entry.getContent())));
        }

        return scoredEntries.stream()
                .filter(e -> scores.get(e.getId()) > 0.0)
                .sorted(Comparator.comparingDouble((MemoryEntry e) -> scores.get(e.getId()))
                        .reversed())
                .limit(Math.max(0, topK))
                .collect(java.util.stream.Collectors.toList());
    }

    @Override
    public boolean delete(String memoryId) {
        return memories.remove(memoryId) != null;
    }

    @Override
    public void clear() {
        memories.clear();
    }

    @Override
    public List<MemoryEntry> listAll() {
        return new ArrayList<>(memories.values());
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private static Set<String> tokenize(String text) {
        Set<String> out = new HashSet<>();
        if (text == null) return out;
        for (String w : text.toLowerCase().split("\\s+")) {
            if (!w.isEmpty()) out.add(w);
        }
        return out;
    }

    private static double jaccard(Set<String> a, Set<String> b) {
        if (a.isEmpty() || b.isEmpty()) return 0.0;
        Set<String> intersection = new HashSet<>(a);
        intersection.retainAll(b);
        Set<String> union = new HashSet<>(a);
        union.addAll(b);
        return union.isEmpty() ? 0.0 : (double) intersection.size() / union.size();
    }

    private static String generateId(String content) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest((content + System.currentTimeMillis()).getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.substring(0, 16);
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 is always available on the JVM; fall back to a content hash.
            return Integer.toHexString((content + System.currentTimeMillis()).hashCode());
        }
    }
}
