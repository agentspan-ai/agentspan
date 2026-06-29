// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.List;

/**
 * Abstract backend for memory storage.
 *
 * <p>Implement this to integrate with external vector databases
 * (Pinecone, Weaviate, ChromaDB, etc.) or services like Mem0.
 * Mirrors the Python ({@code MemoryStore}) and C# ({@code MemoryStore}) interfaces.
 */
public interface MemoryStore {

    /** Store a memory entry. Returns the entry ID. */
    String add(MemoryEntry entry);

    /** Search for memories similar to the query, most relevant first. */
    List<MemoryEntry> search(String query, int topK);

    /** Delete a memory entry by ID. Returns {@code true} if it existed. */
    boolean delete(String memoryId);

    /** Delete all memories. */
    void clear();

    /** Return all stored memories. */
    List<MemoryEntry> listAll();
}
