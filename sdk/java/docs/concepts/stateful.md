# Stateful Agents

By default each `run()` is independent — the agent has no memory of previous runs. For
conversational or long-lived agents, Conductor Agent offers three complementary mechanisms.

## Sessions — multi-turn continuity

Give an agent a `sessionId` and the server keys conversation continuity to it. Multiple runs that
share a session id form one conversation.

```java
Agent assistant = Agent.builder()
    .name("assistant")
    .model("openai/gpt-4o-mini")
    .instructions("You are a helpful assistant.")
    .sessionId("user-42")
    .build();
```

## Stateful mode — durable history + isolation

`stateful(true)` tells the server to persist conversation history across runs of the same agent.
It also flips on **per-execution worker domain isolation**: each run gets a unique domain so that
concurrent stateful runs never dequeue each other's tool tasks.

```java
Agent agent = Agent.builder()
    .name("hr_assistant")
    .model("openai/gpt-4o-mini")
    .instructions("You are an HR assistant. Remember earlier turns.")
    .stateful(true)
    .build();

// Subsequent runs against this agent see prior exchanges.
```

A tool can be marked stateful too (`ToolDef.builder()...stateful(true)`); any stateful tool in the
agent tree triggers the same domain isolation for the whole run.

## Conversation memory — seed prior turns

`ConversationMemory` lets you supply message history up front (e.g. restored from your own store)
and optionally cap how many messages the server retains:

```java
import org.conductoross.conductor.ai.model.ConversationMemory;

ConversationMemory memory = new ConversationMemory(20)   // retain at most 20 messages; null = unbounded
    .addSystem("You are concise.")
    .addUser("My name is Alice.")
    .addAssistant("Nice to meet you, Alice.");

Agent agent = Agent.builder()
    .name("assistant")
    .model("openai/gpt-4o-mini")
    .memory(memory)
    .build();
```

`addUser`, `addAssistant`, and `addSystem` are chainable; each message serializes as
`{"role": ..., "message": ...}`. Oldest messages beyond `maxMessages` are trimmed server-side.

## Sharing state between tools

Within a single execution, tools can pass data through `ToolContext.getState()` — a mutable map
that persists across tool calls. See [Tools → ToolContext](tools.md#toolcontext).
