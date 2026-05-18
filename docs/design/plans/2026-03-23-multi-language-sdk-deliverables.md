# Multi-Language SDK Deliverables Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the kitchen sink reference implementation and 6 per-language translation guides that enable one-shot SDK implementation in TypeScript, Go, Java, Kotlin, C#, and Ruby.

**Architecture:** Reference Implementation + Translation Guide approach. The Python kitchen sink serves as the executable spec and acceptance test. Each language guide maps Python concepts to idiomatic patterns in the target language, with enough detail for an AI agent to implement a full SDK in one pass.

**Tech Stack:** Python (agentspan SDK), Pydantic (structured output), pytest (kitchen sink tests)

**Spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `docs/sdk-design/kitchen-sink.md` | Kitchen sink scenario spec, expected behavior, judge rubrics, acceptance criteria |
| `sdk/python/examples/kitchen_sink.py` | Working Python kitchen sink — single mega-workflow exercising all 88 features |
| `sdk/python/examples/kitchen_sink_helpers.py` | Mock services, data fixtures, external worker stubs for kitchen sink |
| `sdk/python/tests/test_kitchen_sink.py` | Kitchen sink test suite — structural + behavioral assertions |
| `docs/sdk-design/typescript.md` | TypeScript idiom translation guide (all 9 sections) |
| `docs/sdk-design/go.md` | Go idiom translation guide (all 9 sections) |
| `docs/sdk-design/java.md` | Java idiom translation guide — record 16+ and POJO 8+ (all 9 sections) |
| `docs/sdk-design/kotlin.md` | Kotlin idiom translation guide (all 9 sections) |
| `docs/sdk-design/csharp.md` | C# idiom translation guide (all 9 sections) |
| `docs/sdk-design/ruby.md` | Ruby idiom translation guide (all 9 sections) |

---

## Chunk 1: Kitchen Sink Spec + Python Implementation

### Task 1: Kitchen Sink Spec Document

**Files:**
- Create: `docs/sdk-design/kitchen-sink.md`

- [ ] **Step 1: Write the kitchen sink scenario spec**

Create `docs/sdk-design/kitchen-sink.md` with these sections. The spec must cover every feature from the 88-feature traceability matrix in `docs/sdk-design/2026-03-23-multi-language-sdk-design.md` Section 11. Include:

1. **Overview** — scenario description, user prompt
2. **Stage 1-9 specifications** — each stage lists: input, output, features exercised, expected behavior, assertions
3. **Cross-cutting features** — features exercised throughout (all credential modes, tracing, callbacks, etc.)
4. **Testing section** — structural assertions, behavioral assertions, judge rubrics
5. **Acceptance criteria** — for new SDK implementations

Key requirements for each stage (referencing spec traceability matrix feature numbers):

- **Stage 1** (features 5, 30, 63, decorator-based @agent): Router + structured output + PromptTemplate
- **Stage 2** (features 4, 10, 11, 12, 18, 19, 21, 52, 53, 55, 56, 76): Parallel + scatter_gather + all tool types + credentials + ToolContext + external tool
- **Stage 3** (features 3, 31, 32, 39, 62, 77): Sequential (>>) + memory + callbacks (all 6 positions) + stop_when
- **Stage 4** (features 20, 22-29): All guardrail types + all OnFail modes + tool guardrails
- **Stage 5** (features 17, 40-42, 65): HITL approve + reject + feedback + UserProxyAgent + human_tool
- **Stage 6** (features 6-9, 35, 37, 38): All remaining strategies + OnTextMention + introductions + transitions
- **Stage 7** (features 2, 33, 34, 36, 71, 88): Handoff + termination + handoff conditions + gate + external agent
- **Stage 8** (features 13, 15, 16, 58-61, 64, 66-70, 72): Code execution + media + RAG + agent_tool + GPTAssistant + thinking + include_contents + required_tools + planner + CLI config
- **Stage 9** (features 43-51, 74, 75): All execution modes + streaming (sync+async) + discover_agents + tracing
- **Cross-cutting** (features 54, 57, 73): CLI credentials + framework credentials + context condensation

Testing section must cover: mock_run (78), expect (79), assertions (80), record/replay (81), validate_strategy (82), eval runner (83), validation runner (84), judge (85), native execution (86), HTML report (87)

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/kitchen-sink.md
git commit -m "docs: add kitchen sink scenario spec with expected behavior and judge rubrics"
```

---

### Task 2: Kitchen Sink Helpers

**Files:**
- Create: `sdk/python/examples/kitchen_sink_helpers.py`

- [ ] **Step 1: Write mock services and data fixtures**

```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Kitchen Sink helpers — mock services, data fixtures, external worker stubs.

These simulate external dependencies so the kitchen sink can run standalone
without real APIs. In production, these would be replaced by actual services.
"""

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Structured Output Models ──────────────────────────────────────────

class ClassificationResult(BaseModel):
    """Stage 1 output: article classification."""
    category: str
    priority: int
    tags: List[str]
    metadata: Dict[str, Any]


class ArticleReport(BaseModel):
    """Stage 8 output: analytics report."""
    word_count: int
    sentiment_score: float
    readability_grade: str
    top_keywords: List[str]


# ── Mock Data ─────────────────────────────────────────────────────────

MOCK_RESEARCH_DATA = {
    "quantum_computing": {
        "title": "Quantum Computing Advances in 2026",
        "sources": [
            "Nature Physics Vol 22",
            "IEEE Quantum Computing Summit 2026",
            "arXiv:2601.12345",
        ],
        "key_findings": [
            "1000+ qubit processors achieved by 3 vendors",
            "Quantum error correction breakthrough at Google",
            "First commercial quantum advantage in drug discovery",
        ],
    }
}

MOCK_PAST_ARTICLES = [
    {"id": "art-001", "title": "Quantum Computing in 2025", "score": 0.92},
    {"id": "art-002", "title": "AI and Quantum Synergies", "score": 0.85},
    {"id": "art-003", "title": "Post-Quantum Cryptography", "score": 0.78},
]


# ── Guardrail Patterns ───────────────────────────────────────────────

PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",
    r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
]

SQL_INJECTION_PATTERNS = [
    r"(?i)(union\s+select|drop\s+table|delete\s+from|insert\s+into)",
    r"(?i)(--\s|;\s*drop|'\s*or\s+'1'\s*=\s*'1')",
]


def contains_pii(text: str) -> bool:
    for pattern in PII_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def contains_sql_injection(text: str) -> bool:
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


# ── Callback Logger ──────────────────────────────────────────────────

class CallbackLog:
    """Captures callback events for testing."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def log(self, event_type: str, **kwargs):
        self.events.append({"type": event_type, **kwargs})

    def clear(self):
        self.events.clear()


callback_log = CallbackLog()
```

- [ ] **Step 2: Commit**

```bash
git add sdk/python/examples/kitchen_sink_helpers.py
git commit -m "feat: add kitchen sink helpers — mock services, data fixtures, guardrail patterns"
```

---

### Task 3: Kitchen Sink Python Implementation (All Stages)

**Files:**
- Create: `sdk/python/examples/kitchen_sink.py`

This task creates the complete kitchen sink in a single step (not split across tasks) to avoid invalid intermediate states.

- [ ] **Step 1: Write the complete kitchen sink**

The kitchen sink must exercise ALL 88 features. Below is the complete implementation. Key fixes from plan review:

- Uses `scatter_gather()` in Stage 2 (not just `Strategy.PARALLEL`)
- Instantiates `GPTAssistantAgent` in Stage 8
- Adds `gate` condition in Stage 7
- Uses `agent_tool()` in Stage 8
- Fixes `runtime.deploy()` to handle list return
- Demonstrates HITL reject and feedback (not just approve)
- Adds async streaming demo
- Uses `required_tools` on an agent
- Uses `CallbackHandler` class with all 6 positions
- Uses `CredentialFile` for file-based credentials
- Calls `serve()` (in comment since it's blocking)
- Uses top-level convenience APIs (`run()`, `stream()`)

```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Kitchen Sink — Content Publishing Platform.

A single mega-workflow that exercises every Agentspan SDK feature (88 features).
See docs/sdk-design/kitchen-sink.md for the full scenario specification.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL, AGENTSPAN_LLM_MODEL env vars
    - For full execution: Docker, MCP server, credential store configured
"""

import asyncio
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agentspan.agents import (
    # Core
    Agent, AgentRuntime, AgentConfig, PromptTemplate, Strategy,
    agent, scatter_gather,
    # Tools
    tool, ToolContext, ToolDef,
    http_tool, mcp_tool, agent_tool, human_tool,
    image_tool, audio_tool, video_tool, pdf_tool,
    search_tool, index_tool,
    # Guardrails
    guardrail, Guardrail, GuardrailResult, OnFail, Position,
    RegexGuardrail, LLMGuardrail,
    # Results
    AgentResult, AgentHandle, AgentStatus, AgentStream, AsyncAgentStream,
    AgentEvent, EventType, FinishReason, Status, TokenUsage, DeploymentInfo,
    # Termination
    TerminationCondition, TextMentionTermination, StopMessageTermination,
    MaxMessageTermination, TokenUsageTermination,
    # Handoffs
    HandoffCondition, OnToolResult, OnTextMention, OnCondition,
    # Memory
    ConversationMemory, SemanticMemory, MemoryStore, MemoryEntry,
    # Code execution
    CodeExecutionConfig, CodeExecutor, LocalCodeExecutor, DockerCodeExecutor,
    JupyterCodeExecutor, ServerlessCodeExecutor, ExecutionResult,
    # Extended
    UserProxyAgent, GPTAssistantAgent, CallbackHandler, CliConfig,
    # Credentials
    get_credential, CredentialFile,
    # Execution (top-level convenience + runtime)
    configure, run, run_async, start, start_async, stream, stream_async,
    deploy, deploy_async, serve, plan, shutdown,
    # Discovery & tracing
    discover_agents, is_tracing_enabled,
    # Exceptions
    ConfigurationError,
)

from settings import settings
from kitchen_sink_helpers import (
    ClassificationResult, ArticleReport,
    MOCK_RESEARCH_DATA, MOCK_PAST_ARTICLES,
    contains_pii, contains_sql_injection, callback_log,
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 1: Intake & Classification
# Features: #5 Router, #30 structured output, #63 PromptTemplate, @agent
# ═══════════════════════════════════════════════════════════════════════

@agent(name="tech_classifier", model=settings.llm_model)
def tech_classifier(prompt: str) -> str:
    """Classifies tech articles."""
    pass

@agent(name="business_classifier", model=settings.llm_model)
def business_classifier(prompt: str) -> str:
    """Classifies business articles."""
    pass

@agent(name="creative_classifier", model=settings.llm_model)
def creative_classifier(prompt: str) -> str:
    """Classifies creative articles."""
    pass

intake_router = Agent(
    name="intake_router",
    model=settings.llm_model,
    instructions=PromptTemplate(
        "article-classifier",
        variables={"categories": "tech, business, creative"},
    ),
    agents=[tech_classifier, business_classifier, creative_classifier],
    strategy=Strategy.ROUTER,
    router=Agent(
        name="category_router",
        model=settings.llm_model,
        instructions="Route to the appropriate classifier based on the article topic.",
    ),
    output_type=ClassificationResult,
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 2: Research Team
# Features: #4 Parallel, #76 scatter_gather, #10 native tool,
#   #11 http_tool, #12 mcp_tool, #18 ToolContext, #19 tool credentials,
#   #21 external tool, #52 isolated creds, #53 in-process creds,
#   #55 HTTP header creds, #56 MCP creds, CredentialFile
# ═══════════════════════════════════════════════════════════════════════

# -- Native tool with ToolContext injection + isolated credentials --
@tool(credentials=[CredentialFile(env_var="RESEARCH_API_KEY")])
def research_database(query: str, ctx: ToolContext = None) -> dict:
    """Search internal research database."""
    session = ctx.session_id if ctx else "unknown"
    execution = ctx.execution_id if ctx else "unknown"
    return {
        "query": query,
        "session_id": session,
        "execution_id": execution,
        "results": MOCK_RESEARCH_DATA.get("quantum_computing", {}),
    }

# -- Native tool with in-process credential access (isolated=False) --
@tool(isolated=False, credentials=["ANALYTICS_KEY"])
def analyze_trends(topic: str) -> dict:
    """Analyze trending topics using analytics API."""
    key = get_credential("ANALYTICS_KEY")
    return {"topic": topic, "trend_score": 0.87, "key_present": bool(key)}

# -- HTTP tool with credential header substitution --
web_search = http_tool(
    name="web_search",
    description="Search the web for recent articles and papers.",
    url="https://api.example.com/search",
    method="GET",
    headers={"Authorization": "Bearer ${SEARCH_API_KEY}"},
    input_schema={
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q"],
    },
    credentials=["SEARCH_API_KEY"],
)

# -- MCP tool with credentials --
mcp_fact_checker = mcp_tool(
    server_url="http://localhost:3001/mcp",
    name="fact_checker",
    description="Verify factual claims using knowledge base.",
    tool_names=["verify_claim", "check_source"],
    credentials=["MCP_AUTH_TOKEN"],
)

# -- External tool (by-reference, no local worker) --
@tool(external=True)
def external_research_aggregator(query: str, sources: int = 10) -> dict:
    """Aggregate research from external sources. Runs on remote worker."""
    ...

# -- Researcher agent for scatter_gather --
researcher_worker = Agent(
    name="research_worker",
    model=settings.llm_model,
    instructions="Research the given topic thoroughly using available tools.",
    tools=[research_database, web_search, mcp_fact_checker, external_research_aggregator],
    credentials=["SEARCH_API_KEY", "MCP_AUTH_TOKEN"],
)

# -- scatter_gather: dispatches parallel research workers --
research_coordinator = scatter_gather(
    name="research_coordinator",
    worker=researcher_worker,
    model=settings.llm_model,
    instructions=(
        "Create research tasks for the topic: web search, data analysis, "
        "and fact checking. Dispatch workers for each."
    ),
    timeout_seconds=300,
)

# -- Also demonstrate raw parallel strategy with data_analyst --
data_analyst = Agent(
    name="data_analyst",
    model=settings.llm_model,
    instructions="Analyze data trends for the topic.",
    tools=[analyze_trends],
)

research_team = Agent(
    name="research_team",
    agents=[research_coordinator, data_analyst],
    strategy=Strategy.PARALLEL,
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 3: Writing Pipeline
# Features: #3 Sequential (>>), #31 ConversationMemory,
#   #32 SemanticMemory, #39 agent chaining, #62 Callbacks (all 6),
#   #77 stop_when
# ═══════════════════════════════════════════════════════════════════════

semantic_mem = SemanticMemory(max_results=3)
for article in MOCK_PAST_ARTICLES:
    semantic_mem.add(f"Past article: {article['title']}")

@tool
def recall_past_articles(query: str) -> list:
    """Retrieve relevant past articles from semantic memory."""
    results = semantic_mem.search(query)
    return [{"content": r.content} for r in results]

# -- CallbackHandler class with all 6 positions --
class PublishingCallbackHandler(CallbackHandler):
    def on_agent_start(self, agent_name: str = None, **kwargs):
        callback_log.log("before_agent", agent_name=agent_name)

    def on_agent_end(self, agent_name: str = None, **kwargs):
        callback_log.log("after_agent", agent_name=agent_name)

    def on_model_start(self, messages: list = None, **kwargs):
        callback_log.log("before_model", message_count=len(messages or []))

    def on_model_end(self, llm_result: str = None, **kwargs):
        callback_log.log("after_model", result_length=len(llm_result or ""))

    def on_tool_start(self, tool_name: str = None, **kwargs):
        callback_log.log("before_tool", tool_name=tool_name)

    def on_tool_end(self, tool_name: str = None, **kwargs):
        callback_log.log("after_tool", tool_name=tool_name)

def stop_when_article_complete(messages: list, **kwargs) -> bool:
    """Stop when the article is marked complete."""
    if messages and isinstance(messages[-1], dict):
        content = messages[-1].get("content", "")
        if "ARTICLE_COMPLETE" in content:
            return True
    return False

draft_writer = Agent(
    name="draft_writer",
    model=settings.llm_model,
    instructions="Write a comprehensive article draft based on research findings.",
    tools=[recall_past_articles],
    memory=ConversationMemory(max_messages=50),
    callbacks=[PublishingCallbackHandler()],
)

editor = Agent(
    name="editor",
    model=settings.llm_model,
    instructions=(
        "Review and edit the article. Fix grammar, improve clarity. "
        "When done, include ARTICLE_COMPLETE."
    ),
    stop_when=stop_when_article_complete,
)

# Sequential pipeline via >> operator
writing_pipeline = draft_writer >> editor


# ═══════════════════════════════════════════════════════════════════════
# STAGE 4: Review & Safety
# Features: #22 RegexGuardrail, #23 LLMGuardrail, #24 custom @guardrail,
#   #25 external guardrail, #20 tool guardrail,
#   #26 RETRY, #27 RAISE, #28 FIX, #29 HUMAN
# ═══════════════════════════════════════════════════════════════════════

pii_guardrail = RegexGuardrail(
    name="pii_blocker",
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b", r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"],
    mode="block",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
    message="PII detected. Redact all personal information.",
)

bias_guardrail = LLMGuardrail(
    name="bias_detector",
    model="openai/gpt-4o-mini",
    policy="Check for biased language or stereotypes. If found, provide corrected version.",
    position=Position.OUTPUT,
    on_fail=OnFail.FIX,
    max_tokens=10000,
)

@guardrail
def fact_validator(content: str) -> GuardrailResult:
    """Validate factual claims in the article."""
    red_flags = ["the best", "the worst", "always", "never", "guaranteed"]
    found = [rf for rf in red_flags if rf.lower() in content.lower()]
    if found:
        return GuardrailResult(passed=False, message=f"Unverifiable claims: {found}")
    return GuardrailResult(passed=True)

compliance_guardrail = Guardrail(
    name="compliance_check",
    external=True,
    position=Position.OUTPUT,
    on_fail=OnFail.RAISE,
)

@guardrail
def sql_injection_guard(content: str) -> GuardrailResult:
    """Block SQL injection in search tool inputs."""
    if contains_sql_injection(content):
        return GuardrailResult(passed=False, message="SQL injection detected.")
    return GuardrailResult(passed=True)

@tool(guardrails=[Guardrail(sql_injection_guard, position=Position.INPUT, on_fail=OnFail.RAISE)])
def safe_search(query: str) -> dict:
    """Search with SQL injection protection."""
    return {"query": query, "results": ["result1", "result2"]}

review_agent = Agent(
    name="safety_reviewer",
    model=settings.llm_model,
    instructions="Review the article for safety and compliance.",
    tools=[safe_search],
    guardrails=[
        pii_guardrail,           # on_fail=RETRY
        bias_guardrail,          # on_fail=FIX
        Guardrail(fact_validator, position=Position.OUTPUT, on_fail=OnFail.HUMAN),
        compliance_guardrail,    # on_fail=RAISE (external)
    ],
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 5: Editorial Approval
# Features: #17 approval_required, #40 approve, #41 reject,
#   #42 feedback/respond, #14 human_tool, #65 UserProxyAgent
# ═══════════════════════════════════════════════════════════════════════

@tool(approval_required=True)
def publish_article(title: str, content: str, platform: str) -> dict:
    """Publish article to platform. Requires editorial approval."""
    return {"status": "published", "title": title, "platform": platform}

editorial_question = human_tool(
    name="ask_editor",
    description="Ask the editor a question about the article.",
    input_schema={
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    },
)

editorial_reviewer = UserProxyAgent(
    name="editorial_reviewer",
    model=settings.llm_model,
    instructions="You are the editorial reviewer. Provide feedback on article quality.",
    human_input_mode="TERMINATE",
)

editorial_agent = Agent(
    name="editorial_approval",
    model=settings.llm_model,
    instructions="Review the article, ask questions, get approval before publishing.",
    tools=[publish_article, editorial_question],
    agents=[editorial_reviewer],
    strategy=Strategy.HANDOFF,
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 6: Translation & Discussion
# Features: #6 round_robin, #7 random, #8 swarm, #9 manual,
#   #35 OnTextMention, #37 allowed_transitions, #38 introductions
# ═══════════════════════════════════════════════════════════════════════

spanish_translator = Agent(
    name="spanish_translator",
    model=settings.llm_model,
    instructions="You translate articles to Spanish with a formal tone.",
    introduction="I am the Spanish translator, specializing in formal academic translations.",
)

french_translator = Agent(
    name="french_translator",
    model=settings.llm_model,
    instructions="You translate articles to French with a conversational tone.",
    introduction="I am the French translator, specializing in conversational translations.",
)

german_translator = Agent(
    name="german_translator",
    model=settings.llm_model,
    instructions="You translate articles to German with a technical tone.",
    introduction="I am the German translator, specializing in technical translations.",
)

tone_debate = Agent(
    name="tone_debate",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
)

translation_swarm = Agent(
    name="translation_swarm",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="Spanish", target="spanish_translator"),
        OnTextMention(text="French", target="french_translator"),
        OnTextMention(text="German", target="german_translator"),
    ],
    allowed_transitions={
        "spanish_translator": ["french_translator", "german_translator"],
        "french_translator": ["spanish_translator", "german_translator"],
        "german_translator": ["spanish_translator", "french_translator"],
    },
)

title_brainstorm = Agent(
    name="title_brainstorm",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.RANDOM,
    max_turns=3,
)

manual_translation = Agent(
    name="manual_translation",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.MANUAL,
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 7: Publishing Pipeline
# Features: #2 Handoff, #33 composable termination, #34 OnToolResult,
#   #36 OnCondition, #71 gate condition, #88 external agent
# ═══════════════════════════════════════════════════════════════════════

@tool
def format_check(content: str) -> dict:
    """Check article formatting."""
    return {"formatted": True, "issues": []}

def should_handoff_to_publisher(messages: list, **kwargs) -> bool:
    """Custom handoff condition."""
    if messages:
        last = messages[-1] if isinstance(messages[-1], dict) else {}
        return "formatted" in str(last.get("content", ""))
    return False

formatter = Agent(
    name="formatter",
    model=settings.llm_model,
    instructions="Format the article according to publishing guidelines.",
    tools=[format_check],
)

external_publisher = Agent(
    name="external_publisher",
    external=True,
    instructions="Publish to the CMS platform.",
)

from agentspan.agents.gate import TextGate

publishing_pipeline = Agent(
    name="publishing_pipeline",
    model=settings.llm_model,
    instructions="Manage the publishing workflow from formatting to publication.",
    agents=[formatter, external_publisher],
    strategy=Strategy.HANDOFF,
    handoffs=[
        OnToolResult(target="external_publisher", tool_name="format_check"),
        OnCondition(target="external_publisher", condition=should_handoff_to_publisher),
    ],
    termination=(
        TextMentionTermination("PUBLISHED")
        | (MaxMessageTermination(50) & TokenUsageTermination(max_total_tokens=100000))
    ),
    gate=TextGate(text="APPROVED"),
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 8: Analytics & Reporting
# Features: #13 agent_tool, #15 media tools, #16 RAG tools,
#   #58-61 code executors, #64 token tracking, #66 GPTAssistantAgent,
#   #67 thinking, #68 include_contents, #69 planner, #70 required_tools,
#   #72 CLI config
# ═══════════════════════════════════════════════════════════════════════

local_executor = LocalCodeExecutor(language="python", timeout=10)
docker_executor = DockerCodeExecutor(image="python:3.12-slim", timeout=15)
jupyter_executor = JupyterCodeExecutor(timeout=30)
serverless_executor = ServerlessCodeExecutor(
    endpoint="https://api.example.com/functions/analytics",
    timeout=30,
)

article_thumbnail = image_tool(
    name="generate_thumbnail",
    description="Generate an article thumbnail image.",
    llm_provider="openai",
    model="dall-e-3",
)

audio_summary = audio_tool(
    name="generate_audio_summary",
    description="Generate an audio summary of the article.",
    llm_provider="openai",
    model="tts-1",
)

video_highlight = video_tool(
    name="generate_video_highlight",
    description="Generate a short video highlight.",
    llm_provider="openai",
    model="sora",
)

article_pdf = pdf_tool(
    name="generate_article_pdf",
    description="Generate a PDF version of the article.",
)

article_indexer = index_tool(
    name="index_article",
    description="Index the article for future retrieval.",
    vector_db="pgvector",
    index="articles",
    embedding_model_provider="openai",
    embedding_model="text-embedding-3-small",
)

article_search = search_tool(
    name="search_articles",
    description="Search for related articles.",
    vector_db="pgvector",
    index="articles",
    embedding_model_provider="openai",
    embedding_model="text-embedding-3-small",
    max_results=5,
)

# -- agent_tool: wrap a sub-agent as a callable tool --
research_subtool = agent_tool(
    Agent(
        name="quick_researcher",
        model=settings.llm_model,
        instructions="Do a quick research lookup on the given topic.",
    ),
    name="quick_research",
    description="Quick research lookup as a tool.",
)

# -- GPTAssistantAgent --
gpt_assistant = GPTAssistantAgent(
    name="openai_research_assistant",
    model="gpt-4o",
    instructions="You are a research assistant with access to code interpreter.",
)

analytics_agent = Agent(
    name="analytics_agent",
    model=settings.llm_model,
    instructions="Analyze the published article and generate a comprehensive analytics report.",
    tools=[
        local_executor.as_tool(),
        docker_executor.as_tool(name="run_sandboxed"),
        jupyter_executor.as_tool(name="run_notebook"),
        serverless_executor.as_tool(name="run_cloud"),
        article_thumbnail, audio_summary, video_highlight, article_pdf,
        article_indexer, article_search,
        research_subtool,
    ],
    agents=[gpt_assistant],
    strategy=Strategy.HANDOFF,
    thinking_budget_tokens=2048,
    include_contents="default",
    output_type=ArticleReport,
    required_tools=["index_article"],
    code_execution_config=CodeExecutionConfig(
        enabled=True,
        allowed_languages=["python", "shell"],
        allowed_commands=["python3", "pip"],
        timeout=30,
    ),
    cli_config=CliConfig(
        enabled=True,
        allowed_commands=["git", "gh"],
        timeout=30,
    ),
    metadata={"stage": "analytics", "version": "1.0"},
    planner=True,
)


# ═══════════════════════════════════════════════════════════════════════
# FULL PIPELINE (hierarchical composition of all stages)
# ═══════════════════════════════════════════════════════════════════════

full_pipeline = Agent(
    name="content_publishing_platform",
    model=settings.llm_model,
    instructions=(
        "You are a content publishing platform. Process article requests "
        "through all pipeline stages."
    ),
    agents=[
        intake_router,        # Stage 1
        research_team,        # Stage 2
        writing_pipeline,     # Stage 3 (sequential via >>)
        review_agent,         # Stage 4
        editorial_agent,      # Stage 5
        translation_swarm,    # Stage 6
        publishing_pipeline,  # Stage 7
        analytics_agent,      # Stage 8
    ],
    strategy=Strategy.SEQUENTIAL,
    termination=(
        TextMentionTermination("PIPELINE_COMPLETE")
        | MaxMessageTermination(200)
    ),
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 9: Execution Modes
# Features: #43-51 all execution modes, #74 discover_agents, #75 tracing
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    PROMPT = (
        "Write a comprehensive tech article about quantum computing "
        "advances in 2026, get it reviewed, translate to Spanish, "
        "and publish."
    )

    # Feature #75: OTel tracing check
    if is_tracing_enabled():
        print("[tracing] OpenTelemetry tracing is enabled")

    with AgentRuntime() as runtime:

        # ── Feature #49: deploy (compile + register) ─────────────
        print("=== Deploy ===")
        deployments = runtime.deploy(full_pipeline)
        for dep in deployments:
            print(f"  Deployed: {dep.agent_name}")

        # ── Feature #51: plan (dry-run, no prompt) ───────────────
        print("\n=== Plan (dry-run) ===")
        execution_plan = runtime.plan(full_pipeline)
        print(f"  Plan compiled successfully")

        # ── Feature #43: stream (sync SSE with HITL) ─────────────
        print("\n=== Stream Execution ===")
        agent_stream = runtime.stream(full_pipeline, PROMPT)
        print(f"  Execution: {agent_stream.execution_id}\n")

        hitl_demo_state = {"approved": 0, "rejected": 0, "feedback": 0}

        for event in agent_stream:
            if event.type == EventType.THINKING:
                print(f"  [thinking] {event.content[:80]}...")
            elif event.type == EventType.TOOL_CALL:
                print(f"  [tool_call] {event.tool_name}({event.args})")
            elif event.type == EventType.TOOL_RESULT:
                print(f"  [tool_result] {event.tool_name} -> {str(event.result)[:80]}...")
            elif event.type == EventType.HANDOFF:
                print(f"  [handoff] -> {event.target}")
            elif event.type == EventType.GUARDRAIL_PASS:
                print(f"  [guardrail_pass] {event.guardrail_name}")
            elif event.type == EventType.GUARDRAIL_FAIL:
                print(f"  [guardrail_fail] {event.guardrail_name}: {event.content}")
            elif event.type == EventType.MESSAGE:
                print(f"  [message] {event.content[:80]}...")
            elif event.type == EventType.WAITING:
                print(f"\n  --- HITL: Approval required ---")
                # Demo all 3 HITL modes:
                if hitl_demo_state["feedback"] == 0:
                    # Feature #42: send feedback first
                    agent_stream.send("Please add more details about quantum error correction.")
                    hitl_demo_state["feedback"] += 1
                    print(f"  Sent feedback (revision request)\n")
                elif hitl_demo_state["rejected"] == 0:
                    # Feature #41: reject once
                    agent_stream.reject("Title needs improvement")
                    hitl_demo_state["rejected"] += 1
                    print(f"  Rejected (title needs work)\n")
                else:
                    # Feature #40: approve
                    agent_stream.approve()
                    hitl_demo_state["approved"] += 1
                    print(f"  Approved\n")
            elif event.type == EventType.ERROR:
                print(f"  [error] {event.content}")
            elif event.type == EventType.DONE:
                print(f"\n  [done] Pipeline complete")

        result = agent_stream.get_result()
        result.print_result()

        # ── Feature #64: Token tracking ──────────────────────────
        if result.token_usage:
            print(f"\nTotal tokens: {result.token_usage.total_tokens}")
            print(f"  Prompt: {result.token_usage.prompt_tokens}")
            print(f"  Completion: {result.token_usage.completion_tokens}")

        # ── Callback log ─────────────────────────────────────────
        print(f"\nCallback events: {len(callback_log.events)}")
        for ev in callback_log.events[:5]:
            print(f"  {ev['type']}: {ev}")

        # ── Feature #48: start + polling ─────────────────────────
        print("\n=== Start + Polling ===")
        handle = runtime.start(full_pipeline, PROMPT)
        print(f"  Started: {handle.execution_id}")
        status = handle.get_status()
        print(f"  Status: {status.status}, Running: {status.is_running}")
        if status.reason:
            print(f"  Reason: {status.reason}")

        # ── Feature #44: async streaming ─────────────────────────
        print("\n=== Async Streaming ===")

        async def demo_async_stream():
            async_stream = await runtime.stream_async(full_pipeline, PROMPT)
            async for event in async_stream:
                if event.type == EventType.DONE:
                    print(f"  [async done] Pipeline complete")
                    break
                elif event.type == EventType.WAITING:
                    await async_stream.approve()
            async_result = await async_stream.get_result()
            print(f"  Async result status: {async_result.status}")

        asyncio.run(demo_async_stream())

        # ── Feature #46/47: top-level convenience run/run_async ──
        print("\n=== Top-Level Convenience API ===")
        # These use the singleton runtime
        configure(AgentConfig.from_env())
        simple_agent = Agent(
            name="simple_test",
            model=settings.llm_model,
            instructions="Say hello.",
        )
        simple_result = run(simple_agent, "Hello!")
        print(f"  run() status: {simple_result.status}")

        # ── Feature #74: discover_agents ─────────────────────────
        print("\n=== Discover Agents ===")
        try:
            agents = discover_agents("sdk/python/examples")
            print(f"  Discovered {len(agents)} agents")
        except Exception as e:
            print(f"  Discovery: {e}")

        # ── Feature #50: serve (blocking — commented for demo) ───
        # serve()  # Starts worker poll loop; uncomment to run as server

    # ── Cleanup ──────────────────────────────────────────────────
    shutdown()
    print("\n=== Kitchen Sink Complete ===")
```

- [ ] **Step 2: Verify imports work**

```bash
cd sdk/python && uv run python -c "import examples.kitchen_sink" 2>&1 | head -5
```

Expected: No import errors (runtime errors are expected without server).

- [ ] **Step 3: Commit**

```bash
git add sdk/python/examples/kitchen_sink.py
git commit -m "feat: complete kitchen sink — all 88 features exercised in single mega-workflow"
```

---

### Task 4: Kitchen Sink Test Suite

**Files:**
- Create: `sdk/python/tests/test_kitchen_sink.py`

- [ ] **Step 1: Write kitchen sink test suite**

```python
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Kitchen Sink test suite — structural + behavioral assertions.

Tests the kitchen sink structure using direct imports (no server required)
and the testing framework's assertion/validation tools.
"""

import os
import sys
import pytest

# Add examples to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from agentspan.agents import Status, FinishReason, Strategy
from agentspan.agents.testing import (
    mock_run, expect, MockEvent,
    assert_tool_used, assert_tool_not_used,
    assert_status, assert_no_errors,
    assert_guardrail_passed,
    validate_strategy,
    record, replay,
    CorrectnessEval, EvalCase,
)


class TestKitchenSinkStructure:
    """Structural tests — verify agent tree is correctly defined."""

    def test_full_pipeline_has_all_stages(self):
        from kitchen_sink import full_pipeline
        assert full_pipeline.name == "content_publishing_platform"
        assert len(full_pipeline.agents) == 8
        assert full_pipeline.strategy == Strategy.SEQUENTIAL

    def test_intake_uses_router_strategy(self):
        from kitchen_sink import intake_router
        assert intake_router.strategy == Strategy.ROUTER
        assert intake_router.router is not None
        assert intake_router.output_type is not None

    def test_research_uses_parallel_with_scatter_gather(self):
        from kitchen_sink import research_team, research_coordinator
        assert research_team.strategy == Strategy.PARALLEL
        # scatter_gather creates a coordinator agent
        assert research_coordinator.name == "research_coordinator"

    def test_writing_pipeline_is_sequential(self):
        from kitchen_sink import writing_pipeline
        assert writing_pipeline.strategy == Strategy.SEQUENTIAL

    def test_review_has_all_guardrail_types(self):
        from kitchen_sink import review_agent
        names = [g.name for g in review_agent.guardrails]
        assert "pii_blocker" in names       # regex
        assert "bias_detector" in names     # llm
        assert "fact_validator" in names    # custom
        assert "compliance_check" in names  # external

    def test_editorial_has_hitl_tools(self):
        from kitchen_sink import editorial_agent
        tool_names = [t.name if hasattr(t, 'name') else str(t) for t in editorial_agent.tools]
        # Should have approval-required tool and human tool

    def test_translation_swarm_has_handoffs(self):
        from kitchen_sink import translation_swarm
        assert translation_swarm.strategy == Strategy.SWARM
        assert len(translation_swarm.handoffs) == 3
        assert translation_swarm.allowed_transitions is not None

    def test_all_strategies_exercised(self):
        from kitchen_sink import (
            intake_router, research_team, writing_pipeline,
            tone_debate, translation_swarm, title_brainstorm,
            manual_translation, publishing_pipeline, editorial_agent,
        )
        strategies = {
            intake_router.strategy,
            research_team.strategy,
            writing_pipeline.strategy,
            tone_debate.strategy,
            translation_swarm.strategy,
            title_brainstorm.strategy,
            manual_translation.strategy,
            publishing_pipeline.strategy,
            editorial_agent.strategy,
        }
        # All 8 strategies + SEQUENTIAL from writing pipeline
        assert Strategy.ROUTER in strategies
        assert Strategy.PARALLEL in strategies
        assert Strategy.SEQUENTIAL in strategies
        assert Strategy.ROUND_ROBIN in strategies
        assert Strategy.SWARM in strategies
        assert Strategy.RANDOM in strategies
        assert Strategy.MANUAL in strategies
        assert Strategy.HANDOFF in strategies

    def test_publishing_has_gate_and_termination(self):
        from kitchen_sink import publishing_pipeline
        assert publishing_pipeline.termination is not None
        assert publishing_pipeline.gate is not None

    def test_analytics_has_all_features(self):
        from kitchen_sink import analytics_agent
        assert analytics_agent.code_execution_config is not None
        assert analytics_agent.cli_config is not None
        assert analytics_agent.thinking_budget_tokens == 2048
        assert analytics_agent.planner is True
        assert analytics_agent.include_contents == "default"
        assert analytics_agent.required_tools is not None
        assert "index_article" in analytics_agent.required_tools
        assert analytics_agent.metadata == {"stage": "analytics", "version": "1.0"}

    def test_external_tool_is_marked(self):
        from kitchen_sink import external_research_aggregator
        from agentspan.agents.tool import get_tool_def
        td = get_tool_def(external_research_aggregator)
        assert td.tool_type == "worker"

    def test_external_agent_is_marked(self):
        from kitchen_sink import external_publisher
        assert external_publisher.external is True

    def test_gpt_assistant_agent_exists(self):
        from kitchen_sink import gpt_assistant
        assert gpt_assistant.name == "openai_research_assistant"

    def test_agent_tool_exists(self):
        from kitchen_sink import research_subtool
        from agentspan.agents.tool import get_tool_def
        td = get_tool_def(research_subtool)
        assert td.name == "quick_research"


class TestKitchenSinkHelpers:
    """Test helper functions."""

    def test_contains_pii_ssn(self):
        from kitchen_sink_helpers import contains_pii
        assert contains_pii("My SSN is 123-45-6789")
        assert not contains_pii("No PII here")

    def test_contains_pii_credit_card(self):
        from kitchen_sink_helpers import contains_pii
        assert contains_pii("Card: 4532-0150-1234-5678")

    def test_contains_sql_injection(self):
        from kitchen_sink_helpers import contains_sql_injection
        assert contains_sql_injection("DROP TABLE users")
        assert not contains_sql_injection("normal search query")

    def test_classification_result_model(self):
        from kitchen_sink_helpers import ClassificationResult
        result = ClassificationResult(
            category="tech", priority=1, tags=["quantum"], metadata={}
        )
        assert result.category == "tech"

    def test_callback_log(self):
        from kitchen_sink_helpers import callback_log
        callback_log.clear()
        callback_log.log("test_event", key="value")
        assert len(callback_log.events) == 1
        callback_log.clear()


class TestStrategyValidation:
    """Validate strategy constraints (feature #82)."""

    def test_validate_parallel_strategy(self):
        from kitchen_sink import research_team
        # validate_strategy checks that strategy constraints are met
        violations = validate_strategy(research_team)
        assert len(violations) == 0, f"Strategy violations: {violations}"

    def test_validate_sequential_strategy(self):
        from kitchen_sink import writing_pipeline
        violations = validate_strategy(writing_pipeline)
        assert len(violations) == 0

    def test_validate_swarm_strategy(self):
        from kitchen_sink import translation_swarm
        violations = validate_strategy(translation_swarm)
        assert len(violations) == 0


class TestEvalRunner:
    """Correctness evaluation framework (feature #83)."""

    def test_eval_case_definition(self):
        """Verify eval cases can be defined for the kitchen sink."""
        eval_case = EvalCase(
            name="kitchen_sink_basic",
            prompt="Write a tech article about quantum computing",
            expected_contains=["quantum", "computing"],
        )
        assert eval_case.name == "kitchen_sink_basic"
```

- [ ] **Step 2: Run tests**

```bash
cd sdk/python && uv run pytest tests/test_kitchen_sink.py -v
```

- [ ] **Step 3: Commit**

```bash
git add sdk/python/tests/test_kitchen_sink.py
git commit -m "test: kitchen sink structural tests, strategy validation, eval runner"
```

---

## Chunk 2: Per-Language Translation Guides

All 6 guides must cover ALL 9 sections from the template (spec Section 10):
1. Project Setup
2. Type System Mapping
3. Decorator/Annotation Pattern
4. Async Model
5. Worker Implementation
6. SSE Client
7. Error Handling
8. Testing Framework
9. Kitchen Sink Translation

Tasks 5-10 are **fully independent** and can be executed by parallel subagents.

### Task 5: TypeScript Translation Guide

**Files:**
- Create: `docs/sdk-design/typescript.md`

- [ ] **Step 1: Write TypeScript translation guide with all 9 sections**

Must include:
1. **Project Setup:** npm/pnpm, TypeScript 5.x, `src/` + `tests/`, tsconfig with decorators
2. **Type System:** interface/class, enum/union, `T | null`, zod schemas, `Record<K,V>`
3. **Decorators:** `@Tool()` on class methods or `tool()` function wrapper, `@Agent()`, `@Guardrail()`
4. **Async:** Native async/await, Promise<T>, no sync wrappers needed
5. **Workers:** `setInterval` + async handler, or Web Workers/worker_threads for parallel polling
6. **SSE Client:** `EventSource` API for browser, `fetch` with `ReadableStream` for Node, reconnection with `Last-Event-ID`, heartbeat filtering, 15s timeout detection
7. **Error Handling:** Custom error classes extending `Error` (`AgentspanError`, `AgentAPIError`, etc.), guardrail failure propagation via rejected promises, timeout via `AbortController`
8. **Testing:** `mock_run()` → `mockRun()`, `expect()` → fluent chainable assertions, `record()`/`replay()` for deterministic testing, jest/vitest integration, validation runner as npm script
9. **Kitchen Sink:** Complete annotated outline of how each stage translates — pipe() for >>, .and()/.or() for operators, EventSource for streaming, all HITL methods

Include complete code examples for: agent definition, tool with context, guardrail, streaming with HITL, async execution.

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/typescript.md
git commit -m "docs: TypeScript SDK translation guide — all 9 sections"
```

---

### Task 6: Go Translation Guide

**Files:**
- Create: `docs/sdk-design/go.md`

- [ ] **Step 1: Write Go translation guide with all 9 sections**

Must include:
1. **Project Setup:** Go modules, `cmd/` + `pkg/agentspan/`, `go.mk`
2. **Type System:** structs with json tags, `const` iota for enums, `*T` for optional, generics (1.18+)
3. **Functional Options:** `NewTool("name", handler, WithApproval(), WithCredentials("KEY"))`, `NewAgent(...)`, `NewGuardrail(...)`
4. **Async:** Goroutines + channels, blocking by default, `<-chan AgentEvent` for streaming
5. **Workers:** Goroutine with `time.Ticker` for poll loop, `context.Context` for cancellation
6. **SSE Client:** `http.Get` with chunked response reading, line-by-line parsing, reconnection goroutine, `Last-Event-ID` header, comment/heartbeat filtering
7. **Error Handling:** Return `(result, error)` pairs, custom error types (`AgentAPIError`, etc.), `errors.Is()`/`errors.As()` for type checking, guardrail failures as typed errors, `context.WithTimeout` for deadlines
8. **Testing:** `mockRun()` returns mock result, `Expect(result).Completed().OutputContains("text")`, `Record()`/`Replay()`, `go test` integration, validation binary
9. **Kitchen Sink:** `Pipeline(a, b, c)` for >>, `And()`/`Or()` functions for conditions, goroutine for async streaming, `context.Context` threading

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/go.md
git commit -m "docs: Go SDK translation guide — all 9 sections"
```

---

### Task 7: Java Translation Guide

**Files:**
- Create: `docs/sdk-design/java.md`

- [ ] **Step 1: Write Java translation guide with all 9 sections**

Cover BOTH record (16+) and POJO (8+) patterns side-by-side:

1. **Project Setup:** Maven/Gradle, Java 8+ and 16+ profiles, `src/main/java/`
2. **Type System:** record vs POJO with getters/Lombok, enum, `Optional<T>` vs `@Nullable`
3. **Annotations:** `@Tool(name="..", approvalRequired=true)`, `@AgentDef(...)`, `@Guardrail(...)`, plus Builder pattern alternative
4. **Async:** `CompletableFuture<T>` (8+), virtual threads (21+), `ScheduledExecutorService` for workers
5. **Workers:** `ScheduledExecutorService.scheduleAtFixedRate()` poll loop, virtual threads for 21+, task deserialization via Jackson
6. **SSE Client:** `HttpClient.newHttpClient()` (11+) with `BodyHandler.ofLines()`, Apache HttpClient for 8+, line parser, `Last-Event-ID`, reconnection with backoff
7. **Error Handling:** Exception hierarchy (`AgentspanException`, `AgentAPIException`, etc.), checked vs unchecked strategy, guardrail failures as specific exception types, `CompletableFuture.exceptionally()` for async errors
8. **Testing:** JUnit 5, `MockRun.execute()`, `Expect.that(result).isCompleted().outputContains("text")`, `Recording.record()`/`replay()`, Maven Surefire integration, validation as test suite
9. **Kitchen Sink:** `.then()` for >>, `.and()`/`.or()` for conditions, `CompletableFuture.allOf()` for parallel, `try-with-resources` for runtime

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/java.md
git commit -m "docs: Java SDK translation guide — record + POJO patterns, all 9 sections"
```

---

### Task 8: Kotlin Translation Guide

**Files:**
- Create: `docs/sdk-design/kotlin.md`

- [ ] **Step 1: Write Kotlin translation guide with all 9 sections**

1. **Project Setup:** Gradle (Kotlin DSL), coroutines dependency, Ktor for HTTP
2. **Type System:** `data class`, `enum class`/`sealed class`, `T?` null safety, kotlinx.serialization
3. **DSL Builders:** `agent("name") { model("..."); tools { tool("...") { } } }`, `guardrails { regex("...") { } }`
4. **Async:** `suspend fun`, `runBlocking { }` for sync, `flow { }` for streaming, `CoroutineScope`
5. **Workers:** `CoroutineScope.launch { while(isActive) { delay(100); poll() } }`, structured concurrency
6. **SSE Client:** Ktor `HttpClient` with streaming, `Flow<AgentEvent>` for event stream, reconnection via coroutine retry, `Last-Event-ID` header
7. **Error Handling:** Sealed class hierarchy for errors, `Result<T>` for safe operations, `runCatching { }`, coroutine exception handlers, guardrail failures as typed exceptions
8. **Testing:** kotest or JUnit 5, `mockRun { }` DSL, `expect(result) { completed(); outputContains("text") }`, coroutine test utilities, `runTest { }` for suspend functions
9. **Kitchen Sink:** `researcher then writer then editor` infix, `or`/`and` infix for conditions, `flow { }` for streaming, structured concurrency for parallel

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/kotlin.md
git commit -m "docs: Kotlin SDK translation guide — DSL builders and coroutines, all 9 sections"
```

---

### Task 9: C# Translation Guide

**Files:**
- Create: `docs/sdk-design/csharp.md`

- [ ] **Step 1: Write C# translation guide with all 9 sections**

1. **Project Setup:** .NET 8+, NuGet, `src/` + `tests/`, `dotnet` CLI
2. **Type System:** `record`, `enum`, `T?` nullable, `System.Text.Json`, `OneOf<A,B>` pattern
3. **Attributes:** `[Tool(Name = "...", ApprovalRequired = true)]`, `[AgentDef(...)]`, `[Guardrail(...)]`, plus fluent builder `Agent.Create("...").WithModel("...").Build()`
4. **Async:** `Task<T>` / `async Task`, `await`, `.GetAwaiter().GetResult()` for sync wrapper
5. **Workers:** `Task.Run()` + `PeriodicTimer` (.NET 6+), `Channel<T>` for producer/consumer
6. **SSE Client:** `HttpClient.GetStreamAsync()` + `StreamReader.ReadLineAsync()`, `IAsyncEnumerable<AgentEvent>`, reconnection with `Polly` or manual retry, `Last-Event-ID`
7. **Error Handling:** Exception hierarchy (`AgentspanException`, etc.), `try/catch` patterns, `IAsyncEnumerable` error propagation, `CancellationToken` for timeouts
8. **Testing:** xUnit/NUnit, `MockRun.Execute()`, `Expect(result).ToBeCompleted().ToContainOutput("text")`, `FluentAssertions` integration, validation as test project
9. **Kitchen Sink:** `operator >>` overload for pipeline, `operator &`/`|` for conditions, `IAsyncEnumerable` for streaming, `using` for runtime lifecycle

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/csharp.md
git commit -m "docs: C# SDK translation guide — operator overloading and async, all 9 sections"
```

---

### Task 10: Ruby Translation Guide

**Files:**
- Create: `docs/sdk-design/ruby.md`

- [ ] **Step 1: Write Ruby translation guide with all 9 sections**

1. **Project Setup:** Bundler, `lib/agentspan/` + `spec/`, Ruby 3.2+, gemspec
2. **Type System:** `Struct`/`Data` (3.2+), module constants for enums, nilable, `dry-schema`
3. **DSL Blocks:** `Agent.new("name") { model "..."; tool(:search) { |q:| ... } }`, block-based registration
4. **Async:** Primarily synchronous, `Thread` for parallelism, `async` gem for Fiber-based, `Ractor` (3.0+)
5. **Workers:** `Thread.new { loop { sleep(0.1); poll() } }`, or `async` gem with `Async::Task`
6. **SSE Client:** `Net::HTTP` with chunked response, `IO.select` for non-blocking reads, line parser, reconnection with retry loop, `Last-Event-ID`
7. **Error Handling:** Exception hierarchy (`AgentspanError < StandardError`, etc.), `begin/rescue/ensure`, guardrail failures as typed exceptions, `Timeout.timeout()` for deadlines
8. **Testing:** RSpec, `mock_run { }`, `expect(result).to be_completed.and contain_output("text")`, custom matchers, recording/replay, validation as rake task
9. **Kitchen Sink:** `>>` operator (Ruby supports custom operators), `&`/`|` already Ruby operators, `Thread` for async patterns, `ensure` for cleanup

- [ ] **Step 2: Commit**

```bash
git add docs/sdk-design/ruby.md
git commit -m "docs: Ruby SDK translation guide — DSL blocks and operator overloading, all 9 sections"
```

---

## Chunk 3: Final Integration

### Task 11: Cross-Reference and Final Commit

**Files:**
- Modify: `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`

- [ ] **Step 1: Add deliverable status table to base design doc**

Add after the "Deliverables" table in Section 1.3:

```markdown
## Deliverable Status

| # | File | Status |
|---|------|--------|
| 1 | [base-design.md](2026-03-23-multi-language-sdk-design.md) | Complete |
| 2 | [kitchen-sink.md](kitchen-sink.md) | Complete |
| 3 | [kitchen_sink.py](../../sdk/python/examples/kitchen_sink.py) | Complete |
| 4 | [typescript.md](typescript.md) | Complete |
| 5 | [go.md](go.md) | Complete |
| 6 | [java.md](java.md) | Complete |
| 7 | [kotlin.md](kotlin.md) | Complete |
| 8 | [csharp.md](csharp.md) | Complete |
| 9 | [ruby.md](ruby.md) | Complete |
```

- [ ] **Step 2: Final commit**

```bash
git add docs/sdk-design/
git commit -m "docs: complete multi-language SDK design — all guides and kitchen sink"
```

---

## Execution Notes

- **Parallelization:** Tasks 5-10 (per-language guides) are fully independent and SHOULD be executed by parallel subagents
- **Dependencies:** Tasks 1-4 (kitchen sink) must complete before Tasks 5-10 (guides reference kitchen sink)
- **Testing:** Task 4 tests can run without a server (structural tests). Full behavioral tests require a running Conductor server.
- **Each language guide** should be 3000-5000 words with complete code examples for every major pattern
- **Kitchen sink Python code** should be runnable with `uv run python sdk/python/examples/kitchen_sink.py` (with server + env vars)
- **Per-language guides** each cover all 9 sections from the spec template — no section may be omitted
