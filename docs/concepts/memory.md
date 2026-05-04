---
title: Memory
description: ConversationMemory for chat history, SemanticMemory for long-term knowledge retrieval
---

# Memory

Agentspan provides two memory systems: **ConversationMemory** for managing chat history and **SemanticMemory** for long-term knowledge retrieval. They serve different purposes and can be used together.

## Import

```python
from agentspan.agents import Agent, ConversationMemory
from agentspan.agents.semantic_memory import SemanticMemory
```

## ConversationMemory

Manages chat history as a list of messages. Messages are prepended to the LLM's message list at compile time, giving the LLM context from previous interactions.

```python
from agentspan.agents import Agent, AgentRuntime, ConversationMemory

memory = ConversationMemory(max_messages=100)

agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    instructions="You are a helpful assistant.",
    memory=memory,
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "My name is Alice.")
    memory.add_user_message("My name is Alice.")
    memory.add_assistant_message(result.output['result'])

    result2 = runtime.run(agent, "What's my name?")
    result2.print_result()   # "Your name is Alice."
```

### Parameters

| Field | Type | Default | Description |
|---|---|---|---|
| `messages` | `list[dict]` | `[]` | Accumulated conversation messages |
| `max_messages` | `int` | `None` | Maximum messages to retain. `None` = unlimited |

### Methods

| Method | Description |
|---|---|
| `add_user_message(content)` | Append a user message |
| `add_assistant_message(content)` | Append an assistant message |
| `add_system_message(content)` | Append a system message |
| `add_tool_call(tool_name, args, task_reference_name)` | Record a tool invocation |
| `add_tool_result(tool_name, result, task_reference_name)` | Record a tool result |
| `clear()` | Clear all history |

### Trimming Behavior

When `max_messages` is set and the message count exceeds it:
1. System messages are preserved in their original positions
2. Oldest non-system messages are removed first
3. Budget: `max_messages - system_count` non-system messages kept (newest)

## SemanticMemory

Long-term memory with similarity-based retrieval. Stores facts, preferences, and knowledge recalled by relevance to the current query.

```python
from agentspan.agents.semantic_memory import SemanticMemory

memory = SemanticMemory(max_results=3)

memory.add("Customer prefers email communication.")
memory.add("Account is on the Enterprise plan since March 2021.")
memory.add("Last issue: billing discrepancy on invoice #1042.")

context = memory.get_context("What plan am I on?")
# "Relevant context from memory:\n  1. Account is on the Enterprise plan..."
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `store` | `MemoryStore` | `InMemoryStore()` | Storage backend |
| `max_results` | `int` | `5` | Maximum memories to retrieve per query |
| `session_id` | `str` | `None` | Optional session scope |

### Methods

| Method | Returns | Description |
|---|---|---|
| `add(content, metadata)` | `str` (entry ID) | Store a memory |
| `search(query, top_k)` | `list[str]` | Return relevant memory content strings |
| `search_entries(query, top_k)` | `list[MemoryEntry]` | Return full `MemoryEntry` objects |
| `get_context(query)` | `str` | Get memories formatted for prompt injection |
| `delete(memory_id)` | `bool` | Delete a memory by ID |
| `clear()` | — | Delete all memories |
| `list_all()` | `list[MemoryEntry]` | Return all stored memories |

### Usage: Expose as a Tool (recommended)

The agent decides when to search and what to query:

```python
from agentspan.agents import Agent, AgentRuntime, tool
from agentspan.agents.semantic_memory import SemanticMemory

memory = SemanticMemory(max_results=3)
memory.add("User prefers Python over JavaScript")
memory.add("User is a senior engineer with 10 years experience")

@tool
def get_context(query: str) -> str:
    """Retrieve relevant context from memory."""
    return memory.get_context(query)

agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    tools=[get_context],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What language should I use?")
    result.print_result()
```

### Usage: Inject into System Prompt

```python
def build_instructions() -> str:
    context = memory.get_context("relevant query")
    return f"You are a support agent.\n\n{context}"

agent = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions=build_instructions,   # callable
)
```

## Storage Backends

The default `InMemoryStore` uses Jaccard similarity. Non-persistent — suitable for development.

For production, implement `MemoryStore`:

```python
from agentspan.agents.semantic_memory import MemoryStore, MemoryEntry, SemanticMemory

class PineconeStore(MemoryStore):
    def __init__(self, index_name: str, api_key: str):
        self.index = pinecone.Index(index_name, api_key=api_key)

    def add(self, entry: MemoryEntry) -> str:
        embedding = get_embedding(entry.content)
        self.index.upsert([(entry.id, embedding, {"content": entry.content})])
        return entry.id

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        embedding = get_embedding(query)
        results = self.index.query(embedding, top_k=top_k)
        return [MemoryEntry(id=r.id, content=r.metadata["content"]) for r in results.matches]

    def delete(self, memory_id: str) -> bool:
        self.index.delete(ids=[memory_id])
        return True

    def clear(self) -> None:
        self.index.delete(delete_all=True)

    def list_all(self) -> list[MemoryEntry]:
        ...

memory = SemanticMemory(store=PineconeStore("my-index", api_key="..."))
```

Compatible backends: Pinecone, Weaviate, ChromaDB, Qdrant, Mem0, or any vector search service.

## Comparison

| | ConversationMemory | SemanticMemory |
|---|---|---|
| **Purpose** | Chat history (messages) | Long-term knowledge (facts) |
| **Retrieval** | All messages, FIFO trimmed | Similarity search |
| **Injection** | Prepended as LLM messages | Formatted text via tool or instructions |
| **Persistence** | In-process (lost on restart) | Pluggable backend (can persist) |
| **Best for** | Multi-turn conversations in a session | Cross-session preferences, user facts |
