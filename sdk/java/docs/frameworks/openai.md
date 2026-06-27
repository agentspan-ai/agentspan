# OpenAI Agents SDK

Use the Conductor Agents Java SDK with OpenAI Agents SDK-style tool definitions. The `OpenAIAgent` bridge accepts `@Tool`-annotated POJOs and registers them as Conductor worker tasks, routing the agent through the server's `OpenAINormalizer`.

## Dependency

```groovy
implementation 'org.conductoross.conductor:conductor-agent-sdk:0.1.0'
```

The bridge uses the LangChain4j `@Tool` annotation as a practical equivalent of the Python OpenAI Agents SDK `@function_tool` decorator — add it if you need the annotation:

```groovy
compileOnly 'dev.langchain4j:langchain4j:1.0.0'
```

## Usage

```java
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.agent.tool.P;
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.frameworks.OpenAIAgent;

public class ShoppingTools {

    @Tool(name = "search_products", value = "Search for products by keyword")
    public String searchProducts(@P("query") String query, @P("maxResults") int maxResults) {
        return callSearchApi(query, maxResults);
    }

    @Tool(name = "add_to_cart", value = "Add a product to the shopping cart")
    public String addToCart(@P("productId") String productId, @P("quantity") int quantity) {
        return cartService.add(productId, quantity);
    }
}

Agent agent = OpenAIAgent.builder()
    .name("shopping_assistant")
    .model("openai/gpt-4o-mini")
    .instructions("Help users find and purchase products.")
    .tools(new ShoppingTools())
    .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "Find me a blue jacket under $100");
    System.out.println(result.getOutput());
}
```

## Handoffs

OpenAI Agents SDK-style handoffs let the LLM transfer control to a specialist agent:

```java
Agent billingAgent = Agent.builder()
    .name("billing_agent")
    .model("openai/gpt-4o-mini")
    .instructions("Handle billing and payment questions.")
    .build();

Agent supportAgent = OpenAIAgent.builder()
    .name("support_agent")
    .model("openai/gpt-4o-mini")
    .instructions("Handle general support. Transfer billing issues to the billing agent.")
    .handoffs(billingAgent)                      // adds billing_agent as a handoff target
    .build();
```

## Structured output

```java
Agent agent = OpenAIAgent.builder()
    .name("classifier")
    .model("openai/gpt-4o-mini")
    .instructions("Classify the sentiment of the input.")
    .outputType("SentimentResult")               // server-side structured output type name
    .build();
```

## Builder reference

| Method | Description |
|---|---|
| `name(String)` | **Required.** Agent and workflow name. |
| `model(String)` | **Required.** `"provider/model"` string. |
| `instructions(String)` | System prompt. |
| `tools(Object...)` | `@Tool`-annotated POJOs; each method becomes a worker task. |
| `handoffs(Agent...)` | Sub-agents the LLM can hand off to. |
| `outputType(String)` | Structured output type name for the server normalizer. |
