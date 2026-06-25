# API Reference

Complete method signatures for the Agentspan Java SDK public API.

## AgentRuntime

The SDK entry point. Thread-safe — share one instance.

```java
// Constructors
AgentRuntime()                                    // reads AGENTSPAN_* env vars
AgentRuntime(AgentConfig config)                  // env vars + explicit tuning
AgentRuntime(ApiClient client)                    // explicit client
AgentRuntime(ApiClient client, AgentConfig config)

// Static factories for ApiClient
static ApiClient clientFromEnv()
static ApiClient client(String serverUrl)
static ApiClient client(String serverUrl, String authKey, String authSecret)
```

### Run

```java
AgentResult  run(Agent agent, String prompt)
AgentResult  run(Agent agent, String prompt, Plan plan)

CompletableFuture<AgentResult>  runAsync(Agent agent, String prompt)
CompletableFuture<AgentResult>  runAsync(Agent agent, String prompt, Plan plan)
```

### Start (fire-and-forget)

```java
AgentHandle  start(Agent agent, String prompt)
CompletableFuture<AgentHandle>  startAsync(Agent agent, String prompt)
CompletableFuture<AgentHandle>  startAsync(Agent agent, String prompt, Plan plan)
```

### Stream

```java
AgentStream  stream(Agent agent, String prompt)
CompletableFuture<AgentStream>  streamAsync(Agent agent, String prompt)
```

### Deploy / serve

```java
CompileResponse            plan(Agent agent)                    // compile only, no run
List<DeploymentInfo>       deploy(Agent... agents)
DeploymentInfo             deploy(Agent agent, List<Schedule> schedules)
CompletableFuture<List<DeploymentInfo>>  deployAsync(Agent... agents)
void                       serve(Agent... agents)               // blocks indefinitely
```

### Resume / schedule

```java
AgentHandle                         resume(String executionId, Agent agent)
CompletableFuture<AgentHandle>      resumeAsync(String executionId, Agent agent)
Schedules                           schedules()
```

### Lifecycle

```java
void  shutdown()      // stop workers, release HTTP connections
void  close()         // alias for shutdown(); implements AutoCloseable
```

---

## Agent.Builder

```java
Agent.builder()
    // Identity
    .name(String)                          // required
    .model(String)                         // required
    .instructions(String)
    .instructions(Supplier<String>)        // dynamic — re-evaluated on each run submission
    .instructionsTemplate(PromptTemplate)
    .introduction(String)
    .metadata(Map<String,Object>)

    // LLM
    .maxTurns(int)                         // default 25
    .maxTokens(int)
    .temperature(double)
    .thinkingBudgetTokens(int)             // Anthropic extended thinking
    .reasoningEffort(String)               // OpenAI reasoning models: "low"|"medium"|"high"
    .contextWindowBudget(int)              // token threshold for proactive condensation
    .timeoutSeconds(int)                   // default 0 (server applies its own default)

    // Tools
    .tools(List<ToolDef>)
    .tools(ToolDef...)

    // Multi-agent
    .agents(List<Agent>)
    .agents(Agent...)
    .strategy(Strategy)
    .router(Agent)
    .handoffs(List<Handoff>)
    .handoffs(Handoff...)
    .allowedTransitions(Map<String,List<String>>)

    // Termination
    .termination(TerminationCondition)

    // Guardrails
    .guardrails(List<GuardrailDef>)
    .guardrails(GuardrailDef...)

    // Auth
    .credentials(List<String>)
    .credentials(String...)

    // Code execution
    .localCodeExecution(boolean)
    .allowedLanguages(List<String>)
    .codeExecutionTimeout(int)             // seconds

    // Callbacks (intercept the agent loop)
    .beforeModelCallback(Function<Map<String,Object>, Map<String,Object>>)
    .afterModelCallback(Function<Map<String,Object>, Map<String,Object>>)
    .beforeAgentCallback(Function<Map<String,Object>, Map<String,Object>>)
    .afterAgentCallback(Function<Map<String,Object>, Map<String,Object>>)
    .callbacks(List<CallbackHandler>)
    .callbacks(CallbackHandler...)

    // Stateful (session isolation)
    .sessionId(String)
    .stateful(boolean)
    .memory(ConversationMemory)            // multi-turn message history

    // Privacy
    .maskedFields(String...)               // redact fields in history/UI

    // Advanced
    .outputType(Class<?>)                  // structured output
    .fallback(Agent)
    .fallbackMaxTurns(int)
    .planner(Agent)
    .plannerContext(List<Context>)
    .plannerContext(String...)
    .prefillTools(List<PrefillToolCall>)
    .synthesize(boolean)
    .enablePlanning(boolean)
    .baseUrl(String)
    .gate(TextGate)
    .includeContents(String)
    .cliConfig(CliConfig)
    .requiredTools(String...)
    .stopWhen(String)                      // task name to stop on
    .allowedCommands(List<String>)
    .framework(String)                     // for bridge agents
    .frameworkConfig(Map<String,Object>)

    .build()
```

---

## @AgentDef annotation

Declarative alternative to the builder — annotate a method to define an agent
(see [Agents](concepts/agents.md#agentdef-annotation) for attribute details):

```java
import org.conductoross.conductor.ai.annotations.AgentDef;

public class Weather {
    @Tool(name = "get_weather", description = "Get weather for a city")
    public String getWeather(String city) { return "Sunny, 72F in " + city; }

    @AgentDef(model = "openai/gpt-4o")     // @Tool methods attach automatically
    public String weatherbot() {
        // returned String = instructions; no-arg form is lazy — re-evaluated per run
        return "You are a weather assistant. Today is " + LocalDate.now() + ".";
    }

    @AgentDef(model = "openai/gpt-4o")     // optional Agent.Builder param = full builder API
    public void researcher(Agent.Builder builder) {
        builder.termination(new MaxMessageTermination(10));
    }

    @AgentDef                              // return Agent (or Agent.Builder) = full factory
    public Agent reviewer() {
        return Agent.builder().name("reviewer").model("openai/gpt-4o")
                .instructions("Review the draft.").build();
    }

    @AgentDef(model = "openai/gpt-4o")     // return PromptTemplate = server-side template
    public PromptTemplate support() {
        return new PromptTemplate("customer-support", Map.of("tone", "friendly"));
    }
}
```

```java
List<Agent> agents = Agent.fromInstance(instance);          // resolve all @AgentDef methods
Agent agent       = Agent.fromInstance(instance, "name");   // resolve one by name
```

---

## AgentResult

```java
Object                   getOutput()        // final LLM output (String or structured object)
<T> T                    getOutput(Class<T> type)   // deserialize structured output
AgentStatus              getStatus()        // COMPLETED | FAILED | TERMINATED | TIMED_OUT
String                   getExecutionId()
List<Map<String,Object>> getToolCalls()
List<AgentEvent>         getEvents()
TokenUsage               getTokenUsage()
boolean                  isSuccess()
String                   getError()
```

---

## AgentHandle

```java
String       getExecutionId()
AgentResult  waitForResult()                             // blocks; default 600s timeout
AgentResult  waitForResult(long timeoutMs, long pollMs)  // explicit timeout
boolean      waitUntilWaiting(long timeoutMs)            // wait for HITL pause
boolean      isWaiting()                                 // true if a HITL task is paused
void         approve()
void         approve(String comment)
void         reject(String reason)
void         respond(Map<String,Object> data)            // arbitrary HITL response (MANUAL strategy)
```

---

## AgentStream

`AgentStream` implements `Iterable<AgentEvent>` and `AutoCloseable`.

```java
try (AgentStream stream = runtime.stream(agent, prompt)) {
    for (AgentEvent event : stream) {
        EventType type = event.getType();    // MESSAGE | TOOL_CALL | TOOL_RESULT | …
        String content  = event.getContent();
        String toolName = event.getToolName();
        Map<String,Object> args   = event.getArgs();
        String executionId        = event.getExecutionId();
    }
}

// Approve from a stream
stream.approve(event);
stream.reject(event, "reason");
```

---

## Tool builders

```java
// @Tool-annotated POJO → list of worker tools
ToolRegistry.fromInstance(Object pojo)                 // returns List<ToolDef>

// Sub-agent as a tool
AgentTool.from(Agent agent)
AgentTool.from(Agent agent, String description)

// HTTP
HttpTool.builder().name(String).description(String).url(String).method(String).build()

// MCP
McpTool.builder().name(String).description(String).serverUrl(String).build()

// Human
HumanTool.create(String name, String description)

// PDF
PdfTool.create(String name, String description)

// Wait for message
WaitForMessageTool.create(String name, String description)

// Image / media
MediaTools.imageTool(String name, String description, String provider, String model)
```

---

## Termination conditions

```java
MaxMessageTermination.of(int maxMessages)
StopMessageTermination.of(String stopMessage)
TextMentionTermination.of(String text)
TextMentionTermination.of(String text, boolean caseSensitive)
TokenUsageTermination.ofTotal(int maxTokens)

// Compose
condition.and(TerminationCondition other)   // both must be true
condition.or(TerminationCondition other)    // either must be true
```

---

## Handoffs

```java
OnTextMention.of(String text, String targetAgent)
OnToolResult.of(String toolName, String targetAgent)
OnToolResult.of(String toolName, String targetAgent, String resultContains)
new OnCondition(String targetAgent, Function<Map<String,Object>,Boolean> predicate)
```

---

## Schedules

```java
Schedules schedules = runtime.schedules();

schedules.save(Schedule schedule, String agentName)
schedules.get(String wireName)                         // → ScheduleInfo
schedules.list(String agentName)                       // → List<ScheduleInfo>
schedules.runNow(ScheduleInfo info)                    // → String executionId
schedules.pause(String wireName)
schedules.pause(String wireName, String reason)
schedules.resume(String wireName)
schedules.delete(String wireName)
schedules.previewNext(String cron, int n)              // → List<Long> (epoch ms)

// Schedule.builder()
Schedule.builder()
    .name(String)         // required
    .cron(String)         // required; standard 5-field cron
    .timezone(String)     // default "UTC"
    .input(Map)
    .description(String)
    .paused(boolean)
    .catchup(boolean)
    .startAt(long)        // epoch ms
    .endAt(long)          // epoch ms
    .build()
```

---

## Credentials

```java
// In a @Tool method (ToolContext required as last param):
String value = Credentials.get("SECRET_NAME");
String value = Credentials.getOrNull("SECRET_NAME");  // null if not found

// Store via CLI:
// agentspan secrets set SECRET_NAME value
```

---

## Skill

```java
Agent Skill.skill(Path path, String model)
Agent Skill.skill(Path path, String model, Map<String,String> agentModels)
Map<String,Agent> Skill.loadSkills(Path directory, String model)
```

---

## Framework bridges

```java
// LangChain4j
Agent LangChain4jAgent.from(String name, String model, String instructions, Object... tools)
boolean LangChain4jAgent.isLangChain4jTools(Object obj)

// OpenAI Agents SDK style
OpenAIAgent.builder()
    .name(String).model(String).instructions(String)
    .tools(Object...)        // @Tool-annotated POJOs
    .handoffs(Agent...)
    .outputType(String)
    .build()

// Google ADK
Agent AdkBridge.toAgentspan(BaseAgent adkAgent)
Agent.Builder AdkBridge.agentBuilder(BaseAgent adkAgent)
```

---

## AgentConfig

```java
new AgentConfig()                                 // defaults: 100ms poll, 1 thread
new AgentConfig(int pollIntervalMs, int threads)
AgentConfig.fromEnv()                             // reads AGENTSPAN_WORKER_* env vars

config.getWorkerPollIntervalMs()
config.getWorkerThreadCount()
```
