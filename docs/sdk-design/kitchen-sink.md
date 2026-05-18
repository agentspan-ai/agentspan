# Kitchen Sink: Content Publishing Platform

## Overview

A single mega-workflow that processes an article request through a complete publishing pipeline, exercising every Agentspan SDK feature (89 features per the traceability matrix in `2026-03-23-multi-language-sdk-design.md` Section 11).

**Reference implementation:** `sdk/python/examples/kitchen_sink.py`

## Scenario

**User prompt:**
> "Write a comprehensive tech article about quantum computing advances in 2026, get it reviewed, translate to Spanish, and publish."

The workflow processes this through 9 stages, each targeting a specific feature cluster.

---

## Stage 1: Intake & Classification

**Input:** User prompt
**Output:** `ClassificationResult { category, priority, tags, metadata }`

**Features exercised:**
- `#5` Router strategy (`Strategy.ROUTER`)
- `#30` Structured output (`output_type=ClassificationResult`)
- `#63` PromptTemplate (server-managed `"article-classifier"` template)
- `@agent` decorator (3 classifier agents defined via decorator)

**Expected behavior:**
- Router agent examines the prompt and selects the `tech_classifier` agent
- Classification returns `ClassificationResult` with `category="tech"`, `priority=1`
- PromptTemplate `"article-classifier"` is referenced by name, not inlined
- Variables `{"categories": "tech, business, creative"}` are passed to the template

**Assertions:**
- `result.output` is a valid `ClassificationResult` instance
- `result.output.category == "tech"`
- Router strategy was used (validate via strategy validator)

---

## Stage 2: Research Team

**Input:** Classification result + original prompt
**Output:** Aggregated research findings from multiple sources

**Features exercised:**
- `#4` Parallel strategy (`Strategy.PARALLEL`)
- `#76` `scatter_gather()` (coordinator dispatches parallel research workers)
- `#10` Native `@tool` functions with `ToolContext` injection
- `#11` `http_tool()` with credential header substitution (`${SEARCH_API_KEY}`)
- `#12` `mcp_tool()` with credentials
- `#18` `ToolContext` (session_id, execution_id accessible in tool)
- `#19` Tool-level credentials (`@tool(credentials=[...])`)
- `#21` External tool (`@tool(external=True)` — no local worker)
- `#52` Isolated credential mode (default — subprocess with env vars)
- `#53` In-process credential mode (`isolated=False` + `get_credential()`)
- `#55` HTTP header credential substitution (`${NAME}` syntax)
- `#56` MCP tool credentials
- `#89` `api_tool()` (auto-discovery from OpenAPI/Swagger/Postman spec)
- `CredentialFile` for file-based credential declarations

**Expected behavior:**
- `scatter_gather()` creates a coordinator that dispatches parallel research workers
- `research_team` runs `research_coordinator` and `data_analyst` in parallel
- `research_database` tool receives `ToolContext` with valid `session_id` and `execution_id`
- `analyze_trends` tool runs in-process (not isolated) and calls `get_credential()`
- `web_search` HTTP tool has `Authorization: Bearer ${SEARCH_API_KEY}` header
- `mcp_fact_checker` connects to MCP server with credentials
- `external_research_aggregator` has no local worker — task dispatched to remote queue
- `petstore_api` auto-discovers operations from the OpenAPI spec at workflow startup and creates HTTP tasks for each operation (capped at `max_tools=5`)

**Assertions:**
- `assert_tool_used("research_database")`
- `assert_tool_used("web_search")`
- All parallel agents produced results (`result.sub_results` has entries)
- `ToolContext.session_id` is non-empty in research_database output
- External tool task was emitted but may not have a result (no remote worker in test)

---

## Stage 3: Writing Pipeline

**Input:** Research findings
**Output:** Edited article draft

**Features exercised:**
- `#3` Sequential strategy (`Strategy.SEQUENTIAL` via `>>` operator)
- `#31` `ConversationMemory` (carries context through chain, `max_messages=50`)
- `#32` `SemanticMemory` (recalls past articles via similarity search)
- `#39` Agent chaining (`draft_writer >> editor`)
- `#62` `CallbackHandler` (all 6 positions: `before_agent`, `after_agent`, `before_model`, `after_model`, `before_tool`, `after_tool`)
- `#77` `stop_when` callable (stops when output contains `"ARTICLE_COMPLETE"`)

**Expected behavior:**
- `draft_writer >> editor` creates a sequential pipeline
- `draft_writer` uses `ConversationMemory` with `max_messages=50`
- `recall_past_articles` tool queries `SemanticMemory` and returns 3 relevant articles
- `PublishingCallbackHandler` logs events for all 6 callback positions
- `editor` stops processing when output contains `"ARTICLE_COMPLETE"`

**Assertions:**
- `assert_agent_ran("draft_writer")`
- `assert_agent_ran("editor")`
- Callback log contains events for `before_model`, `after_model`, `before_tool`, `after_tool`
- `assert_tool_used("recall_past_articles")`
- Pipeline ran in order: draft_writer first, then editor

---

## Stage 4: Review & Safety

**Input:** Article draft
**Output:** Validated, safe article

**Features exercised:**
- `#22` `RegexGuardrail` (PII detection, `on_fail=RETRY`)
- `#23` `LLMGuardrail` (bias detection, `on_fail=FIX`)
- `#24` Custom `@guardrail` function (`fact_validator`, `on_fail=HUMAN`)
- `#25` External guardrail (`compliance_check`, `external=True`, `on_fail=RAISE`)
- `#20` Tool guardrail (`sql_injection_guard` on `safe_search` tool input)
- `#26` OnFail: RETRY (PII guardrail retries with redaction feedback)
- `#27` OnFail: RAISE (compliance guardrail fails workflow on violation)
- `#28` OnFail: FIX (bias guardrail provides corrected output)
- `#29` OnFail: HUMAN (fact guardrail pauses for human review)

**Expected behavior:**
- `RegexGuardrail("pii_blocker")` catches SSN/credit card patterns and retries
- `LLMGuardrail("bias_detector")` sends output to judge LLM, auto-fixes if biased
- `@guardrail fact_validator` detects superlatives ("the best", "always"), pauses for human
- `compliance_check` external guardrail dispatches to remote worker
- `sql_injection_guard` on `safe_search` blocks `"DROP TABLE"` input

**Assertions:**
- `assert_guardrail_passed("pii_blocker")` (after retry)
- `assert_guardrail_passed("bias_detector")` (after fix)
- If PII is in draft: initial `guardrail_fail` event, then retry, then pass
- Tool guardrail blocks malicious input (no `safe_search` result for injection attempt)

---

## Stage 5: Editorial Approval

**Input:** Validated article
**Output:** Approved (or revised) article

**Features exercised:**
- `#17` `approval_required=True` on `publish_article` tool
- `#40` `handle.approve()` / `stream.approve()`
- `#41` `handle.reject(reason)` / `stream.reject(reason)`
- `#42` `handle.send(message)` / `stream.send(message)` (feedback)
- `#14` `human_tool()` for inline editorial questions
- `#65` `UserProxyAgent` as editorial reviewer

**Expected behavior:**
- `publish_article` tool has `approval_required=True` → workflow pauses with `WAITING` event
- First HITL interaction: `stream.send("Please add more details...")` — feedback/revision
- Second HITL interaction: `stream.reject("Title needs improvement")` — rejection
- Third HITL interaction: `stream.approve()` — approval
- `human_tool("ask_editor")` allows agent to ask editor questions during review
- `UserProxyAgent("editorial_reviewer")` participates in review discussion

**Assertions:**
- `WAITING` event emitted at least once
- All 3 HITL modes exercised (approve, reject, send)
- `assert_tool_used("publish_article")` after approval

---

## Stage 6: Translation & Discussion

**Input:** Approved article
**Output:** Translated article with agreed-upon tone

**Features exercised:**
- `#6` Round-robin strategy (`Strategy.ROUND_ROBIN`)
- `#7` Random strategy (`Strategy.RANDOM`)
- `#8` Swarm strategy (`Strategy.SWARM`)
- `#9` Manual strategy (`Strategy.MANUAL`)
- `#35` `OnTextMention` handoff condition
- `#37` `allowed_transitions` (constrains delegation paths)
- `#38` `agent_introductions` (agents announce their role)

**Expected behavior:**
- `tone_debate`: 3 translators take turns in round-robin (6 turns = 2 rounds)
- `translation_swarm`: auto-handoff when output mentions "Spanish", "French", or "German"
- `title_brainstorm`: random agent selection for brainstorming titles
- `manual_translation`: human picks which translator to use
- All translators have `introduction` text
- `allowed_transitions` restricts: each translator can only delegate to the other two

**Assertions:**
- `tone_debate` uses `ROUND_ROBIN` strategy with `max_turns=6`
- `translation_swarm` has 3 `OnTextMention` handoffs
- `allowed_transitions` dict has 3 entries with 2 targets each
- All 3 agents have non-empty `introduction`

---

## Stage 7: Publishing Pipeline

**Input:** Translated article
**Output:** Published article

**Features exercised:**
- `#2` Handoff strategy (`Strategy.HANDOFF`)
- `#33` Composable termination (`TextMention | (MaxMessage & TokenUsage)`)
- `#34` `OnToolResult` handoff condition
- `#36` `OnCondition` handoff (custom callable)
- `#71` Gate condition (`TextGate(text="APPROVED")`)
- `#88` External agent (`external=True`, runs as remote `SUB_WORKFLOW`)

**Expected behavior:**
- `OnToolResult(target="external_publisher", tool_name="format_check")`: hands off after formatting
- `OnCondition(target="external_publisher", condition=should_handoff_to_publisher)`: custom logic
- `TextGate(text="APPROVED")`: next pipeline stage only runs if previous output contains "APPROVED"
- Termination: `TextMention("PUBLISHED") | (MaxMessage(50) & TokenUsage(100000))`
- `external_publisher` is an external agent (SUB_WORKFLOW dispatched to remote)

**Assertions:**
- `publishing_pipeline.gate` is not None
- `publishing_pipeline.termination` is not None
- Termination is composable (OR of TextMention and AND of MaxMessage+TokenUsage)
- `external_publisher.external == True`

---

## Stage 8: Analytics & Reporting

**Input:** Published article metadata
**Output:** `ArticleReport { word_count, sentiment_score, readability_grade, top_keywords }`

**Features exercised:**
- `#13` `agent_tool()` (sub-agent wrapped as callable tool)
- `#15` Media tools (`image_tool`, `audio_tool`, `video_tool`, `pdf_tool`)
- `#16` RAG tools (`search_tool`, `index_tool` with `rag_search`/`rag_index` types)
- `#58` `LocalCodeExecutor`
- `#59` `DockerCodeExecutor`
- `#60` `JupyterCodeExecutor`
- `#61` `ServerlessCodeExecutor`
- `#64` Token tracking (`TokenUsage` across all stages)
- `#66` `GPTAssistantAgent` (wraps OpenAI Assistants API)
- `#67` Extended thinking (`thinking_budget_tokens=2048`)
- `#68` `include_contents="default"` (pass parent context to sub-agents)
- `#69` Planner mode (`planner=True`)
- `#70` `required_tools=["index_article"]`
- `#72` `CliConfig` (allowlist: git, gh)

**Expected behavior:**
- `local_executor.as_tool()` runs Python word count analysis
- `docker_executor.as_tool("run_sandboxed")` runs sandboxed sentiment analysis
- `jupyter_executor.as_tool("run_notebook")` generates matplotlib visualization
- `serverless_executor.as_tool("run_cloud")` calls remote analytics function
- `agent_tool(quick_researcher)` wraps a sub-agent as a callable tool
- `GPTAssistantAgent` wraps OpenAI assistant for research
- `thinking_budget_tokens=2048` enables extended thinking on analysis agent
- `required_tools=["index_article"]` forces LLM to use the indexer
- `planner=True` enables planning before execution
- `CliConfig(allowed_commands=["git", "gh"])` restricts CLI access
- Media tools generate thumbnail, audio summary, video highlight, PDF
- RAG tools index the article and search for related content

**Assertions:**
- `analytics_agent.thinking_budget_tokens == 2048`
- `analytics_agent.planner == True`
- `analytics_agent.required_tools == ["index_article"]`
- `analytics_agent.include_contents == "default"`
- `analytics_agent.code_execution_config` is not None
- `analytics_agent.cli_config` is not None
- `GPTAssistantAgent` instance exists with correct name

---

## Stage 9: Execution Modes

**Features exercised:**
- `#43` Sync streaming (`runtime.stream()` → `AgentStream`)
- `#44` Async streaming (`runtime.stream_async()` → `AsyncAgentStream`)
- `#45` Polling fallback (`handle.get_status()`)
- `#46` Sync execution (`run()` top-level convenience)
- `#47` Async execution (`run_async()` top-level convenience)
- `#48` Fire-and-forget (`runtime.start()` → `AgentHandle`)
- `#49` Deploy (`runtime.deploy()` → `[DeploymentInfo]`)
- `#50` Serve (`serve()` — commented since blocking)
- `#51` Plan dry-run (`runtime.plan()` — compile only, no prompt)
- `#74` Agent discovery (`discover_agents()`)
- `#75` OTel tracing check (`is_tracing_enabled()`)

**Expected behavior:**
- `runtime.deploy(full_pipeline)` returns list of `DeploymentInfo` objects
- `runtime.plan(full_pipeline)` compiles without execution (no prompt needed)
- `runtime.stream(full_pipeline, PROMPT)` returns `AgentStream` with SSE events
- `runtime.start(full_pipeline, PROMPT)` returns `AgentHandle` for polling
- `handle.get_status()` returns `AgentStatus` with `is_running`, `is_complete`, etc.
- Async streaming via `runtime.stream_async()` yields events via `async for`
- Top-level `run()` uses singleton runtime
- `discover_agents("sdk/python/examples")` finds registered agents
- `is_tracing_enabled()` returns bool based on OTel configuration

**Assertions:**
- `deployments` is a list with at least one `DeploymentInfo`
- `execution_plan` compiles without error
- `agent_stream.execution_id` is non-empty
- `handle.execution_id` is non-empty
- `status.is_running or status.is_complete` is True

---

## Cross-Cutting Features

Exercised throughout the workflow (not tied to a specific stage):

| Feature | Where |
|---------|-------|
| `#54` CLI credential mode | via `CliConfig` on analytics agent |
| `#57` Framework credential passthrough | would be exercised with framework agents (LangChain/LangGraph) |
| `#73` Context condensation | server-side — occurs on long conversations, emits `context_condensed` SSE event |
| All credential modes | Stages 2, 5, 8 (isolated, in-process, HTTP, MCP, CredentialFile) |
| Token tracking (`#64`) | Available on every `AgentResult.token_usage` |
| Metadata propagation | `analytics_agent.metadata = {"stage": "analytics", "version": "1.0"}` |

---

## Testing & Validation

### Structural Assertions (no server required)

```python
assert full_pipeline.strategy == Strategy.SEQUENTIAL
assert len(full_pipeline.agents) == 8
assert intake_router.strategy == Strategy.ROUTER
assert research_team.strategy == Strategy.PARALLEL
assert translation_swarm.strategy == Strategy.SWARM
assert analytics_agent.thinking_budget_tokens == 2048
assert analytics_agent.planner == True
assert external_publisher.external == True
```

### Behavioral Assertions (require server)

```python
expect(result).completed().output_contains("quantum computing")
assert_tool_used("research_database")
assert_tool_used("web_search")
assert_guardrail_passed("pii_blocker")
assert_handoff_to("external_publisher")
assert_agent_ran("draft_writer")
assert_agent_ran("editor")
assert_status(Status.COMPLETED)
assert_no_errors()
```

### Testing Framework Features

| Feature # | Test Type | Description |
|-----------|-----------|-------------|
| `#78` | `mock_run()` | Execute without server for unit testing |
| `#79` | `expect()` | Fluent assertion builder |
| `#80` | `assert_*()` | Individual assertion functions |
| `#81` | `record()`/`replay()` | Capture execution for deterministic replay |
| `#82` | `validate_strategy()` | Verify strategy constraints respected |
| `#83` | `CorrectnessEval` | LLM judge evaluates output against rubrics |

### Validation Framework Features

| Feature # | Component | Description |
|-----------|-----------|-------------|
| `#84` | Validation runner | Concurrent executor, TOML config, grouped test suites |
| `#85` | LLM judge | Cross-run semantic evaluation with rubrics |
| `#86` | Native execution | Run examples via native SDK for comparison |
| `#87` | HTML report | Interactive dashboard with score heatmap |

### Judge Rubrics

| Rubric | Weight | Criteria (1-5 scale) |
|--------|--------|---------------------|
| Research quality | 20% | Sources cited, facts checked, recent data referenced |
| Writing quality | 20% | Coherent, on-topic, well-structured, engaging |
| Safety | 20% | No PII leaked, no bias, no harmful content |
| Completeness | 20% | All pipeline stages executed, all features exercised |
| Translation quality | 20% | Accurate, natural-sounding, preserves meaning |

**Pass threshold:** Average score >= 3.5 across all rubrics.

---

## Acceptance Criteria for New SDKs

A new language SDK passes the kitchen sink if:

1. **Wire format parity:** Produces identical AgentConfig JSON for the same agent tree
2. **Worker execution:** All tool/guardrail/callback workers execute successfully
3. **SSE streaming:** Same event sequence (types + order) as Python SDK
4. **HITL parity:** approve, reject, and send all work correctly
5. **Result structure:** `AgentResult` matches expected fields and types
6. **Structural tests pass:** All assertions in `TestKitchenSinkStructure` pass
7. **Judge scores:** LLM judge >= 3.5 on all rubrics
8. **Validation framework:** Runner produces HTML report with passing results
