"""Suite 11: LangGraph Cross-SDK Parity Tests — serialization, schema, and compilation.

Tests that LangGraph graphs serialize identically in Python and TypeScript:
  - Framework detection
  - Full extraction: create_agent → model + tools in rawConfig
  - Graph-structure: StateGraph → nodes + edges in rawConfig._graph
  - Tool schema: valid JSON Schema (not raw Pydantic)
  - Conditional routing: conditional_edges in rawConfig
  - Messages state: _input_is_messages flag
  - Checkpointer: forces passthrough path
  - Compile via server: /agent/compile returns 200
  - Runtime execution: agent with tool produces correct output

All validation is algorithmic — no LLM output parsing.
"""

import math
import os
from typing import Dict, List, TypedDict

import pytest
import requests

lg = pytest.importorskip("langgraph")

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_core.tools import tool as lc_tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from agentspan.agents.frameworks.langgraph import serialize_langgraph  # noqa: E402
from agentspan.agents.frameworks.serializer import detect_framework  # noqa: E402

pytestmark = [pytest.mark.e2e]

TIMEOUT = 120
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE_URL = SERVER_URL.rstrip("/").replace("/api", "")


# ═══════════════════════════════════════════════════════════════════════════
# Helper: server availability check
# ═══════════════════════════════════════════════════════════════════════════


def _server_available() -> bool:
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        return resp.json().get("healthy") is True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Tool definitions (reusable across tests)
# ═══════════════════════════════════════════════════════════════════════════


@lc_tool
def calculate(expression: str) -> str:
    """Evaluate a safe mathematical expression and return the result.

    Supports +, -, *, /, **, sqrt, and basic math operations.
    """
    try:
        result = eval(
            expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi}
        )
        return f"{result}"
    except Exception as e:
        return f"Error: {e}"


@lc_tool
def count_words(text: str) -> str:
    """Count the number of words in the provided text."""
    words = text.split()
    return f"The text contains {len(words)} word(s)."


@lc_tool
def multiply(a: int, b: int) -> str:
    """Multiply two numbers and return the product."""
    return str(a * b)


# ═══════════════════════════════════════════════════════════════════════════
# Module-level LLM instance — needed for StateGraph node functions that
# reference `llm` via closure. The LLM detection in the serializer finds
# module-level variables via func.__globals__ but not closure variables.
_module_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.timeout(600)
class TestSuite11LangGraph:
    """LangGraph: serialization parity, schema validation, compilation."""

    # ── 1. Framework detection ────────────────────────────────────────

    def test_framework_detection(self):
        """create_react_agent graph -> detect_framework returns 'langgraph'."""
        from langchain.agents import create_agent

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(llm, tools=[], name="detect_test")

        framework = detect_framework(graph)
        assert framework == "langgraph", (
            f"[Detection] Expected 'langgraph', got '{framework}'. "
            f"type={type(graph).__name__}, module={type(graph).__module__}"
        )

    # ── 2. Hello world full extraction ────────────────────────────────

    def test_hello_world_full_extraction(self):
        """create_agent(llm, tools=[]) serializes to full extraction path."""
        from langchain.agents import create_agent

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(llm, tools=[], name="hello_world_test")

        raw_config, workers = serialize_langgraph(graph)

        # Full extraction: must have 'model' key
        assert "model" in raw_config, (
            f"[HelloWorld] 'model' missing from rawConfig. "
            f"Keys: {list(raw_config.keys())}"
        )

        # Must have 'tools' key (empty list)
        assert "tools" in raw_config, (
            f"[HelloWorld] 'tools' missing from rawConfig. "
            f"Keys: {list(raw_config.keys())}"
        )
        assert isinstance(raw_config["tools"], list), (
            f"[HelloWorld] tools is not a list: {type(raw_config['tools'])}"
        )
        assert len(raw_config["tools"]) == 0, (
            f"[HelloWorld] Expected 0 tools, got {len(raw_config['tools'])}"
        )

        # Must NOT be graph-structure or passthrough
        assert "_graph" not in raw_config, (
            f"[HelloWorld] Unexpected '_graph' key — should be full extraction. "
            f"Keys: {list(raw_config.keys())}"
        )
        assert "_worker_name" not in raw_config, (
            f"[HelloWorld] Unexpected '_worker_name' key — should not be passthrough. "
            f"Keys: {list(raw_config.keys())}"
        )

        # No workers for a no-tool agent
        assert len(workers) == 0, (
            f"[HelloWorld] Expected 0 workers, got {len(workers)}: "
            f"{[w.name for w in workers]}"
        )

    # ── 3. React agent with tools — full extraction ──────────────────

    def test_react_tools_full_extraction(self):
        """create_agent(llm, tools=[calculate, count_words]) -> full extraction."""
        from langchain.agents import create_agent

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(
            llm, tools=[calculate, count_words], name="react_tools_test"
        )

        raw_config, workers = serialize_langgraph(graph)

        # Model present
        assert "model" in raw_config, (
            f"[React] 'model' missing. Keys: {list(raw_config.keys())}"
        )
        assert "gpt-4o-mini" in str(raw_config["model"]), (
            f"[React] Wrong model: {raw_config['model']}"
        )

        # Tools must be present
        tools = raw_config.get("tools", [])
        assert len(tools) == 2, (
            f"[React] Expected 2 tools, got {len(tools)}: "
            f"{[t.get('_worker_ref', t.get('name')) for t in tools]}"
        )

        # Each tool has _worker_ref, description, parameters
        for t in tools:
            ref = t.get("_worker_ref") or t.get("name")
            assert ref, f"[React] Tool missing _worker_ref: {t}"
            assert t.get("description"), (
                f"[React] Tool '{ref}' missing description"
            )
            params = t.get("parameters", {})
            assert params.get("type") == "object", (
                f"[React] Tool '{ref}' parameters.type != 'object'. "
                f"Got: {params}. This may indicate raw Pydantic was passed."
            )
            assert "properties" in params, (
                f"[React] Tool '{ref}' parameters.properties missing. "
                f"Keys: {list(params.keys())}"
            )

        # Tool names
        tool_names = [t.get("_worker_ref") or t.get("name") for t in tools]
        assert "calculate" in tool_names, f"[React] 'calculate' not found. Got: {tool_names}"
        assert "count_words" in tool_names, (
            f"[React] 'count_words' not found. Got: {tool_names}"
        )

        # Check properties for calculate tool
        calc_tool = next(t for t in tools if (t.get("_worker_ref") or t.get("name")) == "calculate")
        calc_params = calc_tool.get("parameters", {})
        assert "expression" in calc_params.get("properties", {}), (
            f"[React] calculate missing 'expression' property. "
            f"Props: {list(calc_params.get('properties', {}).keys())}"
        )

        # Workers: 2 (one per tool)
        assert len(workers) == 2, (
            f"[React] Expected 2 workers, got {len(workers)}: "
            f"{[w.name for w in workers]}"
        )
        worker_names = [w.name for w in workers]
        assert "calculate" in worker_names, f"[React] Worker 'calculate' missing"
        assert "count_words" in worker_names, f"[React] Worker 'count_words' missing"

    # ── 4. StateGraph — graph structure ──────────────────────────────

    def test_stategraph_graph_structure(self):
        """3-node StateGraph with llm.invoke() -> graph-structure path."""
        # Use module-level _module_llm so the serializer's LLM detection
        # can find it via func.__globals__ (closure vars are not visible).

        class State(TypedDict):
            query: str
            refined_query: str
            answer: str

        def validate_query(state: State) -> dict:
            """Ensure the query is not empty and trim whitespace."""
            query = state.get("query", "").strip()
            if not query:
                query = "What can you help me with?"
            return {"query": query, "refined_query": "", "answer": ""}

        def refine_query(state: State) -> dict:
            """Rewrite the query using the LLM."""
            response = _module_llm.invoke([
                SystemMessage(content="Rewrite the query to be more specific."),
                HumanMessage(content=state["query"]),
            ])
            return {"refined_query": response.content.strip()}

        def generate_answer(state: State) -> dict:
            """Generate an answer using the LLM."""
            response = _module_llm.invoke([
                SystemMessage(content="Answer the question concisely."),
                HumanMessage(content=state["refined_query"] or state["query"]),
            ])
            return {"answer": response.content.strip()}

        builder = StateGraph(State)
        builder.add_node("validate", validate_query)
        builder.add_node("refine", refine_query)
        builder.add_node("answer", generate_answer)

        builder.add_edge(START, "validate")
        builder.add_edge("validate", "refine")
        builder.add_edge("refine", "answer")
        builder.add_edge("answer", END)

        graph = builder.compile(name="query_pipeline")

        raw_config, workers = serialize_langgraph(graph)

        # Must be graph-structure path: has _graph key
        assert "_graph" in raw_config, (
            f"[StateGraph] '_graph' missing from rawConfig. "
            f"Keys: {list(raw_config.keys())}"
        )

        graph_data = raw_config["_graph"]

        # 3 nodes
        nodes = graph_data.get("nodes", [])
        assert len(nodes) == 3, (
            f"[StateGraph] Expected 3 nodes, got {len(nodes)}: "
            f"{[n.get('name') for n in nodes]}"
        )
        node_names = [n["name"] for n in nodes]
        assert "validate" in node_names, f"[StateGraph] 'validate' missing. Nodes: {node_names}"
        assert "refine" in node_names, f"[StateGraph] 'refine' missing. Nodes: {node_names}"
        assert "answer" in node_names, f"[StateGraph] 'answer' missing. Nodes: {node_names}"

        # LLM node detection: refine and answer should have _llm_node: True
        for name in ("refine", "answer"):
            node = next(n for n in nodes if n["name"] == name)
            assert node.get("_llm_node") is True, (
                f"[StateGraph] Node '{name}' missing _llm_node=True. Got: {node}"
            )

        # Edges: START->validate, validate->refine, refine->answer, answer->END = 4
        edges = graph_data.get("edges", [])
        assert len(edges) == 4, (
            f"[StateGraph] Expected 4 edges, got {len(edges)}: {edges}"
        )

        # input_key should be "query"
        assert graph_data.get("input_key") == "query", (
            f"[StateGraph] Expected input_key='query', got '{graph_data.get('input_key')}'"
        )

        # Workers: validate (1 regular) + refine_prep + refine_finish + answer_prep + answer_finish = 5
        assert len(workers) == 5, (
            f"[StateGraph] Expected 5 workers, got {len(workers)}: "
            f"{[w.name for w in workers]}"
        )

    # ── 5. Conditional routing — graph structure ─────────────────────

    def test_conditional_routing_graph_structure(self):
        """StateGraph with add_conditional_edges -> conditional_edges in rawConfig."""

        class RouteState(TypedDict):
            query: str
            category: str
            answer: str

        def classify(state: RouteState) -> dict:
            """Classify the query."""
            q = state.get("query", "").lower()
            if "math" in q:
                return {"category": "math"}
            return {"category": "general"}

        def route_query(state: RouteState) -> str:
            """Route based on category."""
            return state.get("category", "general")

        def handle_math(state: RouteState) -> dict:
            """Handle math queries."""
            return {"answer": "math_answer"}

        def handle_general(state: RouteState) -> dict:
            """Handle general queries."""
            return {"answer": "general_answer"}

        builder = StateGraph(RouteState)
        builder.add_node("classify", classify)
        builder.add_node("handle_math", handle_math)
        builder.add_node("handle_general", handle_general)

        builder.add_edge(START, "classify")
        builder.add_conditional_edges(
            "classify",
            route_query,
            {"math": "handle_math", "general": "handle_general"},
        )
        builder.add_edge("handle_math", END)
        builder.add_edge("handle_general", END)

        graph = builder.compile(name="conditional_test")

        raw_config, workers = serialize_langgraph(graph)

        # Must be graph-structure path
        assert "_graph" in raw_config, (
            f"[Conditional] '_graph' missing. Keys: {list(raw_config.keys())}"
        )

        graph_data = raw_config["_graph"]

        # conditional_edges must be non-empty
        cond_edges = graph_data.get("conditional_edges", [])
        assert len(cond_edges) > 0, (
            f"[Conditional] conditional_edges is empty. Graph keys: {list(graph_data.keys())}"
        )

        # First conditional edge must have _router_ref
        ce = cond_edges[0]
        assert "_router_ref" in ce, (
            f"[Conditional] conditional_edges[0] missing '_router_ref'. Got: {ce}"
        )

        # Source should be "classify"
        assert ce.get("source") == "classify", (
            f"[Conditional] Expected source='classify', got '{ce.get('source')}'"
        )

        # Targets should map to handle_math and handle_general
        targets = ce.get("targets", {})
        assert "math" in targets, f"[Conditional] 'math' not in targets: {targets}"
        assert "general" in targets, f"[Conditional] 'general' not in targets: {targets}"

    # ── 6. Messages state detection ──────────────────────────────────

    def test_messages_state_detection(self):
        """StateGraph with messages: List[dict] state -> _input_is_messages flag."""

        class MessagesState(TypedDict):
            messages: List[dict]
            output: str

        def process_messages(state: MessagesState) -> dict:
            """Process messages."""
            return {"output": "processed"}

        builder = StateGraph(MessagesState)
        builder.add_node("process", process_messages)
        builder.add_edge(START, "process")
        builder.add_edge("process", END)

        graph = builder.compile(name="messages_test")

        raw_config, _workers = serialize_langgraph(graph)

        # Must be graph-structure path
        assert "_graph" in raw_config, (
            f"[Messages] '_graph' missing. Keys: {list(raw_config.keys())}"
        )

        graph_data = raw_config["_graph"]

        # _input_is_messages must be True
        assert graph_data.get("_input_is_messages") is True, (
            f"[Messages] '_input_is_messages' should be True. "
            f"Graph data keys: {list(graph_data.keys())}. "
            f"Got: {graph_data.get('_input_is_messages')}"
        )

    # ── 7. Checkpointer forces passthrough ───────────────────────────

    def test_checkpointer_forces_passthrough(self):
        """Graph with MemorySaver checkpointer -> passthrough path."""
        from langgraph.checkpoint.memory import MemorySaver

        class SimpleState(TypedDict):
            query: str
            answer: str

        def echo(state: SimpleState) -> dict:
            """Echo the query."""
            return {"answer": state.get("query", "")}

        builder = StateGraph(SimpleState)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)

        graph = builder.compile(name="checkpointer_test", checkpointer=MemorySaver())

        raw_config, workers = serialize_langgraph(graph)

        # Must be passthrough: has _worker_name
        assert "_worker_name" in raw_config, (
            f"[Checkpointer] '_worker_name' missing — should be passthrough. "
            f"Keys: {list(raw_config.keys())}"
        )

        # Must NOT have _graph (not graph-structure)
        assert "_graph" not in raw_config, (
            f"[Checkpointer] Unexpected '_graph' — checkpointer should force passthrough. "
            f"Keys: {list(raw_config.keys())}"
        )

        # Exactly 1 worker
        assert len(workers) == 1, (
            f"[Checkpointer] Expected 1 passthrough worker, got {len(workers)}: "
            f"{[w.name for w in workers]}"
        )

    # ── 8. Tool schema is valid JSON Schema ──────────────────────────

    def test_tool_schema_is_json_schema(self):
        """React agent tool parameters must be valid JSON Schema."""
        from langchain.agents import create_agent

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(
            llm, tools=[calculate, multiply], name="schema_test"
        )

        raw_config, _workers = serialize_langgraph(graph)

        tools = raw_config.get("tools", [])
        assert len(tools) >= 2, f"[Schema] Expected >=2 tools, got {len(tools)}"

        for t in tools:
            ref = t.get("_worker_ref") or t.get("name")
            params = t.get("parameters", {})

            # Must be valid JSON Schema
            assert params.get("type") == "object", (
                f"[Schema] Tool '{ref}' parameters.type != 'object'. "
                f"Got keys: {list(params.keys())}. "
                f"This indicates raw Pydantic/Zod was passed instead of JSON Schema."
            )
            assert "properties" in params, (
                f"[Schema] Tool '{ref}' parameters.properties missing. "
                f"Keys: {list(params.keys())}"
            )

            # Must NOT have _def (raw Pydantic marker)
            assert "_def" not in params, (
                f"[Schema] Tool '{ref}' has '_def' key — raw Pydantic, not JSON Schema. "
                f"Keys: {list(params.keys())}"
            )

        # Check specific tool: multiply should have 'a' and 'b' properties
        mult = next(
            t for t in tools
            if (t.get("_worker_ref") or t.get("name")) == "multiply"
        )
        mult_params = mult.get("parameters", {})
        props = mult_params.get("properties", {})
        assert "a" in props, f"[Schema] multiply missing property 'a'. Props: {list(props.keys())}"
        assert "b" in props, f"[Schema] multiply missing property 'b'. Props: {list(props.keys())}"

        # Check required
        required = mult_params.get("required", [])
        assert "a" in required, f"[Schema] multiply 'a' not in required: {required}"
        assert "b" in required, f"[Schema] multiply 'b' not in required: {required}"

    # ── 9. Compile via server ────────────────────────────────────────

    def test_compile_hello_world_via_server(self):
        """Send hello_world rawConfig to /agent/compile, expect 200."""
        if not _server_available():
            pytest.skip("Server not available")

        from langchain.agents import create_agent

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(llm, tools=[], name="compile_hello_world")

        raw_config, _workers = serialize_langgraph(graph)

        resp = requests.post(
            f"{BASE_URL}/api/agent/compile",
            json={"framework": "langgraph", "rawConfig": raw_config},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"[Compile hello_world] Expected 200, got {resp.status_code}. "
            f"Body: {resp.text[:500]}"
        )

    def test_compile_react_tools_via_server(self):
        """Send react_with_tools rawConfig to /agent/compile, expect 200."""
        if not _server_available():
            pytest.skip("Server not available")

        from langchain.agents import create_agent

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        graph = create_agent(
            llm, tools=[calculate, count_words], name="compile_react_tools"
        )

        raw_config, _workers = serialize_langgraph(graph)

        resp = requests.post(
            f"{BASE_URL}/api/agent/compile",
            json={"framework": "langgraph", "rawConfig": raw_config},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"[Compile react_tools] Expected 200, got {resp.status_code}. "
            f"Body: {resp.text[:500]}"
        )

    def test_compile_stategraph_via_server(self):
        """Send stategraph rawConfig to /agent/compile, expect 200."""
        if not _server_available():
            pytest.skip("Server not available")

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        class State(TypedDict):
            query: str
            answer: str

        def validate_q(state: State) -> dict:
            return {"query": state.get("query", "").strip() or "default"}

        def answer_q(state: State) -> dict:
            response = llm.invoke([
                SystemMessage(content="Answer concisely."),
                HumanMessage(content=state["query"]),
            ])
            return {"answer": response.content.strip()}

        builder = StateGraph(State)
        builder.add_node("validate", validate_q)
        builder.add_node("answer", answer_q)
        builder.add_edge(START, "validate")
        builder.add_edge("validate", "answer")
        builder.add_edge("answer", END)

        graph = builder.compile(name="compile_stategraph")

        raw_config, _workers = serialize_langgraph(graph)

        resp = requests.post(
            f"{BASE_URL}/api/agent/compile",
            json={"framework": "langgraph", "rawConfig": raw_config},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert resp.status_code == 200, (
            f"[Compile stategraph] Expected 200, got {resp.status_code}. "
            f"Body: {resp.text[:500]}"
        )

    # ── 10. Runtime execution ────────────────────────────────────────

    def test_runtime_execution(self, runtime, model):
        """Run react agent with multiply tool -> output contains '56'."""
        if not _server_available():
            pytest.skip("Server not available")

        result = runtime.run(
            _make_react_agent_with_multiply(),
            "Multiply 7 by 8",
            timeout=TIMEOUT,
        )

        assert result.execution_id, (
            f"[Runtime] No execution_id. status={result.status}"
        )
        assert result.status == "COMPLETED", (
            f"[Runtime] Expected COMPLETED, got {result.status}. "
            f"execution_id={result.execution_id}"
        )

        # Output must contain "56" (7*8) — deterministic tool output
        output_str = str(result.output)
        assert "56" in output_str, (
            f"[Runtime] Output should contain '56' (7*8). "
            f"output={output_str[:300]}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Helper: build react agent for runtime test
# ═══════════════════════════════════════════════════════════════════════════


def _make_react_agent_with_multiply():
    """Build a react agent with multiply tool for runtime execution."""
    from langchain.agents import create_agent

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return create_agent(llm, tools=[multiply], name="e2e_lg_runtime")
