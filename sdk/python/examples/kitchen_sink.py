# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Kitchen Sink — Content Publishing Platform.

A single mega-workflow that exercises every Agentspan SDK feature (89 features).
See docs/sdk-design/kitchen-sink.md for the full scenario specification.

Demonstrates:
    - All 8 multi-agent strategies
    - All tool types (worker, http, mcp, api, agent_tool, human, media, RAG)
    - All guardrail types (regex, llm, custom, external) with all OnFail modes
    - HITL (approve, reject, feedback, UserProxyAgent, human_tool)
    - Memory (conversation + semantic)
    - Code execution (local, docker, jupyter, serverless)
    - Credentials (all isolation modes, CredentialFile)
    - Streaming (sync + async), termination, handoffs, callbacks
    - Structured output, prompt templates, agent chaining, gate conditions
    - Extended thinking, planner mode, required_tools, include_contents
    - GPTAssistantAgent, agent_tool(), scatter_gather()

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
    Agent,
    AgentRuntime,
    AgentConfig,
    PromptTemplate,
    Strategy,
    agent,
    scatter_gather,
    # Tools
    tool,
    ToolContext,
    ToolDef,
    http_tool,
    mcp_tool,
    api_tool,
    agent_tool,
    human_tool,
    image_tool,
    audio_tool,
    video_tool,
    pdf_tool,
    search_tool,
    index_tool,
    # Guardrails
    guardrail,
    Guardrail,
    GuardrailResult,
    OnFail,
    Position,
    RegexGuardrail,
    LLMGuardrail,
    # Results
    AgentResult,
    AgentHandle,
    AgentStatus,
    AgentStream,
    AsyncAgentStream,
    AgentEvent,
    EventType,
    FinishReason,
    Status,
    TokenUsage,
    DeploymentInfo,
    # Termination
    TerminationCondition,
    TextMentionTermination,
    StopMessageTermination,
    MaxMessageTermination,
    TokenUsageTermination,
    # Handoffs
    HandoffCondition,
    OnToolResult,
    OnTextMention,
    OnCondition,
    # Memory
    ConversationMemory,
    SemanticMemory,
    MemoryStore,
    MemoryEntry,
    # Code execution
    CodeExecutionConfig,
    CodeExecutor,
    LocalCodeExecutor,
    DockerCodeExecutor,
    JupyterCodeExecutor,
    ServerlessCodeExecutor,
    ExecutionResult,
    # Extended
    UserProxyAgent,
    GPTAssistantAgent,
    CallbackHandler,
    CliConfig,
    # Credentials
    get_credential,
    CredentialFile,
    # Execution (top-level convenience + runtime)
    configure,
    run,
    run_async,
    start,
    start_async,
    stream,
    stream_async,
    deploy,
    deploy_async,
    serve,
    plan,
    shutdown,
    # Discovery & tracing
    discover_agents,
    is_tracing_enabled,
    # Exceptions
    ConfigurationError,
)

from settings import settings
from kitchen_sink_helpers import (
    ClassificationResult,
    ArticleReport,
    MOCK_RESEARCH_DATA,
    MOCK_PAST_ARTICLES,
    contains_pii,
    contains_sql_injection,
    callback_log,
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
#   #11 http_tool, #12 mcp_tool, #89 api_tool, #18 ToolContext,
#   #19 tool credentials, #21 external tool, #52 isolated creds,
#   #53 in-process creds, #55 HTTP header creds, #56 MCP creds, CredentialFile
# ═══════════════════════════════════════════════════════════════════════


# -- Native tool with ToolContext injection + file-based credentials --
@tool(credentials=[CredentialFile(env_var="RESEARCH_API_KEY")])
def research_database(query: str, ctx: ToolContext = None) -> dict:
    """Search internal research database."""
    session = ctx.session_id if ctx else "unknown"
    workflow = ctx.execution_id if ctx else "unknown"
    return {
        "query": query,
        "session_id": session,
        "execution_id": workflow,
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

# -- API tool (auto-discovered from OpenAPI spec) --
petstore_api = api_tool(
    url="https://petstore3.swagger.io/api/v3/openapi.json",
    name="petstore",
    max_tools=5,
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

# -- scatter_gather (#76): dispatches parallel research workers --
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
    tools=[analyze_trends, petstore_api],
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
    """Callback handler that logs all lifecycle events."""

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

# Sequential pipeline via >> operator (#39)
writing_pipeline = draft_writer >> editor


# ═══════════════════════════════════════════════════════════════════════
# STAGE 4: Review & Safety
# Features: #22 RegexGuardrail, #23 LLMGuardrail, #24 custom @guardrail,
#   #25 external guardrail, #20 tool guardrail,
#   #26 RETRY, #27 RAISE, #28 FIX, #29 HUMAN
# ═══════════════════════════════════════════════════════════════════════

# -- Regex guardrail (server-side INLINE, on_fail=RETRY) --
pii_guardrail = RegexGuardrail(
    name="pii_blocker",
    patterns=[
        r"\b\d{3}-\d{2}-\d{4}\b",
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    ],
    mode="block",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
    message="PII detected. Redact all personal information.",
)

# -- LLM guardrail (server-side judge, on_fail=FIX) --
bias_guardrail = LLMGuardrail(
    name="bias_detector",
    model="openai/gpt-4o-mini",
    policy="Check for biased language or stereotypes. If found, provide corrected version.",
    position=Position.OUTPUT,
    on_fail=OnFail.FIX,
    max_tokens=10000,
)


# -- Custom guardrail (SDK worker, on_fail=HUMAN) --
@guardrail
def fact_validator(content: str) -> GuardrailResult:
    """Validate factual claims in the article."""
    red_flags = ["the best", "the worst", "always", "never", "guaranteed"]
    found = [rf for rf in red_flags if rf.lower() in content.lower()]
    if found:
        return GuardrailResult(passed=False, message=f"Unverifiable claims: {found}")
    return GuardrailResult(passed=True)


# -- External guardrail (remote worker, on_fail=RAISE) --
compliance_guardrail = Guardrail(
    name="compliance_check",
    external=True,
    position=Position.OUTPUT,
    on_fail=OnFail.RAISE,
)


# -- Tool guardrail (input validation on safe_search) --
@guardrail
def sql_injection_guard(content: str) -> GuardrailResult:
    """Block SQL injection in search tool inputs."""
    if contains_sql_injection(content):
        return GuardrailResult(passed=False, message="SQL injection detected.")
    return GuardrailResult(passed=True)


@tool(
    guardrails=[
        Guardrail(sql_injection_guard, position=Position.INPUT, on_fail=OnFail.RAISE)
    ]
)
def safe_search(query: str) -> dict:
    """Search with SQL injection protection."""
    return {"query": query, "results": ["result1", "result2"]}


review_agent = Agent(
    name="safety_reviewer",
    model=settings.llm_model,
    instructions="Review the article for safety and compliance.",
    tools=[safe_search],
    guardrails=[
        pii_guardrail,  # #26 on_fail=RETRY
        bias_guardrail,  # #28 on_fail=FIX
        Guardrail(fact_validator, position=Position.OUTPUT, on_fail=OnFail.HUMAN),  # #29
        compliance_guardrail,  # #27 on_fail=RAISE (external)
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

# Round-robin debate on translation tone (#6)
tone_debate = Agent(
    name="tone_debate",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
)

# Swarm with automatic handoff (#8, #35)
translation_swarm = Agent(
    name="translation_swarm",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="Spanish", target="spanish_translator"),
        OnTextMention(text="French", target="french_translator"),
        OnTextMention(text="German", target="german_translator"),
    ],
    allowed_transitions={  # #37
        "spanish_translator": ["french_translator", "german_translator"],
        "french_translator": ["spanish_translator", "german_translator"],
        "german_translator": ["spanish_translator", "french_translator"],
    },
)

# Random strategy for brainstorming (#7)
title_brainstorm = Agent(
    name="title_brainstorm",
    agents=[spanish_translator, french_translator, german_translator],
    strategy=Strategy.RANDOM,
    max_turns=3,
)

# Manual selection (#9)
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

# External agent — runs as remote SUB_WORKFLOW (#88)
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
        OnToolResult(target="external_publisher", tool_name="format_check"),  # #34
        OnCondition(
            target="external_publisher", condition=should_handoff_to_publisher
        ),  # #36
    ],
    termination=(  # #33 composable
        TextMentionTermination("PUBLISHED")
        | (MaxMessageTermination(50) & TokenUsageTermination(max_total_tokens=100000))
    ),
    gate=TextGate(text="APPROVED"),  # #71
)


# ═══════════════════════════════════════════════════════════════════════
# STAGE 8: Analytics & Reporting
# Features: #13 agent_tool, #15 media tools, #16 RAG tools,
#   #58-61 code executors, #64 token tracking, #66 GPTAssistantAgent,
#   #67 thinking, #68 include_contents, #69 planner, #70 required_tools,
#   #72 CLI config
# ═══════════════════════════════════════════════════════════════════════

# -- Code executors (#58-61) --
local_executor = LocalCodeExecutor(language="python", timeout=10)
docker_executor = DockerCodeExecutor(image="python:3.12-slim", timeout=15)
jupyter_executor = JupyterCodeExecutor(timeout=30)
serverless_executor = ServerlessCodeExecutor(
    endpoint="https://api.example.com/functions/analytics",
    timeout=30,
)

# -- Media tools (#15) --
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

# -- RAG tools (#16) --
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

# -- agent_tool: wrap a sub-agent as a callable tool (#13) --
research_subtool = agent_tool(
    Agent(
        name="quick_researcher",
        model=settings.llm_model,
        instructions="Do a quick research lookup on the given topic.",
    ),
    name="quick_research",
    description="Quick research lookup as a tool.",
)

# -- GPTAssistantAgent (#66) --
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
        article_thumbnail,
        audio_summary,
        video_highlight,
        article_pdf,
        article_indexer,
        article_search,
        research_subtool,
    ],
    agents=[gpt_assistant],
    strategy=Strategy.HANDOFF,
    thinking_budget_tokens=2048,  # #67
    include_contents="default",  # #68
    output_type=ArticleReport,  # #30
    required_tools=["index_article"],  # #70
    code_execution_config=CodeExecutionConfig(  # #58
        enabled=True,
        allowed_languages=["python", "shell"],
        allowed_commands=["python3", "pip"],
        timeout=30,
    ),
    cli_config=CliConfig(  # #72
        enabled=True,
        allowed_commands=["git", "gh"],
        timeout=30,
    ),
    metadata={"stage": "analytics", "version": "1.0"},
    planner=True,  # #69
)


# ═══════════════════════════════════════════════════════════════════════
# FULL PIPELINE (hierarchical composition of all stages)
# ═══════════════════════════════════════════════════════════════════════

full_pipeline = Agent(
    name="content_publishing_platform",
    model=settings.llm_model,
    instructions=(
        "You are a content publishing platform. Process article requests "
        "through all pipeline stages: classification, research, writing, "
        "review, editorial approval, translation, publishing, and analytics."
    ),
    agents=[
        intake_router,  # Stage 1
        research_team,  # Stage 2
        writing_pipeline,  # Stage 3 (sequential via >>)
        review_agent,  # Stage 4
        editorial_agent,  # Stage 5
        translation_swarm,  # Stage 6
        publishing_pipeline,  # Stage 7
        analytics_agent,  # Stage 8
    ],
    strategy=Strategy.SEQUENTIAL,
    termination=(
        TextMentionTermination("PIPELINE_COMPLETE") | MaxMessageTermination(200)
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
        result = runtime.run(full_pipeline, PROMPT)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(full_pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.kitchen_sink
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(full_pipeline)
        #
        # Additional execution-mode alternatives:
        # runtime.plan(full_pipeline)
        # agent_stream = runtime.stream(full_pipeline, PROMPT)
        # handle = runtime.start(full_pipeline, PROMPT)

        # ── Feature #64: Token tracking ──────────────────────────
        if result.token_usage:
            print(f"\nTotal tokens: {result.token_usage.total_tokens}")
            print(f"  Prompt: {result.token_usage.prompt_tokens}")
            print(f"  Completion: {result.token_usage.completion_tokens}")

        # ── Callback log ─────────────────────────────────────────
        print(f"\nCallback events: {len(callback_log.events)}")
        for ev in callback_log.events[:5]:
            print(f"  {ev['type']}: {ev}")

        # ── Feature #46/47: top-level convenience APIs ───────────
        print("\n=== Top-Level Convenience API ===")
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
