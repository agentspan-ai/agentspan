# Tools

Tools give agents the ability to take actions. In Conductor Agent, each tool invocation runs as a Conductor task — distributed, retryable, and observable in the workflow audit log.

## Java method tools (`@Tool`)

Annotate methods with `@Tool` and convert the containing object to tools with `ToolRegistry.fromInstance()` (returns a `List<ToolDef>`, one per annotated method):

```java
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.model.ToolContext;

public class SearchTools {

    @Tool(name = "web_search", description = "Search the web for current information")
    public String search(String query) {
        return callSearchApi(query);
    }

    @Tool(name = "get_page", description = "Fetch the content of a URL")
    public String getPage(String url) {
        return fetchUrl(url);
    }
}

Agent agent = Agent.builder()
    .name("research_agent")
    .model("openai/gpt-4o-mini")
    .tools(ToolRegistry.fromInstance(new SearchTools()))
    .build();
```

### Tool parameters

The LLM sees a JSON Schema built from the method signature. Supported parameter types: `String`, `int`/`Integer`, `long`/`Long`, `double`/`Double`, `boolean`/`Boolean`, `List<T>`, `Map<String,Object>`, and any `record` or POJO with public getters.

```java
@Tool(name = "create_issue", description = "Create a GitHub issue")
public String createIssue(
    String title,
    String body,
    List<String> labels
) {
    // ...
}
```

### ToolContext

Inject `ToolContext` as the last parameter to access execution metadata, shared state, and credentials:

```java
@Tool(name = "send_email", description = "Send an email", credentials = {"SENDGRID_API_KEY"})
public String sendEmail(String to, String subject, String body, ToolContext ctx) {
    String apiKey       = ctx.getCredential("SENDGRID_API_KEY");
    String executionId  = ctx.getExecutionId();
    String sessionId    = ctx.getSessionId();
    // ...
}
```

`ToolContext.getState()` is a mutable `Map<String,Object>` that persists across tool calls
within the same execution — use it to pass data between tools without routing it through the LLM.

### Credentials in tools

Declare which secrets a tool needs and read them off the `ToolContext`. There is **no** static
`Credentials` class — Java cannot mutate `System.getenv()` at runtime, so the SDK passes resolved
secrets on the per-call context. Declare credentials per tool with `@Tool(credentials = {...})`,
or for all of an agent's tools with `Agent.builder().credentials(...)`:

```java
public class GitHubTools {
    @Tool(name = "create_issue", description = "Create a GitHub issue",
          credentials = {"GITHUB_TOKEN"})
    public String createIssue(String title, ToolContext ctx) {
        String token = ctx.getCredential("GITHUB_TOKEN");      // throws if unresolved
        // String token = ctx.getCredentialOrNull("GITHUB_TOKEN"); // null if unresolved
        // ...
    }
}

// Agent-level declaration (applies to every tool the agent calls):
Agent agent = Agent.builder()
    .name("github_agent")
    .model("openai/gpt-4o-mini")
    .credentials("GITHUB_TOKEN")
    .tools(ToolRegistry.fromInstance(new GitHubTools()))
    .build();

// Store the secret once via the CLI or API:
// agentspan secrets set GITHUB_TOKEN ghp_xxxxx
```

The worker fetches each declared secret from the server (via the execution token) before the
handler runs; if a declared secret is missing on the server, the task fails terminally before
your code executes.

---

## HTTP tools

Call any REST endpoint without writing Java code:

```java
import org.conductoross.conductor.ai.tools.HttpTool;

ToolDef searchTool = HttpTool.builder()
    .name("search")
    .description("Search for products")
    .url("https://api.mystore.com/search")
    .method("GET")
    .build();

Agent agent = Agent.builder()
    .name("shop_agent")
    .model("openai/gpt-4o-mini")
    .tools(searchTool)
    .build();
```

---

## MCP tools

Connect to any [Model Context Protocol](https://modelcontextprotocol.io) server:

```java
import org.conductoross.conductor.ai.tools.McpTool;

ToolDef mcpTool = McpTool.builder()
    .name("filesystem")
    .description("Access the local filesystem via MCP")
    .serverUrl("http://localhost:3001")
    .build();
```

---

## CLI tools

Run shell commands as tool calls. The command runs in your local process; the agent decides the arguments.

```java
import org.conductoross.conductor.ai.execution.CliConfig;

Agent agent = Agent.builder()
    .name("devops_agent")
    .model("openai/gpt-4o-mini")
    .instructions("Run git commands as requested.")
    .cliConfig(CliConfig.builder()
        .allowedCommands(List.of("git status", "git log", "git diff"))
        .timeout(30)
        .build())
    .build();
```

!!! warning "Security"
    Use `allowedCommands` to restrict which commands the agent can execute. Without a whitelist, the agent can run any command the JVM user has permission to execute.

---

## Human-in-the-loop tools

Pause the agent and wait for a human decision:

```java
import org.conductoross.conductor.ai.tools.HumanTool;

ToolDef approvalTool = HumanTool.create(
    "approve_deployment",
    "Request human approval before deploying to production"
);

Agent agent = Agent.builder()
    .name("deploy_agent")
    .model("openai/gpt-4o-mini")
    .tools(approvalTool)
    .build();
```

When the agent calls this tool, execution pauses. Resume it with:

```java
AgentHandle handle = runtime.start(agent, "Deploy version 2.1 to production");

// Later, once a human decides:
handle.approve("Approved by Alice");
// or
handle.reject("Needs more testing");
```

The workflow can wait days — it's stored durably in Conductor.

---

## PDF generation

```java
import org.conductoross.conductor.ai.tools.PdfTool;

ToolDef pdfTool = PdfTool.create("generate_report", "Generate a formatted PDF report");
```

---

## Media generation tools

`MediaTools` produces server-side generation tools — image, audio, video, and PDF. Each takes a
name, description, LLM provider, and model (plus an optional trailing `Map<String,Object>` input
schema to override the defaults):

```java
import org.conductoross.conductor.ai.tools.MediaTools;

ToolDef imageTool = MediaTools.imageTool("generate_image", "Generate an image", "openai", "dall-e-3");
ToolDef audioTool = MediaTools.audioTool("generate_speech", "Text to speech", "openai", "tts-1");
ToolDef videoTool = MediaTools.videoTool("generate_video", "Generate a clip", "openai", "sora");
```

---

## RAG tools

Search and index against a vector database configured on the server (e.g. `pgvectordb`). Provide
the vector DB integration name, index, and embedding provider/model:

```java
import org.conductoross.conductor.ai.tools.RagTools;

ToolDef searchDocs = RagTools.searchTool(
    "search_docs", "Search the knowledge base",
    "pgvectordb", "my_index", "openai", "text-embedding-3-small",
    3);                                   // maxResults

ToolDef indexDoc = RagTools.indexTool(
    "index_doc", "Index a document into the knowledge base",
    "pgvectordb", "my_index", "openai", "text-embedding-3-small");
```

Both have an extra `String namespace` overload (inserted before the last argument); the default
namespace is `"default_ns"`.

---

## Async message tools

Pause the agent loop until an external event delivers a message to the workflow:

```java
import org.conductoross.conductor.ai.tools.WaitForMessageTool;

// Blocking, single message
ToolDef waitTool = WaitForMessageTool.create(
    "wait_for_payment",
    "Wait until the payment webhook confirms the transaction");

// Pull a batch (server cap 100); set blocking=false for a non-blocking poll
ToolDef pullBatch = WaitForMessageTool.create("pull_updates", "Pull queued updates", 10, false);
```

---

## Agent tools (sub-agents)

Any `Agent` can be wrapped as a tool with `AgentTool.from(...)`. Unlike handoff sub-agents, an
agent tool is invoked **inline** by the parent LLM — like a function call — and the child runs its
own workflow before returning its output:

```java
import org.conductoross.conductor.ai.tools.AgentTool;

Agent researcher = Agent.builder()
    .name("researcher")
    .model("openai/gpt-4o-mini")
    .instructions("Research a topic and return a summary.")
    .build();

Agent manager = Agent.builder()
    .name("manager")
    .model("openai/gpt-4o-mini")
    .instructions("Use the researcher tool to gather information.")
    .tools(AgentTool.from(researcher))            // callable like a function
    // AgentTool.from(researcher, "custom description") to override the description
    .build();
```

Adding a sub-agent via `.agents(researcher)` (with a [strategy](multi-agent.md)) instead delegates
control rather than calling inline. See [Multi-Agent](multi-agent.md) for orchestration patterns.
