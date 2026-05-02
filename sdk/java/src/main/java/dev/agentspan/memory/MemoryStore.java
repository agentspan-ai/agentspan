// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.memory;

import java.util.List;

/**
 * Abstract interface for a memory storage backend.
 *
 * <p>Implement this to integrate with external vector databases (Pinecone, Weaviate, ChromaDB)
 * or services. The default {@link SemanticMemory} uses an in-memory keyword-overlap store.
 */
public abstract class MemoryStore {

    /** Store a memory entry. Returns the entry ID. */
    public abstract String add(MemoryEntry entry);

    /** Search for memories similar to the query. Returns up to {@code topK} results. */
    public abstract List<MemoryEntry> search(String query, int topK);

    /** Delete a memory entry by ID. Returns {@code true} if deleted. */
    public abstract boolean delete(String memoryId);

    /** Delete all memories. */
    public abstract void clear();

    /** Return all stored memories. */
    public abstract List<MemoryEntry> listAll();
}
