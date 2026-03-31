# Go SDK Translation Guide

**Date:** 2026-03-23
**Base Spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`
**Python Reference:** `sdk/python/examples/kitchen_sink.py`

---

## 1. Project Setup

### Module and Directory Layout

Initialize a Go module rooted at the repository's `sdk/go/` directory:

```
sdk/go/
  go.mod                         # module github.com/agentspan/agentspan-go
  go.sum
  cmd/
    agentspan-validate/          # validation runner CLI binary
      main.go
    kitchen-sink/                # kitchen sink acceptance test binary
      main.go
  pkg/
    agentspan/                   # public SDK package
      agent.go                   # Agent, Strategy, PromptTemplate
      tool.go                    # Tool, ToolContext, tool constructors
      guardrail.go               # Guardrail, GuardrailResult, OnFail, Position
      result.go                  # AgentResult, AgentHandle, AgentStatus, AgentStream
      event.go                   # AgentEvent, EventType
      termination.go             # TerminationCondition and combinators
      handoff.go                 # HandoffCondition types
      memory.go                  # ConversationMemory, SemanticMemory
      credential.go              # GetCredential, CredentialFile, ResolveCredentials
      callback.go                # CallbackHandler interface
      code_executor.go           # CodeExecutor interface + 4 implementations
      config.go                  # AgentConfig, env var loading
      runtime.go                 # AgentRuntime, singleton
      run.go                     # Top-level Run, Start, Stream, Deploy, etc.
      serialize.go               # AgentConfig JSON serialization
      errors.go                  # Error types
      ext.go                     # UserProxyAgent, GPTAssistantAgent
      discovery.go               # DiscoverAgents
      tracing.go                 # IsTracingEnabled
    agentspan/sse/               # internal SSE client
      client.go
    agentspan/worker/            # internal Conductor worker
      poller.go
    agentspan/testing/           # public testing utilities
      mock.go                    # MockRun
      expect.go                  # Expect fluent API
      record.go                  # Record / Replay
      assertions.go              # AssertToolUsed, etc.
  internal/
    httpclient/                  # shared HTTP transport
      client.go
  examples/
    kitchen_sink/
      main.go
      helpers.go
```

### go.mod

```go
module github.com/agentspan/agentspan-go

go 1.22

require (
    github.com/conductor-sdk/conductor-go v1.5.0  // Conductor client (if available)
    github.com/BurntSushi/toml v1.3.0              // TOML config for validation
    go.opentelemetry.io/otel v1.24.0               // optional OTel integration
)
```

### Build Toolchain

All commands assume the standard Go toolchain:

```bash
go build ./...                         # compile everything
go test ./pkg/agentspan/... -v         # run all SDK tests
go run ./cmd/kitchen-sink/             # run kitchen sink
go vet ./...                           # static analysis
golangci-lint run                      # linting (CI)
```

### Key Dependencies

| Dependency | Purpose |
|-----------|---------|
| `net/http` (stdlib) | REST client, SSE streaming |
| `encoding/json` (stdlib) | JSON marshal/unmarshal for AgentConfig |
| `bufio` (stdlib) | Line-by-line SSE parsing |
| `context` (stdlib) | Cancellation, deadlines throughout |
| `sync` (stdlib) | WaitGroup for worker goroutines |
| `time` (stdlib) | Ticker for poll loops, timeouts |
| `conductor-go` | Conductor task polling (optional; can implement directly against REST) |
| `go.opentelemetry.io/otel` | Optional tracing integration |

---

## 2. Type System Mapping

### Mapping Table

| Python | Go | Notes |
|--------|-----|-------|
| `dataclass` | `struct` with `json:"camelCase"` tags | All config structs use camelCase JSON tags |
| `enum(str, Enum)` | `type X string` + `const` block | String-valued constants, not iota |
| `Optional[T]` | `*T` (pointer) | `nil` means absent; use `omitempty` in tags |
| `list[T]` | `[]T` | Nil slice omits from JSON with `omitempty` |
| `dict[K,V]` | `map[K]V` | `map[string]any` for dynamic maps |
| `Callable` | `func(...)` type | Named function types for signatures |
| `Pydantic BaseModel` | struct + `json` tags + manual validation | No runtime schema generation; build JSON Schema explicitly |
| `Union[A,B]` | `interface` or tagged struct | Use `json.RawMessage` where union serialization is needed |

### Core Struct Definitions

```go
package agentspan

import (
    "context"
    "encoding/json"
)

// ── Strategy ────────────────────────────────────────────────────────

type Strategy string

const (
    StrategyHandoff    Strategy = "handoff"
    StrategySequential Strategy = "sequential"
    StrategyParallel   Strategy = "parallel"
    StrategyRouter     Strategy = "router"
    StrategyRoundRobin Strategy = "round_robin"
    StrategyRandom     Strategy = "random"
    StrategySwarm      Strategy = "swarm"
    StrategyManual     Strategy = "manual"
)

// ── Agent ───────────────────────────────────────────────────────────

type Agent struct {
    Name                string                 `json:"name"`
    Model               string                 `json:"model,omitempty"`
    Instructions        any                    `json:"instructions,omitempty"`    // string | *PromptTemplate
    Tools               []Tool                 `json:"tools,omitempty"`
    Agents              []*Agent               `json:"agents,omitempty"`
    Strategy            Strategy               `json:"strategy,omitempty"`
    Router              *Agent                 `json:"router,omitempty"`
    OutputType          *OutputType            `json:"outputType,omitempty"`
    Guardrails          []Guardrail            `json:"guardrails,omitempty"`
    Memory              *ConversationMemory    `json:"memory,omitempty"`
    MaxTurns            *int                   `json:"maxTurns,omitempty"`
    MaxTokens           *int                   `json:"maxTokens,omitempty"`
    Temperature         *float64               `json:"temperature,omitempty"`
    TimeoutSeconds      *int                   `json:"timeoutSeconds,omitempty"`
    External            bool                   `json:"external,omitempty"`
    StopWhen            StopWhenFunc           `json:"-"`                         // not serialized directly
    StopWhenTask        *TaskRef               `json:"stopWhen,omitempty"`        // wire format
    Termination         TerminationCondition   `json:"termination,omitempty"`
    Handoffs            []HandoffCondition     `json:"handoffs,omitempty"`
    AllowedTransitions  map[string][]string    `json:"allowedTransitions,omitempty"`
    Introduction        string                 `json:"introduction,omitempty"`
    Metadata            map[string]any         `json:"metadata,omitempty"`
    Callbacks           []CallbackHandler      `json:"-"`                         // handlers, not serialized
    CallbackConfigs     []CallbackConfig       `json:"callbacks,omitempty"`       // wire format
    Planner             bool                   `json:"planner,omitempty"`
    IncludeContents     string                 `json:"includeContents,omitempty"`
    ThinkingBudget      *int                   `json:"thinkingConfig,omitempty"`
    RequiredTools       []string               `json:"requiredTools,omitempty"`
    Gate                GateCondition          `json:"gate,omitempty"`
    CodeExecution       *CodeExecutionConfig   `json:"codeExecution,omitempty"`
    CLIConfig           *CLIConfig             `json:"cliConfig,omitempty"`
    Credentials         []any                  `json:"credentials,omitempty"`     // string | CredentialFile
}

type StopWhenFunc func(messages []map[string]any) bool

type TaskRef struct {
    TaskName string `json:"taskName"`
}

type PromptTemplate struct {
    Type      string            `json:"type"`      // always "prompt_template"
    Name      string            `json:"name"`
    Variables map[string]string `json:"variables,omitempty"`
    Version   *int              `json:"version,omitempty"`
}

type OutputType struct {
    Schema    map[string]any `json:"schema"`
    ClassName string         `json:"className,omitempty"`
}

type CallbackConfig struct {
    Position string `json:"position"`
    TaskName string `json:"taskName"`
}

// ── AgentResult ─────────────────────────────────────────────────────

type Status string

const (
    StatusCompleted  Status = "COMPLETED"
    StatusFailed     Status = "FAILED"
    StatusTerminated Status = "TERMINATED"
    StatusTimedOut   Status = "TIMED_OUT"
)

type FinishReason string

const (
    FinishStop      FinishReason = "STOP"
    FinishLength    FinishReason = "LENGTH"
    FinishToolCalls FinishReason = "TOOL_CALLS"
    FinishError     FinishReason = "ERROR"
    FinishCancelled FinishReason = "CANCELLED"
    FinishTimeout   FinishReason = "TIMEOUT"
    FinishGuardrail FinishReason = "GUARDRAIL"
    FinishRejected  FinishReason = "REJECTED"
)

type AgentResult struct {
    Output        map[string]any        `json:"output"`
    ExecutionID   string                `json:"executionId"`
    CorrelationID string                `json:"correlationId,omitempty"`
    Messages      []map[string]any      `json:"messages,omitempty"`
    ToolCalls     []ToolCall            `json:"toolCalls,omitempty"`
    Status        Status                `json:"status"`
    FinishReason  FinishReason          `json:"finishReason,omitempty"`
    Error         string                `json:"error,omitempty"`
    TokenUsage    *TokenUsage           `json:"tokenUsage,omitempty"`
    Metadata      map[string]any        `json:"metadata,omitempty"`
    Events        []AgentEvent          `json:"events,omitempty"`
    SubResults    map[string]any        `json:"subResults,omitempty"`
}

func (r *AgentResult) IsSuccess() bool  { return r.Status == StatusCompleted }
func (r *AgentResult) IsFailed() bool   { return r.Status == StatusFailed }
func (r *AgentResult) IsRejected() bool { return r.FinishReason == FinishRejected }

type ToolCall struct {
    Name string         `json:"name"`
    Args map[string]any `json:"args"`
}

type TokenUsage struct {
    PromptTokens     int `json:"promptTokens"`
    CompletionTokens int `json:"completionTokens"`
    TotalTokens      int `json:"totalTokens"`
}

// ── ToolContext ──────────────────────────────────────────────────────

type ToolContext struct {
    SessionID    string         `json:"sessionId"`
    ExecutionID  string         `json:"executionId"`
    AgentName    string         `json:"agentName"`
    Metadata     map[string]any `json:"metadata"`
    Dependencies map[string]any `json:"dependencies"`
    State        map[string]any `json:"state"`
}

// ── GuardrailResult ─────────────────────────────────────────────────

type GuardrailResult struct {
    Passed      bool   `json:"passed"`
    Message     string `json:"message,omitempty"`
    FixedOutput string `json:"fixedOutput,omitempty"`
}

// ── CodeExecutionConfig / CLIConfig ─────────────────────────────────

type CodeExecutionConfig struct {
    Enabled          bool     `json:"enabled"`
    AllowedLanguages []string `json:"allowedLanguages,omitempty"`
    AllowedCommands  []string `json:"allowedCommands,omitempty"`
    Timeout          int      `json:"timeout,omitempty"`
}

type CLIConfig struct {
    Enabled         bool     `json:"enabled"`
    AllowedCommands []string `json:"allowedCommands,omitempty"`
    Timeout         int      `json:"timeout,omitempty"`
    AllowShell      bool     `json:"allowShell,omitempty"`
}

// ── Credential types ────────────────────────────────────────────────

type CredentialFile struct {
    EnvVar       string `json:"envVar"`
    RelativePath string `json:"relativePath,omitempty"`
    Content      string `json:"content,omitempty"`
}

// ── DeploymentInfo ──────────────────────────────────────────────────

type DeploymentInfo struct {
    RegisteredName string `json:"registeredName"`
    AgentName    string `json:"agentName"`
}
```

---

## 3. Functional Options Pattern

Go has no decorators. The idiomatic replacement is the **functional options** pattern: variadic `Option` functions that configure a struct before use.

### Tool Options

```go
// ToolHandler is the user function signature. ToolContext is optional.
type ToolHandler func(ctx context.Context, input map[string]any, tc *ToolContext) (any, error)

type ToolOption func(*Tool)

func WithApproval() ToolOption {
    return func(t *Tool) { t.ApprovalRequired = true }
}

func WithCredentials(names ...string) ToolOption {
    return func(t *Tool) { t.Credentials = append(t.Credentials, names...) }
}

func WithToolTimeout(seconds int) ToolOption {
    return func(t *Tool) { t.TimeoutSeconds = &seconds }
}

func WithIsolated(v bool) ToolOption {
    return func(t *Tool) { t.Isolated = v }
}

func WithExternal() ToolOption {
    return func(t *Tool) { t.External = true }
}

func WithToolGuardrails(gs ...Guardrail) ToolOption {
    return func(t *Tool) { t.Guardrails = append(t.Guardrails, gs...) }
}

// NewTool creates a worker tool with functional options.
func NewTool(name, description string, handler ToolHandler, opts ...ToolOption) Tool {
    t := Tool{
        Name:        name,
        Description: description,
        ToolType:    ToolTypeWorker,
        handler:     handler,
        Isolated:    true, // default
    }
    for _, o := range opts {
        o(&t)
    }
    return t
}
```

Usage:

```go
searchTool := agentspan.NewTool(
    "web_search",
    "Search the web for recent articles.",
    func(ctx context.Context, input map[string]any, tc *agentspan.ToolContext) (any, error) {
        query := input["query"].(string)
        return map[string]any{"results": []string{query + " result"}}, nil
    },
    agentspan.WithCredentials("SEARCH_API_KEY"),
    agentspan.WithToolTimeout(30),
)
```

### Agent Options

```go
type AgentOption func(*Agent)

func WithModel(model string) AgentOption {
    return func(a *Agent) { a.Model = model }
}

func WithInstructions(instr string) AgentOption {
    return func(a *Agent) { a.Instructions = instr }
}

func WithPromptTemplate(name string, vars map[string]string) AgentOption {
    return func(a *Agent) {
        a.Instructions = &PromptTemplate{
            Type: "prompt_template", Name: name, Variables: vars,
        }
    }
}

func WithTools(tools ...Tool) AgentOption {
    return func(a *Agent) { a.Tools = append(a.Tools, tools...) }
}

func WithSubAgents(agents ...*Agent) AgentOption {
    return func(a *Agent) { a.Agents = append(a.Agents, agents...) }
}

func WithStrategy(s Strategy) AgentOption {
    return func(a *Agent) { a.Strategy = s }
}

func WithOutputSchema(schema map[string]any, className string) AgentOption {
    return func(a *Agent) { a.OutputType = &OutputType{Schema: schema, ClassName: className} }
}

func WithGuardrails(gs ...Guardrail) AgentOption {
    return func(a *Agent) { a.Guardrails = append(a.Guardrails, gs...) }
}

func WithMemory(mem *ConversationMemory) AgentOption {
    return func(a *Agent) { a.Memory = mem }
}

func WithTermination(tc TerminationCondition) AgentOption {
    return func(a *Agent) { a.Termination = tc }
}

func WithHandoffs(hs ...HandoffCondition) AgentOption {
    return func(a *Agent) { a.Handoffs = append(a.Handoffs, hs...) }
}

func WithPlanner() AgentOption {
    return func(a *Agent) { a.Planner = true }
}

func WithThinkingBudget(tokens int) AgentOption {
    return func(a *Agent) { a.ThinkingBudget = &tokens }
}

func WithCallbacks(cbs ...CallbackHandler) AgentOption {
    return func(a *Agent) { a.Callbacks = append(a.Callbacks, cbs...) }
}

func NewAgent(name string, opts ...AgentOption) *Agent {
    a := &Agent{Name: name}
    for _, o := range opts {
        o(a)
    }
    return a
}
```

Usage:

```go
reviewer := agentspan.NewAgent("safety_reviewer",
    agentspan.WithModel("openai/gpt-4o"),
    agentspan.WithInstructions("Review the article for safety and compliance."),
    agentspan.WithTools(safeTool),
    agentspan.WithGuardrails(piiGuardrail, biasGuardrail),
)
```

### Guardrail Options

```go
type GuardrailOption func(*Guardrail)

func WithPosition(p Position) GuardrailOption {
    return func(g *Guardrail) { g.Position = p }
}

func WithOnFail(m OnFail) GuardrailOption {
    return func(g *Guardrail) { g.OnFail = m }
}

func WithMaxRetries(n int) GuardrailOption {
    return func(g *Guardrail) { g.MaxRetries = n }
}

type GuardrailFunc func(content string) GuardrailResult

func NewGuardrail(name string, fn GuardrailFunc, opts ...GuardrailOption) Guardrail {
    g := Guardrail{
        Name:          name,
        GuardrailType: GuardrailCustom,
        handler:       fn,
    }
    for _, o := range opts {
        o(&g)
    }
    return g
}
```

Usage:

```go
factValidator := agentspan.NewGuardrail(
    "fact_validator",
    func(content string) agentspan.GuardrailResult {
        if strings.Contains(strings.ToLower(content), "guaranteed") {
            return agentspan.GuardrailResult{Passed: false, Message: "Unverifiable claim"}
        }
        return agentspan.GuardrailResult{Passed: true}
    },
    agentspan.WithPosition(agentspan.PositionOutput),
    agentspan.WithOnFail(agentspan.OnFailHuman),
)
```

---

## 4. Async Model

Go is blocking by default. Goroutines and channels provide the async surface. There is no need for `_async` method variants; instead, the pattern is: blocking functions for synchronous use, goroutine wrappers for concurrency.

### Execution Functions

```go
// Run executes the agent synchronously. Blocks until completion.
func (rt *AgentRuntime) Run(ctx context.Context, agent *Agent, prompt string) (*AgentResult, error) {
    handle, err := rt.Start(ctx, agent, prompt)
    if err != nil {
        return nil, err
    }
    return handle.Wait(ctx)
}

// RunAsync starts execution and returns a channel that receives the result.
func (rt *AgentRuntime) RunAsync(ctx context.Context, agent *Agent, prompt string) <-chan AsyncResult {
    ch := make(chan AsyncResult, 1)
    go func() {
        defer close(ch)
        result, err := rt.Run(ctx, agent, prompt)
        ch <- AsyncResult{Result: result, Err: err}
    }()
    return ch
}

type AsyncResult struct {
    Result *AgentResult
    Err    error
}

// Start fires-and-forgets, returning a handle for later polling.
func (rt *AgentRuntime) Start(ctx context.Context, agent *Agent, prompt string) (*AgentHandle, error) {
    cfg, err := Serialize(agent)
    if err != nil {
        return nil, fmt.Errorf("serialize: %w", err)
    }
    resp, err := rt.httpClient.Post(ctx, "/agent/start", startRequest{
        AgentConfig: cfg,
        Prompt:      prompt,
    })
    if err != nil {
        return nil, err
    }
    return &AgentHandle{
        ExecutionID: resp.ExecutionID,
        runtime:    rt,
    }, nil
}

// Stream opens an SSE connection and returns a channel-based stream.
func (rt *AgentRuntime) Stream(ctx context.Context, agent *Agent, prompt string) (*AgentStream, error) {
    handle, err := rt.Start(ctx, agent, prompt)
    if err != nil {
        return nil, err
    }
    return handle.Stream(ctx)
}
```

### AgentHandle

```go
type AgentHandle struct {
    ExecutionID string
    runtime     *AgentRuntime
}

// Wait polls until the execution completes and returns the result.
func (h *AgentHandle) Wait(ctx context.Context) (*AgentResult, error) {
    ticker := time.NewTicker(500 * time.Millisecond)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done():
            return nil, ctx.Err()
        case <-ticker.C:
            status, err := h.GetStatus(ctx)
            if err != nil {
                return nil, err
            }
            if status.IsComplete {
                return statusToResult(status), nil
            }
        }
    }
}

// GetStatus polls the execution status once.
func (h *AgentHandle) GetStatus(ctx context.Context) (*AgentStatus, error) {
    return h.runtime.httpClient.GetStatus(ctx, h.ExecutionID)
}

// Approve sends HITL approval.
func (h *AgentHandle) Approve(ctx context.Context) error {
    return h.runtime.httpClient.Respond(ctx, h.ExecutionID, map[string]any{"approved": true})
}

// Reject sends HITL rejection with a reason.
func (h *AgentHandle) Reject(ctx context.Context, reason string) error {
    return h.runtime.httpClient.Respond(ctx, h.ExecutionID, map[string]any{
        "approved": false, "reason": reason,
    })
}

// Send sends a feedback message to a waiting agent.
func (h *AgentHandle) Send(ctx context.Context, message string) error {
    return h.runtime.httpClient.Respond(ctx, h.ExecutionID, map[string]any{"message": message})
}

// Stream returns a channel-based event stream for this execution.
func (h *AgentHandle) Stream(ctx context.Context) (*AgentStream, error) {
    events := make(chan AgentEvent, 64)
    sseClient := h.runtime.sseClient
    go func() {
        defer close(events)
        sseClient.Connect(ctx, h.ExecutionID, events)
    }()
    return &AgentStream{
        events: events,
        handle: h,
    }, nil
}
```

### AgentStream (Channel-Based Iteration)

```go
type AgentStream struct {
    events     <-chan AgentEvent
    handle     *AgentHandle
    collected  []AgentEvent
}

// Events returns the read-only event channel for range iteration.
func (s *AgentStream) Events() <-chan AgentEvent {
    return s.events
}

// GetResult drains remaining events and builds an AgentResult.
func (s *AgentStream) GetResult(ctx context.Context) (*AgentResult, error) {
    for evt := range s.events {
        s.collected = append(s.collected, evt)
    }
    return s.handle.GetStatus(ctx) // fetch final status to build result
}

// HITL methods delegate to the handle.
func (s *AgentStream) Approve(ctx context.Context) error       { return s.handle.Approve(ctx) }
func (s *AgentStream) Reject(ctx context.Context, r string) error { return s.handle.Reject(ctx, r) }
func (s *AgentStream) Send(ctx context.Context, msg string) error  { return s.handle.Send(ctx, msg) }
```

Usage with `for range`:

```go
stream, err := runtime.Stream(ctx, agent, "Write an article about Go.")
if err != nil {
    log.Fatal(err)
}
for evt := range stream.Events() {
    switch evt.Type {
    case agentspan.EventThinking:
        fmt.Printf("[thinking] %s\n", evt.Content[:80])
    case agentspan.EventToolCall:
        fmt.Printf("[tool_call] %s(%v)\n", evt.ToolName, evt.Args)
    case agentspan.EventWaiting:
        stream.Approve(ctx)
    case agentspan.EventDone:
        fmt.Println("[done]")
    }
}
```

### context.Context Threading

Every public function accepts `context.Context` as its first argument. This enables:

- **Deadlines:** `ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)`
- **Cancellation:** `cancel()` propagates to SSE goroutines, HTTP calls, worker loops
- **Values:** Pass request-scoped data (tracing spans, etc.)

---

## 5. Worker Implementation

Workers are goroutine-based Conductor task pollers. Each registered tool, guardrail, or callback gets a worker goroutine that polls for tasks, executes the handler, and reports the result.

### Worker Poller

```go
package worker

import (
    "context"
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "time"

    "github.com/agentspan/agentspan-go/pkg/agentspan"
)

type TaskHandler func(ctx context.Context, input map[string]any) (any, error)

type WorkerConfig struct {
    TaskName     string
    PollInterval time.Duration  // default 100ms
    ThreadCount  int            // default 1
    Timeout      time.Duration  // default 120s
}

type Poller struct {
    cfg     WorkerConfig
    handler TaskHandler
    client  *http.Client
    baseURL string
    authHeaders map[string]string
}

func NewPoller(baseURL string, auth map[string]string, cfg WorkerConfig, handler TaskHandler) *Poller {
    return &Poller{
        cfg:         cfg,
        handler:     handler,
        client:      &http.Client{Timeout: cfg.Timeout},
        baseURL:     baseURL,
        authHeaders: auth,
    }
}

// Run starts the poll loop. Blocks until ctx is cancelled.
func (p *Poller) Run(ctx context.Context) {
    ticker := time.NewTicker(p.cfg.PollInterval)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done():
            return
        case <-ticker.C:
            task, err := p.pollTask(ctx)
            if err != nil || task == nil {
                continue
            }
            go p.executeTask(ctx, task)
        }
    }
}

type conductorTask struct {
    TaskID string          `json:"taskId"`
    Input  json.RawMessage `json:"inputData"`
}

func (p *Poller) pollTask(ctx context.Context) (*conductorTask, error) {
    url := fmt.Sprintf("%s/tasks/poll/%s", p.baseURL, p.cfg.TaskName)
    req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
    for k, v := range p.authHeaders {
        req.Header.Set(k, v)
    }
    resp, err := p.client.Do(req)
    if err != nil || resp.StatusCode == http.StatusNoContent {
        return nil, err
    }
    defer resp.Body.Close()
    var task conductorTask
    if err := json.NewDecoder(resp.Body).Decode(&task); err != nil {
        return nil, err
    }
    return &task, nil
}

func (p *Poller) executeTask(ctx context.Context, task *conductorTask) {
    var input map[string]any
    _ = json.Unmarshal(task.Input, &input)

    // Extract ToolContext from __agentspan_ctx__
    var tc *agentspan.ToolContext
    if raw, ok := input["__agentspan_ctx__"]; ok {
        if ctxMap, ok := raw.(map[string]any); ok {
            tc = &agentspan.ToolContext{}
            b, _ := json.Marshal(ctxMap)
            _ = json.Unmarshal(b, tc)
        }
        delete(input, "__agentspan_ctx__")
    }

    // Resolve credentials if execution token is present
    if tc != nil {
        _ = p.resolveCredentials(ctx, tc, input)
    }

    result, err := p.handler(ctx, input)

    status := "COMPLETED"
    var errMsg string
    if err != nil {
        status = "FAILED"
        errMsg = err.Error()
    }

    p.reportResult(ctx, task.TaskID, status, result, errMsg)
}

func (p *Poller) resolveCredentials(ctx context.Context, tc *agentspan.ToolContext, input map[string]any) error {
    // POST /api/credentials/resolve with execution token
    // Inject resolved values into environment or input
    return nil // implementation detail
}

func (p *Poller) reportResult(ctx context.Context, taskID, status string, output any, errMsg string) {
    body := map[string]any{
        "taskId":     taskID,
        "status":     status,
        "outputData": map[string]any{"result": output},
    }
    if errMsg != "" {
        body["reasonForIncompletion"] = errMsg
    }
    // POST to Conductor task update endpoint
}
```

### Worker Manager

The runtime aggregates all workers and starts them as goroutines with a shared context:

```go
type WorkerManager struct {
    pollers []*worker.Poller
    cancel  context.CancelFunc
}

func (wm *WorkerManager) Register(p *worker.Poller) {
    wm.pollers = append(wm.pollers, p)
}

func (wm *WorkerManager) StartAll(parentCtx context.Context) {
    ctx, cancel := context.WithCancel(parentCtx)
    wm.cancel = cancel
    for _, p := range wm.pollers {
        go p.Run(ctx)
    }
}

func (wm *WorkerManager) Shutdown() {
    if wm.cancel != nil {
        wm.cancel()
    }
}
```

---

## 6. SSE Client

The SSE client opens a long-lived HTTP GET with `Accept: text/event-stream`, parses the line-based protocol, handles reconnection, and delivers events through a channel.

```go
package sse

import (
    "bufio"
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "strings"
    "time"

    "github.com/agentspan/agentspan-go/pkg/agentspan"
)

type Client struct {
    baseURL     string
    httpClient  *http.Client
    authHeaders map[string]string
}

func NewClient(baseURL string, auth map[string]string) *Client {
    return &Client{
        baseURL:     baseURL,
        httpClient:  &http.Client{Timeout: 0}, // no timeout on SSE
        authHeaders: auth,
    }
}

// Connect streams events into the channel. Handles reconnection automatically.
// Blocks until ctx is cancelled or a "done" event is received.
func (c *Client) Connect(ctx context.Context, workflowID string, events chan<- agentspan.AgentEvent) {
    var lastEventID string
    for {
        err := c.stream(ctx, workflowID, lastEventID, events, &lastEventID)
        if err == nil {
            return // clean close (done event received)
        }
        if ctx.Err() != nil {
            return // context cancelled
        }
        // Reconnect after brief delay
        select {
        case <-ctx.Done():
            return
        case <-time.After(1 * time.Second):
            // retry with Last-Event-ID
        }
    }
}

func (c *Client) stream(
    ctx context.Context,
    workflowID string,
    lastEventID string,
    events chan<- agentspan.AgentEvent,
    outLastID *string,
) error {
    url := fmt.Sprintf("%s/agent/stream/%s", c.baseURL, workflowID)
    req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
    req.Header.Set("Accept", "text/event-stream")
    req.Header.Set("Cache-Control", "no-cache")
    if lastEventID != "" {
        req.Header.Set("Last-Event-ID", lastEventID)
    }
    for k, v := range c.authHeaders {
        req.Header.Set(k, v)
    }

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return err
    }
    defer resp.Body.Close()

    scanner := bufio.NewScanner(resp.Body)
    var (
        eventType string
        eventID   string
        dataLines []string
    )

    heartbeatTimer := time.NewTimer(15 * time.Second)
    defer heartbeatTimer.Stop()

    for {
        // Check for heartbeat timeout in a non-blocking manner
        select {
        case <-heartbeatTimer.C:
            // 15 seconds with no data at all — SSE may be unavailable
            return fmt.Errorf("heartbeat timeout")
        default:
        }

        if !scanner.Scan() {
            return fmt.Errorf("connection closed: %w", scanner.Err())
        }
        line := scanner.Text()

        // Reset heartbeat timer on any data
        heartbeatTimer.Reset(15 * time.Second)

        // Heartbeat comment — filter out
        if strings.HasPrefix(line, ":") {
            continue
        }

        // Empty line = end of event
        if line == "" {
            if len(dataLines) > 0 {
                data := strings.Join(dataLines, "\n")
                evt := parseEvent(eventType, eventID, data)
                *outLastID = eventID
                events <- evt
                if evt.Type == agentspan.EventDone {
                    return nil // clean termination
                }
            }
            eventType, eventID, dataLines = "", "", nil
            continue
        }

        // Parse field
        if strings.HasPrefix(line, "event:") {
            eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
        } else if strings.HasPrefix(line, "id:") {
            eventID = strings.TrimSpace(strings.TrimPrefix(line, "id:"))
        } else if strings.HasPrefix(line, "data:") {
            dataLines = append(dataLines, strings.TrimPrefix(line, "data:"))
        }
    }
}

func parseEvent(eventType, id, data string) agentspan.AgentEvent {
    var raw map[string]any
    _ = json.Unmarshal([]byte(data), &raw)

    evt := agentspan.AgentEvent{
        Type:       agentspan.EventType(eventType),
        ExecutionID: getStr(raw, "executionId"),
    }
    switch evt.Type {
    case agentspan.EventThinking, agentspan.EventMessage, agentspan.EventError:
        evt.Content = getStr(raw, "content")
    case agentspan.EventToolCall:
        evt.ToolName = getStr(raw, "toolName")
        if args, ok := raw["args"].(map[string]any); ok {
            evt.Args = args
        }
    case agentspan.EventToolResult:
        evt.ToolName = getStr(raw, "toolName")
        evt.Result = raw["result"]
    case agentspan.EventHandoff:
        evt.Target = getStr(raw, "target")
    case agentspan.EventGuardrailPass, agentspan.EventGuardrailFail:
        evt.GuardrailName = getStr(raw, "guardrailName")
        evt.Content = getStr(raw, "content")
    case agentspan.EventDone:
        if output, ok := raw["output"].(map[string]any); ok {
            evt.Output = output
        }
    case agentspan.EventWaiting:
        if pt, ok := raw["pendingTool"].(map[string]any); ok {
            evt.PendingTool = pt
        }
    }
    return evt
}

func getStr(m map[string]any, key string) string {
    if v, ok := m[key].(string); ok {
        return v
    }
    return ""
}
```

Key design points:

- **Reconnection:** On connection drop, the outer `Connect` loop retries with `Last-Event-ID`.
- **Heartbeat filtering:** Lines starting with `:` are ignored (no event emitted).
- **15-second timeout:** If no data (including heartbeats) arrives for 15 seconds, treat as connection lost.
- **Channel delivery:** Events are pushed into a buffered channel. The consumer iterates with `for evt := range stream.Events()`.
- **Clean termination:** On `done` event, the goroutine returns and the channel is closed by the caller.

---

## 7. Error Handling

Go uses explicit `(result, error)` return pairs. The SDK defines a hierarchy of sentinel and typed errors.

### Error Types

```go
package agentspan

import (
    "errors"
    "fmt"
)

// Base error. All SDK errors wrap this.
type AgentspanError struct {
    Message string
    Cause   error
}

func (e *AgentspanError) Error() string {
    if e.Cause != nil {
        return fmt.Sprintf("agentspan: %s: %v", e.Message, e.Cause)
    }
    return fmt.Sprintf("agentspan: %s", e.Message)
}

func (e *AgentspanError) Unwrap() error { return e.Cause }

// AgentAPIError is returned when the server responds with an HTTP error.
type AgentAPIError struct {
    AgentspanError
    StatusCode int
    Body       string
}

// AgentNotFoundError is returned when a referenced agent does not exist.
type AgentNotFoundError struct {
    AgentspanError
    AgentName string
}

// ConfigurationError is returned for invalid agent config.
type ConfigurationError struct {
    AgentspanError
    Field string
}

// CredentialNotFoundError — credential does not exist in the store.
type CredentialNotFoundError struct {
    AgentspanError
    CredentialName string
}

// CredentialAuthError — execution token invalid or expired.
type CredentialAuthError struct {
    AgentspanError
}

// CredentialRateLimitError — 120 calls/min exceeded.
type CredentialRateLimitError struct {
    AgentspanError
}

// CredentialServiceError — server-side error during credential resolution.
type CredentialServiceError struct {
    AgentspanError
}

// GuardrailFailedError wraps a guardrail failure with its result.
type GuardrailFailedError struct {
    AgentspanError
    GuardrailName string
    Result        GuardrailResult
}
```

### Usage with errors.Is / errors.As

```go
result, err := runtime.Run(ctx, agent, "write an article")
if err != nil {
    var apiErr *agentspan.AgentAPIError
    if errors.As(err, &apiErr) {
        log.Printf("API error %d: %s", apiErr.StatusCode, apiErr.Body)
        return
    }

    var credErr *agentspan.CredentialNotFoundError
    if errors.As(err, &credErr) {
        log.Printf("Missing credential: %s", credErr.CredentialName)
        return
    }

    var guardErr *agentspan.GuardrailFailedError
    if errors.As(err, &guardErr) {
        log.Printf("Guardrail %s failed: %s", guardErr.GuardrailName, guardErr.Result.Message)
        return
    }

    log.Fatalf("unexpected error: %v", err)
}
```

### Context Deadlines

```go
// 5-minute timeout for the entire execution
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
defer cancel()

result, err := runtime.Run(ctx, agent, prompt)
if errors.Is(err, context.DeadlineExceeded) {
    log.Println("Agent execution timed out")
}
```

### Tool Error Convention

Tool handlers return `(any, error)`. An `error` return causes the worker to report `FAILED` to Conductor. The server handles retry logic based on the task definition's retry policy. Tool functions never panic; deferred recovery in the worker wraps panics into errors:

```go
func (p *Poller) executeTask(ctx context.Context, task *conductorTask) {
    defer func() {
        if r := recover(); r != nil {
            p.reportResult(ctx, task.TaskID, "FAILED", nil, fmt.Sprintf("panic: %v", r))
        }
    }()
    // ... normal execution
}
```

---

## 8. Testing Framework

The `agentspan/testing` package provides unit testing utilities that mirror the Python `testing` subpackage.

### MockRun

Execute an agent without a server. Useful for testing agent configuration, tool wiring, and serialization:

```go
package testing

import (
    "context"

    "github.com/agentspan/agentspan-go/pkg/agentspan"
)

type MockResult struct {
    Output   map[string]any
    Events   []agentspan.AgentEvent
    Status   agentspan.Status
    ToolCalls []agentspan.ToolCall
}

type MockOption func(*mockConfig)

type mockConfig struct {
    toolResults map[string]any   // tool name -> mock result
    events      []agentspan.AgentEvent
}

func WithMockToolResult(name string, result any) MockOption {
    return func(c *mockConfig) {
        c.toolResults[name] = result
    }
}

func MockRun(ctx context.Context, agent *agentspan.Agent, prompt string, opts ...MockOption) (*MockResult, error) {
    cfg := &mockConfig{toolResults: make(map[string]any)}
    for _, o := range opts {
        o(cfg)
    }
    // Validate serialization, simulate tool calls, return mock result
    _, err := agentspan.Serialize(agent)
    if err != nil {
        return nil, err
    }
    return &MockResult{
        Output:   map[string]any{"result": "mock output for: " + prompt},
        Status:   agentspan.StatusCompleted,
    }, nil
}
```

### Fluent Assertions (Expect)

```go
type Expectation struct {
    result *agentspan.AgentResult
    t      TestingT // *testing.T or compatible
}

type TestingT interface {
    Errorf(format string, args ...any)
    FailNow()
}

func Expect(t TestingT, result *agentspan.AgentResult) *Expectation {
    return &Expectation{result: result, t: t}
}

func (e *Expectation) Completed() *Expectation {
    if e.result.Status != agentspan.StatusCompleted {
        e.t.Errorf("expected COMPLETED, got %s", e.result.Status)
    }
    return e
}

func (e *Expectation) Failed() *Expectation {
    if e.result.Status != agentspan.StatusFailed {
        e.t.Errorf("expected FAILED, got %s", e.result.Status)
    }
    return e
}

func (e *Expectation) OutputContains(text string) *Expectation {
    output := fmt.Sprintf("%v", e.result.Output)
    if !strings.Contains(output, text) {
        e.t.Errorf("output does not contain %q: %s", text, output)
    }
    return e
}

func (e *Expectation) ToolUsed(toolName string) *Expectation {
    for _, tc := range e.result.ToolCalls {
        if tc.Name == toolName {
            return e
        }
    }
    e.t.Errorf("tool %q was not used", toolName)
    return e
}

func (e *Expectation) GuardrailPassed(name string) *Expectation {
    for _, evt := range e.result.Events {
        if evt.Type == agentspan.EventGuardrailPass && evt.GuardrailName == name {
            return e
        }
    }
    e.t.Errorf("guardrail %q did not pass", name)
    return e
}
```

### Table-Driven Tests

```go
func TestAgentConfigs(t *testing.T) {
    tests := []struct {
        name     string
        agent    *agentspan.Agent
        prompt   string
        wantTool string
    }{
        {
            name: "research with search tool",
            agent: agentspan.NewAgent("researcher",
                agentspan.WithModel("openai/gpt-4o"),
                agentspan.WithTools(searchTool),
            ),
            prompt:   "find articles about Go",
            wantTool: "web_search",
        },
        {
            name: "editor with guardrails",
            agent: agentspan.NewAgent("editor",
                agentspan.WithModel("openai/gpt-4o"),
                agentspan.WithGuardrails(piiGuardrail),
            ),
            prompt:   "review this article",
            wantTool: "",
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result, err := astesting.MockRun(context.Background(), tt.agent, tt.prompt)
            if err != nil {
                t.Fatalf("MockRun: %v", err)
            }
            exp := astesting.Expect(t, toAgentResult(result)).Completed()
            if tt.wantTool != "" {
                exp.ToolUsed(tt.wantTool)
            }
        })
    }
}
```

### Record / Replay

```go
// Record wraps a runtime and captures all HTTP interactions.
func Record(rt *agentspan.AgentRuntime, path string) *RecordingRuntime {
    return &RecordingRuntime{inner: rt, filePath: path}
}

// Replay loads a recording and replays responses without a server.
func Replay(path string) (*agentspan.AgentRuntime, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, err
    }
    // Build a runtime with a mock HTTP transport that replays recorded responses
    return newReplayRuntime(data)
}
```

### Validation Binary

The `cmd/agentspan-validate/` binary reads a TOML config (same format as the Python runner) and executes examples:

```toml
# validation/runs.toml
[runs.openai]
model = "openai/gpt-4o"
group = "SMOKE_TEST"
timeout = 300

[runs.anthropic]
model = "anthropic/claude-3-sonnet"
group = "SMOKE_TEST"
timeout = 300

[judge]
model = "openai/gpt-4o-mini"
max_output_chars = 3000
max_tokens = 300
```

```bash
go run ./cmd/agentspan-validate/ --config validation/runs.toml
go run ./cmd/agentspan-validate/ --config validation/runs.toml --run openai --dry-run
go run ./cmd/agentspan-validate/ --config validation/runs.toml --judge
```

---

## 9. Kitchen Sink Translation

This section provides the complete annotated outline of the Python kitchen sink translated to idiomatic Go. Each stage maps directly to the Python reference at `sdk/python/examples/kitchen_sink.py`.

### Pipeline and Condition Helpers

Go has no `>>` operator overloading. Use `Pipeline()` to build sequential agents and `And()`/`Or()` functions for termination composition:

```go
// Pipeline creates a sequential agent from a list of agents (replaces >>).
func Pipeline(agents ...*Agent) *Agent {
    return &Agent{
        Name:     agents[0].Name + "_pipeline",
        Agents:   agents,
        Strategy: StrategySequential,
    }
}

// Or composes two termination conditions with OR semantics.
func Or(a, b TerminationCondition) TerminationCondition {
    return TerminationCondition{Type: "or", Conditions: []TerminationCondition{a, b}}
}

// And composes two termination conditions with AND semantics.
func And(a, b TerminationCondition) TerminationCondition {
    return TerminationCondition{Type: "and", Conditions: []TerminationCondition{a, b}}
}
```

### Stage 1: Intake and Classification

```go
// Structured output schema for classification
classificationSchema := map[string]any{
    "type": "object",
    "properties": map[string]any{
        "category": map[string]any{"type": "string"},
        "priority": map[string]any{"type": "integer"},
        "metadata": map[string]any{"type": "object"},
    },
    "required": []string{"category", "priority"},
}

techClassifier := agentspan.NewAgent("tech_classifier",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Classifies tech articles."),
)
businessClassifier := agentspan.NewAgent("business_classifier",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Classifies business articles."),
)
creativeClassifier := agentspan.NewAgent("creative_classifier",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Classifies creative articles."),
)

intakeRouter := agentspan.NewAgent("intake_router",
    agentspan.WithModel(llmModel),
    agentspan.WithPromptTemplate("article-classifier", map[string]string{
        "categories": "tech, business, creative",
    }),
    agentspan.WithSubAgents(techClassifier, businessClassifier, creativeClassifier),
    agentspan.WithStrategy(agentspan.StrategyRouter),
    agentspan.WithOutputSchema(classificationSchema, "ClassificationResult"),
)
// Set router as a nested agent
intakeRouter.Router = agentspan.NewAgent("category_router",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Route to the appropriate classifier based on the article topic."),
)
```

### Stage 2: Research Team

```go
// Native tool with ToolContext injection + file-based credentials
researchDB := agentspan.NewTool(
    "research_database",
    "Search internal research database.",
    func(ctx context.Context, input map[string]any, tc *agentspan.ToolContext) (any, error) {
        session := "unknown"
        if tc != nil { session = tc.SessionID }
        return map[string]any{
            "query": input["query"], "session_id": session,
            "results": mockResearchData,
        }, nil
    },
    agentspan.WithCredentials("RESEARCH_API_KEY"),
)

// HTTP tool with credential header substitution
webSearch := agentspan.HTTPTool("web_search",
    "Search the web for recent articles and papers.",
    "https://api.example.com/search", "GET",
    agentspan.WithHTTPHeaders(map[string]string{
        "Authorization": "Bearer ${SEARCH_API_KEY}",
    }),
    agentspan.WithCredentials("SEARCH_API_KEY"),
)

// MCP tool
mcpFactChecker := agentspan.MCPTool(
    "http://localhost:3001/mcp",
    agentspan.WithMCPName("fact_checker"),
    agentspan.WithMCPToolNames("verify_claim", "check_source"),
    agentspan.WithCredentials("MCP_AUTH_TOKEN"),
)

// Auto-discover from OpenAPI/Swagger/Postman spec
stripe := agentspan.NewApiTool("https://api.stripe.com/openapi.json",
    agentspan.WithHeaders(map[string]string{"Authorization": "Bearer ${STRIPE_KEY}"}),
    agentspan.WithCredentials("STRIPE_KEY"),
    agentspan.WithMaxTools(20),
)

// External tool (by-reference, no local worker)
externalResearch := agentspan.NewTool(
    "external_research_aggregator",
    "Aggregate research from external sources. Runs on remote worker.",
    nil, // no handler
    agentspan.WithExternal(),
)

// scatter_gather
researchCoordinator := agentspan.ScatterGather("research_coordinator",
    agentspan.NewAgent("research_worker",
        agentspan.WithModel(llmModel),
        agentspan.WithTools(researchDB, webSearch, mcpFactChecker, externalResearch),
    ),
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Create research tasks for the topic."),
)

dataAnalyst := agentspan.NewAgent("data_analyst",
    agentspan.WithModel(llmModel),
    agentspan.WithTools(analyzeTrends),
)

researchTeam := agentspan.NewAgent("research_team",
    agentspan.WithSubAgents(researchCoordinator, dataAnalyst),
    agentspan.WithStrategy(agentspan.StrategyParallel),
)
```

### Stage 3: Writing Pipeline

```go
semanticMem := agentspan.NewSemanticMemory(3)
for _, article := range mockPastArticles {
    semanticMem.Add("Past article: " + article.Title)
}

recallTool := agentspan.NewTool("recall_past_articles",
    "Retrieve relevant past articles from semantic memory.",
    func(ctx context.Context, input map[string]any, _ *agentspan.ToolContext) (any, error) {
        results := semanticMem.Search(input["query"].(string))
        out := make([]map[string]any, len(results))
        for i, r := range results { out[i] = map[string]any{"content": r.Content} }
        return out, nil
    },
)

// CallbackHandler implementation
type publishingCallbacks struct{}

func (p *publishingCallbacks) OnAgentStart(name string, _ map[string]any)  { log.Printf("before_agent: %s", name) }
func (p *publishingCallbacks) OnAgentEnd(name string, _ map[string]any)    { log.Printf("after_agent: %s", name) }
func (p *publishingCallbacks) OnModelStart(name string, _ map[string]any)  { log.Printf("before_model: %s", name) }
func (p *publishingCallbacks) OnModelEnd(name string, _ map[string]any)    { log.Printf("after_model: %s", name) }
func (p *publishingCallbacks) OnToolStart(name string, _ map[string]any)   { log.Printf("before_tool: %s", name) }
func (p *publishingCallbacks) OnToolEnd(name string, _ map[string]any)     { log.Printf("after_tool: %s", name) }

draftWriter := agentspan.NewAgent("draft_writer",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Write a comprehensive article draft based on research findings."),
    agentspan.WithTools(recallTool),
    agentspan.WithMemory(agentspan.NewConversationMemory(50)),
    agentspan.WithCallbacks(&publishingCallbacks{}),
)

editor := agentspan.NewAgent("editor",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Review and edit the article. When done, include ARTICLE_COMPLETE."),
)
editor.StopWhen = func(messages []map[string]any) bool {
    if len(messages) == 0 { return false }
    content, _ := messages[len(messages)-1]["content"].(string)
    return strings.Contains(content, "ARTICLE_COMPLETE")
}

// Sequential pipeline (replaces >> operator)
writingPipeline := agentspan.Pipeline(draftWriter, editor)
```

### Stage 4: Review and Safety

```go
piiGuardrail := agentspan.NewRegexGuardrail("pii_blocker",
    []string{`\b\d{3}-\d{2}-\d{4}\b`, `\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b`},
    "block",
    agentspan.WithPosition(agentspan.PositionOutput),
    agentspan.WithOnFail(agentspan.OnFailRetry),
)

biasGuardrail := agentspan.NewLLMGuardrail("bias_detector",
    "openai/gpt-4o-mini",
    "Check for biased language or stereotypes.",
    agentspan.WithPosition(agentspan.PositionOutput),
    agentspan.WithOnFail(agentspan.OnFailFix),
)

factValidator := agentspan.NewGuardrail("fact_validator",
    func(content string) agentspan.GuardrailResult {
        flags := []string{"the best", "the worst", "always", "never", "guaranteed"}
        var found []string
        for _, f := range flags {
            if strings.Contains(strings.ToLower(content), f) { found = append(found, f) }
        }
        if len(found) > 0 {
            return agentspan.GuardrailResult{Passed: false, Message: fmt.Sprintf("Unverifiable claims: %v", found)}
        }
        return agentspan.GuardrailResult{Passed: true}
    },
    agentspan.WithPosition(agentspan.PositionOutput),
    agentspan.WithOnFail(agentspan.OnFailHuman),
)

complianceGuardrail := agentspan.Guardrail{
    Name:          "compliance_check",
    External:      true,
    Position:      agentspan.PositionOutput,
    OnFail:        agentspan.OnFailRaise,
    GuardrailType: agentspan.GuardrailExternal,
}

reviewAgent := agentspan.NewAgent("safety_reviewer",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("Review the article for safety and compliance."),
    agentspan.WithGuardrails(piiGuardrail, biasGuardrail, factValidator, complianceGuardrail),
)
```

### Stage 5: Editorial Approval (HITL)

```go
publishTool := agentspan.NewTool("publish_article",
    "Publish article to platform. Requires editorial approval.",
    func(ctx context.Context, input map[string]any, _ *agentspan.ToolContext) (any, error) {
        return map[string]any{"status": "published", "title": input["title"]}, nil
    },
    agentspan.WithApproval(),
)

editorialQuestion := agentspan.HumanTool("ask_editor",
    "Ask the editor a question about the article.",
)

editorialReviewer := agentspan.NewUserProxyAgent("editorial_reviewer",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("You are the editorial reviewer."),
    agentspan.WithHumanInputMode("TERMINATE"),
)

editorialAgent := agentspan.NewAgent("editorial_approval",
    agentspan.WithModel(llmModel),
    agentspan.WithTools(publishTool, editorialQuestion),
    agentspan.WithSubAgents(editorialReviewer),
    agentspan.WithStrategy(agentspan.StrategyHandoff),
)
```

### Stage 6: Translation and Discussion

```go
spanishTranslator := agentspan.NewAgent("spanish_translator",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("You translate articles to Spanish with a formal tone."),
)
spanishTranslator.Introduction = "I am the Spanish translator."

frenchTranslator := agentspan.NewAgent("french_translator",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("You translate articles to French with a conversational tone."),
)
frenchTranslator.Introduction = "I am the French translator."

germanTranslator := agentspan.NewAgent("german_translator",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("You translate articles to German with a technical tone."),
)
germanTranslator.Introduction = "I am the German translator."

// Swarm with OnTextMention handoffs and allowed_transitions
translationSwarm := agentspan.NewAgent("translation_swarm",
    agentspan.WithSubAgents(spanishTranslator, frenchTranslator, germanTranslator),
    agentspan.WithStrategy(agentspan.StrategySwarm),
    agentspan.WithHandoffs(
        agentspan.OnTextMention{Text: "Spanish", Target: "spanish_translator"},
        agentspan.OnTextMention{Text: "French", Target: "french_translator"},
        agentspan.OnTextMention{Text: "German", Target: "german_translator"},
    ),
)
translationSwarm.AllowedTransitions = map[string][]string{
    "spanish_translator": {"french_translator", "german_translator"},
    "french_translator":  {"spanish_translator", "german_translator"},
    "german_translator":  {"spanish_translator", "french_translator"},
}
```

### Stage 7: Publishing Pipeline

```go
publishingPipeline := agentspan.NewAgent("publishing_pipeline",
    agentspan.WithModel(llmModel),
    agentspan.WithSubAgents(formatter, externalPublisher),
    agentspan.WithStrategy(agentspan.StrategyHandoff),
    agentspan.WithHandoffs(
        agentspan.OnToolResult{Target: "external_publisher", ToolName: "format_check"},
        agentspan.OnCondition{Target: "external_publisher", Func: shouldHandoffToPublisher},
    ),
    agentspan.WithTermination(agentspan.Or(
        agentspan.TextMention("PUBLISHED"),
        agentspan.And(
            agentspan.MaxMessages(50),
            agentspan.MaxTotalTokens(100000),
        ),
    )),
)
publishingPipeline.Gate = agentspan.TextGate("APPROVED")
```

### Stage 8: Analytics and Reporting

```go
localExec := agentspan.NewLocalCodeExecutor("python", 10)
dockerExec := agentspan.NewDockerCodeExecutor("python:3.12-slim", 15)

analyticsAgent := agentspan.NewAgent("analytics_agent",
    agentspan.WithModel(llmModel),
    agentspan.WithTools(
        localExec.AsTool(),
        dockerExec.AsTool("run_sandboxed"),
        articleThumbnail, audioSummary, videoHighlight, articlePDF,
        articleIndexer, articleSearch, researchSubtool,
    ),
    agentspan.WithStrategy(agentspan.StrategyHandoff),
    agentspan.WithThinkingBudget(2048),
    agentspan.WithOutputSchema(articleReportSchema, "ArticleReport"),
    agentspan.WithPlanner(),
)
analyticsAgent.IncludeContents = "default"
analyticsAgent.RequiredTools = []string{"index_article"}
analyticsAgent.CodeExecution = &agentspan.CodeExecutionConfig{
    Enabled: true, AllowedLanguages: []string{"python", "shell"},
    AllowedCommands: []string{"python3", "pip"}, Timeout: 30,
}
analyticsAgent.CLIConfig = &agentspan.CLIConfig{
    Enabled: true, AllowedCommands: []string{"git", "gh"}, Timeout: 30,
}
analyticsAgent.Metadata = map[string]any{"stage": "analytics", "version": "1.0"}
```

### Full Pipeline Composition

```go
fullPipeline := agentspan.NewAgent("content_publishing_platform",
    agentspan.WithModel(llmModel),
    agentspan.WithInstructions("You are a content publishing platform."),
    agentspan.WithSubAgents(
        intakeRouter,       // Stage 1
        researchTeam,       // Stage 2
        writingPipeline,    // Stage 3
        reviewAgent,        // Stage 4
        editorialAgent,     // Stage 5
        translationSwarm,   // Stage 6
        publishingPipeline, // Stage 7
        analyticsAgent,     // Stage 8
    ),
    agentspan.WithStrategy(agentspan.StrategySequential),
    agentspan.WithTermination(agentspan.Or(
        agentspan.TextMention("PIPELINE_COMPLETE"),
        agentspan.MaxMessages(200),
    )),
)
```

### Stage 9: Execution Modes (main function)

```go
func main() {
    ctx := context.Background()
    prompt := "Write a comprehensive tech article about quantum computing advances in 2026."

    if agentspan.IsTracingEnabled() {
        log.Println("[tracing] OpenTelemetry tracing is enabled")
    }

    runtime, err := agentspan.NewRuntime()
    if err != nil {
        log.Fatal(err)
    }
    defer runtime.Shutdown()

    // Deploy
    deployments, err := runtime.Deploy(ctx, fullPipeline)
    if err != nil {
        log.Fatal(err)
    }
    for _, d := range deployments {
        fmt.Printf("Deployed: %s (%s)\n", d.WorkflowName, d.AgentName)
    }

    // Plan (dry-run)
    plan, err := runtime.Plan(ctx, fullPipeline)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Plan compiled: %v\n", plan != nil)

    // Stream execution with HITL
    stream, err := runtime.Stream(ctx, fullPipeline, prompt)
    if err != nil {
        log.Fatal(err)
    }

    hitlState := map[string]int{"approved": 0, "rejected": 0, "feedback": 0}

    for evt := range stream.Events() {
        switch evt.Type {
        case agentspan.EventThinking:
            fmt.Printf("[thinking] %s...\n", truncate(evt.Content, 80))
        case agentspan.EventToolCall:
            fmt.Printf("[tool_call] %s(%v)\n", evt.ToolName, evt.Args)
        case agentspan.EventToolResult:
            fmt.Printf("[tool_result] %s -> %s...\n", evt.ToolName, truncate(fmt.Sprint(evt.Result), 80))
        case agentspan.EventHandoff:
            fmt.Printf("[handoff] -> %s\n", evt.Target)
        case agentspan.EventWaiting:
            fmt.Println("--- HITL: Approval required ---")
            if hitlState["feedback"] == 0 {
                stream.Send(ctx, "Please add more details about quantum error correction.")
                hitlState["feedback"]++
            } else if hitlState["rejected"] == 0 {
                stream.Reject(ctx, "Title needs improvement")
                hitlState["rejected"]++
            } else {
                stream.Approve(ctx)
                hitlState["approved"]++
            }
        case agentspan.EventDone:
            fmt.Println("[done] Pipeline complete")
        case agentspan.EventError:
            fmt.Printf("[error] %s\n", evt.Content)
        }
    }

    result, err := stream.GetResult(ctx)
    if err != nil {
        log.Fatal(err)
    }
    if result.TokenUsage != nil {
        fmt.Printf("Total tokens: %d (prompt: %d, completion: %d)\n",
            result.TokenUsage.TotalTokens, result.TokenUsage.PromptTokens,
            result.TokenUsage.CompletionTokens)
    }

    // Start + polling
    handle, err := runtime.Start(ctx, fullPipeline, prompt)
    if err != nil {
        log.Fatal(err)
    }
    status, _ := handle.GetStatus(ctx)
    fmt.Printf("Status: %s, Running: %v\n", status.Status, status.IsRunning)

    // Async execution via goroutine + channel
    asyncCh := runtime.RunAsync(ctx, fullPipeline, prompt)
    go func() {
        res := <-asyncCh
        if res.Err != nil {
            log.Printf("async error: %v", res.Err)
            return
        }
        fmt.Printf("Async result status: %s\n", res.Result.Status)
    }()

    // Top-level convenience API
    agentspan.Configure(agentspan.ConfigFromEnv())
    simple := agentspan.NewAgent("simple_test",
        agentspan.WithModel(llmModel),
        agentspan.WithInstructions("Say hello."),
    )
    simpleResult, _ := agentspan.Run(ctx, simple, "Hello!")
    fmt.Printf("run() status: %s\n", simpleResult.Status)

    // Discover agents
    agents, err := agentspan.DiscoverAgents("examples/")
    if err == nil {
        fmt.Printf("Discovered %d agents\n", len(agents))
    }

    fmt.Println("=== Kitchen Sink Complete ===")
}

func truncate(s string, n int) string {
    if len(s) > n { return s[:n] }
    return s
}
```

### Summary of Python-to-Go Translations

| Python Pattern | Go Equivalent |
|---------------|---------------|
| `@agent(name=..., model=...)` | `NewAgent("name", WithModel("..."))` |
| `@tool(credentials=[...])` | `NewTool("name", "desc", handler, WithCredentials(...))` |
| `@guardrail` | `NewGuardrail("name", fn, WithPosition(...), WithOnFail(...))` |
| `agent_a >> agent_b >> agent_c` | `Pipeline(agentA, agentB, agentC)` |
| `A \| B` (termination) | `Or(A, B)` |
| `A & B` (termination) | `And(A, B)` |
| `async for event in stream` | `for evt := range stream.Events()` |
| `await stream.approve()` | `stream.Approve(ctx)` |
| `asyncio.run(coro)` | `go func() { ... }()` + channel |
| `Optional[T]` | `*T` (pointer, nil = absent) |
| `with AgentRuntime() as rt` | `rt, _ := NewRuntime(); defer rt.Shutdown()` |
| `CallbackHandler` class | `CallbackHandler` interface with 6 methods |
| `Pydantic BaseModel` | `struct` + JSON tags + manual JSON Schema |
| `get_credential("KEY")` | `agentspan.GetCredential(ctx, "KEY")` |
| `is_tracing_enabled()` | `agentspan.IsTracingEnabled()` |
| `context.WithTimeout` for deadlines | Same -- `context.WithTimeout(ctx, d)` |
