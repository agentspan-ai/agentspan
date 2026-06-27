# LangChain4j

Use LangChain4j `@Tool`-annotated POJOs directly with Conductor Agents. The bridge reflects your annotated methods, builds a JSON Schema from the parameter types, and registers each method as a Conductor worker task.

## Dependency

```groovy
implementation 'org.conductoross.conductor:conductor-agent-sdk:0.1.0'
compileOnly 'dev.langchain4j:langchain4j:1.0.0'
```

## Usage

```java
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.agent.tool.P;
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.frameworks.LangChain4jAgent;

// Your existing LangChain4j tool POJO — no changes needed
public class CalculatorTools {

    @Tool("Add two integers and return the result")
    public int add(@P("a") int a, @P("b") int b) {
        return a + b;
    }

    @Tool("Look up the current stock price for a ticker symbol")
    public double stockPrice(@P("ticker") String ticker) {
        return fetchPrice(ticker);
    }
}

// Wrap with LangChain4jAgent
Agent agent = LangChain4jAgent.from(
    "calculator_agent",                         // agent name
    "openai/gpt-4o-mini",                       // model
    "You can perform math and look up prices.", // instructions
    new CalculatorTools()                       // one or more tool POJOs
);

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "What is 7 plus 8?");
    System.out.println(result.getOutput());
}
```

## Detection

Check whether an object has LangChain4j `@Tool` methods:

```java
boolean isTools = LangChain4jAgent.isLangChain4jTools(new CalculatorTools()); // true
boolean isTools = LangChain4jAgent.isLangChain4jTools(new Object());           // false
```

## What gets mapped

| LangChain4j annotation | Conductor Agents mapping |
|---|---|
| `@Tool("description")` | Tool name = method name; description = annotation value |
| `@Tool(name="x", value="desc")` | Tool name = `x`; description = `desc` |
| `@P("paramName")` | JSON Schema property name |
| Method return type | Output schema |

## Using with LangChainBridge

For `ChatModel`-based agents (not `@Tool` POJOs):

```java
import dev.langchain4j.model.chat.ChatModel;
import org.conductoross.conductor.ai.frameworks.LangChainBridge;

ChatModel model = OpenAiChatModel.builder()
    .apiKey(System.getenv("OPENAI_API_KEY"))
    .modelName("gpt-4o-mini")
    .build();

Agent agent = LangChainBridge.agentBuilder("lc_agent", model, "You are helpful.")
    .tools(ToolRegistry.fromInstance(new SearchTools()))
    .build();
```
