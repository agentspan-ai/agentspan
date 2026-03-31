# Java SDK Translation Guide

**Date:** 2026-03-23
**Status:** Draft
**Base Spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`
**Reference Implementation:** `sdk/python/examples/kitchen_sink.py`

This guide covers implementing the Agentspan SDK in Java with full feature parity against the Python reference. It addresses **two** target audiences simultaneously: projects on Java 16+ (records, sealed interfaces, pattern matching) and projects constrained to Java 8+ (POJOs, Lombok optional). Every section shows both styles side-by-side.

---

## 1. Project Setup

### 1.1 Module Coordinates

```
groupId:    dev.agentspan
artifactId: agentspan-sdk
version:    0.1.0
```

### 1.2 Maven Configuration

```xml
<project>
  <groupId>dev.agentspan</groupId>
  <artifactId>agentspan-sdk</artifactId>
  <version>0.1.0</version>

  <properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
    <jackson.version>2.17.0</jackson.version>
  </properties>

  <dependencies>
    <!-- JSON serialization -->
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>${jackson.version}</version>
    </dependency>
    <dependency>
      <groupId>com.fasterxml.jackson.datatype</groupId>
      <artifactId>jackson-datatype-jdk8</artifactId>
      <version>${jackson.version}</version>
    </dependency>

    <!-- HTTP client (Java 8 baseline) -->
    <dependency>
      <groupId>org.apache.httpcomponents.client5</groupId>
      <artifactId>httpclient5</artifactId>
      <version>5.3</version>
    </dependency>

    <!-- Conductor client -->
    <dependency>
      <groupId>io.orkes.conductor</groupId>
      <artifactId>orkes-conductor-client</artifactId>
      <version>4.0.1</version>
    </dependency>

    <!-- SLF4J logging -->
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.12</version>
    </dependency>

    <!-- Testing -->
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <profiles>
    <!-- Java 11+: Use built-in HttpClient instead of Apache -->
    <profile>
      <id>java11</id>
      <activation>
        <jdk>[11,)</jdk>
      </activation>
      <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
      </properties>
    </profile>

    <!-- Java 16+: Enable records -->
    <profile>
      <id>java16</id>
      <activation>
        <jdk>[16,)</jdk>
      </activation>
      <properties>
        <maven.compiler.source>16</maven.compiler.source>
        <maven.compiler.target>16</maven.compiler.target>
      </properties>
    </profile>

    <!-- Java 21+: Enable virtual threads -->
    <profile>
      <id>java21</id>
      <activation>
        <jdk>[21,)</jdk>
      </activation>
      <properties>
        <maven.compiler.source>21</maven.compiler.source>
        <maven.compiler.target>21</maven.compiler.target>
      </properties>
    </profile>
  </profiles>
</project>
```

### 1.3 Gradle Alternative

Same dependencies as Maven. Use `com.github.johnrengelman.shadow` for fat JARs. Set `sourceCompatibility = JavaVersion.VERSION_1_8` as baseline.

### 1.4 Source Layout

```
src/main/java/dev/agentspan/
    Agentspan.java              // Top-level convenience API (configure, run, stream, ...)
    AgentRuntime.java           // Runtime lifecycle (AutoCloseable)
    agent/                      // Agent, AgentConfig, Strategy, PromptTemplate
    tool/                       // @Tool, ToolDef, ToolContext, HttpTool, McpTool,
                                //   AgentTool, HumanTool, MediaTools, RagTools
    guardrail/                  // @Guardrail, GuardrailResult, RegexGuardrail,
                                //   LLMGuardrail, OnFail, Position
    result/                     // AgentResult, AgentHandle, AgentStatus, AgentStream,
                                //   AsyncAgentStream, AgentEvent, EventType, Status,
                                //   FinishReason, TokenUsage, DeploymentInfo
    termination/                // TerminationCondition and all subclasses
    handoff/                    // HandoffCondition, OnToolResult, OnTextMention, OnCondition
    memory/                     // ConversationMemory, SemanticMemory, MemoryStore
    code/                       // CodeExecutionConfig, CodeExecutor (Local/Docker/Jupyter/Serverless)
    credential/                 // Credentials, CredentialFile
    callback/                   // CallbackHandler
    ext/                        // UserProxyAgent, GPTAssistantAgent
    gate/                       // GateCondition, TextGate
    cli/                        // CliConfig
    exception/                  // AgentspanException hierarchy
    internal/                   // SseClient, WorkerManager, HttpApi, JsonMapper
    testing/                    // MockRun, Expect, Recording
```

---

## 2. Type System Mapping

### 2.1 Primitive and Container Mapping

| Python | Java 16+ (record) | Java 8+ (POJO) |
|--------|-------------------|-----------------|
| `@dataclass` | `record` | `class` + getters (or `@lombok.Data`) |
| `str` | `String` | `String` |
| `int` | `int` / `Integer` | `int` / `Integer` |
| `float` | `double` / `Double` | `double` / `Double` |
| `bool` | `boolean` / `Boolean` | `boolean` / `Boolean` |
| `Optional[T]` | `Optional<T>` | `@Nullable T` (or `Optional<T>`) |
| `list[T]` | `List<T>` | `List<T>` |
| `dict[K, V]` | `Map<K, V>` | `Map<K, V>` |
| `Any` | `Object` | `Object` |
| `Callable[[A], R]` | `Function<A, R>` | `Function<A, R>` (Java 8+) |
| `Callable[[], R]` | `Supplier<R>` | `Supplier<R>` |
| `Callable[[A], None]` | `Consumer<A>` | `Consumer<A>` |
| `Union[A, B]` | `sealed interface` | Interface + instanceof checks |
| `enum(str, Enum)` | `enum` | `enum` |
| `BaseModel` (Pydantic) | Jackson `@JsonProperty` on record | Jackson `@JsonProperty` on POJO |

### 2.2 Core Type Definitions

#### Agent

**Record (Java 16+):**

```java
public record Agent(
    String name,
    @Nullable String model,
    @Nullable Object instructions,  // String | PromptTemplate | Supplier<String>
    List<ToolDef> tools,
    List<Agent> agents,
    @Nullable Strategy strategy,
    @Nullable Agent router,
    @Nullable Class<?> outputType,
    List<Guardrail> guardrails,
    @Nullable ConversationMemory memory,
    int maxTurns,
    @Nullable Integer maxTokens,
    @Nullable Double temperature,
    int timeoutSeconds,
    boolean external,
    @Nullable Function<List<Map<String, Object>>, Boolean> stopWhen,
    @Nullable TerminationCondition termination,
    List<HandoffCondition> handoffs,
    @Nullable Map<String, List<String>> allowedTransitions,
    @Nullable String introduction,
    @Nullable Map<String, Object> metadata,
    List<CallbackHandler> callbacks,
    boolean planner,
    @Nullable String includeContents,
    @Nullable Integer thinkingBudgetTokens,
    @Nullable List<String> requiredTools,
    @Nullable GateCondition gate,
    @Nullable CodeExecutionConfig codeExecutionConfig,
    @Nullable CliConfig cliConfig,
    @Nullable List<Object> credentials  // String | CredentialFile
) {
    public Agent {
        if (tools == null) tools = List.of();
        if (agents == null) agents = List.of();
        if (guardrails == null) guardrails = List.of();
        if (handoffs == null) handoffs = List.of();
        if (callbacks == null) callbacks = List.of();
        if (maxTurns <= 0) maxTurns = 25;
    }

    /** Chaining: agent1.then(agent2) creates a sequential pipeline. */
    public Agent then(Agent next) {
        return Agent.builder()
            .name(this.name + "_seq_" + next.name)
            .agents(List.of(this, next))
            .strategy(Strategy.SEQUENTIAL)
            .build();
    }
}
```

**POJO (Java 8+):** Same fields as the record, all `private final`. Private constructor takes a `Builder`. Standard getters (`getName()`, `getModel()`, etc.). Null collections default to `Collections.emptyList()`. Same `.then()` method for chaining. Static `builder()` factory method returns `Agent.Builder` (see Section 3).

#### ToolContext

**Record:**
```java
public record ToolContext(
    String sessionId,
    String executionId,
    String agentName,
    Map<String, Object> metadata,
    Map<String, Object> dependencies,
    Map<String, Object> state
) {}
```

**POJO:** Same fields as record, with `private final` fields, all-args constructor, and standard getters (`getSessionId()`, `getExecutionId()`, etc.). Null maps default to `Collections.emptyMap()`.

#### AgentResult

**Record:**
```java
public record AgentResult(
    Object output,
    String executionId,
    @Nullable String correlationId,
    List<Map<String, Object>> messages,
    List<Map<String, Object>> toolCalls,
    Status status,
    @Nullable FinishReason finishReason,
    @Nullable String error,
    @Nullable TokenUsage tokenUsage,
    @Nullable Map<String, Object> metadata,
    List<AgentEvent> events,
    @Nullable Map<String, Object> subResults
) {
    public boolean isSuccess() { return status == Status.COMPLETED; }
    public boolean isFailed() { return status == Status.FAILED; }
    public boolean isRejected() { return finishReason == FinishReason.REJECTED; }
}
```

**POJO:** Same fields with `private final`, standard getters, and the same three convenience methods (`isSuccess()`, `isFailed()`, `isRejected()`).

#### GuardrailResult

**Record:**
```java
public record GuardrailResult(boolean passed, @Nullable String message, @Nullable String fixedOutput) {
    public static GuardrailResult pass() { return new GuardrailResult(true, null, null); }
    public static GuardrailResult fail(String message) { return new GuardrailResult(false, message, null); }
    public static GuardrailResult fix(String fixedOutput) { return new GuardrailResult(false, null, fixedOutput); }
}
```

**POJO:**
```java
public class GuardrailResult {
    private final boolean passed;
    private final String message;
    private final String fixedOutput;

    private GuardrailResult(boolean passed, String message, String fixedOutput) {
        this.passed = passed; this.message = message; this.fixedOutput = fixedOutput;
    }

    public static GuardrailResult pass() { return new GuardrailResult(true, null, null); }
    public static GuardrailResult fail(String message) { return new GuardrailResult(false, message, null); }
    public static GuardrailResult fix(String fixedOutput) { return new GuardrailResult(false, null, fixedOutput); }

    public boolean isPassed() { return passed; }
    public String getMessage() { return message; }
    public String getFixedOutput() { return fixedOutput; }
}
```

#### Enums (Identical for Both Styles)

```java
public enum Strategy {
    @JsonProperty("handoff")     HANDOFF,
    @JsonProperty("sequential")  SEQUENTIAL,
    @JsonProperty("parallel")    PARALLEL,
    @JsonProperty("router")      ROUTER,
    @JsonProperty("round_robin") ROUND_ROBIN,
    @JsonProperty("random")      RANDOM,
    @JsonProperty("swarm")       SWARM,
    @JsonProperty("manual")      MANUAL;
}

public enum EventType {
    THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING,
    MESSAGE, ERROR, DONE, GUARDRAIL_PASS, GUARDRAIL_FAIL;
}

public enum OnFail {
    @JsonProperty("retry") RETRY,
    @JsonProperty("raise") RAISE,
    @JsonProperty("fix")   FIX,
    @JsonProperty("human") HUMAN;
}

public enum Position {
    @JsonProperty("input")  INPUT,
    @JsonProperty("output") OUTPUT;
}

public enum Status { COMPLETED, FAILED, TERMINATED, TIMED_OUT; }
public enum FinishReason { STOP, LENGTH, TOOL_CALLS, ERROR, CANCELLED, TIMEOUT, GUARDRAIL, REJECTED; }

public record TokenUsage(int promptTokens, int completionTokens, int totalTokens) {}
// POJO equivalent: class with three int fields + getters
```

---

## 3. Annotations + Builder Pattern

Java offers two complementary definition styles: annotations on methods/classes and the builder pattern for programmatic construction. Both must produce identical AgentConfig JSON.

### 3.1 Annotations

#### @Tool

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Tool {
    String name() default "";
    String description() default "";
    boolean approvalRequired() default false;
    boolean external() default false;
    boolean isolated() default true;
    int timeoutSeconds() default 120;
    String[] credentials() default {};
}
```

Usage (identical across Java versions):

```java
public class ResearchTools {

    @Tool(credentials = {"RESEARCH_API_KEY"})
    public Map<String, Object> researchDatabase(String query, ToolContext ctx) {
        String session = ctx != null ? ctx.sessionId() : "unknown";
        return Map.of("query", query, "session_id", session, "results", List.of());
    }

    @Tool(isolated = false, credentials = {"ANALYTICS_KEY"})
    public Map<String, Object> analyzeTrends(String topic) {
        String key = Credentials.get("ANALYTICS_KEY");
        return Map.of("topic", topic, "trend_score", 0.87, "key_present", key != null);
    }

    @Tool(approvalRequired = true)
    public Map<String, Object> publishArticle(String title, String content, String platform) {
        return Map.of("status", "published", "title", title, "platform", platform);
    }

    @Tool(external = true)
    public Map<String, Object> externalResearchAggregator(String query, int sources) {
        throw new UnsupportedOperationException("External tool - runs on remote worker");
    }
}
```

The SDK annotation processor (or reflective scanner at runtime) extracts the method name, parameter types, and return type to generate JSON Schema for `inputSchema` and registers the method as a Conductor SIMPLE worker.

#### @AgentDef

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface AgentDef {
    String name();
    String model() default "";
    String instructions() default "";
}
```

Usage:

```java
@AgentDef(name = "tech_classifier", model = "openai/gpt-4o")
public class TechClassifier {
    /** Classifies tech articles. */
    public String classify(String prompt) { return null; /* runtime-managed */ }
}
```

#### @Guardrail

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Guardrail {
    String name() default "";
    Position position() default Position.OUTPUT;
    OnFail onFail() default OnFail.RAISE;
    int maxRetries() default 3;
}
```

Usage:

```java
public class SafetyGuardrails {

    @Guardrail(onFail = OnFail.HUMAN)
    public GuardrailResult factValidator(String content) {
        List<String> redFlags = List.of("the best", "always", "never", "guaranteed");
        List<String> found = redFlags.stream()
            .filter(rf -> content.toLowerCase().contains(rf.toLowerCase()))
            .collect(Collectors.toList());
        if (!found.isEmpty()) {
            return GuardrailResult.fail("Unverifiable claims: " + found);
        }
        return GuardrailResult.pass();
    }

    @Guardrail(position = Position.INPUT, onFail = OnFail.RAISE)
    public GuardrailResult sqlInjectionGuard(String content) {
        if (containsSqlInjection(content)) {
            return GuardrailResult.fail("SQL injection detected.");
        }
        return GuardrailResult.pass();
    }
}
```

### 3.2 Builder Pattern

The builder is the primary programmatic API. It works identically on Java 8+ and 16+.

```java
Agent intakeRouter = Agent.builder()
    .name("intake_router")
    .model("openai/gpt-4o")
    .instructions(PromptTemplate.of("article-classifier", Map.of("categories", "tech, business, creative")))
    .agents(List.of(techClassifier, businessClassifier, creativeClassifier))
    .strategy(Strategy.ROUTER)
    .router(Agent.builder()
        .name("category_router")
        .model("openai/gpt-4o")
        .instructions("Route to the appropriate classifier based on the article topic.")
        .build())
    .outputType(ClassificationResult.class)
    .build();
```

Builder for tools (server-side, no annotation needed):

```java
ToolDef webSearch = HttpTool.builder()
    .name("web_search")
    .description("Search the web for recent articles and papers.")
    .url("https://api.example.com/search")
    .method("GET")
    .headers(Map.of("Authorization", "Bearer ${SEARCH_API_KEY}"))
    .inputSchema(Map.of(
        "type", "object",
        "properties", Map.of("q", Map.of("type", "string")),
        "required", List.of("q")
    ))
    .credentials(List.of("SEARCH_API_KEY"))
    .build();

ToolDef mcpFactChecker = McpTool.builder()
    .serverUrl("http://localhost:3001/mcp")
    .name("fact_checker")
    .description("Verify factual claims using knowledge base.")
    .toolNames(List.of("verify_claim", "check_source"))
    .credentials(List.of("MCP_AUTH_TOKEN"))
    .build();

// Auto-discover from OpenAPI/Swagger/Postman spec
var stripe = ApiTool.builder()
    .url("https://api.stripe.com/openapi.json")
    .header("Authorization", "Bearer ${STRIPE_KEY}")
    .credentials("STRIPE_KEY")
    .maxTools(20)
    .build();

ToolDef researchSubtool = AgentTool.of(
    Agent.builder().name("quick_researcher").model("openai/gpt-4o")
        .instructions("Do a quick research lookup on the given topic.").build(),
    "quick_research",
    "Quick research lookup as a tool."
);

ToolDef editorialQuestion = HumanTool.of(
    "ask_editor",
    "Ask the editor a question about the article.",
    Map.of("type", "object",
        "properties", Map.of("question", Map.of("type", "string")),
        "required", List.of("question"))
);
```

Builder for guardrails (server-side):

```java
Guardrail piiGuardrail = RegexGuardrail.builder()
    .name("pii_blocker")
    .patterns(List.of("\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b"))
    .mode("block")
    .position(Position.OUTPUT)
    .onFail(OnFail.RETRY)
    .message("PII detected. Redact all personal information.")
    .build();

Guardrail biasGuardrail = LLMGuardrail.builder()
    .name("bias_detector")
    .model("openai/gpt-4o-mini")
    .policy("Check for biased language or stereotypes. If found, provide corrected version.")
    .position(Position.OUTPUT)
    .onFail(OnFail.FIX)
    .maxTokens(10000)
    .build();
```

### 3.3 Termination Condition Composition

Python uses `|` and `&` operators. Java uses `.or()` and `.and()` methods:

```java
// Python: TextMentionTermination("PUBLISHED") | (MaxMessageTermination(50) & TokenUsageTermination(100000))
TerminationCondition termination = TextMentionTermination.of("PUBLISHED")
    .or(MaxMessageTermination.of(50).and(TokenUsageTermination.ofTotal(100000)));

// Python: TextMentionTermination("PIPELINE_COMPLETE") | MaxMessageTermination(200)
TerminationCondition pipelineTermination = TextMentionTermination.of("PIPELINE_COMPLETE")
    .or(MaxMessageTermination.of(200));
```

The `TerminationCondition` base class (or sealed interface on 16+) defines:

```java
// Java 16+
public sealed interface TerminationCondition
    permits TextMentionTermination, StopMessageTermination,
            MaxMessageTermination, TokenUsageTermination,
            AndTermination, OrTermination {

    default TerminationCondition and(TerminationCondition other) {
        return new AndTermination(List.of(this, other));
    }

    default TerminationCondition or(TerminationCondition other) {
        return new OrTermination(List.of(this, other));
    }
}

// Java 8+
public abstract class TerminationCondition {
    public TerminationCondition and(TerminationCondition other) {
        return new AndTermination(Arrays.asList(this, other));
    }
    public TerminationCondition or(TerminationCondition other) {
        return new OrTermination(Arrays.asList(this, other));
    }
}
```

---

## 4. Async Model

### 4.1 Core Principle

The internal implementation is async-native using `CompletableFuture<T>`. Sync methods delegate to async and call `.join()`.

### 4.2 Execution API Signatures

```java
public class AgentRuntime implements AutoCloseable {

    // --- Blocking (sync) ---
    public AgentResult run(Agent agent, String prompt) {
        return runAsync(agent, prompt).join();
    }

    public AgentHandle start(Agent agent, String prompt) {
        return startAsync(agent, prompt).join();
    }

    public AgentStream stream(Agent agent, String prompt) {
        return streamAsync(agent, prompt).join();
    }

    public DeploymentInfo deploy(Agent agent) {
        return deployAsync(agent).join();
    }

    // --- Async ---
    public CompletableFuture<AgentResult> runAsync(Agent agent, String prompt) { ... }

    public CompletableFuture<AgentHandle> startAsync(Agent agent, String prompt) { ... }

    public CompletableFuture<AgentStream> streamAsync(Agent agent, String prompt) { ... }

    public CompletableFuture<DeploymentInfo> deployAsync(Agent agent) { ... }

    // --- Other ---
    public ExecutionPlan plan(Agent agent) { ... }

    public void serve() { ... }  // Blocking: starts worker poll loop

    @Override
    public void close() { shutdown(); }

    public void shutdown() { ... }
}
```

### 4.3 AgentStream as Iterator

`AgentStream` implements `Iterable<AgentEvent>` for use in enhanced for-loops:

```java
public class AgentStream implements Iterable<AgentEvent>, AutoCloseable {
    private final String executionId;
    private final SseClient sseClient;
    private final List<AgentEvent> events = new ArrayList<>();

    @Override
    public Iterator<AgentEvent> iterator() { return new SseEventIterator(); }

    public AgentResult getResult() { /* drain + build result */ }

    // HITL methods
    public void approve() { ... }
    public void reject(String reason) { ... }
    public void send(String message) { ... }
    public void respond(Object output) { ... }

    @Override
    public void close() { sseClient.close(); }
}
```

Usage (matches Python `for event in agent_stream`):

```java
try (AgentStream agentStream = runtime.stream(pipeline, prompt)) {
    for (AgentEvent event : agentStream) {
        switch (event.type()) {
            case THINKING    -> System.out.println("[thinking] " + event.content());
            case TOOL_CALL   -> System.out.println("[tool_call] " + event.toolName());
            case WAITING     -> agentStream.approve();
            case DONE        -> System.out.println("[done]");
            default          -> {}
        }
    }
    AgentResult result = agentStream.getResult();
}
```

### 4.4 Java 8 Switch Equivalent

On Java 8 (no switch expressions), replace `switch` with `if (event.getType() == EventType.THINKING) { ... } else if ...` chains using getter methods (`getType()`, `getContent()`, etc.) instead of record accessors.

### 4.5 Virtual Threads (Java 21+)

When running on Java 21+, the worker manager should prefer virtual threads over platform threads for the Conductor poll loop:

```java
// Java 21+
ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

// Java 8-20
ExecutorService executor = Executors.newFixedThreadPool(
    Runtime.getRuntime().availableProcessors()
);
```

The SDK should detect the runtime version and select automatically.

### 4.6 Top-Level Convenience API

Static methods on the `Agentspan` class mirror Python's module-level functions:

```java
public final class Agentspan {
    private static volatile AgentRuntime singleton;

    public static void configure(AgentConfig config) { ... }
    public static AgentResult run(Agent agent, String prompt) { return getSingleton().run(agent, prompt); }
    public static CompletableFuture<AgentResult> runAsync(Agent agent, String prompt) { return getSingleton().runAsync(agent, prompt); }
    public static AgentHandle start(Agent agent, String prompt) { return getSingleton().start(agent, prompt); }
    public static AgentStream stream(Agent agent, String prompt) { return getSingleton().stream(agent, prompt); }
    public static DeploymentInfo deploy(Agent agent) { return getSingleton().deploy(agent); }
    public static void serve() { getSingleton().serve(); }
    public static ExecutionPlan plan(Agent agent) { return getSingleton().plan(agent); }
    public static void shutdown() { if (singleton != null) singleton.shutdown(); }

    private static AgentRuntime getSingleton() { /* lazy init */ }
}
```

---

## 5. Worker Implementation

Workers poll Conductor for tasks, execute the registered tool/guardrail/callback function, and report results back. This is the most runtime-critical component.

### 5.1 Worker Manager

```java
public class WorkerManager implements AutoCloseable {
    private final ScheduledExecutorService scheduler;
    private final Map<String, WorkerRegistration> workers = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;
    private final HttpApi httpApi;
    private final Duration pollInterval;

    public WorkerManager(AgentConfig config) {
        this.pollInterval = Duration.ofMillis(config.workerPollInterval());
        // Java 21+: Executors.newVirtualThreadPerTaskExecutor()
        // Java 8+:  Executors.newScheduledThreadPool(config.workerThreads())
        this.scheduler = createScheduler(config);
        this.mapper = JsonMapper.create();
        this.httpApi = new HttpApi(config);
    }

    public void register(String taskName, Function<Map<String, Object>, Object> handler,
                         List<String> credentials, boolean isolated) {
        workers.put(taskName, new WorkerRegistration(taskName, handler, credentials, isolated));
    }

    public void startAll() {
        for (WorkerRegistration reg : workers.values()) {
            scheduler.scheduleAtFixedRate(
                () -> pollAndExecute(reg),
                0, pollInterval.toMillis(), TimeUnit.MILLISECONDS
            );
        }
    }

    private void pollAndExecute(WorkerRegistration reg) {
        try {
            // 1. Poll Conductor for tasks
            Map<String, Object> task = httpApi.pollTask(reg.taskName());
            if (task == null) return;

            String taskId = (String) task.get("taskId");
            Map<String, Object> inputData = cast(task.get("inputData"));

            // 2. Extract ToolContext from __agentspan_ctx__
            ToolContext ctx = extractContext(inputData);
            inputData.remove("__agentspan_ctx__");

            // 3. Resolve credentials if declared
            Map<String, String> creds = Collections.emptyMap();
            if (!reg.credentials().isEmpty() && ctx != null) {
                creds = Credentials.resolve(ctx, reg.credentials());
            }

            // 4. Execute: isolated (subprocess) or in-process
            Object result;
            if (reg.isolated() && !creds.isEmpty()) {
                result = executeIsolated(reg.handler(), inputData, creds);
            } else {
                if (!creds.isEmpty()) {
                    Credentials.setThreadLocal(creds);
                }
                try {
                    result = reg.handler().apply(inputData);
                } finally {
                    Credentials.clearThreadLocal();
                }
            }

            // 5. Report success
            Map<String, Object> output = Map.of("result", mapper.writeValueAsString(result));
            httpApi.completeTask(taskId, output);

        } catch (Exception e) {
            log.error("Worker {} failed", reg.taskName(), e);
            // Report failure to Conductor
            httpApi.failTask(reg.taskName(), e.getMessage());
        }
    }

    private ToolContext extractContext(Map<String, Object> inputData) {
        Object raw = inputData.get("__agentspan_ctx__");
        if (raw == null) return null;
        return mapper.convertValue(raw, ToolContext.class);
    }

    @Override
    public void close() {
        scheduler.shutdownNow();
    }
}
```

### 5.2 Java 21+ Virtual Thread Variant

Detect `Runtime.version().feature() >= 21` and use `Executors.newVirtualThreadPerTaskExecutor()` instead of the `ScheduledThreadPool`. With virtual threads, each worker gets a dedicated virtual thread running a simple blocking poll loop (`pollTask` -> `processTask` -> `sleep`) instead of `scheduleAtFixedRate`.

---

## 6. SSE Client

### 6.1 Java 11+ Implementation (java.net.http)

```java
public class SseClient implements AutoCloseable {
    private final HttpClient httpClient;
    private final String streamUrl;
    private final Map<String, String> headers;
    private final BlockingQueue<AgentEvent> eventQueue = new LinkedBlockingQueue<>();
    private volatile String lastEventId = null;
    private volatile boolean closed = false;
    private final ObjectMapper mapper = JsonMapper.create();

    public SseClient(String serverUrl, String executionId, Map<String, String> authHeaders) {
        this.httpClient = HttpClient.newHttpClient();
        this.streamUrl = serverUrl + "/agent/stream/" + executionId;
        this.headers = authHeaders;
    }

    public void connect() {
        CompletableFuture.runAsync(this::streamLoop);
    }

    private void streamLoop() {
        while (!closed) {
            try {
                HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                    .uri(URI.create(streamUrl))
                    .header("Accept", "text/event-stream");

                headers.forEach(reqBuilder::header);

                if (lastEventId != null) {
                    reqBuilder.header("Last-Event-ID", lastEventId);
                }

                HttpResponse<Stream<String>> response = httpClient.send(
                    reqBuilder.GET().build(),
                    HttpResponse.BodyHandlers.ofLines()
                );

                parseSseStream(response.body());

            } catch (Exception e) {
                if (!closed) {
                    log.warn("SSE connection lost, reconnecting in 1s", e);
                    sleep(1000);
                }
            }
        }
    }

    private void parseSseStream(Stream<String> lines) {
        String currentEvent = null;
        String currentId = null;
        StringBuilder dataBuffer = new StringBuilder();

        lines.forEach(line -> {
            if (closed) return;

            if (line.startsWith(":")) {
                // Heartbeat comment -- ignore
                return;
            }
            if (line.startsWith("event:")) {
                currentEvent = line.substring(6).trim();
            } else if (line.startsWith("id:")) {
                currentId = line.substring(3).trim();
                lastEventId = currentId;
            } else if (line.startsWith("data:")) {
                dataBuffer.append(line.substring(5).trim());
            } else if (line.isEmpty() && dataBuffer.length() > 0) {
                // End of event -- dispatch
                dispatchEvent(currentEvent, dataBuffer.toString());
                currentEvent = null;
                dataBuffer.setLength(0);
            }
        });
    }

    private void dispatchEvent(String eventType, String data) {
        try {
            Map<String, Object> parsed = mapper.readValue(data, Map.class);
            AgentEvent event = AgentEvent.fromMap(eventType, parsed);
            eventQueue.put(event);
        } catch (Exception e) {
            log.warn("Failed to parse SSE event: {}", data, e);
        }
    }

    public AgentEvent nextEvent() throws InterruptedException {
        return eventQueue.take();  // blocks until event available
    }

    public AgentEvent nextEvent(long timeout, TimeUnit unit) throws InterruptedException {
        return eventQueue.poll(timeout, unit);
    }

    @Override
    public void close() {
        closed = true;
    }
}
```

### 6.2 Java 8+ Implementation (Apache HttpClient 5)

Same architecture as the Java 11 version but uses `CloseableHttpAsyncClient` from Apache HttpClient 5 with `AbstractCharResponseConsumer<Void>` for streaming character data. The SSE line-parsing logic (`:` heartbeat, `event:`, `id:`, `data:`, blank-line dispatch) is identical. Key differences:

- Use `HttpAsyncClients.createDefault()` with `.start()` for the async client.
- Implement `FutureCallback<Void>` on the execute call; on `failed()`, schedule a reconnect.
- Parse incoming `CharBuffer` data by accumulating into a line buffer and splitting on `\n`.
- Close with `httpClient.close(CloseMode.GRACEFUL)` on shutdown.

### 6.3 Key SSE Behaviors

- **Heartbeat filtering:** Lines beginning with `:` (e.g., `:heartbeat`) are silently dropped.
- **Reconnection:** On any connection drop, wait 1 second, then reconnect with `Last-Event-ID` set to the last received `id:` value. The server replays missed events from its 200-event / 5-minute buffer.
- **Completion detection:** When a `done` event is received, close the connection.
- **Polling fallback:** If only heartbeats arrive for 15 seconds (no real events), fall back to polling `GET /agent/{id}/status` at 500ms intervals.

---

## 7. Error Handling

### 7.1 Exception Hierarchy

```java
/**
 * Base exception. Extends RuntimeException (unchecked) because most callers
 * use CompletableFuture, which wraps checked exceptions in CompletionException.
 */
public class AgentspanException extends RuntimeException {
    public AgentspanException(String message) { super(message); }
    public AgentspanException(String message, Throwable cause) { super(message, cause); }
}

/** Server returned a non-2xx response. */
public class AgentAPIException extends AgentspanException {
    private final int statusCode;
    private final String responseBody;

    public AgentAPIException(int statusCode, String responseBody) {
        super("API error " + statusCode + ": " + responseBody);
        this.statusCode = statusCode;
        this.responseBody = responseBody;
    }

    public int getStatusCode() { return statusCode; }
    public String getResponseBody() { return responseBody; }
}

/** Invalid agent configuration. */
public class ConfigurationException extends AgentspanException {
    public ConfigurationException(String message) { super(message); }
}

/** Credential not found in store. */
public class CredentialNotFoundException extends AgentspanException {
    private final String credentialName;
    public CredentialNotFoundException(String name) {
        super("Credential not found: " + name);
        this.credentialName = name;
    }
    public String getCredentialName() { return credentialName; }
}

/** Execution token invalid or expired. */
public class CredentialAuthException extends AgentspanException {
    public CredentialAuthException(String message) { super(message); }
}

/** Credential resolution rate limit exceeded (120/min). */
public class CredentialRateLimitException extends AgentspanException {
    public CredentialRateLimitException() { super("Credential resolution rate limit exceeded (120/min)"); }
}

/** Credential service server error. */
public class CredentialServiceException extends AgentspanException {
    public CredentialServiceException(String message) { super(message); }
}

/** Guardrail failure (on_fail=RAISE). */
public class GuardrailFailedException extends AgentspanException {
    private final String guardrailName;
    private final GuardrailResult result;

    public GuardrailFailedException(String guardrailName, GuardrailResult result) {
        super("Guardrail '" + guardrailName + "' failed: " + result.message());
        this.guardrailName = guardrailName;
        this.result = result;
    }

    public String getGuardrailName() { return guardrailName; }
    public GuardrailResult getResult() { return result; }
}
```

### 7.2 Checked vs. Unchecked Strategy

All Agentspan exceptions are **unchecked** (`RuntimeException`). Rationale:

1. `CompletableFuture` wraps checked exceptions in `CompletionException`, forcing awkward unwrapping.
2. Most callers cannot meaningfully recover from server errors or missing credentials.
3. Java ecosystem trend (Spring, Jackson, etc.) favors unchecked exceptions for non-recoverable errors.

Users who want explicit handling can catch `AgentspanException` or its subtypes:

```java
try {
    AgentResult result = runtime.run(agent, prompt);
} catch (AgentAPIException e) {
    log.error("Server error {}: {}", e.getStatusCode(), e.getResponseBody());
} catch (CredentialNotFoundException e) {
    log.error("Missing credential: {}", e.getCredentialName());
} catch (AgentspanException e) {
    log.error("Agentspan error", e);
}
```

### 7.3 Async Error Handling

```java
runtime.runAsync(agent, prompt)
    .thenAccept(result -> {
        System.out.println("Output: " + result.output());
    })
    .exceptionally(ex -> {
        Throwable cause = ex.getCause();  // unwrap CompletionException
        if (cause instanceof AgentAPIException apiEx) {
            System.err.println("API error: " + apiEx.getStatusCode());
        } else if (cause instanceof ConfigurationException) {
            System.err.println("Config error: " + cause.getMessage());
        } else {
            System.err.println("Unexpected: " + cause.getMessage());
        }
        return null;
    });
```

Java 8 equivalent (no pattern matching):

```java
.exceptionally(ex -> {
    Throwable cause = ex.getCause();
    if (cause instanceof AgentAPIException) {
        AgentAPIException apiEx = (AgentAPIException) cause;
        System.err.println("API error: " + apiEx.getStatusCode());
    } else {
        System.err.println("Error: " + cause.getMessage());
    }
    return null;
});
```

---

## 8. Testing Framework

### 8.1 MockRun

`MockRun` executes an agent locally without a running server, suitable for unit tests.

```java
public class MockRun {

    /** Execute agent with mock server, returning a result. */
    public static AgentResult execute(Agent agent, String prompt) { ... }

    /** Execute and return the stream for event-level assertions. */
    public static AgentStream stream(Agent agent, String prompt) { ... }
}
```

Usage with JUnit 5:

```java
@Test
void testClassifier() {
    Agent classifier = Agent.builder()
        .name("test_classifier")
        .model("openai/gpt-4o")
        .instructions("Classify articles.")
        .outputType(ClassificationResult.class)
        .build();

    AgentResult result = MockRun.execute(classifier, "Write about quantum computing");

    Expect.that(result)
        .isCompleted()
        .outputContains("tech");
}
```

### 8.2 Expect (Fluent Assertions)

```java
public class Expect {
    public static AgentResultExpect that(AgentResult result) {
        return new AgentResultExpect(result);
    }

    public static class AgentResultExpect {
        private final AgentResult result;
        AgentResultExpect(AgentResult result) { this.result = result; }

        public AgentResultExpect isCompleted()               { assertEquals(Status.COMPLETED, result.status()); return this; }
        public AgentResultExpect isFailed()                  { assertEquals(Status.FAILED, result.status()); return this; }
        public AgentResultExpect outputContains(String text)  { assertTrue(result.output().toString().contains(text)); return this; }
        public AgentResultExpect hasToolCall(String toolName) { assertTrue(result.toolCalls().stream().anyMatch(tc -> toolName.equals(tc.get("name")))); return this; }
        public AgentResultExpect guardrailPassed(String name) { assertTrue(result.events().stream().anyMatch(e -> e.type() == EventType.GUARDRAIL_PASS && name.equals(e.guardrailName()))); return this; }
        public AgentResultExpect tokenUsageBelow(int max)     { assertNotNull(result.tokenUsage()); assertTrue(result.tokenUsage().totalTokens() <= max); return this; }
    }
}
```

### 8.3 Recording and Replay

```java
public class Recording {

    /** Record all HTTP interactions during execution. */
    public static AgentResult record(Agent agent, String prompt, Path outputFile) {
        // Intercepts HTTP client, records request/response pairs
        // Writes to outputFile as JSON
    }

    /** Replay a previously recorded execution. */
    public static AgentResult replay(Path recordingFile) {
        // Reads recorded interactions, replays without network
    }
}
```

### 8.4 Maven Surefire Integration

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <includes>
            <include>**/*Test.java</include>
        </includes>
        <systemPropertyVariables>
            <agentspan.test.mode>mock</agentspan.test.mode>
        </systemPropertyVariables>
    </configuration>
</plugin>
```

### 8.5 Validation as Test Suite

The validation framework runs as a JUnit 5 `@TestFactory` producing `DynamicTest` instances from TOML config (`validation/runs.toml`). Each run executes the agent, asserts completion via `Expect`, and optionally evaluates with `Judge.evaluate()` against score thresholds. This mirrors the Python validation runner with TOML config, groups, judge, and HTML report generation.

---

## 9. Kitchen Sink Translation

This section translates key patterns from `kitchen_sink.py` to idiomatic Java. The full pipeline structure maps directly; the differences are syntactic.

### 9.1 Chaining: `>>` becomes `.then()`

Python:
```python
writing_pipeline = draft_writer >> editor
```

Java:
```java
Agent writingPipeline = draftWriter.then(editor);
```

Under the hood, `.then()` creates a new agent with `Strategy.SEQUENTIAL` and both agents as children -- identical AgentConfig JSON.

### 9.2 Parallel Composition: `CompletableFuture.allOf()`

Python:
```python
research_team = Agent(
    name="research_team",
    agents=[research_coordinator, data_analyst],
    strategy=Strategy.PARALLEL,
)
```

Java:
```java
Agent researchTeam = Agent.builder()
    .name("research_team")
    .agents(List.of(researchCoordinator, dataAnalyst))
    .strategy(Strategy.PARALLEL)
    .build();
```

For explicit client-side parallelism (not server-side FORK_JOIN):

```java
CompletableFuture<AgentResult> r1 = runtime.runAsync(agent1, prompt);
CompletableFuture<AgentResult> r2 = runtime.runAsync(agent2, prompt);
CompletableFuture.allOf(r1, r2).join();
```

### 9.3 Termination Conditions: `.and()` / `.or()`

Python:
```python
termination=(
    TextMentionTermination("PUBLISHED")
    | (MaxMessageTermination(50) & TokenUsageTermination(max_total_tokens=100000))
)
```

Java:
```java
.termination(
    TextMentionTermination.of("PUBLISHED")
        .or(MaxMessageTermination.of(50)
            .and(TokenUsageTermination.ofTotal(100000)))
)
```

### 9.4 Callbacks

Python:
```python
class PublishingCallbackHandler(CallbackHandler):
    def on_agent_start(self, agent_name=None, **kwargs):
        callback_log.log("before_agent", agent_name=agent_name)
    def on_agent_end(self, agent_name=None, **kwargs):
        callback_log.log("after_agent", agent_name=agent_name)
    # ... 4 more methods
```

Java:
```java
public class PublishingCallbackHandler extends CallbackHandler {
    @Override
    public void onAgentStart(String agentName, Map<String, Object> kwargs) {
        callbackLog.log("before_agent", Map.of("agent_name", agentName));
    }
    @Override
    public void onAgentEnd(String agentName, Map<String, Object> kwargs) {
        callbackLog.log("after_agent", Map.of("agent_name", agentName));
    }
    @Override
    public void onModelStart(String agentName, List<Map<String, Object>> messages, Map<String, Object> kwargs) {
        callbackLog.log("before_model", Map.of("message_count", messages.size()));
    }
    @Override
    public void onModelEnd(String agentName, String response, Map<String, Object> kwargs) {
        callbackLog.log("after_model", Map.of("result_length", response.length()));
    }
    @Override
    public void onToolStart(String agentName, String toolName, Map<String, Object> kwargs) {
        callbackLog.log("before_tool", Map.of("tool_name", toolName));
    }
    @Override
    public void onToolEnd(String agentName, String toolName, Map<String, Object> kwargs) {
        callbackLog.log("after_tool", Map.of("tool_name", toolName));
    }
}
```

### 9.5 Runtime Lifecycle: `try-with-resources`

Python:
```python
with AgentRuntime() as runtime:
    deployments = runtime.deploy(full_pipeline)
    agent_stream = runtime.stream(full_pipeline, PROMPT)
    for event in agent_stream:
        ...
shutdown()
```

Java:
```java
try (AgentRuntime runtime = new AgentRuntime()) {

    // Deploy
    DeploymentInfo deployment = runtime.deploy(fullPipeline);
    System.out.println("Deployed: " + deployment.registeredName());

    // Plan (dry-run)
    ExecutionPlan plan = runtime.plan(fullPipeline);
    System.out.println("Plan compiled successfully");

    // Stream with HITL
    try (AgentStream agentStream = runtime.stream(fullPipeline, PROMPT)) {
        System.out.println("Execution: " + agentStream.getExecutionId());

        int feedbackCount = 0, rejectedCount = 0, approvedCount = 0;

        for (AgentEvent event : agentStream) {
            switch (event.type()) {
                case THINKING       -> System.out.println("[thinking] " + truncate(event.content(), 80));
                case TOOL_CALL      -> System.out.println("[tool_call] " + event.toolName() + "(" + event.args() + ")");
                case TOOL_RESULT    -> System.out.println("[tool_result] " + event.toolName());
                case HANDOFF        -> System.out.println("[handoff] -> " + event.target());
                case GUARDRAIL_PASS -> System.out.println("[guardrail_pass] " + event.guardrailName());
                case GUARDRAIL_FAIL -> System.out.println("[guardrail_fail] " + event.guardrailName() + ": " + event.content());
                case MESSAGE        -> System.out.println("[message] " + truncate(event.content(), 80));
                case WAITING -> {
                    System.out.println("--- HITL: Approval required ---");
                    if (feedbackCount == 0) {
                        agentStream.send("Please add more details about quantum error correction.");
                        feedbackCount++;
                    } else if (rejectedCount == 0) {
                        agentStream.reject("Title needs improvement");
                        rejectedCount++;
                    } else {
                        agentStream.approve();
                        approvedCount++;
                    }
                }
                case ERROR -> System.out.println("[error] " + event.content());
                case DONE  -> System.out.println("[done] Pipeline complete");
            }
        }

        AgentResult result = agentStream.getResult();
        if (result.tokenUsage() != null) {
            System.out.println("Total tokens: " + result.tokenUsage().totalTokens());
        }
    }

    // Start + polling
    AgentHandle handle = runtime.start(fullPipeline, PROMPT);
    AgentStatus status = handle.getStatus();
    System.out.println("Status: " + status.status() + ", Running: " + status.isRunning());

    // Async streaming
    runtime.streamAsync(fullPipeline, PROMPT)
        .thenAccept(asyncStream -> {
            for (AgentEvent event : asyncStream) {
                if (event.type() == EventType.DONE) break;
                if (event.type() == EventType.WAITING) asyncStream.approve();
            }
            AgentResult asyncResult = asyncStream.getResult();
            System.out.println("Async result status: " + asyncResult.status());
        })
        .join();

    // Top-level convenience
    Agentspan.configure(AgentConfig.fromEnv());
    Agent simpleAgent = Agent.builder()
        .name("simple_test")
        .model("openai/gpt-4o")
        .instructions("Say hello.")
        .build();
    AgentResult simpleResult = Agentspan.run(simpleAgent, "Hello!");
    System.out.println("run() status: " + simpleResult.status());

} // runtime.close() called automatically
Agentspan.shutdown();
System.out.println("=== Kitchen Sink Complete ===");
```

### 9.6 Full Pipeline Assembly

```java
Agent fullPipeline = Agent.builder()
    .name("content_publishing_platform")
    .model("openai/gpt-4o")
    .instructions(
        "You are a content publishing platform. Process article requests " +
        "through all pipeline stages: classification, research, writing, " +
        "review, editorial approval, translation, publishing, and analytics."
    )
    .agents(List.of(
        intakeRouter,           // Stage 1
        researchTeam,           // Stage 2
        writingPipeline,        // Stage 3 (sequential via .then())
        reviewAgent,            // Stage 4
        editorialAgent,         // Stage 5
        translationSwarm,       // Stage 6
        publishingPipeline,     // Stage 7
        analyticsAgent          // Stage 8
    ))
    .strategy(Strategy.SEQUENTIAL)
    .termination(
        TextMentionTermination.of("PIPELINE_COMPLETE")
            .or(MaxMessageTermination.of(200))
    )
    .build();
```

### 9.7 Scatter-Gather

Python:
```python
research_coordinator = scatter_gather(
    name="research_coordinator",
    worker=researcher_worker,
    model=settings.llm_model,
    instructions="Create research tasks...",
    timeout_seconds=300,
)
```

Java:
```java
Agent researchCoordinator = ScatterGather.builder()
    .name("research_coordinator")
    .worker(researcherWorker)
    .model("openai/gpt-4o")
    .instructions("Create research tasks for the topic: web search, data analysis, and fact checking.")
    .timeoutSeconds(300)
    .build();
```

### 9.8 Memory

```java
SemanticMemory semanticMem = new SemanticMemory(3);
for (Map<String, String> article : MOCK_PAST_ARTICLES) {
    semanticMem.add("Past article: " + article.get("title"));
}

Agent draftWriter = Agent.builder()
    .name("draft_writer")
    .model("openai/gpt-4o")
    .instructions("Write a comprehensive article draft based on research findings.")
    .tools(List.of(recallPastArticles))
    .memory(new ConversationMemory(50))
    .callbacks(List.of(new PublishingCallbackHandler()))
    .build();
```

### 9.9 Code Executors and Media Tools

```java
CodeExecutor localExecutor = new LocalCodeExecutor("python", 10);
CodeExecutor dockerExecutor = new DockerCodeExecutor("python:3.12-slim", 15);
CodeExecutor jupyterExecutor = new JupyterCodeExecutor(30);
CodeExecutor serverlessExecutor = new ServerlessCodeExecutor(
    "https://api.example.com/functions/analytics", 30);

ToolDef thumbnail = MediaTools.imageToolBuilder()
    .name("generate_thumbnail")
    .description("Generate an article thumbnail image.")
    .llmProvider("openai").model("dall-e-3").build();

ToolDef audioSummary = MediaTools.audioToolBuilder()
    .name("generate_audio_summary")
    .description("Generate an audio summary of the article.")
    .llmProvider("openai").model("tts-1").build();

ToolDef articleSearch = RagTools.searchToolBuilder()
    .name("search_articles")
    .description("Search for related articles.")
    .vectorDb("pgvector").index("articles")
    .embeddingModelProvider("openai")
    .embeddingModel("text-embedding-3-small")
    .maxResults(5).build();

Agent analyticsAgent = Agent.builder()
    .name("analytics_agent")
    .model("openai/gpt-4o")
    .instructions("Analyze the published article and generate a comprehensive analytics report.")
    .tools(List.of(
        localExecutor.asTool(),
        dockerExecutor.asTool("run_sandboxed"),
        jupyterExecutor.asTool("run_notebook"),
        serverlessExecutor.asTool("run_cloud"),
        thumbnail, audioSummary, articleSearch, researchSubtool
    ))
    .agents(List.of(gptAssistant))
    .strategy(Strategy.HANDOFF)
    .thinkingBudgetTokens(2048)
    .includeContents("default")
    .outputType(ArticleReport.class)
    .requiredTools(List.of("index_article"))
    .codeExecutionConfig(CodeExecutionConfig.builder()
        .enabled(true)
        .allowedLanguages(List.of("python", "shell"))
        .allowedCommands(List.of("python3", "pip"))
        .timeout(30)
        .build())
    .cliConfig(CliConfig.builder()
        .enabled(true)
        .allowedCommands(List.of("git", "gh"))
        .timeout(30)
        .build())
    .metadata(Map.of("stage", "analytics", "version", "1.0"))
    .planner(true)
    .build();
```

### 9.10 Translation Summary Table

| Python Pattern | Java Equivalent |
|----------------|-----------------|
| `@agent(name="...", model="...")` | `@AgentDef(name="...", model="...")` on class, or `Agent.builder()` |
| `@tool` | `@Tool` on method |
| `@tool(approval_required=True)` | `@Tool(approvalRequired = true)` |
| `@guardrail` | `@Guardrail` on method |
| `agent_a >> agent_b` | `agentA.then(agentB)` |
| `cond_a \| cond_b` | `condA.or(condB)` |
| `cond_a & cond_b` | `condA.and(condB)` |
| `with AgentRuntime() as rt:` | `try (AgentRuntime rt = new AgentRuntime()) { }` |
| `for event in stream:` | `for (AgentEvent event : stream) { }` |
| `await runtime.stream_async(...)` | `runtime.streamAsync(...).join()` or `.thenAccept(...)` |
| `asyncio.run(coro)` | `future.join()` |
| `async for event in stream:` | Iterate `AgentStream` from `streamAsync()` result |
| `configure(AgentConfig.from_env())` | `Agentspan.configure(AgentConfig.fromEnv())` |
| `run(agent, prompt)` | `Agentspan.run(agent, prompt)` |
| `shutdown()` | `Agentspan.shutdown()` |
| `Optional[T]` parameter | `@Nullable T` (POJO) or `Optional<T>` (record) |
| `BaseModel` for structured output | Class with Jackson annotations + `outputType(MyClass.class)` |
| `scatter_gather(...)` | `ScatterGather.builder().worker(...).build()` |
| `discover_agents(path)` | `Agentspan.discoverAgents(Path.of("..."))` |
| `is_tracing_enabled()` | `Agentspan.isTracingEnabled()` |
