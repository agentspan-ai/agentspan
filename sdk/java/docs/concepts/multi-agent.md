# Multi-Agent

Agentspan has one primitive — `Agent` — and multiple strategies for composing agents together. Pick the strategy that matches your workflow's structure.

## Strategy overview

| Strategy | Description | Use when |
|---|---|---|
| `SEQUENTIAL` | Agents run one after another; output of each feeds the next | Linear pipelines (research → write → edit) |
| `PARALLEL` | All sub-agents run concurrently; results are synthesized | Independent parallel tasks |
| `HANDOFF` | Sub-agent is called as a tool; parent LLM decides when and which | Dynamic routing by LLM |
| `ROUTER` | A dedicated router agent decides which sub-agent runs | Rule-based or LLM-based routing |
| `SWARM` | Any agent can transfer control to another based on triggers | Open-ended conversation routing |
| `ROUND_ROBIN` | Sub-agents take turns in a fixed cycle | Structured multi-agent discussions |
| `RANDOM` | A randomly-selected sub-agent runs each turn | Varied multi-agent discussions |
| `PLAN_EXECUTE` | A planner agent produces a structured plan; steps execute against it | Complex multi-step tasks with dependencies |
| `MANUAL` | No automatic orchestration; you drive the loop | Custom control flow |

---

## Sequential

```java
Agent researcher = Agent.builder()
    .name("researcher").model("openai/gpt-4o-mini")
    .instructions("Research the topic and return key facts.")
    .build();

Agent writer = Agent.builder()
    .name("writer").model("openai/gpt-4o-mini")
    .instructions("Write a 200-word article from the research notes.")
    .build();

// Shorthand
Agent pipeline = researcher.then(writer);

// Equivalent explicit form
Agent pipeline = Agent.builder()
    .name("research_pipeline")
    .model("openai/gpt-4o-mini")
    .agents(researcher, writer)
    .strategy(Strategy.SEQUENTIAL)
    .build();

AgentResult result = runtime.run(pipeline, "Write about the history of jazz");
```

---

## Parallel

Sub-agents run concurrently. A synthesizer (the parent's LLM) combines their outputs.

```java
Agent french   = Agent.builder().name("french_translator").model("openai/gpt-4o-mini")
    .instructions("Translate to French.").build();
Agent spanish  = Agent.builder().name("spanish_translator").model("openai/gpt-4o-mini")
    .instructions("Translate to Spanish.").build();
Agent german   = Agent.builder().name("german_translator").model("openai/gpt-4o-mini")
    .instructions("Translate to German.").build();

Agent translator = Agent.builder()
    .name("multi_translator")
    .model("openai/gpt-4o-mini")
    .agents(french, spanish, german)
    .strategy(Strategy.PARALLEL)
    .synthesize(true)                      // merge sub-agent outputs
    .build();
```

---

## Handoff

Sub-agents are tools the parent's LLM can call. The LLM decides dynamically which agent to invoke and when.

```java
Agent mathAgent = Agent.builder()
    .name("math_agent").model("openai/gpt-4o-mini")
    .instructions("Solve math problems.").build();

Agent textAgent = Agent.builder()
    .name("text_agent").model("openai/gpt-4o-mini")
    .instructions("Summarise or rewrite text.").build();

Agent dispatcher = Agent.builder()
    .name("dispatcher")
    .model("openai/gpt-4o-mini")
    .instructions("Route requests to the appropriate specialist.")
    .agents(mathAgent, textAgent)
    .strategy(Strategy.HANDOFF)            // default strategy
    .build();
```

---

## Router

A dedicated router agent reads the input and selects which sub-agent runs. The router's output is the name of the sub-agent to invoke.

```java
Agent router = Agent.builder()
    .name("intent_router")
    .model("openai/gpt-4o-mini")
    .instructions("Reply with exactly one word: 'math', 'code', or 'text'.")
    .build();

Agent parent = Agent.builder()
    .name("smart_dispatcher")
    .model("openai/gpt-4o-mini")
    .router(router)
    .agents(mathAgent, codeAgent, textAgent)
    .strategy(Strategy.ROUTER)
    .build();
```

---

## Swarm

Agents transfer control to each other based on text mentions or tool results. Good for conversational routing.

```java
import org.conductoross.conductor.ai.handoff.OnTextMention;
import org.conductoross.conductor.ai.handoff.OnToolResult;

Agent support = Agent.builder()
    .name("support_agent")
    .model("openai/gpt-4o-mini")
    .instructions("Handle general support. Transfer billing issues to billing_agent.")
    .handoffs(
        OnTextMention.of("billing", "billing_agent"),
        OnTextMention.of("refund",  "billing_agent"),
        OnToolResult.of("escalate_tool", "escalation_agent")
    )
    .build();

Agent billing = Agent.builder()
    .name("billing_agent").model("openai/gpt-4o-mini")
    .instructions("Handle billing questions.").build();

Agent team = Agent.builder()
    .name("support_team")
    .model("openai/gpt-4o-mini")
    .agents(support, billing)
    .strategy(Strategy.SWARM)
    .build();
```

### Handoff triggers

| Class | Factory | Triggers when |
|---|---|---|
| `OnTextMention` | `OnTextMention.of(text, target)` | Agent output contains `text` |
| `OnToolResult` | `OnToolResult.of(toolName, target)` | Tool `toolName` returns any result |
| `OnToolResult` | `OnToolResult.of(toolName, target, contains)` | Tool result contains `contains` |
| `OnCondition` | `new OnCondition(target, predicate)` | Custom Java predicate on the message map |

---

## Plan-Execute

A planner agent produces a structured `Plan`; a separate executor runs each step. Steps can have dependencies and run in parallel when safe to do so.

```java
import org.conductoross.conductor.ai.plans.*;

// Each Op names a tool/worker and passes args. Use new Ref("stepId") to wire a
// later step's input to an earlier step's output. For an LLM-generated step,
// pass a Generate spec: .generate(Generate.builder().instructions("...").build()).
Plan plan = Plan.builder()
    .step(Step.builder("fetch_data")
        .operation(Op.builder("get_data").args(Map.of("source", "database")).build())
        .build())
    .step(Step.builder("analyse")
        .dependsOn("fetch_data")
        .operation(Op.builder("analyse_data")
            .args(Map.of("rows", new Ref("fetch_data")))   // consumes fetch_data's output
            .build())
        .build())
    .step(Step.builder("summarise")
        .dependsOn("analyse")
        .operation(Op.builder("summarise")
            .args(Map.of("analysis", new Ref("analyse")))
            .build())
        .build())
    .build();

Agent planExecuteAgent = Agent.builder()
    .name("research_pac")
    .model("openai/gpt-4o-mini")
    .strategy(Strategy.PLAN_EXECUTE)
    .build();

AgentResult result = runtime.run(planExecuteAgent, "Analyse last month's sales", plan);
```

---

## Termination conditions

Stop a multi-agent loop early without hitting `maxTurns`:

```java
import org.conductoross.conductor.ai.termination.*;

// Stop after 5 messages
Agent agent = Agent.builder()
    .termination(MaxMessageTermination.of(5))
    .build();

// Stop when output contains "DONE"
Agent agent = Agent.builder()
    .termination(StopMessageTermination.of("DONE"))
    .build();

// Compose with AND / OR
TerminationCondition cond = MaxMessageTermination.of(10)
    .or(StopMessageTermination.of("FINISHED"));

Agent agent = Agent.builder()
    .termination(cond)
    .build();
```

See [Termination](termination.md) for the full list.
