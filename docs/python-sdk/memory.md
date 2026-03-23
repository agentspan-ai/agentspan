# Memory Design

The SDK provides two memory systems for agents: **ConversationMemory** for chat history management and **SemanticMemory** for long-term knowledge retrieval. They serve different purposes and can be used together.

---

## Overview

```
┌──────────────────────────────────────────────────────┐
│                    Agent Memory                       │
│                                                       │
│  ConversationMemory          SemanticMemory           │
│  ├─ Chat history             ├─ Long-term knowledge   │
│  ├─ Message accumulation     ├─ Similarity search     │
│  ├─ Trimming (max_messages)  ├─ Pluggable backends    │
│  └─ Injected as messages     └─ Injected into prompt  │
│                                                       │
│  Conductor Server (built-in)                          │
│  └─ getHistory() — automatic DoWhile accumulation     │
└──────────────────────────────────────────────────────┘
```

---

## ConversationMemory

Manages chat history as a list of messages. Messages are prepended to the LLM's message list at compile time.

```python
from agentspan.agents import Agent, ConversationMemory

memory = ConversationMemory(max_messages=100)

agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    instructions="You are a helpful assistant.",
    memory=memory,
)
```

### Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `messages` | `list[dict]` | `[]` | Accumulated conversation messages. |
| `max_messages` | `int` | `None` | Maximum messages to retain. `None` means unlimited. |

### Message Format

Messages follow Conductor's chat message format:

```python
{"role": "user", "message": "Hello!"}
{"role": "assistant", "message": "Hi there!"}
{"role": "system", "message": "You are helpful."}
{"role": "tool_call", "message": "", "tool_calls": [{...}]}
{"role": "tool", "message": "result", "toolCallId": "ref", "taskReferenceName": "ref"}
```

### Methods

| Method | Description |
|--------|-------------|
| `add_user_message(content)` | Append a user message. |
| `add_assistant_message(content)` | Append an assistant message. |
| `add_system_message(content)` | Append a system message. |
| `add_tool_call(tool_name, arguments, task_reference_name)` | Record a tool invocation. |
| `add_tool_result(tool_name, result, task_reference_name)` | Record a tool result. |
| `to_chat_messages()` | Return deep copy of messages in ChatMessage format. |
| `clear()` | Clear all history. |

### Trimming Behavior

When `max_messages` is set and the message count exceeds it:

1. **System messages are preserved** — they stay in their original positions
2. **Oldest non-system messages are removed first**
3. The budget is: `max_messages - system_count` non-system messages kept (newest)
4. If system messages alone exceed the budget, only the latest system messages are kept

### How It Compiles

When `agent.memory` is set, the compiler prepends `memory.to_chat_messages()` to the LLM task's message list. These messages appear before the current user prompt, giving the LLM context from previous interactions.

This works alongside Conductor's built-in `getHistory()` mechanism, which automatically accumulates conversation within a DoWhile loop iteration (tool calls, tool results, LLM responses). ConversationMemory provides the cross-session context; `getHistory()` handles within-session accumulation.

---

## SemanticMemory

Long-term memory with similarity-based retrieval. Stores facts, preferences, and knowledge that can be recalled based on relevance to the current query.

```python
from agentspan.agents.semantic_memory import SemanticMemory

memory = SemanticMemory(max_results=3)

# Store knowledge
memory.add("Customer prefers email communication.")
memory.add("Account is on the Enterprise plan since March 2021.")
memory.add("Last issue: billing discrepancy on invoice #1042.")

# Retrieve relevant context
context = memory.get_context("What plan am I on?")
# Returns: "Relevant context from memory:\n  1. Account is on the Enterprise plan..."
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `store` | `MemoryStore` | `InMemoryStore()` | Storage backend. |
| `max_results` | `int` | `5` | Maximum memories to retrieve per query. |
| `session_id` | `str` | `None` | Optional session scope. Added as metadata to entries. |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `add(content, metadata)` | `str` (entry ID) | Store a memory. Optional metadata dict (e.g. `{"type": "preference"}`). |
| `search(query, top_k)` | `list[str]` | Search for relevant memories. Returns content strings, most relevant first. |
| `search_entries(query, top_k)` | `list[MemoryEntry]` | Search and return full `MemoryEntry` objects (with metadata). |
| `get_context(query)` | `str` | Get relevant memories formatted for prompt injection. Returns empty string if no matches. |
| `delete(memory_id)` | `bool` | Delete a memory by ID. |
| `clear()` | — | Delete all memories. |
| `list_all()` | `list[MemoryEntry]` | Return all stored memories. |

### MemoryEntry

Each stored memory is a `MemoryEntry`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | auto-generated | Unique identifier (SHA-256 hash). |
| `content` | `str` | `""` | The memory text. |
| `metadata` | `dict` | `{}` | Arbitrary metadata (type, source, importance, session_id). |
| `embedding` | `list[float]` | `None` | Optional embedding vector for similarity search. |
| `created_at` | `float` | auto | Unix timestamp. |

### Usage Patterns

#### As a Tool

The most common pattern — expose memory search as a tool the agent can call:

```python
memory = SemanticMemory(max_results=3)
memory.add("User prefers Python over JavaScript")

@tool
def get_context(query: str) -> str:
    """Retrieve relevant context from memory."""
    return memory.get_context(query)

agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    tools=[get_context],
)
```

The agent decides when to search memory, what to query, and how to use the results.

#### Injected into System Prompt

Memory context can also be injected directly into instructions:

```python
def build_instructions() -> str:
    context = memory.get_context(current_query)
    return f"You are a support agent.\n\n{context}"

agent = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions=build_instructions,  # callable instructions
)
```

---

## Storage Backends

### MemoryStore Interface

The `MemoryStore` abstract class defines the backend contract:

```python
from agentspan.agents.semantic_memory import MemoryStore, MemoryEntry

class MemoryStore(ABC):
    def add(self, entry: MemoryEntry) -> str: ...
    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]: ...
    def delete(self, memory_id: str) -> bool: ...
    def clear(self) -> None: ...
    def list_all(self) -> List[MemoryEntry]: ...
```

### InMemoryStore (Default)

Lightweight fallback using keyword overlap (Jaccard similarity). Non-persistent — memories are lost when the process exits.

```python
memory = SemanticMemory()  # uses InMemoryStore by default
```

**Similarity algorithm:** Jaccard similarity over word sets — `|intersection| / |union|` of query words and memory words. Entries with zero overlap are excluded. Results sorted by score, descending.

Suitable for development and testing. For production, use a vector database backend.

### Custom Backend

Implement `MemoryStore` to integrate with vector databases:

```python
class PineconeStore(MemoryStore):
    def __init__(self, index_name: str, api_key: str):
        self.index = pinecone.Index(index_name, api_key=api_key)

    def add(self, entry: MemoryEntry) -> str:
        embedding = get_embedding(entry.content)
        self.index.upsert([(entry.id, embedding, {"content": entry.content})])
        return entry.id

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        embedding = get_embedding(query)
        results = self.index.query(embedding, top_k=top_k)
        return [MemoryEntry(id=r.id, content=r.metadata["content"]) for r in results.matches]

    def delete(self, memory_id: str) -> bool:
        self.index.delete(ids=[memory_id])
        return True

    def clear(self) -> None:
        self.index.delete(delete_all=True)

    def list_all(self) -> List[MemoryEntry]:
        ...

memory = SemanticMemory(store=PineconeStore("my-index", api_key="..."))
```

Compatible backends: Pinecone, Weaviate, ChromaDB, Qdrant, Mem0, or any service that supports vector similarity search.

---

## ConversationMemory vs SemanticMemory
| -   | ConversationMemory | SemanticMemory |
|-----|---------|-------------|
| **Purpose** | Chat history (messages) | Long-term knowledge (facts) |
| **Retrieval** | All messages (FIFO, trimmed) | Similarity search (relevant subset) |
| **Injection** | Prepended as LLM messages | Formatted text in system prompt or tool result |
| **Persistence** | In-process (lost on restart) | Pluggable backend (can persist) |
| **Compilation** | Messages added to LLM task's message list | Used via tool or callable instructions |
| **Scaling** | Bounded by `max_messages` | Bounded by `max_results` per query |
| **Best for** | Multi-turn conversations within a session | Cross-session knowledge, user preferences, facts |

---

## Conductor Server-Side Memory

Independent of the SDK's memory classes, Conductor's `LLM_CHAT_COMPLETE` task has built-in conversation accumulation when running inside a DoWhile loop. The server's `getHistory()` mechanism automatically tracks:

- User messages
- Assistant responses
- Tool calls and results

This happens transparently — no SDK configuration needed. The SDK's `ConversationMemory` adds **cross-session** context on top of this built-in within-session accumulation.
