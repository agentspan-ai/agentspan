# Spring Boot

The `conductor-ai-sdk-spring` module provides Spring Boot auto-configuration. Add it and your `AgentRuntime` is wired automatically from `application.properties`.

## Dependency

=== "Gradle"

    ```groovy
    implementation 'org.conductoross.conductor:conductor-ai-sdk-spring:0.1.0'
    ```

=== "Maven"

    ```xml
    <dependency>
        <groupId>org.conductoross.conductor</groupId>
        <artifactId>conductor-ai-sdk-spring</artifactId>
        <version>0.1.0</version>
    </dependency>
    ```

This pulls in both `conductor-ai-sdk` and `conductor-client-spring` (which wires the `ApiClient`).

## Configuration

```properties
# application.properties

# Conductor server — from conductor-client-spring
conductor.root-uri=http://localhost:6767/api
conductor.security.client.key-id=your-key      # optional
conductor.security.client.secret=your-secret   # optional

# Agentspan worker tuning
agentspan.worker-poll-interval-ms=100
agentspan.worker-thread-count=1
```

## Inject and use

```java
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.Agent;
import org.springframework.stereotype.Service;

@Service
public class ChatService {

    private final AgentRuntime runtime;

    public ChatService(AgentRuntime runtime) {
        this.runtime = runtime;
    }

    public String answer(String question) {
        Agent agent = Agent.builder()
            .name("assistant")
            .model("openai/gpt-4o-mini")
            .instructions("You are a helpful assistant.")
            .build();

        return runtime.run(agent, question).getOutput();
    }
}
```

## Declare agents on beans with @AgentDef

Any Spring bean can declare agents with [`@AgentDef` methods](concepts/agents.md#agentdef-annotation). The auto-configured `AgentCatalog` collects them from every bean in the context:

```java
import org.conductoross.conductor.ai.annotations.AgentDef;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.spring.AgentCatalog;

@Component
public class SupportCrew {

    @Tool(description = "Look up an order by id")
    public String lookupOrder(String orderId) { ... }

    @AgentDef(model = "openai/gpt-4o")          // lookupOrder attaches automatically
    public String support() {
        return "You handle support tickets.";
    }
}

@Service
public class TicketService {
    private final AgentRuntime runtime;
    private final AgentCatalog agents;

    public TicketService(AgentRuntime runtime, AgentCatalog agents) {
        this.runtime = runtime;
        this.agents = agents;
    }

    public String answer(String ticket) {
        return runtime.run(agents.get("support"), ticket).getOutput().toString();
    }
}
```

The catalog scans lazily on first access; only beans whose class declares `@AgentDef` methods are touched. Duplicate agent names across beans fail fast with both bean names in the error. Proxied beans (e.g. `@Transactional`) work — discovery looks through the proxy subclass to the annotated declaration, and invocation goes through the proxy.

## Beans provided

| Bean type | Bean name | Condition |
|---|---|---|
| `ApiClient` | `orkesConductorClient` | From `conductor-client-spring`; `@ConditionalOnMissingBean` |
| `AgentConfig` | `agentspanConfig` | From `agentspan.*` properties; `@ConditionalOnMissingBean` |
| `AgentRuntime` | `agentRuntime` | Wires `ApiClient` + `AgentConfig`; `@ConditionalOnMissingBean` |
| `AgentCatalog` | `agentCatalog` | Collects `@AgentDef` agents from all beans; `@ConditionalOnMissingBean` |

All beans are `@ConditionalOnMissingBean` — declare your own to override any of them.

## Override the ApiClient

To connect to multiple servers or use custom TLS:

```java
@Configuration
public class MyAgentspanConfig {

    @Bean
    public ApiClient agentspanClient() {
        return AgentRuntime.client("http://myserver:6767", "key", "secret");
    }
}
```

## Override AgentConfig

```java
@Bean
public AgentConfig agentspanConfig() {
    return new AgentConfig(500, 4);   // 500ms poll, 4 worker threads
}
```

## Graceful shutdown

`AgentRuntime` is `AutoCloseable`. Spring calls `close()` on context shutdown automatically when it is a Spring-managed bean — worker threads stop and HTTP connections are released cleanly.
