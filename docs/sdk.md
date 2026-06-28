---
title: SDK Overview
description: Conductor agent SDK — coordinates, Agent 101, and framework integrations for Python, TypeScript, Java, and C#.
---

# SDK Overview

The Conductor agent SDK lets you build and run Agentspan agents in four languages. Install the package, point it at an Agentspan server, and you're running agents in under 30 seconds.

## Quick reference

| Language | Install | Import | Full docs |
|---|---|---|---|
| **Python** | `pip install conductor-agent-sdk` | `from conductor.ai.agents import Agent, AgentRuntime` | [Python SDK](python-sdk/README.md) |
| **TypeScript** | `npm install @conductoross/conductor-agent-sdk` | `import { Agent, AgentRuntime } from '@conductoross/conductor-agent-sdk'` | [TypeScript SDK](typescript-sdk/README.md) |
| **Java** | `org.conductoross.conductor:conductor-agent-sdk:0.1.0` | `import org.conductoross.conductor.ai.*` | [Java SDK](java-sdk/index.md) |
| **C#** | `dotnet add package conductor-agent-sdk` | `using Conductor.AI;` | [C# SDK](csharp-sdk/README.md) |

## Environment setup

All SDKs read the same environment variables:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export OPENAI_API_KEY=<YOUR-KEY>
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
```

Start a local server:

```bash
agentspan server start   # downloads the runtime jar on first run, starts on :6767
```

---

## Agent 101

The minimal loop: define an `Agent`, open a runtime, call `run`.

=== "Python"

    ```python
    from conductor.ai.agents import Agent, AgentRuntime, tool

    @tool
    def get_weather(city: str) -> str:
        """Return current weather for a city."""
        return f"72°F and sunny in {city}"

    agent = Agent(
        name="weather_agent",
        model="anthropic/claude-sonnet-4-6",
        instructions="You are a helpful assistant. Use available tools.",
        tools=[get_weather],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(agent, "What's the weather in San Francisco?")
        result.print_result()
    ```

=== "TypeScript"

    ```ts
    import { Agent, AgentRuntime, tool } from '@conductoross/conductor-agent-sdk';
    import { z } from 'zod';

    const getWeather = tool({
      name: 'get_weather',
      description: 'Return current weather for a city.',
      parameters: z.object({ city: z.string() }),
      execute: async ({ city }) => `72°F and sunny in ${city}`,
    });

    const agent = new Agent({
      name: 'weather_agent',
      model: 'anthropic/claude-sonnet-4-6',
      instructions: 'You are a helpful assistant. Use available tools.',
      tools: [getWeather],
    });

    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(agent, "What's the weather in San Francisco?");
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
    ```

=== "Java"

    ```java
    import org.conductoross.conductor.ai.Agent;
    import org.conductoross.conductor.ai.AgentRuntime;
    import org.conductoross.conductor.ai.tool.Tool;

    public class WeatherExample {
        @Tool(description = "Return current weather for a city.")
        public static String getWeather(String city) {
            return "72°F and sunny in " + city;
        }

        public static void main(String[] args) throws Exception {
            Agent agent = Agent.builder()
                .name("weather_agent")
                .model("anthropic/claude-sonnet-4-6")
                .instructions("You are a helpful assistant. Use available tools.")
                .tools(WeatherExample.class)
                .build();

            try (AgentRuntime runtime = new AgentRuntime()) {
                var result = runtime.run(agent, "What's the weather in San Francisco?");
                result.printResult();
            }
        }
    }
    ```

=== "C#"

    ```csharp
    using Conductor.AI;
    using Conductor.AI.Tools;

    [AgentTools]
    public static class WeatherTools
    {
        [AgentTool(Description = "Return current weather for a city.")]
        public static string GetWeather(string city) =>
            $"72°F and sunny in {city}";
    }

    var agent = new Agent("weather_agent")
    {
        Model        = "anthropic/claude-sonnet-4-6",
        Instructions = "You are a helpful assistant. Use available tools.",
        Tools        = ToolRegistry.FromType<WeatherTools>(),
    };

    await using var runtime = new AgentRuntime();
    var result = await runtime.RunAsync(agent, "What's the weather in San Francisco?");
    result.PrintResult();
    ```

---

## What `run()` returns

All four SDKs return an `AgentResult` with the same fields:

| Field | Description |
|---|---|
| `output` / `Output` | Final text response from the agent |
| `execution_id` / `ExecutionId` | Server-side workflow execution ID — use to poll, stream, or inspect |
| `status` | `COMPLETED`, `FAILED`, `TIMED_OUT` |
| `usage` | Token counts (input, output, total) |
| `print_result()` / `PrintResult()` | Pretty-print to stdout |

---

## Framework agents

You don't have to rewrite agents authored in another framework. Pass the framework object directly to `runtime.run()` — the runtime auto-detects the framework and runs it on Agentspan.

### LangGraph

=== "Python"

    ```python
    import math
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
    from conductor.ai.agents import AgentRuntime

    @tool
    def calculate(expression: str) -> str:
        """Evaluate a safe math expression."""
        return str(eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi}))

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    graph = create_react_agent(llm, tools=[calculate], name="math_agent")

    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What is sqrt(256) + 2**10?")
        result.print_result()
    ```

=== "TypeScript"

    ```ts
    import { createReactAgent } from '@langchain/langgraph/prebuilt';
    import { ChatOpenAI } from '@langchain/openai';
    import { tool } from '@langchain/core/tools';
    import { z } from 'zod';
    import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

    const calculate = tool(
      async ({ expression }) => String(eval(expression)),
      { name: 'calculate', description: 'Evaluate a math expression.',
        schema: z.object({ expression: z.string() }) }
    );

    const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
    const graph = createReactAgent({ llm, tools: [calculate], name: 'math_agent' });

    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(graph, 'What is sqrt(256) + 2**10?');
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
    ```

=== "Java (LangGraph4j)"

    ```java
    import dev.langchain4j.model.openai.OpenAiChatModel;
    import org.bsc.langgraph4j.agentexecutor.AgentExecutor;
    import org.conductoross.conductor.ai.AgentRuntime;

    var model = OpenAiChatModel.builder()
        .apiKey("agentspan-server-handles-credentials")
        .modelName("anthropic/claude-sonnet-4-6")
        .build();

    AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);

    try (AgentRuntime runtime = new AgentRuntime()) {
        var result = runtime.run(agent, "What is sqrt(256) + 2**10?");
        result.printResult();
    }
    ```

---

### LangChain

=== "Python"

    ```python
    from conductor.ai.agents import AgentRuntime
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    @tool
    def lookup_order(order_id: str) -> str:
        """Look up an order by ID."""
        return f"Order {order_id}: shipped, arriving tomorrow."

    llm = ChatOpenAI(model="gpt-4o-mini")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an order support assistant."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    lc_agent = create_tool_calling_agent(llm, [lookup_order], prompt)
    executor = AgentExecutor(agent=lc_agent, tools=[lookup_order])

    with AgentRuntime() as runtime:
        result = runtime.run(executor, "Where is order #12345?")
        result.print_result()
    ```

=== "TypeScript"

    ```ts
    import { createAgentExecutor } from '@conductoross/conductor-agent-sdk/langchain';
    import { AgentRuntime } from '@conductoross/conductor-agent-sdk';
    import { ChatOpenAI } from '@langchain/openai';
    import { tool } from '@langchain/core/tools';
    import { z } from 'zod';

    const lookupOrder = tool(
      async ({ orderId }) => `Order ${orderId}: shipped, arriving tomorrow.`,
      { name: 'lookup_order', description: 'Look up an order.',
        schema: z.object({ orderId: z.string() }) }
    );

    const llm = new ChatOpenAI({ model: 'gpt-4o-mini' });
    const executor = createAgentExecutor({ llm, tools: [lookupOrder] });

    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(executor, 'Where is order #12345?');
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
    ```

---

### OpenAI Agents SDK

=== "Python"

    ```python
    from conductor.ai import Runner          # drop-in: replaces `from agents import Runner`
    from agents import Agent, function_tool

    @function_tool
    def get_weather(city: str) -> str:
        return f"72°F and sunny in {city}"

    agent = Agent(
        name="weather_assistant",
        model="gpt-4o",
        tools=[get_weather],
        instructions="You are a helpful assistant.",
    )

    result = Runner.run_sync(agent, "What's the weather in NYC?")
    print(result.final_output)
    ```

    One import change — everything else stays as written.

=== "TypeScript"

    ```ts
    import { Agent, setTracingDisabled } from '@openai/agents';
    import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

    setTracingDisabled(true);

    const agent = new Agent({
      name: 'support_agent',
      instructions: 'You are a helpful support assistant.',
      model: 'gpt-4o',
    });

    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(agent, 'How do I reset my password?');
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
    ```

=== "Java"

    ```java
    import org.conductoross.conductor.ai.Agent;
    import org.conductoross.conductor.ai.AgentRuntime;
    import org.conductoross.conductor.ai.Strategy;

    // OpenAI Agents SDK agents are expressed as native Agentspan agents
    // with Strategy.HANDOFF for multi-agent handoffs
    Agent agent = Agent.builder()
        .name("support_agent")
        .model("gpt-4o")
        .instructions("You are a helpful support assistant.")
        .strategy(Strategy.HANDOFF)
        .build();

    try (AgentRuntime runtime = new AgentRuntime()) {
        var result = runtime.run(agent, "How do I reset my password?");
        result.printResult();
    }
    ```

---

### Google ADK

=== "Python"

    ```python
    from google.adk.agents import LlmAgent
    from google.adk.tools import FunctionTool
    from conductor.ai.agents import AgentRuntime

    def get_weather(city: str) -> dict:
        """Get current weather for a city."""
        return {"city": city, "condition": "Sunny", "temp_c": 22}

    adk_agent = LlmAgent(
        name="weather_agent",
        model="gemini-2.0-flash",
        instruction="Answer weather questions using tools.",
        tools=[FunctionTool(func=get_weather)],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(adk_agent, "What's the weather in Tokyo?")
        result.print_result()
    ```

=== "TypeScript"

    ```ts
    import { LlmAgent } from '@google/adk';
    import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

    const agent = new LlmAgent({
      name: 'weather_agent',
      model: 'gemini-2.0-flash',
      instruction: 'Answer weather questions using available tools.',
    });

    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(agent, "What's the weather in Tokyo?");
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
    ```

=== "Java"

    ```java
    import com.google.adk.agents.LlmAgent;
    import org.conductoross.conductor.ai.AgentRuntime;
    import org.conductoross.conductor.ai.frameworks.AdkBridge;

    LlmAgent adkAgent = LlmAgent.builder()
        .name("weather_agent")
        .model("gemini-2.0-flash")
        .instruction("Answer weather questions.")
        .build();

    try (AgentRuntime runtime = new AgentRuntime()) {
        var result = runtime.run(AdkBridge.toAgentspan(adkAgent), "What's the weather in Tokyo?");
        result.printResult();
    }
    ```

---

### Vercel AI SDK

=== "TypeScript"

    **Option 1 — Use AI SDK tools on a native Agent (recommended):**

    The Conductor agent SDK auto-detects Vercel AI SDK `tool()` objects — no wrapper needed.

    ```ts
    import { tool as aiTool } from 'ai';
    import { z } from 'zod';
    import { Agent, AgentRuntime } from '@conductoross/conductor-agent-sdk';

    const getWeather = aiTool({
      description: 'Get current weather for a city.',
      parameters: z.object({ city: z.string() }),
      execute: async ({ city }) => ({ city, tempF: 72, condition: 'Sunny' }),
    });

    const agent = new Agent({
      name: 'weather_agent',
      model: 'anthropic/claude-sonnet-4-6',
      instructions: 'Use tools to answer weather questions.',
      tools: [getWeather],
    });

    const runtime = new AgentRuntime();
    try {
      const result = await runtime.run(agent, "What's the weather in SF?");
      result.printResult();
    } finally {
      await runtime.shutdown();
    }
    ```

    **Option 2 — Drop-in `generateText`:**

    ```ts
    import { generateText } from '@conductoross/conductor-agent-sdk/vercel-ai';

    const { text } = await generateText({
      model: 'anthropic/claude-sonnet-4-6',
      prompt: 'Write a haiku about durable execution.',
    });
    console.log(text);
    ```

---

## Next steps

- [Why Agentspan](why-agentspan.md) — the case for server-side execution
- [Quickstart](quickstart.md) — full local setup in 60 seconds
- [Plan-Execute](concepts/plan-execute.md) — dynamic agents with deterministic execution
- [Scheduling](scheduling.md) — cron-triggered agents
- Per-SDK deep dives: [Python](python-sdk/README.md) · [TypeScript](typescript-sdk/README.md) · [Java](java-sdk/index.md) · [C#](csharp-sdk/README.md)
