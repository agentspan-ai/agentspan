# Roll the Dice: Build a Brainstorming Session with the Random Strategy

*By Deepti Reddy | May 2026*

*This is Part 6 of an 8-part series covering every multi-agent strategy in AgentSpan. Today: the random strategy — a random agent is selected each turn. No rotation, no decision — pure randomness.*

---

In Part 1, we built a sequential pipeline where each agent's output fed into the next. In Part 2, all three reviewers ran simultaneously. In Part 3, the LLM decided which agent ran. In Part 4, agents transferred work between each other peer-to-peer. In Part 5, agents took turns in a fixed rotation: architect, security, pragmatist, architect, security, pragmatist. Predictable. Structured.

But what if predictability is the problem? In brainstorming, you do not want a fixed order. You want surprise. You want the creative thinker to jump in twice in a row, or the critical thinker to challenge an idea the moment it lands. Fixed rotations produce fixed thinking.

That is the random strategy. Each turn, a random agent is selected. No pattern. No schedule. The same agent might go twice in a row, or not at all for three turns. The randomness creates variety in perspective that a fixed rotation cannot.

## What is AgentSpan

AgentSpan is an orchestration layer for building, bringing, and observing AI agents as durable workflows.

- **Build**: define agents with the AgentSpan SDK using Agent, @tool, and 8 multi-agent strategies. Compiles to server-side workflows that survive crashes.
- **Bring**: already using an agent framework such as LangGraph, OpenAI Agents SDK, or Google ADK? Pass your agents directly to run(). AgentSpan adds durability and orchestration on top.
- **Observe**: every execution is inspectable in the dashboard. See agent flows, inputs/outputs, tool calls, and token usage. Debug failures, replay runs.

## Setup

Two commands:

```bash
pip install agentspan
agentspan server start
```

This gives you a local AgentSpan server with a visual dashboard at localhost:6767.

## What we are building

A brainstorming session with three thinkers:

1. **Creative**: bold, unconventional ideas — "what if we did the opposite?"
2. **Practical**: feasibility, timelines, resources — "what would it actually take?"
3. **Critical**: risks, holes, blind spots — "what could go wrong?"

Each turn, one is randomly selected. After 6 turns, a summarizer distills the session into the top ideas and next steps.

```
Turn 1:  [Creative]    <- random
Turn 2:  [Critical]    <- random
Turn 3:  [Creative]    <- random (again!)
Turn 4:  [Practical]   <- random
Turn 5:  [Critical]    <- random
Turn 6:  [Practical]   <- random
              |
        [Summarizer] -> top 3 ideas + next step
```

## How is this different from round robin?

In **round robin** (Part 6), the order is fixed: A, B, C, A, B, C. Every agent gets equal time. Every agent knows when their turn is.

In **random**, there is no order. Agent A might speak three times. Agent C might speak once. The distribution is uneven by design — some perspectives naturally dominate in any real brainstorming session, and that is fine.

| | Round Robin | Random |
|---|---|---|
| Selection | Fixed rotation | Random each turn |
| Equal participation | Guaranteed | Not guaranteed |
| Predictable | Yes | No |
| Best for | Structured debate, reviews | Brainstorming, creative exploration |

## Defining the thinkers

Three agents with deliberately different thinking styles:

```python
from agentspan.agents import Agent, AgentRuntime, Strategy


creative = Agent(
    name="creative",
    model="openai/gpt-4o",
    instructions=(
        "You are a creative thinker. Generate bold, unconventional ideas. "
        "Push boundaries. Think 'what if we did the opposite of what everyone "
        "expects?' Read what others said before you and build on their ideas "
        "or take them in a surprising direction. Keep your response to 2-3 paragraphs."
    ),
)

practical = Agent(
    name="practical",
    model="openai/gpt-4o",
    instructions=(
        "You are a practical thinker. Focus on what can actually be built "
        "and shipped. Consider timelines, resources, and feasibility. Read "
        "what others said before you and ground their ideas in reality — "
        "what would it take to actually do this? Keep your response to 2-3 paragraphs."
    ),
)

critical = Agent(
    name="critical",
    model="openai/gpt-4o",
    instructions=(
        "You are a critical thinker. Find the holes, the risks, the things "
        "nobody wants to talk about. Read what others said before you and "
        "stress-test their ideas — what could go wrong? What are they not "
        "considering? Keep your response to 2-3 paragraphs."
    ),
)
```

The key instruction in each: "Read what others said before you." Each agent sees the full conversation. The difference from round robin is that who speaks next is random, not predetermined.

## The summarizer

After the brainstorm, a summarizer produces actionable output:

```python
summarizer = Agent(
    name="summarizer",
    model="openai/gpt-4o",
    instructions=(
        "You observed a brainstorming session between a creative thinker, "
        "a practical thinker, and a critical thinker. Produce a summary:\n\n"
        "1. Top 3 ideas (ranked by potential)\n"
        "2. Biggest risk identified\n"
        "3. Recommended next step (one sentence)\n\n"
        "Be concise and actionable."
    ),
)
```

## The random strategy

```python
brainstorm = Agent(
    name="brainstorm",
    model="openai/gpt-4o",
    agents=[creative, practical, critical],
    strategy=Strategy.RANDOM,
    max_turns=6,
)

pipeline = brainstorm >> summarizer
```

`max_turns=6` means 6 randomly selected turns. Some agents might go multiple times, others might be skipped entirely. Then `>>` pipes the brainstorm transcript to the summarizer.

Compare the strategies:

```python
# Sequential: fixed order, each runs once
pipeline = a >> b >> c

# Parallel: all run at once
team = Agent(agents=[a, b, c], strategy=Strategy.PARALLEL)

# Handoff: parent LLM picks one
triage = Agent(agents=[a, b, c], strategy=Strategy.HANDOFF)

# Router: classifier picks one
triage = Agent(agents=[a, b, c], strategy=Strategy.ROUTER, router=classifier)

# Swarm: agents transfer between each other
team = Agent(agents=[a, b, c], strategy=Strategy.SWARM)

# Round robin: fixed rotation
debate = Agent(agents=[a, b, c], strategy=Strategy.ROUND_ROBIN, max_turns=6)

# Random: random selection each turn
brainstorm = Agent(agents=[a, b, c], strategy=Strategy.RANDOM, max_turns=6)
```

Same `Agent` class. Different strategy. Different behavior.

## Running it

```python
with AgentRuntime() as runtime:
    result = runtime.run(
        pipeline,
        "How should a developer tools company get its first 1,000 users?",
    )
    result.print_result()
```

Every run produces a different conversation because the agent selection is random. Run it twice and you get two different brainstorming sessions. That is the point.

## When to use random

Random is not a strategy for everything. It is specifically useful when:

- **Brainstorming** — you want diverse, unpredictable perspectives
- **Load balancing across models** — distribute prompts across GPT-4o, Claude, Gemini randomly to compare output quality
- **Stress testing** — randomly select different scenarios to hit an agent with
- **Creative writing** — different voices or styles contribute randomly to a collaborative piece

If you need every agent to participate equally, use round robin. If you need one specific agent, use handoff or router. Random is for when variety itself is the goal.

## How durability works

The random selection is made server-side and persisted. If your process crashes after turn 4:

1. Turns 1–4 and their random selections are persisted on the server.
2. You restart your script.
3. Turns 5–6 continue with new random selections — the first 4 are not re-run.

## Composability

Random composes with other strategies:

```python
# Random brainstorm, then structured review
brainstorm = Agent(agents=[creative, practical, critical], strategy=Strategy.RANDOM, max_turns=6)
review = Agent(agents=[architect, security], strategy=Strategy.ROUND_ROBIN, max_turns=4)

pipeline = brainstorm >> review >> summarizer
```

Random generates ideas. Round robin reviews them. The summarizer produces the final output. Three strategies, one pipeline.

## Try it

```bash
pip install agentspan
agentspan server start
python 07_brainstorm_random.py
```

- **GitHub**: [github.com/agentspan-ai/agentspan](https://github.com/agentspan-ai/agentspan)
- **Blog examples**: [github.com/agentspan-ai/agentspan/tree/main/sdk/python/examples/blog_and_videos/random](https://github.com/agentspan-ai/agentspan/tree/main/sdk/python/examples/blog_and_videos/random)
- **Docs**: [agentspan.ai/docs](https://agentspan.ai/docs)
- **Discord**: [https://discord.com/invite/ajcA66JcKq](https://discord.com/invite/ajcA66JcKq)

## What's next

**Part 7: Manual** — The human picks which agent speaks next. No LLM deciding, no classifier, no randomness — full human control over the orchestration.
