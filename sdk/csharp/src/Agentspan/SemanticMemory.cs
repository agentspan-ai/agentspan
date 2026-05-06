// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Security.Cryptography;
using System.Text;

namespace Agentspan;

/// <summary>A single memory entry stored in a <see cref="MemoryStore"/>.</summary>
public sealed class MemoryEntry
{
    public string Id        { get; init; } = "";
    public string Content   { get; init; } = "";
    public Dictionary<string, object> Metadata { get; init; } = new();
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;
}

/// <summary>Abstract backend for memory storage.</summary>
public abstract class MemoryStore
{
    public abstract string            Add(MemoryEntry entry);
    public abstract List<MemoryEntry> Search(string query, int topK = 5);
    public abstract bool              Delete(string id);
    public abstract void              Clear();
    public abstract List<MemoryEntry> ListAll();
}

/// <summary>
/// In-memory store using Jaccard keyword overlap for similarity.
/// Lightweight fallback — for production, implement <see cref="MemoryStore"/> with a vector DB.
/// </summary>
public sealed class InMemoryStore : MemoryStore
{
    private readonly Dictionary<string, MemoryEntry> _memories = new();

    public override string Add(MemoryEntry entry)
    {
        var id = string.IsNullOrEmpty(entry.Id)
            ? GenerateId(entry.Content)
            : entry.Id;

        var stored = new MemoryEntry
        {
            Id        = id,
            Content   = entry.Content,
            Metadata  = entry.Metadata,
            CreatedAt = entry.CreatedAt == default ? DateTimeOffset.UtcNow : entry.CreatedAt,
        };
        _memories[id] = stored;
        return id;
    }

    public override List<MemoryEntry> Search(string query, int topK = 5)
    {
        if (_memories.Count == 0) return [];

        var queryWords = Tokenize(query);
        var scored = new List<(double Score, MemoryEntry Entry)>();

        foreach (var entry in _memories.Values)
        {
            var entryWords = Tokenize(entry.Content);
            double score   = JaccardSimilarity(queryWords, entryWords);
            scored.Add((score, entry));
        }

        return scored
            .Where(x => x.Score > 0)
            .OrderByDescending(x => x.Score)
            .Take(topK)
            .Select(x => x.Entry)
            .ToList();
    }

    public override bool              Delete(string id)       => _memories.Remove(id);
    public override void              Clear()                 => _memories.Clear();
    public override List<MemoryEntry> ListAll()               => [.. _memories.Values];

    // ── helpers ──────────────────────────────────────────────────────

    private static HashSet<string> Tokenize(string text)
        => [.. text.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries)];

    private static double JaccardSimilarity(HashSet<string> a, HashSet<string> b)
    {
        if (a.Count == 0 || b.Count == 0) return 0.0;
        int intersection = a.Count(w => b.Contains(w));
        int union        = a.Union(b).Count();
        return union == 0 ? 0.0 : (double)intersection / union;
    }

    private static string GenerateId(string content)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(content + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()));
        return Convert.ToHexString(hash)[..16].ToLowerInvariant();
    }
}

/// <summary>
/// High-level semantic memory for agents with similarity-based retrieval.
/// Relevant memories are injected into prompts via <see cref="GetContext"/>.
/// </summary>
public sealed class SemanticMemory(MemoryStore? store = null, int maxResults = 5, string? sessionId = null)
{
    private readonly MemoryStore _store = store ?? new InMemoryStore();

    public int     MaxResults { get; } = maxResults;
    public string? SessionId  { get; } = sessionId;

    /// <summary>Add a memory entry. Returns the entry ID.</summary>
    public string Add(string content, Dictionary<string, object>? metadata = null)
    {
        var meta = metadata is null ? new Dictionary<string, object>() : new Dictionary<string, object>(metadata);
        if (SessionId is not null) meta["session_id"] = SessionId;

        return _store.Add(new MemoryEntry { Content = content, Metadata = meta });
    }

    /// <summary>Search for relevant memories and return their content strings.</summary>
    public List<string> Search(string query, int? topK = null)
        => _store.Search(query, topK ?? MaxResults).Select(e => e.Content).ToList();

    /// <summary>Search and return full <see cref="MemoryEntry"/> objects.</summary>
    public List<MemoryEntry> SearchEntries(string query, int? topK = null)
        => _store.Search(query, topK ?? MaxResults);

    /// <summary>Delete a memory by ID.</summary>
    public bool Delete(string id) => _store.Delete(id);

    /// <summary>Delete all memories.</summary>
    public void Clear() => _store.Clear();

    /// <summary>Return all stored memories.</summary>
    public List<MemoryEntry> ListAll() => _store.ListAll();

    /// <summary>
    /// Return relevant memories formatted for injection into an agent prompt.
    /// </summary>
    public string GetContext(string query)
    {
        var memories = Search(query);
        if (memories.Count == 0) return "";

        var lines = new List<string> { "Relevant context from memory:" };
        for (int i = 0; i < memories.Count; i++)
            lines.Add($"  {i + 1}. {memories[i]}");
        return string.Join("\n", lines);
    }

    public override string ToString()
        => $"SemanticMemory(entries={_store.ListAll().Count}, maxResults={MaxResults})";
}
