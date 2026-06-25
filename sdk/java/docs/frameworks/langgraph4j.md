# LangGraph4j

Run a [LangGraph4j](https://github.com/bsorrentino/langgraph4j) `AgentExecutor` on the durable
Agentspan runtime. Hand the runtime a native `AgentExecutor.Builder` and it recovers the
configured `ChatModel` (and system message, if any), then runs the agent server-side.

## Dependency

```groovy
implementation 'org.conductoross.conductor:conductor-ai-sdk:0.1.0'
compileOnly 'dev.langchain4j:langchain4j:1.0.0'
compileOnly 'dev.langchain4j:langchain4j-open-ai:1.0.0'
compileOnly 'org.bsc.langgraph4j:langgraph4j-core:1.6.0-beta5'
compileOnly 'org.bsc.langgraph4j:langgraph4j-agent-executor:1.6.0-beta5'
```

## Usage (drop-in)

The runtime accepts the native `AgentExecutor.Builder` directly — no Agentspan types required.

```java
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import org.bsc.langgraph4j.agentexecutor.AgentExecutor;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.model.AgentResult;

// apiKey is required by the LangChain4j builder but unused — Agentspan runs the
// LLM call on the server using server-registered credentials.
ChatModel model = OpenAiChatModel.builder()
    .apiKey("agentspan-server-handles-credentials")
    .modelName("gpt-4o-mini")
    .build();

AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "Tell me a fun fact about state machines.");
    result.printResult();
}
```

`run`, `start`, and `stream` all accept the `AgentExecutor.Builder` drop-in. To attach `@Tool`
POJOs, pass them as trailing arguments — `runtime.run(agent, prompt, new MyTools())`.

The builder must have a `chatModel` set (the runtime fails fast otherwise) and must build into a
valid LangGraph4j `StateGraph` — the runtime validates this before submitting the agent.

## See also

- [LangChain4j](langchain4j.md) — for `@Tool`-POJO agents and `ChatModel` + `LangChainBridge`.
