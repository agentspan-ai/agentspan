# Kotlin SDK Translation Guide

**Date:** 2026-03-23
**Status:** Draft
**Reference:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md` (base spec)
**Kitchen Sink Reference:** `sdk/python/examples/kitchen_sink.py`

---

## 1. Project Setup

### 1.1 Gradle Configuration (Kotlin DSL)

```kotlin
// build.gradle.kts
plugins {
    kotlin("jvm") version "2.1.0"
    kotlin("plugin.serialization") version "2.1.0"
}

group = "dev.agentspan"
version = "0.1.0"

repositories {
    mavenCentral()
}

dependencies {
    // Coroutines — the async backbone
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")

    // HTTP client with streaming support
    implementation("io.ktor:ktor-client-core:3.0.3")
    implementation("io.ktor:ktor-client-cio:3.0.3")
    implementation("io.ktor:ktor-client-content-negotiation:3.0.3")
    implementation("io.ktor:ktor-serialization-kotlinx-json:3.0.3")

    // JSON serialization
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    // TOML for validation config
    implementation("com.akuleshov7:ktoml-core:0.5.2")
    implementation("com.akuleshov7:ktoml-file:0.5.2")

    // Testing
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    testImplementation("io.kotest:kotest-runner-junit5:5.9.1")
    testImplementation("io.kotest:kotest-assertions-core:5.9.1")
    testImplementation("io.mockk:mockk:1.13.13")
}

tasks.test {
    useJUnitPlatform()
}
```

### 1.2 Directory Layout

```
sdk/kotlin/
  build.gradle.kts
  src/main/kotlin/dev/agentspan/
    Agentspan.kt          # Top-level configure/run/stream/deploy/shutdown
    Agent.kt              # Agent data class + DSL builder
    AgentRuntime.kt       # Runtime lifecycle (Closeable)
    Tool.kt               # Tool DSL + @AgentspanTool annotation
    Guardrail.kt          # Guardrail DSL + sealed class hierarchy
    Result.kt             # AgentResult, AgentHandle, AgentStream
    Events.kt             # AgentEvent, EventType enum
    Strategy.kt           # Strategy enum
    Termination.kt        # TerminationCondition sealed class + operators
    Handoff.kt            # HandoffCondition sealed class
    Memory.kt             # ConversationMemory, SemanticMemory
    CodeExecution.kt      # CodeExecutor hierarchy
    Credentials.kt        # get_credential, CredentialFile, resolve
    Callbacks.kt          # CallbackHandler interface
    Streaming.kt          # SSE client, Flow-based streaming
    Worker.kt             # Conductor worker poll loop
    Errors.kt             # Sealed exception hierarchy
  src/test/kotlin/dev/agentspan/
    testing/MockRun.kt    # mockRun {} DSL
    testing/Expect.kt     # expect(result) { } DSL
    examples/KitchenSink.kt
```

### 1.3 Key Design Decisions

- **Coroutines over threads.** All async work uses `suspend fun` and `Flow`. `CoroutineScope.launch` replaces thread pools.
- **DSL builders as primary API.** Lambda-with-receiver (`T.() -> Unit`) creates readable agent definitions without annotation processors.
- **Annotation alternative.** Provide `@AgentspanTool` / `@AgentspanGuardrail` via KSP as opt-in for Spring-style codebases.
- **kotlinx.serialization for all JSON.** Compile-time safe, multiplatform-ready. No Jackson/Gson.
- **Sealed classes for variants.** TerminationCondition, HandoffCondition, and errors use sealed classes. Strategy/OnFail use enum classes.

---

## 2. Type System Mapping

### 2.1 Core Type Translations

| Python | Kotlin | Notes |
|--------|--------|-------|
| `@dataclass` | `data class` | Automatic `equals`, `hashCode`, `copy`, destructuring |
| `Enum(str, Enum)` | `enum class` | For flat variants (Strategy, OnFail, Position) |
| `Union[A, B]` | `sealed class` / `sealed interface` | For polymorphic types with data (TerminationCondition, HandoffCondition) |
| `Optional[T]` | `T?` | First-class null safety; no `Optional<T>` wrapper |
| `list[T]` | `List<T>` | Immutable by default; use `MutableList<T>` where mutation is needed |
| `dict[K, V]` | `Map<K, V>` | Immutable by default |
| `Callable[[T], R]` | `(T) -> R` or `suspend (T) -> R` | Function types are first-class |
| `Pydantic BaseModel` | `@Serializable data class` | kotlinx.serialization with compile-time codegen |
| `class (base)` | `abstract class` / `interface` | Prefer `interface` unless shared state is needed |

### 2.2 Strategy Enum

```kotlin
@Serializable
enum class Strategy(val wire: String) {
    HANDOFF("handoff"),
    SEQUENTIAL("sequential"),
    PARALLEL("parallel"),
    ROUTER("router"),
    ROUND_ROBIN("round_robin"),
    RANDOM("random"),
    SWARM("swarm"),
    MANUAL("manual");
}
```

### 2.3 Agent Data Class

```kotlin
@Serializable
data class Agent(
    val name: String,
    val model: String? = null,
    val instructions: Instructions? = null,
    val tools: List<ToolDef> = emptyList(),
    val agents: List<Agent> = emptyList(),
    val strategy: Strategy? = null,
    val router: Agent? = null,
    val outputType: OutputType? = null,
    val guardrails: List<GuardrailDef> = emptyList(),
    val memory: ConversationMemory? = null,
    val maxTurns: Int = 25,
    val maxTokens: Int? = null,
    val temperature: Double? = null,
    val timeoutSeconds: Int = 0,
    val external: Boolean = false,
    val stopWhen: StopCondition? = null,
    val termination: TerminationCondition? = null,
    val handoffs: List<HandoffCondition> = emptyList(),
    val allowedTransitions: Map<String, List<String>>? = null,
    val introduction: String? = null,
    val metadata: Map<String, String>? = null,
    val callbacks: List<CallbackHandler> = emptyList(),
    val planner: Boolean = false,
    val includeContents: String? = null,
    val thinkingBudgetTokens: Int? = null,
    val requiredTools: List<String>? = null,
    val gate: GateCondition? = null,
    val codeExecutionConfig: CodeExecutionConfig? = null,
    val cliConfig: CliConfig? = null,
    val credentials: List<CredentialRef> = emptyList(),
)
```

### 2.4 Instructions (Sealed Class for Polymorphism)

Python uses `Union[str, callable, PromptTemplate]`. Kotlin uses a sealed class:

```kotlin
@Serializable
sealed class Instructions {
    @Serializable data class Text(val text: String) : Instructions()
    @Serializable data class Template(val name: String, val variables: Map<String, String> = emptyMap(), val version: Int? = null) : Instructions()
    @Serializable data class Dynamic(@Transient val provider: suspend () -> String = { "" }) : Instructions()
}
```

### 2.5 Other Core Types

```kotlin
@Serializable
data class AgentResult(
    val output: JsonElement? = null, val executionId: String,
    val status: Status, val finishReason: FinishReason? = null,
    val error: String? = null, val tokenUsage: TokenUsage? = null,
    val messages: List<Message> = emptyList(), val toolCalls: List<ToolCall> = emptyList(),
    val events: List<AgentEvent> = emptyList(), val subResults: Map<String, JsonElement>? = null,
) {
    val isSuccess: Boolean get() = status == Status.COMPLETED
    val isFailed: Boolean get() = status == Status.FAILED
    val isRejected: Boolean get() = finishReason == FinishReason.REJECTED
}

data class ToolContext(
    val sessionId: String, val executionId: String, val agentName: String,
    val metadata: Map<String, String> = emptyMap(),
    val state: MutableMap<String, Any> = mutableMapOf(),
)

@Serializable
data class GuardrailResult(val passed: Boolean, val message: String? = null, val fixedOutput: String? = null)
```

### 2.6 Enums

```kotlin
enum class Status { COMPLETED, FAILED, TERMINATED, TIMED_OUT }
enum class FinishReason { STOP, LENGTH, TOOL_CALLS, ERROR, CANCELLED, TIMEOUT, GUARDRAIL, REJECTED }
enum class OnFail(val wire: String) { RETRY("retry"), RAISE("raise"), FIX("fix"), HUMAN("human") }
enum class Position(val wire: String) { INPUT("input"), OUTPUT("output") }
enum class EventType { THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING, MESSAGE, ERROR, DONE, GUARDRAIL_PASS, GUARDRAIL_FAIL }
data class TokenUsage(val promptTokens: Int = 0, val completionTokens: Int = 0, val totalTokens: Int = 0)
```

### 2.9 TerminationCondition (Sealed Class with Operator Overloads)

```kotlin
@Serializable
sealed class TerminationCondition {
    @Serializable
    data class TextMention(val text: String, val caseSensitive: Boolean = false) : TerminationCondition()

    @Serializable
    data class StopMessage(val stopMessage: String) : TerminationCondition()

    @Serializable
    data class MaxMessage(val maxMessages: Int) : TerminationCondition()

    @Serializable
    data class TokenUsageLimit(
        val maxTotalTokens: Int? = null,
        val maxPromptTokens: Int? = null,
        val maxCompletionTokens: Int? = null,
    ) : TerminationCondition()

    @Serializable
    data class And(val conditions: List<TerminationCondition>) : TerminationCondition()

    @Serializable
    data class Or(val conditions: List<TerminationCondition>) : TerminationCondition()

    // Composable operators — mirrors Python's & and |
    infix fun and(other: TerminationCondition): TerminationCondition = And(listOf(this, other))
    infix fun or(other: TerminationCondition): TerminationCondition = Or(listOf(this, other))
}
```

Usage matches the Python style:

```kotlin
val termination = TextMention("PUBLISHED") or (MaxMessage(50) and TokenUsageLimit(maxTotalTokens = 100_000))
```

### 2.10 HandoffCondition (Sealed Class)

```kotlin
@Serializable
sealed class HandoffCondition {
    @Serializable
    data class OnToolResult(
        val target: String,
        val toolName: String,
        val resultContains: String? = null,
    ) : HandoffCondition()

    @Serializable
    data class OnTextMention(
        val target: String,
        val text: String,
    ) : HandoffCondition()

    @Serializable
    data class OnCondition(
        val target: String,
        @Transient val condition: suspend (List<Message>) -> Boolean = { false },
    ) : HandoffCondition()
}
```

---

## 3. DSL Builders

Kotlin DSL builders are the idiomatic way to construct complex object graphs. They use lambda-with-receiver (`T.() -> Unit`) to create a scoped configuration block.

### 3.1 Agent DSL Builder

The builder uses Kotlin's lambda-with-receiver pattern. Each property from the `Agent` data class has a corresponding mutable field or DSL method on `AgentBuilder`:

```kotlin
class AgentBuilder(private val name: String) {
    var model: String? = null
    var strategy: Strategy? = null
    var termination: TerminationCondition? = null
    var planner: Boolean = false
    // ... all Agent fields as mutable vars ...

    private val tools = mutableListOf<ToolDef>()
    private val agents = mutableListOf<Agent>()
    private val guardrails = mutableListOf<GuardrailDef>()

    fun model(m: String) { model = m }
    fun instructions(text: String) { instructions = Instructions.Text(text) }
    fun promptTemplate(name: String, variables: Map<String, String> = emptyMap()) {
        instructions = Instructions.Template(name, variables)
    }
    fun agent(name: String, block: AgentBuilder.() -> Unit) { agents += AgentBuilder(name).apply(block).build() }
    fun agent(existing: Agent) { agents += existing }
    fun tool(existing: ToolDef) { tools += existing }
    fun tools(block: ToolListBuilder.() -> Unit) { tools += ToolListBuilder().apply(block).build() }
    fun guardrails(block: GuardrailListBuilder.() -> Unit) { guardrails += GuardrailListBuilder().apply(block).build() }
    fun handoffs(block: HandoffListBuilder.() -> Unit) { handoffs += HandoffListBuilder().apply(block).build() }
    fun callbacks(vararg handlers: CallbackHandler) { callbacks += handlers }
    fun credentials(vararg names: String) { credentials += names.map { CredentialRef.Name(it) } }
    fun stopWhen(fn: suspend (List<Message>) -> Boolean) { stopWhen = StopCondition.Custom(fn) }

    fun build(): Agent = Agent(name = name, model = model, tools = tools.toList(), agents = agents.toList(), /* ... */)
}

// Top-level entry point
fun agent(name: String, block: AgentBuilder.() -> Unit): Agent =
    AgentBuilder(name).apply(block).build()
```

### 3.2 Tool DSL Builder

```kotlin
class ToolListBuilder {
    private val tools = mutableListOf<ToolDef>()
    fun tool(name: String, block: ToolDefBuilder.() -> Unit) { tools += ToolDefBuilder(name).apply(block).build() }
    fun build(): List<ToolDef> = tools.toList()
}

class ToolDefBuilder(private val name: String) {
    var description: String = ""
    var approvalRequired: Boolean = false
    var external: Boolean = false
    var isolated: Boolean = true
    fun handler(fn: suspend (ToolContext) -> Any?) { /* store handler */ }
    fun credentials(vararg names: String) { /* store credential refs */ }
    fun guardrails(block: GuardrailListBuilder.() -> Unit) { /* nested guardrails */ }
    fun build(): ToolDef = /* construct ToolDef.Worker from collected state */
}
```

### 3.3 Guardrail DSL Builder

```kotlin
class GuardrailListBuilder {
    private val guardrails = mutableListOf<GuardrailDef>()
    fun regex(name: String, block: RegexGuardrailBuilder.() -> Unit) { /* regex guardrail */ }
    fun llm(name: String, block: LlmGuardrailBuilder.() -> Unit) { /* LLM guardrail */ }
    fun custom(name: String, position: Position = Position.OUTPUT, onFail: OnFail = OnFail.RAISE,
               fn: suspend (String) -> GuardrailResult) { /* custom guardrail with lambda handler */ }
    fun external(name: String, position: Position = Position.OUTPUT, onFail: OnFail = OnFail.RAISE) {
        guardrails += GuardrailDef.External(name, position, onFail)
    }
    fun build(): List<GuardrailDef> = guardrails.toList()
}

class RegexGuardrailBuilder(private val name: String) {
    var position: Position = Position.OUTPUT
    var onFail: OnFail = OnFail.RETRY
    var mode: String = "block"
    var message: String? = null
    fun patterns(vararg p: String) { /* collect patterns */ }
    fun onFail(f: OnFail) { onFail = f }
    fun build(): GuardrailDef.Regex = /* construct from state */
}
```

### 3.4 Full DSL Usage Example

```kotlin
val myAgent = agent("researcher") {
    model("openai/gpt-4o")
    instructions("Research the topic thoroughly.")
    tools {
        tool("search") { description = "Search the web"; handler { ctx -> searchWeb(ctx) }; credentials("SEARCH_API_KEY") }
    }
    guardrails {
        regex("pii") { patterns("\\d{3}-\\d{2}-\\d{4}"); onFail(OnFail.RETRY) }
        llm("bias_detector") { policy = "Check for biased language."; onFail = OnFail.FIX }
        custom("fact_check", onFail = OnFail.HUMAN) { content ->
            val found = listOf("the best", "always", "never").filter { it in content.lowercase() }
            if (found.isNotEmpty()) GuardrailResult(passed = false, message = "Unverifiable: $found")
            else GuardrailResult(passed = true)
        }
    }
    memory = ConversationMemory(maxMessages = 50)
    termination = TextMention("DONE") or MaxMessage(100)
}
```

### 3.5 Annotation-Based Alternative

For Spring-style codebases, provide KSP-processed annotations as an opt-in alternative:

```kotlin
@AgentspanTool(name = "research_database", credentials = [CredentialFile(envVar = "RESEARCH_API_KEY")])
suspend fun researchDatabase(query: String, ctx: ToolContext): Map<String, Any> {
    return mapOf("query" to query, "session_id" to ctx.sessionId, "results" to fetchResults(query))
}

@AgentspanGuardrail(name = "fact_validator", position = Position.OUTPUT, onFail = OnFail.HUMAN)
fun factValidator(content: String): GuardrailResult {
    val redFlags = listOf("the best", "the worst", "always", "never", "guaranteed")
    val found = redFlags.filter { it.lowercase() in content.lowercase() }
    return if (found.isNotEmpty()) GuardrailResult(passed = false, message = "Unverifiable: $found")
    else GuardrailResult(passed = true)
}
```

Both annotation and DSL approaches produce identical AgentConfig JSON.

---

## 4. Async Model

### 4.1 Coroutine-First Design

Every I/O-bound operation is a `suspend fun`. The Kotlin SDK is async-native; sync wrappers use `runBlocking`.

```kotlin
// Async-native API (primary)
suspend fun run(agent: Agent, prompt: String): AgentResult
suspend fun start(agent: Agent, prompt: String): AgentHandle
fun stream(agent: Agent, prompt: String): Flow<AgentEvent>
suspend fun deploy(agent: Agent): DeploymentInfo
suspend fun plan(agent: Agent): ExecutionPlan

// Sync wrappers (convenience for scripts, tests, main functions)
fun runBlocking(agent: Agent, prompt: String): AgentResult =
    kotlinx.coroutines.runBlocking { run(agent, prompt) }
```

### 4.2 Streaming with Flow

`Flow<AgentEvent>` is the Kotlin equivalent of Python's `async for event in stream`. It is cold (lazily evaluated), cancellable, and composable via operators like `filter`, `map`, `catch`.

```kotlin
fun AgentRuntime.stream(agent: Agent, prompt: String): Flow<AgentEvent> = flow {
    val handle = start(agent, prompt)
    SseClient(httpClient, config).connect(handle.executionId).collect { emit(it) }
}

// Consumer: exhaustive `when` on EventType
runtime.stream(myAgent, "Write an article").collect { event ->
    when (event.type) {
        EventType.THINKING -> println("[thinking] ${event.content?.take(80)}...")
        EventType.WAITING  -> { /* HITL pause — call handle.approve() */ }
        EventType.DONE     -> println("[done]")
        else -> {}
    }
}
```

### 4.3 AgentHandle and AgentStream

`AgentHandle` wraps a running execution. Every method is `suspend`. `AgentStream` wraps a `Flow<AgentEvent>` with HITL methods and event accumulation.

```kotlin
class AgentHandle(val executionId: String, private val runtime: AgentRuntime) {
    suspend fun getStatus(): AgentStatus = runtime.httpClient.get("agent/$executionId/status")
    suspend fun approve() = runtime.httpClient.post("agent/$executionId/respond") { setBody(mapOf("approved" to true)) }
    suspend fun reject(reason: String? = null) = runtime.httpClient.post("agent/$executionId/respond") { setBody(mapOf("approved" to false, "reason" to reason)) }
    suspend fun send(message: String) = runtime.httpClient.post("agent/$executionId/respond") { setBody(mapOf("message" to message)) }
    suspend fun pause() = runtime.httpClient.post("agent/$executionId/pause")
    suspend fun resume() = runtime.httpClient.post("agent/$executionId/resume")
    suspend fun cancel(reason: String? = null) = runtime.httpClient.post("agent/$executionId/cancel") { setBody(mapOf("reason" to reason)) }
    fun stream(): Flow<AgentEvent> = runtime.streamEvents(executionId)
}

class AgentStream(val handle: AgentHandle, private val eventFlow: Flow<AgentEvent>) {
    private val _events = mutableListOf<AgentEvent>()
    fun asFlow(): Flow<AgentEvent> = eventFlow.onEach { _events += it }
    suspend fun approve() = handle.approve()
    suspend fun reject(reason: String? = null) = handle.reject(reason)
    suspend fun send(message: String) = handle.send(message)
    suspend fun getResult(): AgentResult { asFlow().collect {}; return /* build from status */ }
}
```

### 4.5 Structured Concurrency

`AgentRuntime` implements `Closeable` and owns a `CoroutineScope(SupervisorJob() + Dispatchers.Default)`. Calling `close()` cancels the scope, shutting down all workers, SSE connections, and pending HTTP requests. Use `runtime.use { }` for automatic cleanup.

---

## 5. Worker Implementation

### 5.1 Coroutine-Based Poll Loop

Each worker runs as a coroutine inside the runtime's `CoroutineScope`. Uses `delay()` (non-blocking) instead of `Thread.sleep()`.

```kotlin
class WorkerManager(private val scope: CoroutineScope, private val httpClient: HttpClient, private val config: AgentConfig) {
    private val workers = mutableMapOf<String, Job>()

    fun registerWorker(taskName: String, handler: suspend (JsonObject) -> JsonElement) {
        workers[taskName] = scope.launch {
            while (isActive) {
                try {
                    val task = httpClient.get("tasks/poll/$taskName").body<JsonObject?>()
                    if (task != null) {
                        val input = task["inputData"]?.jsonObject ?: JsonObject(emptyMap())
                        val result = handler(input)
                        httpClient.post("tasks/${task["taskId"]?.jsonPrimitive?.content}") {
                            setBody(buildJsonObject { put("status", "COMPLETED"); put("outputData", buildJsonObject { put("result", result) }) })
                        }
                    }
                } catch (e: CancellationException) { throw e }
                catch (e: Exception) { /* log and continue */ }
                delay(config.workerPollInterval.milliseconds)
            }
        }
    }

    fun shutdownAll() { workers.values.forEach { it.cancel() }; workers.clear() }
}
```

### 5.2 Tool Worker Registration and ToolContext Extraction

When the runtime starts, each non-external `ToolDef.Worker` with a handler is registered. The worker extracts `__agentspan_ctx__` from the Conductor task input, populates a `ToolContext`, resolves credentials, and invokes the user's handler:

```kotlin
fun AgentRuntime.registerToolWorkers(agent: Agent) {
    agent.allTools().filterIsInstance<ToolDef.Worker>()
        .filter { it.handler != null && !it.external }
        .forEach { tool ->
            workerManager.registerWorker(tool.name) { input ->
                val ctx = extractToolContext(input) // parses __agentspan_ctx__ from JSON
                val creds = resolveCredentials(input, tool.credentials)
                injectCredentials(creds, tool.isolated) { tool.handler!!.invoke(ctx) }
            }
        }
}
```

---

## 6. SSE Client

### 6.1 Ktor-Based SSE Implementation

The SSE client returns a `Flow<AgentEvent>`. Key behaviors: line-by-line SSE parsing, heartbeat filtering (`:` prefix lines), reconnection with `Last-Event-ID`, and exponential backoff.

```kotlin
class SseClient(private val httpClient: HttpClient, private val baseUrl: String, private val authHeaders: Map<String, String>) {

    fun connect(executionId: String): Flow<AgentEvent> = flow {
        var lastEventId: String? = null
        var retryDelay = 1.seconds

        retry@ while (true) {
            try {
                httpClient.prepareGet("$baseUrl/agent/stream/$executionId") {
                    header("Accept", "text/event-stream")
                    authHeaders.forEach { (k, v) -> header(k, v) }
                    lastEventId?.let { header("Last-Event-ID", it) }
                }.execute { response ->
                    val channel = response.bodyAsChannel()
                    retryDelay = 1.seconds // reset on successful connect
                    var eventType: String? = null; var data: String? = null; var id: String? = null

                    while (!channel.isClosedForRead) {
                        val line = channel.readUTF8Line() ?: break
                        when {
                            line.startsWith(":") -> continue           // heartbeat
                            line.isEmpty() -> {                        // dispatch
                                if (eventType != null && data != null) {
                                    id?.let { lastEventId = it }
                                    parseEvent(eventType, data)?.let { emit(it) }
                                    if (eventType == "done") return@execute
                                }
                                eventType = null; data = null; id = null
                            }
                            line.startsWith("event:") -> eventType = line.removePrefix("event:").trim()
                            line.startsWith("data:") -> data = line.removePrefix("data:").trim()
                            line.startsWith("id:") -> id = line.removePrefix("id:").trim()
                        }
                    }
                }
                break
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { delay(retryDelay); retryDelay = (retryDelay * 2).coerceAtMost(30.seconds) }
        }
    }

    private fun parseEvent(type: String, data: String): AgentEvent? {
        val json = Json.parseToJsonElement(data).jsonObject
        val eventType = runCatching { EventType.valueOf(type.uppercase()) }.getOrNull() ?: return null
        return AgentEvent(type = eventType, content = json["content"]?.jsonPrimitive?.contentOrNull, /* ... */)
    }
}
```

### 6.2 Polling Fallback

If SSE is unavailable (heartbeat-only for 15s), fall back to polling `GET /agent/{id}/status` at 500ms intervals, emitting synthetic events on state changes until `isComplete`.

---

## 7. Error Handling

### 7.1 Sealed Exception Hierarchy

```kotlin
sealed class AgentspanException(message: String, cause: Throwable? = null) : Exception(message, cause) {

    class ApiError(
        val statusCode: Int,
        message: String,
        cause: Throwable? = null,
    ) : AgentspanException("HTTP $statusCode: $message", cause)

    class NotFound(
        val agentName: String,
    ) : AgentspanException("Agent not found: $agentName")

    class Configuration(
        message: String,
    ) : AgentspanException(message)

    class GuardrailFailure(
        val guardrailName: String,
        val onFail: OnFail,
        message: String,
    ) : AgentspanException("Guardrail '$guardrailName' failed ($onFail): $message")

    class SseReconnectionFailed(
        message: String,
        cause: Throwable? = null,
    ) : AgentspanException(message, cause)

    // Credential exceptions
    class CredentialNotFound(val name: String) : AgentspanException("Credential not found: $name")
    class CredentialAuthError(message: String) : AgentspanException(message)
    class CredentialRateLimit(message: String) : AgentspanException(message)
    class CredentialServiceError(message: String, cause: Throwable? = null) : AgentspanException(message, cause)
}
```

### 7.2 Result-Based Safe Operations

Use Kotlin's `runCatching` for operations that may fail without throwing:

```kotlin
val result = runCatching { runtime.deploy(myAgent) }
result.onSuccess { println("Deployed: ${it.registeredName}") }
      .onFailure { println("Deploy failed: ${it.message}") }
```

### 7.3 Coroutine Exception Handler

Install `CoroutineExceptionHandler` on worker coroutines to log failures without crashing the runtime:

```kotlin
val handler = CoroutineExceptionHandler { ctx, e -> logger.error(e) { "Worker '${ctx[CoroutineName]?.name}' failed" } }
scope.launch(handler + CoroutineName(taskName)) { /* poll loop */ }
```

### 7.4 Typed Error Handling in Streaming

Use Flow's `catch` operator with `when` for exhaustive error handling:

```kotlin
runtime.stream(myAgent, prompt)
    .catch { e -> when (e) {
        is AgentspanException.SseReconnectionFailed -> emit(AgentEvent(type = EventType.ERROR, content = "Connection lost"))
        is AgentspanException.GuardrailFailure -> emit(AgentEvent(type = EventType.GUARDRAIL_FAIL, content = e.message))
        else -> throw e
    }}
    .collect { handleEvent(it) }
```

---

## 8. Testing Framework

### 8.1 mockRun DSL

Run an agent without a server, using mocked tool results:

```kotlin
suspend fun mockRun(agent: Agent, prompt: String, block: MockRunBuilder.() -> Unit): AgentResult {
    val builder = MockRunBuilder().apply(block)
    return MockRuntime(builder.toolResponses, builder.guardrailResults).run(agent, prompt)
}

class MockRunBuilder {
    internal val toolResponses = mutableMapOf<String, Any>()
    internal val guardrailResults = mutableMapOf<String, GuardrailResult>()

    fun toolReturns(name: String, result: Any) { toolResponses[name] = result }
    fun guardrailReturns(name: String, result: GuardrailResult) { guardrailResults[name] = result }
}

// Usage
val result = mockRun(myAgent, "Hello!") {
    toolReturns("search", mapOf("results" to listOf("item1", "item2")))
    guardrailReturns("pii_blocker", GuardrailResult(passed = true))
}
```

### 8.2 expect DSL

Fluent assertions via lambda-with-receiver on `AgentResult`:

```kotlin
class ResultExpectation(private val result: AgentResult) {
    fun completed() = apply { check(result.isSuccess) { "Expected COMPLETED, got ${result.status}" } }
    fun failed() = apply { check(result.isFailed) }
    fun outputContains(text: String) = apply { check(text in (result.output?.toString() ?: "")) }
    fun toolUsed(name: String) = apply { check(result.toolCalls.any { it.name == name }) }
    fun guardrailPassed(name: String) = apply {
        check(result.events.any { it.type == EventType.GUARDRAIL_PASS && it.guardrailName == name })
    }
    fun eventCount(type: EventType, expected: Int) = apply {
        check(result.events.count { it.type == type } == expected)
    }
}

fun expect(result: AgentResult, block: ResultExpectation.() -> Unit) = ResultExpectation(result).apply(block)

// Usage
expect(result) { completed(); outputContains("article"); toolUsed("search"); guardrailPassed("pii_blocker") }
```

### 8.3 Coroutine Test Utilities

Use `kotlinx-coroutines-test` and `runTest {}` for deterministic suspend-function testing:

```kotlin
@Test fun `stream emits events in order`() = runTest {
    val result = mockRun(myAgent, "test") { toolReturns("search", mapOf("data" to "found")) }
    expect(result) { completed(); toolUsed("search") }
}

@Test fun `guardrail failure triggers retry`() = runTest {
    val result = mockRun(reviewAgent, "test with 123-45-6789") { guardrailReturns("pii_blocker", GuardrailResult(passed = false)) }
    expect(result) { eventCount(EventType.GUARDRAIL_FAIL, 1) }
}
```

### 8.4 Validation with TOML Config

Mirror the Python validation runner using ktoml. Config structure: `ValidationConfig` contains `runs: Map<String, RunConfig>` (model, group, timeout) and optional `judge: JudgeConfig` (model, maxOutputChars, maxTokens, rateLimit). Parse from `validation/runs.toml` using `@Serializable` data classes.

---

## 9. Kitchen Sink Translation

This section translates the complete Python kitchen sink (`sdk/python/examples/kitchen_sink.py`) to idiomatic Kotlin, demonstrating all 9 stages.

### 9.1 Infix Functions for Agent Chaining

```kotlin
// Operator overloading for sequential chaining (>> equivalent)
infix fun Agent.then(other: Agent): Agent = Agent(
    name = "${this.name}_then_${other.name}",
    agents = listOf(this, other),
    strategy = Strategy.SEQUENTIAL,
)

// Usage: draftWriter then editor then reviewer
```

### 9.2 Complete Kitchen Sink

```kotlin
package dev.agentspan.examples

import dev.agentspan.*
import dev.agentspan.TerminationCondition.*
import dev.agentspan.HandoffCondition.*
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.runBlocking

// ═══════════════════════════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════════════════════════

val llmModel = System.getenv("AGENTSPAN_LLM_MODEL") ?: "openai/gpt-4o"

// ═══════════════════════════════════════════════════════════════
// STAGE 1: Intake & Classification
// Features: Router, structured output, PromptTemplate
// ═══════════════════════════════════════════════════════════════

val techClassifier = agent("tech_classifier") {
    model(llmModel)
    instructions("Classifies tech articles.")
}

val businessClassifier = agent("business_classifier") {
    model(llmModel)
    instructions("Classifies business articles.")
}

val creativeClassifier = agent("creative_classifier") {
    model(llmModel)
    instructions("Classifies creative articles.")
}

val intakeRouter = agent("intake_router") {
    model(llmModel)
    promptTemplate("article-classifier", variables = mapOf("categories" to "tech, business, creative"))
    agent(techClassifier)
    agent(businessClassifier)
    agent(creativeClassifier)
    strategy = Strategy.ROUTER
    router = agent("category_router") {
        model(llmModel)
        instructions("Route to the appropriate classifier based on the article topic.")
    }
    outputType = OutputType.fromClass<ClassificationResult>()
}

// ═══════════════════════════════════════════════════════════════
// STAGE 2: Research Team
// Features: Parallel, scatter_gather, tools, credentials
// ═══════════════════════════════════════════════════════════════

val researchDatabase = tool("research_database") {
    description = "Search internal research database."; credentials("RESEARCH_API_KEY")
    handler { ctx -> mapOf("query" to ctx.sessionId, "results" to MockData.research["quantum_computing"]) }
}
val analyzeTrends = tool("analyze_trends") {
    description = "Analyze trending topics."; isolated = false; credentials("ANALYTICS_KEY")
    handler { mapOf("topic" to "quantum", "trend_score" to 0.87, "key_present" to (getCredential("ANALYTICS_KEY") != null)) }
}
val webSearch = httpTool(
    name = "web_search", description = "Search the web.", url = "https://api.example.com/search", method = "GET",
    headers = mapOf("Authorization" to "Bearer \${SEARCH_API_KEY}"),
    inputSchema = jsonSchema { property("q", JsonSchema.string); required("q") },
    credentials = listOf("SEARCH_API_KEY"),
)
val mcpFactChecker = mcpTool(
    serverUrl = "http://localhost:3001/mcp", name = "fact_checker", description = "Verify factual claims.",
    toolNames = listOf("verify_claim", "check_source"), credentials = listOf("MCP_AUTH_TOKEN"),
)
// Auto-discover from OpenAPI/Swagger/Postman spec
val stripe = apiTool("https://api.stripe.com/openapi.json") {
    headers("Authorization" to "Bearer \${STRIPE_KEY}")
    credentials("STRIPE_KEY")
    maxTools(20)
}
val externalResearchAggregator = tool("external_research_aggregator") { description = "Remote research."; external = true }

val researcherWorker = agent("research_worker") {
    model(llmModel)
    instructions("Research the given topic thoroughly using available tools.")
    tool(researchDatabase)
    tool(webSearch)
    tool(mcpFactChecker)
    tool(externalResearchAggregator)
    credentials("SEARCH_API_KEY", "MCP_AUTH_TOKEN")
}

val researchCoordinator = scatterGather(
    name = "research_coordinator",
    worker = researcherWorker,
    model = llmModel,
    instructions = "Create research tasks for the topic: web search, data analysis, and fact checking.",
    timeoutSeconds = 300,
)

val dataAnalyst = agent("data_analyst") {
    model(llmModel)
    instructions("Analyze data trends for the topic.")
    tool(analyzeTrends)
}

val researchTeam = agent("research_team") {
    agent(researchCoordinator)
    agent(dataAnalyst)
    strategy = Strategy.PARALLEL
}

// ═══════════════════════════════════════════════════════════════
// STAGE 3: Writing Pipeline
// Features: Sequential, >>/then, ConversationMemory, SemanticMemory, Callbacks
// ═══════════════════════════════════════════════════════════════

val semanticMem = SemanticMemory(maxResults = 3).apply {
    MockData.pastArticles.forEach { add("Past article: ${it["title"]}") }
}

val recallPastArticles = tool("recall_past_articles") {
    description = "Retrieve relevant past articles from semantic memory."
    handler { ctx ->
        semanticMem.search("article").map { mapOf("content" to it.content) }
    }
}

val publishingCallbackHandler = object : CallbackHandler {
    override fun onAgentStart(agentName: String?) { CallbackLog.log("before_agent", agentName) }
    override fun onAgentEnd(agentName: String?) { CallbackLog.log("after_agent", agentName) }
    override fun onModelStart(messages: List<*>?) { CallbackLog.log("before_model") }
    override fun onModelEnd(llmResult: String?) { CallbackLog.log("after_model") }
    override fun onToolStart(toolName: String?) { CallbackLog.log("before_tool", toolName) }
    override fun onToolEnd(toolName: String?) { CallbackLog.log("after_tool", toolName) }
}

val draftWriter = agent("draft_writer") {
    model(llmModel)
    instructions("Write a comprehensive article draft based on research findings.")
    tool(recallPastArticles)
    memory = ConversationMemory(maxMessages = 50)
    callbacks(publishingCallbackHandler)
}

val editor = agent("editor") {
    model(llmModel)
    instructions("Review and edit the article. Fix grammar, improve clarity. When done, include ARTICLE_COMPLETE.")
    stopWhen { messages ->
        messages.lastOrNull()?.content?.contains("ARTICLE_COMPLETE") == true
    }
}

// Sequential pipeline via infix `then`
val writingPipeline = draftWriter then editor

// ═══════════════════════════════════════════════════════════════
// STAGE 4: Review & Safety
// Features: All guardrail types, all OnFail modes, tool guardrails
// ═══════════════════════════════════════════════════════════════

val sqlInjectionGuard = guardrail("sql_injection_guard") { content: String ->
    if (containsSqlInjection(content)) GuardrailResult(passed = false, message = "SQL injection detected.")
    else GuardrailResult(passed = true)
}

val safeSearch = tool("safe_search") {
    description = "Search with SQL injection protection."
    guardrails {
        custom("sql_injection", position = Position.INPUT, onFail = OnFail.RAISE) { content ->
            sqlInjectionGuard.invoke(content)
        }
    }
    handler { ctx -> mapOf("query" to "safe", "results" to listOf("result1", "result2")) }
}

val reviewAgent = agent("safety_reviewer") {
    model(llmModel)
    instructions("Review the article for safety and compliance.")
    tool(safeSearch)
    guardrails {
        // #26 on_fail=RETRY
        regex("pii_blocker") {
            patterns("\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b")
            mode = "block"
            position = Position.OUTPUT
            onFail(OnFail.RETRY)
            message = "PII detected. Redact all personal information."
        }
        // #28 on_fail=FIX
        llm("bias_detector") {
            model = "openai/gpt-4o-mini"
            policy = "Check for biased language or stereotypes. If found, provide corrected version."
            position = Position.OUTPUT
            onFail = OnFail.FIX
            maxTokens = 10000
        }
        // #29 on_fail=HUMAN
        custom("fact_validator", position = Position.OUTPUT, onFail = OnFail.HUMAN) { content ->
            val redFlags = listOf("the best", "the worst", "always", "never", "guaranteed")
            val found = redFlags.filter { it.lowercase() in content.lowercase() }
            if (found.isNotEmpty()) GuardrailResult(passed = false, message = "Unverifiable claims: $found")
            else GuardrailResult(passed = true)
        }
        // #27 on_fail=RAISE (external)
        external("compliance_check", position = Position.OUTPUT, onFail = OnFail.RAISE)
    }
}

// ═══════════════════════════════════════════════════════════════
// STAGE 5: Editorial Approval
// Features: HITL, UserProxyAgent, human_tool
// ═══════════════════════════════════════════════════════════════

val publishArticle = tool("publish_article") {
    description = "Publish article to platform. Requires editorial approval."
    approvalRequired = true
    handler { ctx -> mapOf("status" to "published", "title" to "Article", "platform" to "web") }
}

val editorialQuestion = humanTool(
    name = "ask_editor",
    description = "Ask the editor a question about the article.",
    inputSchema = jsonSchema {
        property("question", JsonSchema.string)
        required("question")
    },
)

val editorialReviewer = UserProxyAgent(
    name = "editorial_reviewer",
    model = llmModel,
    instructions = "You are the editorial reviewer. Provide feedback on article quality.",
    humanInputMode = HumanInputMode.TERMINATE,
)

val editorialAgent = agent("editorial_approval") {
    model(llmModel)
    instructions("Review the article, ask questions, get approval before publishing.")
    tool(publishArticle)
    tool(editorialQuestion)
    agent(editorialReviewer)
    strategy = Strategy.HANDOFF
}

// ═══════════════════════════════════════════════════════════════
// STAGE 6: Translation & Discussion — round_robin, swarm, manual, random, handoffs
// ═══════════════════════════════════════════════════════════════

val spanishTranslator = agent("spanish_translator") {
    model(llmModel); instructions("Translate to Spanish with a formal tone.")
    introduction = "I am the Spanish translator."
}
val frenchTranslator = agent("french_translator") { /* similar */ }
val germanTranslator = agent("german_translator") { /* similar */ }

// Each multi-agent strategy as a separate agent
val toneDebate = agent("tone_debate") {
    agent(spanishTranslator); agent(frenchTranslator); agent(germanTranslator)
    strategy = Strategy.ROUND_ROBIN; maxTurns = 6
}
val translationSwarm = agent("translation_swarm") {
    agent(spanishTranslator); agent(frenchTranslator); agent(germanTranslator)
    strategy = Strategy.SWARM
    handoffs {
        onTextMention("Spanish", target = "spanish_translator")
        onTextMention("French", target = "french_translator")
        onTextMention("German", target = "german_translator")
    }
    allowedTransitions(mapOf(
        "spanish_translator" to listOf("french_translator", "german_translator"),
        "french_translator" to listOf("spanish_translator", "german_translator"),
        "german_translator" to listOf("spanish_translator", "french_translator"),
    ))
}
// Also: titleBrainstorm (RANDOM, maxTurns=3), manualTranslation (MANUAL)

// ═══════════════════════════════════════════════════════════════
// STAGE 7: Publishing Pipeline — Handoff, OnToolResult, OnCondition, external agents, termination, gate
// ═══════════════════════════════════════════════════════════════

val externalPublisher = agent("external_publisher") { external = true; instructions("Publish to CMS.") }

val publishingPipeline = agent("publishing_pipeline") {
    model(llmModel); instructions("Manage publishing workflow.")
    agent(agent("formatter") { model(llmModel); tool(tool("format_check") { handler { mapOf("formatted" to true) } }) })
    agent(externalPublisher)
    strategy = Strategy.HANDOFF
    handoffs {
        onToolResult("external_publisher", toolName = "format_check")
        onCondition("external_publisher") { msgs -> msgs.lastOrNull()?.content?.contains("formatted") == true }
    }
    termination = TextMention("PUBLISHED") or (MaxMessage(50) and TokenUsageLimit(maxTotalTokens = 100_000))
    gate = GateCondition.TextContains("APPROVED")
}

// ═══════════════════════════════════════════════════════════════
// STAGE 8: Analytics — code executors, media tools, RAG, agent_tool, GPTAssistant, thinking, planner
// ═══════════════════════════════════════════════════════════════

val analyticsAgent = agent("analytics_agent") {
    model(llmModel); instructions("Generate a comprehensive analytics report.")
    // Code executors as tools
    tool(LocalCodeExecutor(language = "python", timeout = 10).asTool())
    tool(DockerCodeExecutor(image = "python:3.12-slim", timeout = 15).asTool(name = "run_sandboxed"))
    tool(JupyterCodeExecutor(timeout = 30).asTool(name = "run_notebook"))
    tool(ServerlessCodeExecutor(endpoint = "https://api.example.com/functions/analytics", timeout = 30).asTool(name = "run_cloud"))
    // Media tools
    tool(imageTool(name = "generate_thumbnail", description = "Thumbnail.", llmProvider = "openai", model = "dall-e-3"))
    tool(audioTool(name = "generate_audio_summary", description = "Audio.", llmProvider = "openai", model = "tts-1"))
    tool(videoTool(name = "generate_video_highlight", description = "Video.", llmProvider = "openai", model = "sora"))
    tool(pdfTool(name = "generate_article_pdf", description = "PDF."))
    // RAG tools
    tool(indexTool(name = "index_article", description = "Index.", vectorDb = "pgvector", index = "articles", embeddingModelProvider = "openai", embeddingModel = "text-embedding-3-small"))
    tool(searchTool(name = "search_articles", description = "Search.", vectorDb = "pgvector", index = "articles", embeddingModelProvider = "openai", embeddingModel = "text-embedding-3-small", maxResults = 5))
    // Agent-as-tool
    tool(agentTool(agent = agent("quick_researcher") { model(llmModel); instructions("Quick research.") }, name = "quick_research", description = "Quick research lookup."))
    // GPTAssistantAgent
    agent(GPTAssistantAgent(name = "openai_research_assistant", model = "gpt-4o", instructions = "Research assistant."))
    strategy = Strategy.HANDOFF
    thinkingBudgetTokens = 2048; includeContents = "default"; planner = true
    outputType = OutputType.fromClass<ArticleReport>()
    requiredTools = listOf("index_article")
    codeExecutionConfig = CodeExecutionConfig(enabled = true, allowedLanguages = listOf("python", "shell"), allowedCommands = listOf("python3", "pip"), timeout = 30)
    cliConfig = CliConfig(enabled = true, allowedCommands = listOf("git", "gh"), timeout = 30)
    metadata = mapOf("stage" to "analytics", "version" to "1.0")
}

// ═══════════════════════════════════════════════════════════════
// FULL PIPELINE
// ═══════════════════════════════════════════════════════════════

val fullPipeline = agent("content_publishing_platform") {
    model(llmModel)
    instructions(
        "You are a content publishing platform. Process article requests " +
        "through all pipeline stages: classification, research, writing, " +
        "review, editorial approval, translation, publishing, and analytics."
    )
    agent(intakeRouter)
    agent(researchTeam)
    agent(writingPipeline)
    agent(reviewAgent)
    agent(editorialAgent)
    agent(translationSwarm)
    agent(publishingPipeline)
    agent(analyticsAgent)
    strategy = Strategy.SEQUENTIAL
    termination = TextMention("PIPELINE_COMPLETE") or MaxMessage(200)
}

// ═══════════════════════════════════════════════════════════════
// STAGE 9: Execution Modes
// Features: deploy, plan, stream, start, run, async, discover, tracing
// ═══════════════════════════════════════════════════════════════

fun main() = runBlocking {
    val prompt = "Write a comprehensive tech article about quantum computing advances in 2026."

    if (isTracingEnabled()) println("[tracing] OpenTelemetry tracing is enabled")

    AgentRuntime().use { runtime ->
        // Deploy (compile + register)
        val deployments = runtime.deploy(fullPipeline)
        deployments.forEach { println("  Deployed: ${it.registeredName}") }

        // Plan (dry-run, no execution)
        runtime.plan(fullPipeline)

        // Stream with HITL — exhaustive when on EventType
        val agentStream = runtime.stream(fullPipeline, prompt)
        val hitlState = mutableMapOf("approved" to 0, "rejected" to 0, "feedback" to 0)

        agentStream.asFlow().collect { event ->
            when (event.type) {
                EventType.THINKING       -> println("[thinking] ${event.content?.take(80)}...")
                EventType.TOOL_CALL      -> println("[tool_call] ${event.toolName}")
                EventType.TOOL_RESULT    -> println("[tool_result] ${event.toolName}")
                EventType.HANDOFF        -> println("[handoff] -> ${event.target}")
                EventType.GUARDRAIL_PASS -> println("[guardrail_pass] ${event.guardrailName}")
                EventType.GUARDRAIL_FAIL -> println("[guardrail_fail] ${event.guardrailName}")
                EventType.MESSAGE        -> println("[message] ${event.content?.take(80)}...")
                EventType.WAITING -> when {
                    hitlState["feedback"] == 0   -> { agentStream.send("Add more details."); hitlState["feedback"] = 1 }
                    hitlState["rejected"] == 0   -> { agentStream.reject("Title needs work"); hitlState["rejected"] = 1 }
                    else                         -> { agentStream.approve(); hitlState["approved"] = hitlState.getValue("approved") + 1 }
                }
                EventType.ERROR -> println("[error] ${event.content}")
                EventType.DONE  -> println("[done] Pipeline complete")
            }
        }

        // Token tracking
        val result = agentStream.getResult()
        result.tokenUsage?.let { println("Total tokens: ${it.totalTokens}") }

        // Start + polling
        val handle = runtime.start(fullPipeline, prompt)
        val status = handle.getStatus()
        println("Status: ${status.status}, Running: ${status.isRunning}")

        // Top-level convenience API
        configure(AgentConfig.fromEnv())
        val simpleResult = dev.agentspan.run(agent("simple_test") { model(llmModel); instructions("Say hello.") }, "Hello!")
        println("run() status: ${simpleResult.status}")

        // Discover agents
        runCatching { discoverAgents("sdk/kotlin/examples") }
            .onSuccess { println("Discovered ${it.size} agents") }
            .onFailure { println("Discovery: ${it.message}") }
    }
    shutdown()
}
```

### 9.3 Key Idiom Differences from Python

| Pattern | Python | Kotlin |
|---------|--------|--------|
| Agent chaining | `a >> b >> c` | `a then b then c` (infix) |
| Termination composition | `A() \| (B() & C())` | `A() or (B() and C())` (infix) |
| Decorator-based tool | `@tool def fn(...)` | `tool("name") { handler { ctx -> } }` (DSL) |
| Async iteration | `async for event in stream:` | `flow.collect { event -> }` |
| Context manager | `with AgentRuntime() as rt:` | `AgentRuntime().use { rt -> }` |
| Sync wrapper | `asyncio.run(coro)` | `runBlocking { }` |
| Null safety | `if ctx else "unknown"` | `ctx?.sessionId ?: "unknown"` |
| Pattern matching | `if/elif/else` | `when (event.type) { }` (exhaustive) |
| Union types | `Union[str, PromptTemplate]` | `sealed class` |
