# Ruby SDK Translation Guide

**Date:** 2026-03-23
**Base spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`
**Reference implementation:** `sdk/python/examples/kitchen_sink.py`
**Target:** Ruby 3.2+

---

## 1. Project Setup

### Gem Structure

```
agentspan-ruby/
  agentspan.gemspec
  Gemfile
  Rakefile
  lib/
    agentspan.rb                  # Top-level require, autoload tree
    agentspan/
      version.rb
      configuration.rb            # ENV-based config (AgentConfig)
      agent.rb                    # Agent class + DSL
      agent_runtime.rb            # Runtime lifecycle
      tool.rb                     # @tool equivalent, ToolDef, ToolContext
      guardrail.rb                # Guardrail, RegexGuardrail, LLMGuardrail
      result.rb                   # AgentResult, AgentHandle, AgentStatus
      stream.rb                   # AgentStream (sync), AsyncAgentStream
      event.rb                    # AgentEvent, EventType
      termination.rb              # Composable TerminationCondition
      handoff.rb                  # OnToolResult, OnTextMention, OnCondition
      memory.rb                   # ConversationMemory, SemanticMemory
      code_executor.rb            # Local, Docker, Jupyter, Serverless
      callback.rb                 # CallbackHandler
      credential.rb               # get_credential, CredentialFile, resolve
      prompt_template.rb          # PromptTemplate
      gate.rb                     # TextGate, custom gate
      serializer.rb               # Agent tree -> AgentConfig JSON
      worker.rb                   # Conductor poll loop
      sse_client.rb               # SSE parser + reconnect
      http_client.rb              # REST wrapper (Faraday or Net::HTTP)
      errors.rb                   # Exception hierarchy
      ext/
        user_proxy_agent.rb
        gpt_assistant_agent.rb
      testing/
        mock.rb                   # mock_run
        matchers.rb               # RSpec custom matchers
        recording.rb              # record / replay
        strategy_validators.rb
      discovery.rb                # discover_agents
      tracing.rb                  # is_tracing_enabled?
  spec/
    spec_helper.rb
    agentspan/
      agent_spec.rb
      tool_spec.rb
      guardrail_spec.rb
      serializer_spec.rb
      worker_spec.rb
      sse_client_spec.rb
      ...
```

### Gemspec

```ruby
# agentspan.gemspec
Gem::Specification.new do |s|
  s.name        = "agentspan"
  s.version     = Agentspan::VERSION
  s.summary     = "Agentspan SDK for Ruby"
  s.authors     = ["Agentspan"]
  s.license     = "MIT"
  s.required_ruby_version = ">= 3.2.0"

  s.add_dependency "faraday",       "~> 2.0"
  s.add_dependency "faraday-retry", "~> 2.0"
  s.add_dependency "json",          "~> 2.7"
  s.add_dependency "concurrent-ruby", "~> 1.2"

  s.add_development_dependency "rspec",      "~> 3.13"
  s.add_development_dependency "webmock",    "~> 3.23"
  s.add_development_dependency "rubocop",    "~> 1.60"
  s.add_development_dependency "dry-schema", "~> 1.13"
  s.add_development_dependency "async",      "~> 2.0"
end
```

### Gemfile

```ruby
source "https://rubygems.org"
gemspec

group :development, :test do
  gem "rspec"
  gem "webmock"
  gem "rubocop"
  gem "dry-schema"
  gem "async"
  gem "async-http"
end
```

### Top-Level Require

```ruby
# lib/agentspan.rb
require "json"
require "faraday"
require "concurrent"

module Agentspan
  autoload :VERSION,           "agentspan/version"
  autoload :Configuration,     "agentspan/configuration"
  autoload :Agent,             "agentspan/agent"
  autoload :AgentRuntime,      "agentspan/agent_runtime"
  autoload :ToolDef,           "agentspan/tool"
  autoload :ToolContext,       "agentspan/tool"
  autoload :Guardrail,         "agentspan/guardrail"
  autoload :RegexGuardrail,    "agentspan/guardrail"
  autoload :LLMGuardrail,      "agentspan/guardrail"
  autoload :GuardrailResult,   "agentspan/guardrail"
  autoload :AgentResult,       "agentspan/result"
  autoload :AgentHandle,       "agentspan/result"
  autoload :AgentStatus,       "agentspan/result"
  autoload :AgentStream,       "agentspan/stream"
  autoload :AgentEvent,        "agentspan/event"
  autoload :TerminationCondition, "agentspan/termination"
  autoload :ConversationMemory,   "agentspan/memory"
  autoload :SemanticMemory,       "agentspan/memory"
  # ... remaining autoloads

  class << self
    def configure(config = nil, &block)
      if block
        @config = Configuration.new
        @config.instance_eval(&block)
      else
        @config = config || Configuration.from_env
      end
    end

    def run(agent, prompt, **opts)       = runtime.run(agent, prompt, **opts)
    def start(agent, prompt, **opts)     = runtime.start(agent, prompt, **opts)
    def stream(agent, prompt, **opts)    = runtime.stream(agent, prompt, **opts)
    def deploy(agent, **opts)            = runtime.deploy(agent, **opts)
    def plan(agent)                      = runtime.plan(agent)
    def serve                            = runtime.serve
    def shutdown                         = runtime.shutdown
    def discover_agents(path)            = Discovery.scan(path)
    def tracing_enabled?                 = Tracing.enabled?

    private

    def runtime
      @runtime ||= AgentRuntime.new(@config || Configuration.from_env)
    end
  end
end
```

---

## 2. Type System Mapping

Ruby 3.2 introduced `Data.define`, a frozen value object. Use it for all immutable result/event types. Use plain classes with `attr_reader` for mutable builder-style objects like `Agent`. Use module constants for enums.

### Enum Modules

```ruby
module Agentspan
  module Strategy
    HANDOFF     = "handoff"
    SEQUENTIAL  = "sequential"
    PARALLEL    = "parallel"
    ROUTER      = "router"
    ROUND_ROBIN = "round_robin"
    RANDOM      = "random"
    SWARM       = "swarm"
    MANUAL      = "manual"

    ALL = [HANDOFF, SEQUENTIAL, PARALLEL, ROUTER,
           ROUND_ROBIN, RANDOM, SWARM, MANUAL].freeze
  end

  module EventType
    THINKING       = "thinking"
    TOOL_CALL      = "tool_call"
    TOOL_RESULT    = "tool_result"
    HANDOFF        = "handoff"
    WAITING        = "waiting"
    MESSAGE        = "message"
    ERROR          = "error"
    DONE           = "done"
    GUARDRAIL_PASS = "guardrail_pass"
    GUARDRAIL_FAIL = "guardrail_fail"

    ALL = [THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING,
           MESSAGE, ERROR, DONE, GUARDRAIL_PASS, GUARDRAIL_FAIL].freeze
  end

  module OnFail
    RETRY = "retry"
    RAISE = "raise"
    FIX   = "fix"
    HUMAN = "human"
  end

  module Position
    INPUT  = "input"
    OUTPUT = "output"
  end

  module Status
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    TERMINATED = "TERMINATED"
    TIMED_OUT  = "TIMED_OUT"
  end

  module FinishReason
    STOP       = "stop"
    LENGTH     = "length"
    TOOL_CALLS = "tool_calls"
    ERROR      = "error"
    CANCELLED  = "cancelled"
    TIMEOUT    = "timeout"
    GUARDRAIL  = "guardrail"
    REJECTED   = "rejected"
  end
end
```

### Data Types (Ruby 3.2+ `Data.define`)

```ruby
module Agentspan
  TokenUsage = Data.define(:prompt_tokens, :completion_tokens, :total_tokens)

  GuardrailResult = Data.define(:passed, :message, :fixed_output) do
    def initialize(passed:, message: nil, fixed_output: nil)
      super
    end
  end

  AgentEvent = Data.define(
    :type, :content, :tool_name, :args, :result,
    :target, :output, :execution_id, :guardrail_name
  ) do
    def initialize(type:, content: nil, tool_name: nil, args: nil,
                   result: nil, target: nil, output: nil,
                   execution_id: nil, guardrail_name: nil)
      super
    end
  end

  DeploymentInfo = Data.define(:registered_name, :agent_name)

  ExecutionResult = Data.define(:output, :error, :exit_code, :timed_out) do
    def success? = exit_code == 0 && !timed_out
  end

  PromptTemplate = Data.define(:name, :variables, :version) do
    def initialize(name:, variables: {}, version: nil)
      super
    end

    def to_config
      h = { "type" => "prompt_template", "name" => name, "variables" => variables }
      h["version"] = version if version
      h
    end
  end

  CredentialFile = Data.define(:env_var, :relative_path, :content) do
    def initialize(env_var:, relative_path: nil, content: nil)
      super
    end
  end

  ToolContext = Data.define(
    :session_id, :execution_id, :agent_name, :metadata, :dependencies, :state
  ) do
    def initialize(session_id: nil, execution_id: nil, agent_name: nil,
                   metadata: {}, dependencies: {}, state: {})
      super
    end
  end

  MemoryEntry = Data.define(:id, :content, :metadata, :score)
end
```

### Mutable Classes (Builder Pattern)

```ruby
module Agentspan
  class AgentResult
    attr_reader :output, :execution_id, :correlation_id, :messages,
                :tool_calls, :status, :finish_reason, :error,
                :token_usage, :metadata, :events, :sub_results

    def initialize(**attrs)
      attrs.each { |k, v| instance_variable_set(:"@#{k}", v) }
    end

    def success?   = status == Status::COMPLETED
    def failed?    = status == Status::FAILED
    def rejected?  = finish_reason == FinishReason::REJECTED

    def print_result
      puts "Status: #{status}"
      puts "Output: #{output}"
      puts "Tokens: #{token_usage}" if token_usage
    end
  end

  class AgentStatus
    attr_reader :execution_id, :is_complete, :is_running, :is_waiting,
                :output, :status, :reason, :current_task, :messages,
                :pending_tool

    def initialize(**attrs)
      attrs.each { |k, v| instance_variable_set(:"@#{k}", v) }
    end

    alias_method :complete?,  :is_complete
    alias_method :running?,   :is_running
    alias_method :waiting?,   :is_waiting
  end
end
```

### Nilable Convention

Ruby has no typed nils, but convention is to document nilable fields in YARD docs and check with `nil?`:

```ruby
# @param model [String, nil] LLM model identifier
# @param instructions [String, Proc, PromptTemplate, nil] System prompt
```

### Validation (dry-schema, optional)

```ruby
require "dry-schema"

AgentConfigSchema = Dry::Schema.JSON do
  required(:name).filled(:string)
  optional(:model).maybe(:string)
  optional(:strategy).maybe(included_in?: Strategy::ALL)
  optional(:max_turns).maybe(:integer, gt?: 0)
  optional(:timeout_seconds).maybe(:integer, gteq?: 0)
end
```

---

## 3. DSL Blocks

Ruby excels at internal DSLs via `instance_eval` blocks. The Agent class supports both constructor-keyword and block-based styles.

### Block-Based DSL (Idiomatic Ruby)

```ruby
module Agentspan
  class Agent
    attr_reader :name, :_model, :_instructions, :_tools, :_agents,
                :_strategy, :_router, :_output_type, :_guardrails,
                :_memory, :_max_turns, :_max_tokens, :_temperature,
                :_timeout_seconds, :_external, :_stop_when,
                :_termination, :_handoffs, :_allowed_transitions,
                :_introduction, :_metadata, :_callbacks, :_planner,
                :_include_contents, :_thinking_budget_tokens,
                :_required_tools, :_gate, :_code_execution_config,
                :_cli_config, :_credentials

    def initialize(name, **kwargs, &block)
      @name = name

      # Apply keyword arguments as defaults
      kwargs.each do |key, value|
        instance_variable_set(:"@_#{key}", value)
      end

      # Defaults
      @_tools       ||= []
      @_agents      ||= []
      @_guardrails  ||= []
      @_handoffs    ||= []
      @_callbacks   ||= []
      @_max_turns   ||= 25
      @_external    ||= false
      @_planner     ||= false

      # Evaluate DSL block
      instance_eval(&block) if block
    end

    # ── DSL Methods ──────────────────────────────────────────

    def model(value)
      @_model = value
    end

    def instructions(value = nil, &block)
      @_instructions = block || value
    end

    def strategy(value)
      @_strategy = value
    end

    def max_turns(value)
      @_max_turns = value
    end

    def temperature(value)
      @_temperature = value
    end

    def output_type(klass)
      @_output_type = klass
    end

    def introduction(text)
      @_introduction = text
    end

    def metadata(hash)
      @_metadata = hash
    end

    def planner(enabled = true)
      @_planner = enabled
    end

    def thinking_budget_tokens(value)
      @_thinking_budget_tokens = value
    end

    def include_contents(value)
      @_include_contents = value
    end

    def required_tools(*names)
      @_required_tools = names.flatten
    end

    def credentials(*names)
      @_credentials = names.flatten
    end

    # ── Tool registration via DSL block ──────────────────────

    def tool(name_or_callable, **opts, &block)
      if block
        td = ToolDef.new(name: name_or_callable.to_s, function: block, **opts)
      elsif name_or_callable.is_a?(ToolDef)
        td = name_or_callable
      else
        td = ToolDef.new(name: name_or_callable.to_s, **opts)
      end
      @_tools << td
      td
    end

    # ── Guardrail registration via DSL block ─────────────────

    def guardrail(name_or_callable, **opts, &block)
      if block
        g = Guardrail.new(name: name_or_callable.to_s, function: block, **opts)
      elsif name_or_callable.is_a?(Guardrail)
        g = name_or_callable
      else
        g = Guardrail.new(name: name_or_callable.to_s, **opts)
      end
      @_guardrails << g
      g
    end

    # ── Sub-agent registration ───────────────────────────────

    def agent(child_agent)
      @_agents << child_agent
    end

    def agents(*list)
      @_agents.concat(list.flatten)
    end

    # ── Memory ───────────────────────────────────────────────

    def memory(mem)
      @_memory = mem
    end

    # ── Termination ──────────────────────────────────────────

    def termination(cond)
      @_termination = cond
    end

    def stop_when(callable = nil, &block)
      @_stop_when = callable || block
    end

    # ── Handoffs ─────────────────────────────────────────────

    def handoff(condition)
      @_handoffs << condition
    end

    def handoffs(*list)
      @_handoffs.concat(list.flatten)
    end

    def allowed_transitions(hash)
      @_allowed_transitions = hash
    end

    # ── Gate ─────────────────────────────────────────────────

    def gate(condition)
      @_gate = condition
    end

    # ── Callbacks ────────────────────────────────────────────

    def callback(handler)
      @_callbacks << handler
    end

    def callbacks(*list)
      @_callbacks.concat(list.flatten)
    end

    # ── Code / CLI config ────────────────────────────────────

    def code_execution_config(cfg)
      @_code_execution_config = cfg
    end

    def cli_config(cfg)
      @_cli_config = cfg
    end

    # ── Chaining operator ────────────────────────────────────

    def >>(other)
      Agent.new("#{name}_then_#{other.name}",
                agents: [self, other],
                strategy: Strategy::SEQUENTIAL)
    end
  end
end
```

### Usage Examples

```ruby
# Block-based DSL
researcher = Agentspan::Agent.new("researcher") do
  model "openai/gpt-4o"
  instructions "Research the topic thoroughly."
  temperature 0.3

  tool :web_search do |query:|
    HTTPClient.get("https://api.example.com/search?q=#{query}")
  end

  tool :database_lookup, credentials: ["DB_TOKEN"] do |query:, ctx: nil|
    { results: MockDB.search(query), session: ctx&.session_id }
  end

  guardrail :pii_check, position: Agentspan::Position::OUTPUT,
                         on_fail: Agentspan::OnFail::RETRY do |content|
    if content.match?(/\d{3}-\d{2}-\d{4}/)
      Agentspan::GuardrailResult.new(passed: false, message: "PII detected")
    else
      Agentspan::GuardrailResult.new(passed: true)
    end
  end
end

# Keyword-based construction (no block)
editor = Agentspan::Agent.new("editor",
  model: "openai/gpt-4o",
  instructions: "Review and edit the article. Say ARTICLE_COMPLETE when done.",
  stop_when: ->(messages, **) {
    messages.last&.dig("content")&.include?("ARTICLE_COMPLETE")
  }
)

# Chaining with >>
pipeline = researcher >> editor
```

### Method-Based Registration Alternative

For users who prefer explicit method calls over DSL blocks:

```ruby
agent = Agentspan::Agent.new("my_agent")
agent.model("openai/gpt-4o")
agent.instructions("Do the thing.")
agent.tool(my_tool_def)
agent.guardrail(my_guardrail)
```

### `@agent` Decorator Equivalent

Ruby does not have decorators, but the `Agentspan.define_agent` pattern with a block serves the same purpose:

```ruby
tech_classifier = Agentspan::Agent.new("tech_classifier") do
  model "openai/gpt-4o"
  instructions "Classifies tech articles."
end

# Or use a module-level helper that wraps a Proc:
module MyAgents
  extend Agentspan::AgentDSL

  define_agent :tech_classifier, model: "openai/gpt-4o" do
    instructions "Classifies tech articles."
  end
end
```

---

## 4. Async Model

Ruby is primarily synchronous with three concurrency mechanisms at different levels of maturity.

### Thread (Basic Parallelism)

The simplest and most portable. Use `Thread.new` for background work and `Queue` for communication.

```ruby
# Fire-and-forget with Thread
handle = Thread.new { runtime.run(agent, prompt) }
# ... do other work ...
result = handle.value  # blocks until thread completes

# Parallel execution of multiple agents
threads = agents.map do |a|
  Thread.new { runtime.run(a, prompt) }
end
results = threads.map(&:value)
```

### async Gem (Fiber-Based Concurrency)

The `async` gem provides cooperative concurrency via Fibers. Ideal for I/O-bound workloads like HTTP polling and SSE streaming. This is the recommended approach for the SDK internals.

```ruby
require "async"
require "async/http/internet"

# Async execution
Async do |task|
  # Concurrent SSE + polling
  sse_task = task.async { sse_client.connect(execution_id) }
  poll_task = task.async { poller.start(execution_id) }

  # Wait for first to complete
  result = sse_task.wait
  poll_task.stop
end

# Async stream consumption
Async do
  stream = runtime.stream_async(agent, prompt)
  stream.each do |event|
    case event.type
    when Agentspan::EventType::DONE
      break
    when Agentspan::EventType::WAITING
      stream.approve
    end
  end
end
```

### Ractor (True Parallelism, Ruby 3.0+)

Ractors provide true parallel execution without shared mutable state. Useful for CPU-bound tool execution where credential isolation is important.

```ruby
# Isolated tool execution in a Ractor
ractor = Ractor.new(tool_fn, input, credentials) do |fn, inp, creds|
  # Each Ractor has its own isolated state
  ENV.update(creds)
  result = fn.call(**inp)
  result
end

result = ractor.take  # blocks until Ractor completes
```

### Mapping to SDK Functions

| SDK Function | Ruby Sync | Ruby Async |
|---|---|---|
| `run` | Block on Thread (default) | `Async { runtime.run_async(...) }` |
| `run_async` | Returns `Concurrent::Promises::Future` | Returns `Async::Task` |
| `start` | Returns `AgentHandle` immediately | Same |
| `stream` | Blocking `Enumerator` | `Async::Enumerator` |
| `stream_async` | N/A | `Async { }` block with async iteration |
| `deploy` | Blocking HTTP call | `Async { runtime.deploy_async(...) }` |
| `serve` | Blocking loop (main thread) | `Async { }` event loop |

### concurrent-ruby for Futures

```ruby
require "concurrent"

# Future-based async
future = Concurrent::Promises.future { runtime.run(agent, prompt) }
future.on_fulfillment { |result| puts result.output }
future.on_rejection { |err| puts "Error: #{err}" }

# Or block:
result = future.value!  # raises on failure
```

---

## 5. Worker Implementation

Workers poll the Conductor task queue, execute tool/guardrail/callback functions, and report results back. The Ruby worker uses a background Thread with a poll-sleep loop. For higher concurrency, swap to `Async::Task`.

### Thread-Based Worker

```ruby
module Agentspan
  class Worker
    attr_reader :task_name, :function, :running

    def initialize(task_name:, function:, poll_interval: 0.1,
                   thread_count: 1, timeout: 120, credentials: [],
                   isolated: true, http_client:)
      @task_name     = task_name
      @function      = function
      @poll_interval = poll_interval
      @thread_count  = thread_count
      @timeout       = timeout
      @credentials   = credentials
      @isolated      = isolated
      @http          = http_client
      @running       = false
      @threads       = []
    end

    def start
      @running = true
      @thread_count.times do
        @threads << Thread.new { poll_loop }
      end
    end

    def stop
      @running = false
      @threads.each(&:join)
      @threads.clear
    end

    private

    def poll_loop
      while @running
        begin
          task = poll_for_task
          if task
            execute_task(task)
          else
            sleep(@poll_interval)
          end
        rescue => e
          log_error("Worker #{@task_name} error: #{e.message}")
          sleep(@poll_interval)
        end
      end
    end

    def poll_for_task
      response = @http.post("/tasks/poll/#{@task_name}", {
        "workerId" => worker_id
      }.to_json)
      return nil if response.status == 204 || response.body.nil? || response.body.empty?
      JSON.parse(response.body)
    end

    def execute_task(task)
      task_id  = task["taskId"]
      input    = task.fetch("inputData", {})
      ctx_data = input.delete("__agentspan_ctx__")

      # Resolve credentials if declared
      creds = {}
      if @credentials.any? && ctx_data
        creds = resolve_credentials(ctx_data, @credentials)
      end

      # Build ToolContext if the function accepts it
      tool_ctx = nil
      if ctx_data && accepts_context?(@function)
        tool_ctx = ToolContext.new(
          session_id:  ctx_data["sessionId"],
          execution_id: ctx_data["executionId"],
          agent_name:  ctx_data["agentName"],
          metadata:    ctx_data.fetch("metadata", {}),
          state:       ctx_data.fetch("state", {})
        )
      end

      # Execute: isolated (subprocess) or in-process
      result = if @isolated && creds.any?
                 execute_isolated(input, creds, tool_ctx)
               else
                 execute_in_process(input, creds, tool_ctx)
               end

      # Report success
      report_result(task_id, result)
    rescue => e
      report_failure(task_id, e)
    end

    def execute_in_process(input, creds, tool_ctx)
      # Inject credentials into environment temporarily
      creds.each { |k, v| ENV[k] = v } if creds.any?

      args = input.transform_keys(&:to_sym)
      args[:ctx] = tool_ctx if tool_ctx

      Timeout.timeout(@timeout) { @function.call(**args) }
    ensure
      creds.each_key { |k| ENV.delete(k) } if creds.any?
    end

    def execute_isolated(input, creds, tool_ctx)
      # Fork a subprocess with credentials as env vars
      reader, writer = IO.pipe
      pid = fork do
        reader.close
        creds.each { |k, v| ENV[k] = v }
        args = input.transform_keys(&:to_sym)
        args[:ctx] = tool_ctx if tool_ctx
        result = @function.call(**args)
        writer.write(JSON.generate(result))
        writer.close
      end

      writer.close
      output = reader.read
      reader.close
      Process.wait(pid)

      JSON.parse(output)
    end

    def resolve_credentials(ctx_data, names)
      token = ctx_data["executionToken"]
      return {} unless token

      response = @http.post("/api/credentials/resolve", {
        "token"       => token,
        "credentials" => names
      }.to_json)

      JSON.parse(response.body)
    end

    def report_result(task_id, result)
      @http.post("/tasks/#{task_id}", {
        "status"     => "COMPLETED",
        "outputData" => { "result" => result }
      }.to_json)
    end

    def report_failure(task_id, error)
      @http.post("/tasks/#{task_id}", {
        "status" => "FAILED",
        "reasonForIncompletion" => error.message
      }.to_json)
    end

    def accepts_context?(fn)
      fn.parameters.any? { |type, name| name == :ctx }
    end

    def worker_id
      @worker_id ||= "ruby-#{@task_name}-#{Process.pid}-#{Thread.current.object_id}"
    end

    def log_error(msg)
      $stderr.puts "[Agentspan::Worker] #{msg}"
    end
  end
end
```

### Async Worker (Fiber-Based)

```ruby
require "async"

module Agentspan
  class AsyncWorker < Worker
    def start
      @running = true
      @fiber_task = Async do |task|
        @thread_count.times do
          task.async { async_poll_loop }
        end
      end
    end

    def stop
      @running = false
      @fiber_task&.stop
    end

    private

    def async_poll_loop
      while @running
        task = poll_for_task
        if task
          execute_task(task)
        else
          sleep(@poll_interval)
        end
      rescue => e
        log_error("AsyncWorker #{@task_name} error: #{e.message}")
        sleep(@poll_interval)
      end
    end
  end
end
```

---

## 6. SSE Client

The SSE client connects to `GET /agent/stream/{executionId}`, parses the SSE wire format line by line, handles heartbeats, and reconnects on failure using `Last-Event-ID`.

### Core SSE Client

```ruby
require "net/http"
require "uri"
require "json"

module Agentspan
  class SSEClient
    include Enumerable

    RECONNECT_DELAYS = [0.5, 1, 2, 4, 8, 16].freeze  # exponential backoff cap
    HEARTBEAT_TIMEOUT = 30  # seconds without any data = dead connection

    def initialize(url, headers: {})
      @url     = URI(url)
      @headers = headers.merge(
        "Accept"       => "text/event-stream",
        "Cache-Control" => "no-cache"
      )
      @last_event_id = nil
      @closed        = false
    end

    # Yields AgentEvent objects. Reconnects transparently.
    def each(&block)
      return enum_for(:each) unless block_given?

      retries = 0
      until @closed
        begin
          connect_and_stream(&block)
          break if @closed  # clean close after "done" event
        rescue IOError, Errno::ECONNRESET, Net::ReadTimeout, Timeout::Error => e
          break if @closed
          delay = RECONNECT_DELAYS[[retries, RECONNECT_DELAYS.size - 1].min]
          retries += 1
          sleep(delay)
        end
      end
    end

    def close
      @closed = true
      @http&.finish if @http&.started?
    end

    private

    def connect_and_stream(&block)
      @http = Net::HTTP.new(@url.host, @url.port)
      @http.use_ssl = (@url.scheme == "https")
      @http.read_timeout = HEARTBEAT_TIMEOUT

      request = Net::HTTP::Get.new(@url.request_uri, @headers)
      request["Last-Event-ID"] = @last_event_id if @last_event_id

      @http.request(request) do |response|
        raise AgentAPIError, "SSE #{response.code}" unless response.code == "200"

        event_type = nil
        event_id   = nil
        data_lines = []

        response.read_body do |chunk|
          chunk.each_line do |line|
            line = line.chomp

            if line.start_with?(":")
              # Heartbeat comment — ignore but resets timeout
              next
            elsif line.start_with?("event:")
              event_type = line.sub("event:", "").strip
            elsif line.start_with?("id:")
              event_id = line.sub("id:", "").strip
            elsif line.start_with?("data:")
              data_lines << line.sub("data:", "").strip
            elsif line.empty? && event_type
              # End of event — dispatch
              @last_event_id = event_id if event_id
              data_str = data_lines.join("\n")
              data_lines.clear

              event = parse_event(event_type, data_str)
              event_type = nil
              event_id   = nil

              block.call(event) if event
              break if event&.type == EventType::DONE
            end
          end
        end
      end
    ensure
      @http&.finish if @http&.started?
    end

    def parse_event(type, data_str)
      data = JSON.parse(data_str) rescue {}

      # Pass through server-only event types as raw events
      unless EventType::ALL.include?(type)
        return AgentEvent.new(
          type: type,
          content: data["content"],
          execution_id: data["executionId"]
        )
      end

      AgentEvent.new(
        type:           type,
        content:        data["content"],
        tool_name:      data["toolName"],
        args:           data["args"],
        result:         data["result"],
        target:         data["target"],
        output:         data["output"],
        execution_id:   data["executionId"],
        guardrail_name: data["guardrailName"]
      )
    end
  end
end
```

### Enumerator-Based Delivery

The `each` method returns an `Enumerator` when called without a block, enabling lazy consumption:

```ruby
client = Agentspan::SSEClient.new(url)
stream = client.each  # returns Enumerator

# Pull events on demand
event = stream.next
event = stream.next

# Or use Enumerator::Lazy for filtering
client.each.lazy.select { |e| e.type == Agentspan::EventType::MESSAGE }.first(5)
```

### AgentStream Wrapper

```ruby
module Agentspan
  class AgentStream
    include Enumerable

    attr_reader :execution_id, :events

    def initialize(execution_id:, sse_client:, http_client:)
      @execution_id = execution_id
      @sse_client  = sse_client
      @http        = http_client
      @events      = []
      @result      = nil
    end

    def each(&block)
      return enum_for(:each) unless block_given?

      @sse_client.each do |event|
        @events << event
        block.call(event)
      end
    end

    def get_result
      # Drain remaining events if not already consumed
      each { |_| } unless @result
      build_result
    end

    # ── HITL methods ─────────────────────────────────────────

    def approve
      respond_hitl(approved: true)
    end

    def reject(reason = nil)
      respond_hitl(approved: false, reason: reason)
    end

    def send(message)
      respond_hitl(message: message)
    end

    def respond(output)
      respond_hitl(output: output)
    end

    private

    def respond_hitl(**payload)
      @http.post("/agent/#{@execution_id}/respond", payload.to_json)
    end

    def build_result
      done_event = @events.find { |e| e.type == EventType::DONE }
      AgentResult.new(
        output:      done_event&.output,
        execution_id: @execution_id,
        events:      @events,
        status:      done_event ? Status::COMPLETED : Status::FAILED,
        token_usage: extract_token_usage
      )
    end

    def extract_token_usage
      # Pull from status endpoint if not in events
      status = @http.get("/agent/#{@execution_id}/status")
      data = JSON.parse(status.body)
      tu = data["tokenUsage"]
      return nil unless tu
      TokenUsage.new(
        prompt_tokens:     tu["promptTokens"],
        completion_tokens: tu["completionTokens"],
        total_tokens:      tu["totalTokens"]
      )
    end
  end
end
```

---

## 7. Error Handling

### Exception Hierarchy

```ruby
module Agentspan
  # Base error — all Agentspan exceptions inherit from this
  class AgentspanError < StandardError; end

  # Server returned an HTTP error
  class AgentAPIError < AgentspanError
    attr_reader :status_code, :response_body

    def initialize(message = nil, status_code: nil, response_body: nil)
      @status_code   = status_code
      @response_body = response_body
      super(message || "API error #{status_code}")
    end
  end

  # Invalid agent configuration
  class ConfigurationError < AgentspanError; end

  # Agent not found on server
  class AgentNotFoundError < AgentspanError; end

  # ── Credential exceptions ──────────────────────────────────
  class CredentialError < AgentspanError; end

  class CredentialNotFoundError < CredentialError
    def initialize(name)
      super("Credential not found: #{name}")
    end
  end

  class CredentialAuthError < CredentialError
    def initialize
      super("Execution token invalid or expired")
    end
  end

  class CredentialRateLimitError < CredentialError
    def initialize
      super("Credential resolution rate limit exceeded (120 calls/min)")
    end
  end

  class CredentialServiceError < CredentialError; end

  # ── Guardrail exceptions ───────────────────────────────────
  class GuardrailFailure < AgentspanError
    attr_reader :guardrail_name, :guardrail_result

    def initialize(guardrail_name:, guardrail_result:)
      @guardrail_name   = guardrail_name
      @guardrail_result = guardrail_result
      super("Guardrail '#{guardrail_name}' failed: #{guardrail_result.message}")
    end
  end

  # ── Timeout ────────────────────────────────────────────────
  class TimeoutError < AgentspanError; end

  # ── Streaming errors ───────────────────────────────────────
  class StreamError < AgentspanError; end
  class SSEConnectionError < StreamError; end
end
```

### Usage Patterns

```ruby
# Basic begin/rescue/ensure
begin
  result = Agentspan.run(agent, "Write an article about Ruby")
  puts result.output
rescue Agentspan::AgentAPIError => e
  puts "Server error (#{e.status_code}): #{e.response_body}"
rescue Agentspan::ConfigurationError => e
  puts "Config problem: #{e.message}"
rescue Agentspan::CredentialNotFoundError => e
  puts "Missing credential: #{e.message}"
rescue Agentspan::GuardrailFailure => e
  puts "Guardrail #{e.guardrail_name} failed: #{e.guardrail_result.message}"
rescue Agentspan::AgentspanError => e
  puts "Agentspan error: #{e.message}"
ensure
  Agentspan.shutdown
end
```

### Timeout with Deadline

```ruby
require "timeout"

# Per-operation timeout
begin
  Timeout.timeout(300) do
    result = Agentspan.run(agent, prompt)
  end
rescue Timeout::Error
  raise Agentspan::TimeoutError, "Agent execution exceeded 300s deadline"
end
```

### Guardrail Failure Propagation in Workers

```ruby
# Inside the worker, guardrail on_fail=RAISE triggers this
def execute_guardrail(guardrail_fn, content)
  result = guardrail_fn.call(content)
  unless result.passed
    case guardrail.on_fail
    when OnFail::RAISE
      raise GuardrailFailure.new(
        guardrail_name: guardrail.name,
        guardrail_result: result
      )
    when OnFail::RETRY
      { "__guardrail_retry__" => true, "message" => result.message }
    when OnFail::FIX
      { "__guardrail_fixed__" => true, "output" => result.fixed_output }
    when OnFail::HUMAN
      { "__guardrail_human__" => true, "message" => result.message }
    end
  end
end
```

---

## 8. Testing Framework

All testing infrastructure lives in `lib/agentspan/testing/` and is designed for RSpec.

### mock_run

Executes an agent without a live server, returning a mock result with controllable responses.

```ruby
# lib/agentspan/testing/mock.rb
module Agentspan
  module Testing
    class MockRuntime
      attr_reader :tool_calls, :guardrail_checks

      def initialize
        @tool_calls      = []
        @guardrail_checks = []
        @tool_responses  = {}
        @llm_responses   = []
      end

      def stub_tool(name, &response_block)
        @tool_responses[name.to_s] = response_block
      end

      def stub_llm(*responses)
        @llm_responses = responses
      end

      def run(agent, prompt)
        events = []
        # Simulate tool calls based on agent definition
        agent._tools.each do |tool|
          if @tool_responses.key?(tool.name)
            args = { prompt: prompt }  # simplified
            @tool_calls << { name: tool.name, args: args }
            result = @tool_responses[tool.name].call(**args)
            events << AgentEvent.new(
              type: EventType::TOOL_CALL, tool_name: tool.name, args: args
            )
            events << AgentEvent.new(
              type: EventType::TOOL_RESULT, tool_name: tool.name, result: result
            )
          end
        end

        # Simulate guardrails
        agent._guardrails.each do |g|
          gr = g.function&.call("mock content")
          @guardrail_checks << { name: g.name, result: gr }
        end

        output = @llm_responses.first || { "result" => "mock output" }
        events << AgentEvent.new(type: EventType::DONE, output: output)

        AgentResult.new(
          output:      output,
          execution_id: "mock-#{SecureRandom.uuid}",
          status:      Status::COMPLETED,
          events:      events,
          tool_calls:  @tool_calls,
          messages:    [],
          token_usage: TokenUsage.new(
            prompt_tokens: 100, completion_tokens: 50, total_tokens: 150
          )
        )
      end
    end

    def self.mock_run(agent, prompt, &setup)
      runtime = MockRuntime.new
      setup.call(runtime) if setup
      runtime.run(agent, prompt)
    end
  end
end
```

### RSpec Custom Matchers

```ruby
# lib/agentspan/testing/matchers.rb
require "rspec/expectations"

module Agentspan
  module Testing
    module Matchers
      # expect(result).to be_completed
      RSpec::Matchers.define :be_completed do
        match { |result| result.status == Status::COMPLETED }
        failure_message { |result| "expected COMPLETED, got #{result.status}" }
      end

      # expect(result).to be_failed
      RSpec::Matchers.define :be_failed do
        match { |result| result.status == Status::FAILED }
      end

      # expect(result).to contain_output(text)
      RSpec::Matchers.define :contain_output do |text|
        match do |result|
          output_str = result.output.is_a?(Hash) ? result.output.to_s : result.output.to_s
          output_str.include?(text)
        end
        failure_message do |result|
          "expected output to contain '#{text}', got: #{result.output}"
        end
      end

      # expect(result).to have_used_tool("search")
      RSpec::Matchers.define :have_used_tool do |tool_name|
        match do |result|
          result.events.any? { |e|
            e.type == EventType::TOOL_CALL && e.tool_name == tool_name
          }
        end
        failure_message do |result|
          called = result.events.select { |e| e.type == EventType::TOOL_CALL }
                        .map(&:tool_name)
          "expected tool '#{tool_name}' to be called, but only saw: #{called}"
        end
      end

      # expect(result).to have_passed_guardrail("pii_check")
      RSpec::Matchers.define :have_passed_guardrail do |name|
        match do |result|
          result.events.any? { |e|
            e.type == EventType::GUARDRAIL_PASS && e.guardrail_name == name
          }
        end
      end

      # expect(result).to have_failed_guardrail("bias_detector")
      RSpec::Matchers.define :have_failed_guardrail do |name|
        match do |result|
          result.events.any? { |e|
            e.type == EventType::GUARDRAIL_FAIL && e.guardrail_name == name
          }
        end
      end

      # Composable: expect(result).to be_completed.and contain_output("article")
      # This works natively in RSpec with .and / .or combinators.
    end
  end
end
```

### Record / Replay

```ruby
# lib/agentspan/testing/recording.rb
module Agentspan
  module Testing
    class Recording
      attr_reader :events, :result

      def initialize
        @events = []
        @result = nil
      end

      def save(path)
        File.write(path, JSON.pretty_generate({
          events: @events.map { |e| event_to_hash(e) },
          result: result_to_hash(@result)
        }))
      end

      def self.load(path)
        data = JSON.parse(File.read(path))
        rec = new
        rec.instance_variable_set(:@events,
          data["events"].map { |h| hash_to_event(h) })
        rec.instance_variable_set(:@result,
          hash_to_result(data["result"]))
        rec
      end

      private

      def event_to_hash(e)
        { type: e.type, content: e.content, tool_name: e.tool_name,
          args: e.args, result: e.result, target: e.target,
          output: e.output, execution_id: e.execution_id,
          guardrail_name: e.guardrail_name }
      end
    end

    # Record a live execution
    def self.record(agent, prompt, path: nil)
      rec = Recording.new
      stream = Agentspan.stream(agent, prompt)
      stream.each { |event| rec.events << event }
      rec.instance_variable_set(:@result, stream.get_result)
      rec.save(path) if path
      rec
    end

    # Replay a recorded execution (deterministic)
    def self.replay(path)
      Recording.load(path)
    end
  end
end
```

### RSpec Example

```ruby
# spec/agentspan/pipeline_spec.rb
require "spec_helper"
require "agentspan/testing/matchers"

RSpec.describe "Content Publishing Pipeline" do
  include Agentspan::Testing::Matchers

  let(:agent) do
    Agentspan::Agent.new("test_pipeline") do
      model "openai/gpt-4o"
      instructions "Process the article."
      tool :search do |query:|
        { results: ["result1"] }
      end
    end
  end

  it "completes with expected output" do
    result = Agentspan::Testing.mock_run(agent, "Write about Ruby") do |rt|
      rt.stub_tool("search") { |prompt:| { results: ["Ruby 3.3 released"] } }
      rt.stub_llm({ "result" => "Article about Ruby" })
    end

    expect(result).to be_completed
    expect(result).to contain_output("Ruby")
    expect(result).to have_used_tool("search")
  end

  it "replays a recorded execution" do
    recording = Agentspan::Testing.replay("spec/fixtures/pipeline_run.json")
    expect(recording.result).to be_completed
    expect(recording.events.size).to be > 5
  end
end
```

### Validation as Rake Task

```ruby
# Rakefile
require "agentspan/testing"

namespace :agentspan do
  desc "Run validation suite"
  task :validate, [:config] do |_t, args|
    config_path = args[:config] || "validation/runs.toml"
    Agentspan::Validation::Runner.run(config_path)
  end

  desc "Run LLM judge on results"
  task :judge, [:run_dir] do |_t, args|
    Agentspan::Validation::Judge.run(args[:run_dir])
  end
end
```

---

## 9. Kitchen Sink Translation

Below is the full Ruby translation of the Content Publishing Platform kitchen sink example, exercising all 88 features.

### Stage 1: Intake & Classification

```ruby
require "agentspan"

LLM_MODEL = ENV.fetch("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")

# Structured output types (Ruby Struct for JSON schema generation)
ClassificationResult = Struct.new(:category, :priority, :metadata, keyword_init: true)
ArticleReport        = Struct.new(:title, :score, :summary, keyword_init: true)

# @agent equivalents via block DSL
tech_classifier = Agentspan::Agent.new("tech_classifier") do
  model LLM_MODEL
  instructions "Classifies tech articles."
end

business_classifier = Agentspan::Agent.new("business_classifier") do
  model LLM_MODEL
  instructions "Classifies business articles."
end

creative_classifier = Agentspan::Agent.new("creative_classifier") do
  model LLM_MODEL
  instructions "Classifies creative articles."
end

# Router strategy with PromptTemplate and structured output
intake_router = Agentspan::Agent.new("intake_router",
  model: LLM_MODEL,
  instructions: Agentspan::PromptTemplate.new(
    name: "article-classifier",
    variables: { "categories" => "tech, business, creative" }
  ),
  agents: [tech_classifier, business_classifier, creative_classifier],
  strategy: Agentspan::Strategy::ROUTER,
  router: Agentspan::Agent.new("category_router",
    model: LLM_MODEL,
    instructions: "Route to the appropriate classifier based on the article topic."
  ),
  output_type: ClassificationResult
)
```

### Stage 2: Research Team

```ruby
# Native tool with ToolContext injection + CredentialFile
research_database = Agentspan::ToolDef.new(
  name: "research_database",
  description: "Search internal research database.",
  credentials: [Agentspan::CredentialFile.new(env_var: "RESEARCH_API_KEY")]
) do |query:, ctx: nil|
  session  = ctx&.session_id || "unknown"
  execution = ctx&.execution_id || "unknown"
  { query: query, session_id: session, execution_id: execution,
    results: MOCK_RESEARCH_DATA.fetch("quantum_computing", {}) }
end

# Native tool, in-process credentials (isolated: false)
analyze_trends = Agentspan::ToolDef.new(
  name: "analyze_trends",
  description: "Analyze trending topics using analytics API.",
  isolated: false,
  credentials: ["ANALYTICS_KEY"]
) do |topic:|
  key = Agentspan.get_credential("ANALYTICS_KEY")
  { topic: topic, trend_score: 0.87, key_present: !key.nil? }
end

# HTTP tool with credential header substitution
web_search = Agentspan.http_tool(
  name: "web_search",
  description: "Search the web for recent articles and papers.",
  url: "https://api.example.com/search",
  method: "GET",
  headers: { "Authorization" => "Bearer ${SEARCH_API_KEY}" },
  input_schema: {
    "type" => "object",
    "properties" => { "q" => { "type" => "string" } },
    "required" => ["q"]
  },
  credentials: ["SEARCH_API_KEY"]
)

# MCP tool with credentials
mcp_fact_checker = Agentspan.mcp_tool(
  server_url: "http://localhost:3001/mcp",
  name: "fact_checker",
  description: "Verify factual claims using knowledge base.",
  tool_names: ["verify_claim", "check_source"],
  credentials: ["MCP_AUTH_TOKEN"]
)

# Auto-discover from OpenAPI/Swagger/Postman spec
stripe = Agentspan.api_tool(
  url: "https://api.stripe.com/openapi.json",
  headers: { "Authorization" => "Bearer ${STRIPE_KEY}" },
  credentials: ["STRIPE_KEY"],
  max_tools: 20
)

# External tool (by-reference, no local worker)
external_research_aggregator = Agentspan::ToolDef.new(
  name: "external_research_aggregator",
  description: "Aggregate research from external sources. Runs on remote worker.",
  external: true
)

# scatter_gather
researcher_worker = Agentspan::Agent.new("research_worker",
  model: LLM_MODEL,
  instructions: "Research the given topic thoroughly using available tools.",
  tools: [research_database, web_search, mcp_fact_checker, external_research_aggregator],
  credentials: ["SEARCH_API_KEY", "MCP_AUTH_TOKEN"]
)

research_coordinator = Agentspan.scatter_gather(
  name: "research_coordinator",
  worker: researcher_worker,
  model: LLM_MODEL,
  instructions: "Create research tasks for the topic: web search, data analysis, and fact checking.",
  timeout_seconds: 300
)

data_analyst = Agentspan::Agent.new("data_analyst",
  model: LLM_MODEL,
  instructions: "Analyze data trends for the topic.",
  tools: [analyze_trends]
)

research_team = Agentspan::Agent.new("research_team",
  agents: [research_coordinator, data_analyst],
  strategy: Agentspan::Strategy::PARALLEL
)
```

### Stage 3: Writing Pipeline (Sequential, >>, Memory, Callbacks)

```ruby
semantic_mem = Agentspan::SemanticMemory.new(max_results: 3)
MOCK_PAST_ARTICLES.each { |a| semantic_mem.add("Past article: #{a[:title]}") }

recall_past_articles = Agentspan::ToolDef.new(
  name: "recall_past_articles",
  description: "Retrieve relevant past articles from semantic memory."
) do |query:|
  semantic_mem.search(query).map { |r| { content: r.content } }
end

# CallbackHandler — all 6 lifecycle positions
class PublishingCallbackHandler < Agentspan::CallbackHandler
  def on_agent_start(agent_name: nil, **) = log("before_agent", agent_name)
  def on_agent_end(agent_name: nil, **)   = log("after_agent", agent_name)
  def on_model_start(messages: nil, **)   = log("before_model", (messages || []).size)
  def on_model_end(llm_result: nil, **)   = log("after_model", (llm_result || "").size)
  def on_tool_start(tool_name: nil, **)   = log("before_tool", tool_name)
  def on_tool_end(tool_name: nil, **)     = log("after_tool", tool_name)

  private
  def log(position, detail) = CALLBACK_LOG << { type: position, detail: detail }
end

CALLBACK_LOG = []

draft_writer = Agentspan::Agent.new("draft_writer") do
  model LLM_MODEL
  instructions "Write a comprehensive article draft based on research findings."
  tool recall_past_articles
  memory Agentspan::ConversationMemory.new(max_messages: 50)
  callback PublishingCallbackHandler.new
end

editor = Agentspan::Agent.new("editor") do
  model LLM_MODEL
  instructions "Review and edit the article. Fix grammar, improve clarity. When done, include ARTICLE_COMPLETE."
  stop_when ->(messages, **) {
    messages.last.is_a?(Hash) &&
      messages.last.fetch("content", "").include?("ARTICLE_COMPLETE")
  }
end

# Sequential pipeline via >> operator
writing_pipeline = draft_writer >> editor
```

### Stage 4: Review & Safety (All Guardrail Types)

```ruby
# Regex guardrail (server-side, on_fail=RETRY)
pii_guardrail = Agentspan::RegexGuardrail.new(
  name: "pii_blocker",
  patterns: ['\b\d{3}-\d{2}-\d{4}\b', '\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'],
  mode: "block",
  position: Agentspan::Position::OUTPUT,
  on_fail: Agentspan::OnFail::RETRY,
  message: "PII detected. Redact all personal information."
)

# LLM guardrail (server-side, on_fail=FIX)
bias_guardrail = Agentspan::LLMGuardrail.new(
  name: "bias_detector",
  model: "openai/gpt-4o-mini",
  policy: "Check for biased language or stereotypes. If found, provide corrected version.",
  position: Agentspan::Position::OUTPUT,
  on_fail: Agentspan::OnFail::FIX,
  max_tokens: 10_000
)

# Custom guardrail (SDK worker, on_fail=HUMAN)
fact_validator = Agentspan::Guardrail.new(
  name: "fact_validator",
  position: Agentspan::Position::OUTPUT,
  on_fail: Agentspan::OnFail::HUMAN
) do |content|
  red_flags = ["the best", "the worst", "always", "never", "guaranteed"]
  found = red_flags.select { |rf| content.downcase.include?(rf.downcase) }
  if found.any?
    Agentspan::GuardrailResult.new(passed: false, message: "Unverifiable claims: #{found}")
  else
    Agentspan::GuardrailResult.new(passed: true)
  end
end

# External guardrail (remote worker, on_fail=RAISE)
compliance_guardrail = Agentspan::Guardrail.new(
  name: "compliance_check",
  external: true,
  position: Agentspan::Position::OUTPUT,
  on_fail: Agentspan::OnFail::RAISE
)

# Tool guardrail
sql_injection_guard = Agentspan::Guardrail.new(
  name: "sql_injection_guard",
  position: Agentspan::Position::INPUT,
  on_fail: Agentspan::OnFail::RAISE
) do |content|
  if contains_sql_injection(content)
    Agentspan::GuardrailResult.new(passed: false, message: "SQL injection detected.")
  else
    Agentspan::GuardrailResult.new(passed: true)
  end
end

safe_search = Agentspan::ToolDef.new(
  name: "safe_search",
  description: "Search with SQL injection protection.",
  guardrails: [sql_injection_guard]
) do |query:|
  { query: query, results: ["result1", "result2"] }
end

review_agent = Agentspan::Agent.new("safety_reviewer",
  model: LLM_MODEL,
  instructions: "Review the article for safety and compliance.",
  tools: [safe_search],
  guardrails: [pii_guardrail, bias_guardrail, fact_validator, compliance_guardrail]
)
```

### Stage 5: Editorial Approval (HITL)

```ruby
publish_article = Agentspan::ToolDef.new(
  name: "publish_article",
  description: "Publish article to platform. Requires editorial approval.",
  approval_required: true
) do |title:, content:, platform:|
  { status: "published", title: title, platform: platform }
end

editorial_question = Agentspan.human_tool(
  name: "ask_editor",
  description: "Ask the editor a question about the article.",
  input_schema: {
    "type" => "object",
    "properties" => { "question" => { "type" => "string" } },
    "required" => ["question"]
  }
)

editorial_reviewer = Agentspan::UserProxyAgent.new(
  name: "editorial_reviewer",
  model: LLM_MODEL,
  instructions: "You are the editorial reviewer. Provide feedback on article quality.",
  human_input_mode: "TERMINATE"
)

editorial_agent = Agentspan::Agent.new("editorial_approval",
  model: LLM_MODEL,
  instructions: "Review the article, ask questions, get approval before publishing.",
  tools: [publish_article, editorial_question],
  agents: [editorial_reviewer],
  strategy: Agentspan::Strategy::HANDOFF
)
```

### Stage 6: Translation & Discussion (Multiple Strategies)

```ruby
spanish_translator = Agentspan::Agent.new("spanish_translator",
  model: LLM_MODEL,
  instructions: "You translate articles to Spanish with a formal tone.",
  introduction: "I am the Spanish translator, specializing in formal academic translations."
)

french_translator = Agentspan::Agent.new("french_translator",
  model: LLM_MODEL,
  instructions: "You translate articles to French with a conversational tone.",
  introduction: "I am the French translator, specializing in conversational translations."
)

german_translator = Agentspan::Agent.new("german_translator",
  model: LLM_MODEL,
  instructions: "You translate articles to German with a technical tone.",
  introduction: "I am the German translator, specializing in technical translations."
)

translators = [spanish_translator, french_translator, german_translator]

# Round-robin debate
tone_debate = Agentspan::Agent.new("tone_debate",
  agents: translators, strategy: Agentspan::Strategy::ROUND_ROBIN, max_turns: 6)

# Swarm with OnTextMention handoffs + allowed_transitions
translation_swarm = Agentspan::Agent.new("translation_swarm",
  agents: translators,
  strategy: Agentspan::Strategy::SWARM,
  handoffs: [
    Agentspan::OnTextMention.new(text: "Spanish", target: "spanish_translator"),
    Agentspan::OnTextMention.new(text: "French",  target: "french_translator"),
    Agentspan::OnTextMention.new(text: "German",  target: "german_translator"),
  ],
  allowed_transitions: {
    "spanish_translator" => ["french_translator", "german_translator"],
    "french_translator"  => ["spanish_translator", "german_translator"],
    "german_translator"  => ["spanish_translator", "french_translator"],
  }
)

# Random strategy for brainstorming
title_brainstorm = Agentspan::Agent.new("title_brainstorm",
  agents: translators, strategy: Agentspan::Strategy::RANDOM, max_turns: 3)

# Manual selection
manual_translation = Agentspan::Agent.new("manual_translation",
  agents: translators, strategy: Agentspan::Strategy::MANUAL)
```

### Stage 7: Publishing Pipeline (Handoffs, Termination, Gate)

```ruby
format_check = Agentspan::ToolDef.new(
  name: "format_check",
  description: "Check article formatting."
) do |content:|
  { formatted: true, issues: [] }
end

formatter = Agentspan::Agent.new("formatter",
  model: LLM_MODEL,
  instructions: "Format the article according to publishing guidelines.",
  tools: [format_check]
)

# External agent (remote SUB_WORKFLOW)
external_publisher = Agentspan::Agent.new("external_publisher",
  external: true,
  instructions: "Publish to the CMS platform."
)

# Composable termination: | is OR, & is AND
# Ruby already defines & and | on Object, so we override on TerminationCondition
publishing_pipeline = Agentspan::Agent.new("publishing_pipeline",
  model: LLM_MODEL,
  instructions: "Manage the publishing workflow from formatting to publication.",
  agents: [formatter, external_publisher],
  strategy: Agentspan::Strategy::HANDOFF,
  handoffs: [
    Agentspan::OnToolResult.new(target: "external_publisher", tool_name: "format_check"),
    Agentspan::OnCondition.new(
      target: "external_publisher",
      condition: ->(messages, **) {
        messages.last.is_a?(Hash) &&
          messages.last.fetch("content", "").include?("formatted")
      }
    ),
  ],
  termination: (
    Agentspan::TextMentionTermination.new("PUBLISHED") |
    (Agentspan::MaxMessageTermination.new(50) &
     Agentspan::TokenUsageTermination.new(max_total_tokens: 100_000))
  ),
  gate: Agentspan::TextGate.new(text: "APPROVED")
)
```

### Stage 8: Analytics & Reporting

```ruby
local_executor     = Agentspan::LocalCodeExecutor.new(language: "python", timeout: 10)
docker_executor    = Agentspan::DockerCodeExecutor.new(image: "python:3.12-slim", timeout: 15)
jupyter_executor   = Agentspan::JupyterCodeExecutor.new(timeout: 30)
serverless_executor = Agentspan::ServerlessCodeExecutor.new(
  endpoint: "https://api.example.com/functions/analytics", timeout: 30
)

article_thumbnail = Agentspan.image_tool(
  name: "generate_thumbnail", description: "Generate an article thumbnail image.",
  llm_provider: "openai", model: "dall-e-3"
)
audio_summary = Agentspan.audio_tool(
  name: "generate_audio_summary", description: "Generate an audio summary.",
  llm_provider: "openai", model: "tts-1"
)
video_highlight = Agentspan.video_tool(
  name: "generate_video_highlight", description: "Generate a short video highlight.",
  llm_provider: "openai", model: "sora"
)
article_pdf = Agentspan.pdf_tool(
  name: "generate_article_pdf", description: "Generate a PDF version of the article."
)

article_indexer = Agentspan.index_tool(
  name: "index_article", description: "Index the article for future retrieval.",
  vector_db: "pgvector", index: "articles",
  embedding_model_provider: "openai", embedding_model: "text-embedding-3-small"
)
article_search = Agentspan.search_tool(
  name: "search_articles", description: "Search for related articles.",
  vector_db: "pgvector", index: "articles",
  embedding_model_provider: "openai", embedding_model: "text-embedding-3-small",
  max_results: 5
)

research_subtool = Agentspan.agent_tool(
  Agentspan::Agent.new("quick_researcher",
    model: LLM_MODEL,
    instructions: "Do a quick research lookup on the given topic."
  ),
  name: "quick_research",
  description: "Quick research lookup as a tool."
)

gpt_assistant = Agentspan::GPTAssistantAgent.new(
  name: "openai_research_assistant",
  model: "gpt-4o",
  instructions: "You are a research assistant with access to code interpreter."
)

analytics_agent = Agentspan::Agent.new("analytics_agent",
  model: LLM_MODEL,
  instructions: "Analyze the published article and generate a comprehensive analytics report.",
  tools: [
    local_executor.as_tool,
    docker_executor.as_tool(name: "run_sandboxed"),
    jupyter_executor.as_tool(name: "run_notebook"),
    serverless_executor.as_tool(name: "run_cloud"),
    article_thumbnail, audio_summary, video_highlight, article_pdf,
    article_indexer, article_search, research_subtool,
  ],
  agents: [gpt_assistant],
  strategy: Agentspan::Strategy::HANDOFF,
  thinking_budget_tokens: 2048,
  include_contents: "default",
  output_type: ArticleReport,
  required_tools: ["index_article"],
  code_execution_config: Agentspan::CodeExecutionConfig.new(
    enabled: true, allowed_languages: ["python", "shell"],
    allowed_commands: ["python3", "pip"], timeout: 30
  ),
  cli_config: Agentspan::CliConfig.new(
    enabled: true, allowed_commands: ["git", "gh"], timeout: 30
  ),
  metadata: { "stage" => "analytics", "version" => "1.0" },
  planner: true
)
```

### Full Pipeline + Execution (Stage 9)

```ruby
full_pipeline = Agentspan::Agent.new("content_publishing_platform",
  model: LLM_MODEL,
  instructions: "You are a content publishing platform. Process article requests " \
                "through all pipeline stages.",
  agents: [
    intake_router,        # Stage 1
    research_team,        # Stage 2
    writing_pipeline,     # Stage 3 (sequential via >>)
    review_agent,         # Stage 4
    editorial_agent,      # Stage 5
    translation_swarm,    # Stage 6
    publishing_pipeline,  # Stage 7
    analytics_agent,      # Stage 8
  ],
  strategy: Agentspan::Strategy::SEQUENTIAL,
  termination: (
    Agentspan::TextMentionTermination.new("PIPELINE_COMPLETE") |
    Agentspan::MaxMessageTermination.new(200)
  )
)

PROMPT = "Write a comprehensive tech article about quantum computing " \
         "advances in 2026, get it reviewed, translate to Spanish, and publish."

if Agentspan.tracing_enabled?
  puts "[tracing] OpenTelemetry tracing is enabled"
end

# AgentRuntime as a resource (ensure cleanup)
runtime = Agentspan::AgentRuntime.new
begin
  # Deploy
  puts "=== Deploy ==="
  deployments = runtime.deploy(full_pipeline)
  deployments.each { |dep| puts "  Deployed: #{dep.registered_name} (#{dep.agent_name})" }

  # Plan (dry-run)
  puts "\n=== Plan (dry-run) ==="
  runtime.plan(full_pipeline)
  puts "  Plan compiled successfully"

  # Stream with HITL
  puts "\n=== Stream Execution ==="
  agent_stream = runtime.stream(full_pipeline, PROMPT)
  puts "  Execution: #{agent_stream.execution_id}\n"

  hitl_state = { approved: 0, rejected: 0, feedback: 0 }

  agent_stream.each do |event|
    case event.type
    when Agentspan::EventType::THINKING
      puts "  [thinking] #{event.content[0..79]}..."
    when Agentspan::EventType::TOOL_CALL
      puts "  [tool_call] #{event.tool_name}(#{event.args})"
    when Agentspan::EventType::TOOL_RESULT
      puts "  [tool_result] #{event.tool_name} -> #{event.result.to_s[0..79]}..."
    when Agentspan::EventType::HANDOFF
      puts "  [handoff] -> #{event.target}"
    when Agentspan::EventType::GUARDRAIL_PASS
      puts "  [guardrail_pass] #{event.guardrail_name}"
    when Agentspan::EventType::GUARDRAIL_FAIL
      puts "  [guardrail_fail] #{event.guardrail_name}: #{event.content}"
    when Agentspan::EventType::MESSAGE
      puts "  [message] #{event.content[0..79]}..."
    when Agentspan::EventType::WAITING
      puts "\n  --- HITL: Approval required ---"
      if hitl_state[:feedback] == 0
        agent_stream.send("Please add more details about quantum error correction.")
        hitl_state[:feedback] += 1
        puts "  Sent feedback (revision request)\n"
      elsif hitl_state[:rejected] == 0
        agent_stream.reject("Title needs improvement")
        hitl_state[:rejected] += 1
        puts "  Rejected (title needs work)\n"
      else
        agent_stream.approve
        hitl_state[:approved] += 1
        puts "  Approved\n"
      end
    when Agentspan::EventType::ERROR
      puts "  [error] #{event.content}"
    when Agentspan::EventType::DONE
      puts "\n  [done] Pipeline complete"
    end
  end

  result = agent_stream.get_result
  result.print_result

  # Token tracking
  if result.token_usage
    puts "\nTotal tokens: #{result.token_usage.total_tokens}"
    puts "  Prompt: #{result.token_usage.prompt_tokens}"
    puts "  Completion: #{result.token_usage.completion_tokens}"
  end

  # Callback log
  puts "\nCallback events: #{CALLBACK_LOG.size}"
  CALLBACK_LOG.first(5).each { |ev| puts "  #{ev[:type]}: #{ev}" }

  # Start + polling
  puts "\n=== Start + Polling ==="
  handle = runtime.start(full_pipeline, PROMPT)
  puts "  Started: #{handle.execution_id}"
  status = handle.get_status
  puts "  Status: #{status.status}, Running: #{status.running?}"
  puts "  Reason: #{status.reason}" if status.reason

  # Top-level convenience API
  puts "\n=== Top-Level Convenience API ==="
  Agentspan.configure(Agentspan::Configuration.from_env)
  simple_agent = Agentspan::Agent.new("simple_test",
    model: LLM_MODEL, instructions: "Say hello.")
  simple_result = Agentspan.run(simple_agent, "Hello!")
  puts "  run() status: #{simple_result.status}"

  # Discover agents
  puts "\n=== Discover Agents ==="
  begin
    agents = Agentspan.discover_agents("sdk/ruby/examples")
    puts "  Discovered #{agents.size} agents"
  rescue => e
    puts "  Discovery: #{e.message}"
  end

  # serve() would be: runtime.serve  (blocking, commented for demo)
ensure
  runtime.shutdown
  Agentspan.shutdown
  puts "\n=== Kitchen Sink Complete ==="
end
```

### Operator Overloading Summary

Ruby natively supports overloading `>>`, `&`, and `|`. The implementations:

```ruby
# Agent#>> for sequential chaining
class Agent
  def >>(other)
    Agent.new("#{name}_then_#{other.name}",
              agents: [self, other],
              strategy: Strategy::SEQUENTIAL)
  end
end

# TerminationCondition#& (AND) and #| (OR)
class TerminationCondition
  def &(other)
    AndTermination.new(conditions: [self, other])
  end

  def |(other)
    OrTermination.new(conditions: [self, other])
  end
end
```

These operators compose naturally in Ruby, making the DSL nearly identical to the Python reference:

```ruby
# Ruby
pipeline = researcher >> writer >> editor
condition = TextMentionTermination.new("DONE") |
            (MaxMessageTermination.new(50) & TokenUsageTermination.new(max_total_tokens: 100_000))

# Python (for comparison)
pipeline = researcher >> writer >> editor
condition = TextMentionTermination("DONE") | (MaxMessageTermination(50) & TokenUsageTermination(100000))
```

---

## Appendix: Key Translation Decisions

| Python Pattern | Ruby Equivalent | Rationale |
|---|---|---|
| `@dataclass` | `Data.define` (Ruby 3.2+) | Frozen value objects for immutable types |
| `class` with `__init__` | `class` with `attr_reader` + `initialize` | Mutable objects for builders (Agent) |
| `Enum(str, Enum)` | Module constants (`HANDOFF = "handoff"`) | Simplest; no external dependency |
| `@tool` decorator | `ToolDef.new(name:) { \|args\| }` block | Ruby blocks replace decorators naturally |
| `@guardrail` decorator | `Guardrail.new(name:) { \|content\| }` block | Same pattern |
| `@agent` decorator | `Agent.new(name) { DSL block }` | `instance_eval` gives clean DSL |
| `asyncio` | `Thread` (default) / `async` gem (opt-in) | Ruby is sync-first; threads are practical |
| `Optional[T]` | nilable (`# @return [String, nil]`) | Duck typing; YARD docs for contracts |
| `Pydantic BaseModel` | `dry-schema` (validation) / `Struct` (schema) | `dry-schema` for JSON validation only |
| `with` context manager | `begin/ensure` block | Idiomatic Ruby resource management |
| `__rshift__` (`>>`) | `def >>(other)` | Ruby supports this operator natively |
| `__and__` / `__or__` | `def &(other)` / `def \|(other)` | Ruby supports these operators natively |
