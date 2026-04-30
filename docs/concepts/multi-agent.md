---
title: Multi-Agent Strategies
description: All 8 coordination strategies — sequential, parallel, handoff, router, swarm, round_robin, random, manual
---

# Multi-Agent Strategies

Every multi-agent system in Agentspan is built from one primitive: `Agent`. Set `agents=[...]` and choose a `strategy` to coordinate them.

## Overview

| Strategy | Description |
|---|---|
| `handoff` (default) | LLM chooses which sub-agent handles the request |
| `sequential` | Sub-agents run in order, output feeds forward |
| `parallel` | All sub-agents run concurrently, results aggregated |
| `router` | A router agent or function selects which sub-agent runs |
| `swarm` | Condition-based handoffs between agents |
| `round_robin` | Agents take turns in a fixed rotation |
| `random` | Random sub-agent selection each turn |
| `manual` | Human selects which agent speaks each turn |

## Sequential — `a >> b >> c`

Sub-agents run in order. Each agent's output becomes the next agent's input.

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant R as Researcher
    participant W as Writer
    participant E as Editor
    Code->>Server: run(researcher >> writer >> editor, prompt)
    activate Server
    Server->>R: run
    activate R
    R-->>Server: result
    deactivate R
    Server->>W: run (receives researcher output)
    activate W
    W-->>Server: result
    deactivate W
    Server->>E: run (receives writer output)
    activate E
    E-->>Server: result
    deactivate E
    Server-->>Code: AgentResult
    deactivate Server
```

```python
from agentspan.agents import Agent, AgentRuntime

researcher = Agent(name="researcher", model="openai/gpt-4o",
                   instructions="Research the topic and provide key facts.")
writer = Agent(name="writer", model="openai/gpt-4o",
               instructions="Write an engaging article from the research.")
editor = Agent(name="editor", model="openai/gpt-4o",
               instructions="Polish the article for publication.")

# Operator syntax
pipeline = researcher >> writer >> editor

# Equivalent constructor syntax
pipeline = Agent(
    name="pipeline",
    model="openai/gpt-4o",
    agents=[researcher, writer, editor],
    strategy="sequential",
)

with AgentRuntime() as runtime:
    result = runtime.run(pipeline, "AI agents in software development")
    result.print_result()
```

## Parallel

All sub-agents run concurrently. Results are aggregated into `result.sub_results`.

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant M as Market Analyst
    participant R as Risk Analyst
    participant F as Financial Analyst
    Code->>Server: run(due_diligence, prompt)
    activate Server
    par run concurrently
        Server->>M: run
        activate M
    and
        Server->>R: run
        activate R
    and
        Server->>F: run
        activate F
    end
    M-->>Server: result
    deactivate M
    R-->>Server: result
    deactivate R
    F-->>Server: result
    deactivate F
    Note over Server: synthesize all results
    Server-->>Code: AgentResult
    deactivate Server
```

```python
from agentspan.agents import Agent, AgentRuntime

market = Agent(name="market", model="openai/gpt-4o",
               instructions="Analyze market size, growth, and key players.")
risk = Agent(name="risk", model="openai/gpt-4o",
             instructions="Analyze regulatory, technical, and competitive risks.")
financial = Agent(name="financial", model="openai/gpt-4o",
                  instructions="Analyze financial projections and metrics.")

analysis = Agent(
    name="analysis",
    model="openai/gpt-4o",
    agents=[market, risk, financial],
    strategy="parallel",
)

with AgentRuntime() as runtime:
    result = runtime.run(analysis, "Launching an AI healthcare tool in the US")
    print(result.sub_results["market"])
    print(result.sub_results["risk"])
    print(result.sub_results["financial"])
```

## Handoff (default)

The orchestrator LLM decides which sub-agent handles the request. Sub-agents can also hand off to each other.

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant LLM
    participant B as Billing
    participant T as Technical
    participant G as General
    Code->>Server: run(support, prompt)
    activate Server
    Server->>LLM: route decision
    activate LLM
    LLM-->>Server: "Billing"
    deactivate LLM
    Server->>B: run
    activate B
    B-->>Server: result
    deactivate B
    Server-->>Code: AgentResult
    deactivate Server
```

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def check_balance(account_id: str) -> dict:
    """Check account balance."""
    return {"account_id": account_id, "balance": 5432.10}

billing = Agent(name="billing", model="openai/gpt-4o",
                instructions="Handle billing inquiries.", tools=[check_balance])
technical = Agent(name="technical", model="openai/gpt-4o",
                  instructions="Handle technical issues.")

support = Agent(
    name="support",
    model="openai/gpt-4o",
    instructions="Route customer requests to the right team.",
    agents=[billing, technical],
    strategy="handoff",   # This is the default
)

with AgentRuntime() as runtime:
    result = runtime.run(support, "What's the balance on account ACC-123?")
    result.print_result()
```

## Router

A dedicated router agent or function selects which sub-agent runs:

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant Cls as Classifier
    participant B as Billing
    participant T as Technical
    participant G as General
    Code->>Server: run(support, prompt)
    activate Server
    Server->>Cls: classify intent
    activate Cls
    Cls-->>Server: "Billing"
    deactivate Cls
    Server->>B: run
    activate B
    B-->>Server: result
    deactivate B
    Server-->>Code: AgentResult
    deactivate Server
```

```python
from agentspan.agents import Agent, AgentRuntime

classifier = Agent(
    name="classifier",
    model="openai/gpt-4o-mini",
    instructions="Classify the request as 'billing', 'technical', or 'general'. Reply with just the category.",
)

billing = Agent(name="billing", model="openai/gpt-4o",
                instructions="Handle billing inquiries.")
technical = Agent(name="technical", model="openai/gpt-4o",
                  instructions="Handle technical issues.")
general = Agent(name="general", model="openai/gpt-4o",
                instructions="Handle general questions.")

support = Agent(
    name="support",
    model="openai/gpt-4o",
    agents=[billing, technical, general],
    strategy="router",
    router=classifier,
)

with AgentRuntime() as runtime:
    result = runtime.run(support, "My invoice has a wrong charge")
    result.print_result()
```

You can also use a Python function as the router:

```python
def route(prompt: str) -> str:
    """Return the name of the agent to route to."""
    if "bill" in prompt.lower() or "invoice" in prompt.lower():
        return "billing"
    elif "error" in prompt.lower() or "bug" in prompt.lower():
        return "technical"
    return "general"

support = Agent(
    name="support",
    model="openai/gpt-4o",
    agents=[billing, technical, general],
    strategy="router",
    router=route,
)
```

## Swarm

Condition-based handoffs between agents. Each agent can trigger a handoff based on text patterns or other conditions:

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant T as Triage
    participant Ref as Refund Specialist
    participant Esc as Escalation
    Code->>Server: run(support, prompt)
    activate Server
    Server->>T: run
    activate T
    T-->>Server: "customer wants a refund"
    deactivate T
    Note over Server: OnTextMention("refund") triggers
    Server->>Ref: run
    activate Ref
    Ref-->>Server: result
    deactivate Ref
    Server-->>Code: AgentResult
    deactivate Server
```

```python
from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents import TextMentionTermination

triage = Agent(name="triage", model="openai/gpt-4o",
               instructions="Triage support requests. Say 'BILLING' for billing, 'TECH' for technical.")
billing = Agent(name="billing", model="openai/gpt-4o",
                instructions="Handle billing inquiries.")
technical = Agent(name="technical", model="openai/gpt-4o",
                  instructions="Handle technical issues.")

team = Agent(
    name="support_team",
    model="openai/gpt-4o",
    agents=[triage, billing, technical],
    strategy=Strategy.SWARM,
    handoffs=[
        TextMentionTermination("BILLING", target="billing"),
        TextMentionTermination("TECH", target="technical"),
    ],
)
```

## Round Robin

Agents take turns in a fixed rotation:

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant O as Optimist
    participant P as Pessimist
    participant R as Realist
    Code->>Server: run(debate, prompt)
    activate Server
    loop 3 rounds
        Server->>O: run
        activate O
        O-->>Server: result
        deactivate O
        Server->>P: run
        activate P
        P-->>Server: result
        deactivate P
        Server->>R: run
        activate R
        R-->>Server: result
        deactivate R
    end
    Server-->>Code: AgentResult
    deactivate Server
```

```python
agent1 = Agent(name="agent1", model="openai/gpt-4o",
               instructions="You are the first debater. Argue for AI regulation.")
agent2 = Agent(name="agent2", model="openai/gpt-4o",
               instructions="You are the second debater. Argue against AI regulation.")

debate = Agent(
    name="debate",
    model="openai/gpt-4o",
    agents=[agent1, agent2],
    strategy="round_robin",
    max_turns=6,   # 3 rounds each
)

with AgentRuntime() as runtime:
    result = runtime.run(debate, "Begin the debate.")
    result.print_result()
```

## Random

A random sub-agent is selected each turn. Useful for load balancing across models or creating diverse output ensembles.

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant G as GPT-4o
    participant C as Claude
    participant Ge as Gemini
    Code->>Server: run(ensemble, prompt)
    activate Server
    Note over Server: random selection
    Server->>C: run (randomly chosen)
    activate C
    C-->>Server: result
    deactivate C
    Server-->>Code: AgentResult
    deactivate Server
```

```python
ensemble = Agent(
    name="diverse_writers",
    agents=[
        Agent(name="gpt4", model="openai/gpt-4o", instructions="Write concisely."),
        Agent(name="claude", model="anthropic/claude-sonnet-4-6", instructions="Write creatively."),
        Agent(name="gemini", model="google_gemini/gemini-2.0-flash", instructions="Write with examples."),
    ],
    strategy="random",
)

with AgentRuntime() as runtime:
    result = runtime.run(ensemble, "Explain why consistency matters in distributed systems")
    result.print_result()
```

## Manual

Execution pauses between turns waiting for explicit human selection of the next agent. Useful for human-directed workflows.

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant A as Agent A
    participant B as Agent B
    participant C as Agent C
    Code->>Server: start(workflow, prompt)
    activate Server
    Note over Server,C: paused — waiting for human to pick next agent
    Code->>Server: handle.send("agent_a")
    Server->>A: run
    activate A
    A-->>Server: result
    deactivate A
    Note over Server,C: paused — waiting again
    Code->>Server: handle.send("agent_b")
    Server->>B: run
    activate B
    B-->>Server: result
    deactivate B
    Server-->>Code: AgentResult
    deactivate Server
```

```python
from agentspan.agents import Agent, AgentRuntime, start

workflow = Agent(
    name="manual_workflow",
    agents=[agent_a, agent_b, agent_c],
    strategy="manual",
)

with AgentRuntime() as runtime:
    handle = runtime.start(workflow, "initial prompt")
    # Manual strategy pauses at each turn waiting for input.
    # Use handle.send(agent_name) to select which agent runs next.
    status = handle.get_status()
    if status.is_waiting:
        handle.send("agent_a")  # send the name of the agent to invoke
```

## Termination Conditions

Control when multi-agent loops stop:

```python
from agentspan.agents import (
    MaxMessageTermination,
    TextMentionTermination,
    StopMessageTermination,
    TokenUsageTermination,
)

# Stop after 20 messages
MaxMessageTermination(max_messages=20)

# Stop when an agent says "DONE"
TextMentionTermination("DONE")

# Stop on StopMessage events
StopMessageTermination()

# Stop when token budget is exceeded
TokenUsageTermination(max_total_tokens=10000)
```

Combine multiple conditions:

```python
from agentspan.agents import Agent

agent = Agent(
    name="team",
    model="openai/gpt-4o",
    agents=[agent1, agent2],
    strategy="round_robin",
    stop_when=MaxMessageTermination(20) | TextMentionTermination("DONE"),
)
```

## Nested Strategies

Strategies compose freely — a parallel agent can contain sequential pipelines:

```mermaid
sequenceDiagram
    participant Code as Your Code
    participant Server as Agentspan Server
    participant M as Market Agent
    participant T as Tech Agent
    participant Reg as Regulatory Agent
    participant W as Writer
    participant E as Editor
    participant F as Formatter
    Code->>Server: run(report_pipeline, prompt)
    activate Server
    Note over Server: Stage 1 — Parallel Research
    par run concurrently
        Server->>M: run
        activate M
    and
        Server->>T: run
        activate T
    and
        Server->>Reg: run
        activate Reg
    end
    M-->>Server: result
    deactivate M
    T-->>Server: result
    deactivate T
    Reg-->>Server: result
    deactivate Reg
    Note over Server: Stage 2 — Sequential Publish
    Server->>W: run
    activate W
    W-->>Server: result
    deactivate W
    Server->>E: run (receives Writer output)
    activate E
    E-->>Server: result
    deactivate E
    Server->>F: run (receives Editor output)
    activate F
    F-->>Server: result
    deactivate F
    Server-->>Code: AgentResult
    deactivate Server
```

```python
research_pipeline = researcher >> writer

analysis = Agent(
    name="analysis",
    model="openai/gpt-4o",
    agents=[research_pipeline, financial_agent, risk_agent],
    strategy="parallel",
)
```
