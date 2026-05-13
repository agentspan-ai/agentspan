// ── Memory types and classes ─────────────────────────────

/**
 * A single entry stored in a MemoryStore.
 */
export interface MemoryEntry {
  id: string;
  content: string;
  metadata?: Record<string, unknown>;
  timestamp: number;
}

/**
 * Interface for pluggable memory storage backends.
 */
export interface MemoryStore {
  add(entry: Omit<MemoryEntry, "id"> & { id?: string }): string;
  search(query: string, topK: number): MemoryEntry[];
  delete(id: string): void;
  clear(): void;
  listAll(): MemoryEntry[];
}

// ── Chat message type ───────────────────────────────────

interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content?: string;
  name?: string;
  args?: unknown;
  result?: unknown;
}

// ── ConversationMemory ──────────────────────────────────

/**
 * Conversation memory that tracks chat messages with optional windowing.
 *
 * When `maxMessages` is set, the oldest non-system messages are trimmed
 * so total count stays within the limit. System messages are ALWAYS preserved.
 */
export class ConversationMemory {
  readonly maxMessages?: number;
  private messages: ChatMessage[] = [];

  constructor(options?: { maxMessages?: number }) {
    this.maxMessages = options?.maxMessages;
  }

  addUserMessage(content: string): void {
    this.messages.push({ role: "user", content });
  }

  addAssistantMessage(content: string): void {
    this.messages.push({ role: "assistant", content });
  }

  addSystemMessage(content: string): void {
    this.messages.push({ role: "system", content });
  }

  addToolCall(name: string, args: unknown): void {
    this.messages.push({ role: "tool", name, args });
  }

  addToolResult(name: string, result: unknown): void {
    this.messages.push({ role: "tool", name, result });
  }

  /**
   * Return chat messages. When maxMessages is set, trim oldest non-system
   * messages but always preserve system messages.
   */
  toChatMessages(): ChatMessage[] {
    if (this.maxMessages === undefined || this.messages.length <= this.maxMessages) {
      return [...this.messages];
    }

    // Separate system vs non-system messages
    const systemMessages: ChatMessage[] = [];
    const nonSystemMessages: ChatMessage[] = [];

    for (const msg of this.messages) {
      if (msg.role === "system") {
        systemMessages.push(msg);
      } else {
        nonSystemMessages.push(msg);
      }
    }

    // How many non-system messages can we keep?
    const nonSystemSlots = Math.max(0, this.maxMessages - systemMessages.length);
    const trimmedNonSystem = nonSystemSlots === 0 ? [] : nonSystemMessages.slice(-nonSystemSlots);

    // Reconstruct in order: system messages first, then trimmed non-system
    // Actually, we need to preserve relative ordering. Rebuild from original order.
    const keepSet = new Set<ChatMessage>([...systemMessages, ...trimmedNonSystem]);
    return this.messages.filter((msg) => keepSet.has(msg));
  }

  clear(): void {
    this.messages = [];
  }

  toJSON(): { messages: ChatMessage[]; maxMessages?: number } {
    const result: { messages: ChatMessage[]; maxMessages?: number } = {
      messages: this.toChatMessages(),
    };
    if (this.maxMessages !== undefined) {
      result.maxMessages = this.maxMessages;
    }
    return result;
  }
}

// ── InMemoryStore ───────────────────────────────────────

let nextId = 0;

function generateId(): string {
  return `mem_${Date.now()}_${nextId++}`;
}

/**
 * Tokenize a string into lowercase word tokens.
 */
function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/\W+/)
    .filter((t) => t.length > 0);
}

/**
 * Compute keyword overlap score between two sets of tokens.
 * Returns the number of overlapping unique tokens divided by total unique query tokens.
 */
function overlapScore(queryTokens: Set<string>, contentTokens: Set<string>): number {
  if (queryTokens.size === 0) return 0;
  let overlap = 0;
  for (const token of queryTokens) {
    if (contentTokens.has(token)) {
      overlap++;
    }
  }
  return overlap / queryTokens.size;
}

/**
 * In-memory store using keyword-overlap similarity for search.
 */
export class InMemoryStore implements MemoryStore {
  private entries: Map<string, MemoryEntry> = new Map();

  add(entry: Omit<MemoryEntry, "id"> & { id?: string }): string {
    const id = entry.id ?? generateId();
    const memoryEntry: MemoryEntry = {
      id,
      content: entry.content,
      metadata: entry.metadata,
      timestamp: entry.timestamp,
    };
    this.entries.set(id, memoryEntry);
    return id;
  }

  search(query: string, topK: number): MemoryEntry[] {
    const queryTokens = new Set(tokenize(query));
    const scored: Array<{ entry: MemoryEntry; score: number }> = [];

    for (const entry of this.entries.values()) {
      const contentTokens = new Set(tokenize(entry.content));
      const score = overlapScore(queryTokens, contentTokens);
      if (score > 0) {
        scored.push({ entry, score });
      }
    }

    // Sort descending by score, then by timestamp descending for ties
    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return b.entry.timestamp - a.entry.timestamp;
    });

    return scored.slice(0, topK).map((s) => s.entry);
  }

  delete(id: string): void {
    this.entries.delete(id);
  }

  clear(): void {
    this.entries.clear();
  }

  listAll(): MemoryEntry[] {
    return Array.from(this.entries.values());
  }
}

// ── SemanticMemory ──────────────────────────────────────

export interface SemanticMemoryOptions {
  /** Pluggable memory backend. Defaults to InMemoryStore. */
  store?: MemoryStore;
  /** Maximum results per search query. Default 5. */
  maxResults?: number;
  /** Optional session ID for scoping memories. */
  sessionId?: string;
}

/**
 * Semantic memory backed by a pluggable MemoryStore.
 *
 * Uses the store's search to find relevant entries by content similarity.
 * Supports session-scoped memories and prompt-ready context generation.
 */
export class SemanticMemory {
  private store: MemoryStore;
  readonly maxResults: number;
  readonly sessionId?: string;

  constructor(options?: SemanticMemoryOptions) {
    this.store = options?.store ?? new InMemoryStore();
    this.maxResults = options?.maxResults ?? 5;
    this.sessionId = options?.sessionId;
  }

  add(content: string, metadata?: Record<string, unknown>): string {
    const meta = { ...metadata };
    if (this.sessionId) {
      meta.sessionId = this.sessionId;
    }
    return this.store.add({
      content,
      metadata: meta,
      timestamp: Date.now(),
    });
  }

  /**
   * Search for relevant memories. Returns content strings only.
   */
  search(query: string, topK?: number): string[] {
    const k = topK ?? this.maxResults;
    return this.store.search(query, k).map((e) => e.content);
  }

  /**
   * Search and return full MemoryEntry objects (with id, metadata, timestamp).
   */
  searchEntries(query: string, topK?: number): MemoryEntry[] {
    const k = topK ?? this.maxResults;
    return this.store.search(query, k);
  }

  delete(id: string): void {
    this.store.delete(id);
  }

  clear(): void {
    this.store.clear();
  }

  listAll(): MemoryEntry[] {
    return this.store.listAll();
  }

  /**
   * Get relevant memories formatted for injection into an LLM prompt.
   *
   * Returns a formatted string of relevant memories, or empty string if none found.
   */
  getContext(query: string): string {
    const memories = this.search(query);
    if (memories.length === 0) return "";
    const lines = ["Relevant context from memory:"];
    memories.forEach((mem, i) => {
      lines.push(`  ${i + 1}. ${mem}`);
    });
    return lines.join("\n");
  }
}
