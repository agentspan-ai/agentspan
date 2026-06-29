# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Suite 23: Feature-parity gaps with the Java reference SDK.

Two independent features:

  Gap A — Event-targeted HITL for sub-executions.
    Under HANDOFF / SEQUENTIAL / PARALLEL strategies the pending HUMAN task
    lives in a SUB-execution, so a no-arg ``approve()`` POSTs to the wrong
    (top-level) execution.  The streamed ``WAITING`` event carries the
    sub-execution's ``execution_id``; ``approve(event=...)`` /
    ``reject(event=...)`` / ``respond(..., event=...)`` must target it.

    These tests are deterministic: they assert the streamed event exposes
    ``execution_id`` and that the respond call targets the event's id (by
    spying on the runtime's HTTP-respond method and asserting the targeted
    execution id + request body), and that the respond URL matches the
    server wire format ``/api/agent/{id}/respond``.  No LLM output is parsed.

  Gap B — ``Agent.from_instance`` class resolution.
    Resolve all ``@agent``-decorated METHODS on an object instance into
    Agent objects, attaching ``@tool`` / ``@guardrail`` methods on the same
    object, wiring sub-agents by name, and supporting method bodies that
    return None (attrs only), a str (dynamic instructions), or an Agent.

    Validated structurally (in-process) plus a ``plan()`` round-trip against
    the live server.  No LLM output is parsed.

No mocks for Gap B structure.  Gap A spies on the runtime's own respond
plumbing (not an LLM) to assert deterministic HTTP targeting.
"""

import pytest

from conductor.ai.agents import (
    Agent,
    EventType,
    GuardrailResult,
    Strategy,
    agent,
    guardrail,
    tool,
)
from conductor.ai.agents.result import AgentEvent, AgentHandle, AgentStream

pytestmark = [pytest.mark.e2e]


# ===================================================================
# Gap A — Event-targeted HITL
# ===================================================================


class _RespondSpy:
    """Captures (execution_id, body) for each runtime.respond call."""

    def __init__(self):
        self.calls = []

    def __call__(self, execution_id, output):
        self.calls.append((execution_id, output))


class TestEventTargetedHITL:
    """approve/reject/respond can target a streamed event's sub-execution."""

    TOP_LEVEL = "root-exec-111"
    SUB_EXEC = "sub-exec-999"

    def _stream(self, spy):
        """Build an AgentStream over a no-op iterator with a spied runtime."""

        class _FakeRuntime:
            def respond(self, execution_id, output):
                spy(execution_id, output)

        handle = AgentHandle(execution_id=self.TOP_LEVEL, runtime=_FakeRuntime())
        return AgentStream(handle=handle, event_iterator=iter(()))

    def _waiting_event(self):
        return AgentEvent(
            type=EventType.WAITING,
            content="Waiting for human input",
            execution_id=self.SUB_EXEC,
        )

    # ── Event exposes execution_id ─────────────────────────────────────

    def test_waiting_event_exposes_execution_id(self):
        """A streamed WAITING event carries its (sub-)execution id."""
        ev = self._waiting_event()
        assert ev.execution_id == self.SUB_EXEC, (
            "WAITING event must expose the sub-execution's execution_id so "
            "HITL responses can target it."
        )

    def test_sse_event_inherits_server_execution_id(self):
        """The SSE parser populates execution_id from the server's executionId.

        This is the mechanism that lets a WAITING event from a sub-execution
        carry the sub-execution id (not the top-level stream id).
        """
        from conductor.ai.agents.runtime.runtime import AgentRuntime as RT

        sse_event = {
            "event": "waiting",
            "id": "1",
            "data": {"type": "waiting", "executionId": self.SUB_EXEC},
        }
        # Stream was opened on the top-level id, but the event payload names
        # the sub-execution — the parser must prefer the payload's id.
        ev = RT._sse_to_agent_event(sse_event, self.TOP_LEVEL)
        assert ev is not None
        assert ev.execution_id == self.SUB_EXEC, (
            "SSE event must inherit the server-reported executionId so the "
            f"sub-execution is targetable. Got {ev.execution_id!r}."
        )

    def test_sse_event_falls_back_to_stream_id(self):
        """When the server omits executionId, fall back to the stream id."""
        from conductor.ai.agents.runtime.runtime import AgentRuntime as RT

        sse_event = {"event": "thinking", "id": "1", "data": {"type": "thinking"}}
        ev = RT._sse_to_agent_event(sse_event, self.TOP_LEVEL)
        assert ev.execution_id == self.TOP_LEVEL

    # ── approve(event=...) targets the sub-execution ──────────────────

    def test_approve_event_targets_sub_execution(self):
        """approve(event=WAITING) POSTs {"approved": true} to the event's id."""
        spy = _RespondSpy()
        stream = self._stream(spy)
        stream.approve(event=self._waiting_event())

        assert len(spy.calls) == 1
        exec_id, body = spy.calls[0]
        assert exec_id == self.SUB_EXEC, (
            f"approve(event) must target the event's sub-execution "
            f"{self.SUB_EXEC!r}, not {exec_id!r}."
        )
        assert body == {"approved": True}

    def test_approve_no_event_targets_top_level(self):
        """Counterfactual: no-arg approve() still targets the top-level."""
        spy = _RespondSpy()
        stream = self._stream(spy)
        stream.approve()

        exec_id, body = spy.calls[0]
        assert exec_id == self.TOP_LEVEL, (
            f"No-arg approve() must keep targeting the top-level execution "
            f"{self.TOP_LEVEL!r}, not {exec_id!r}."
        )
        assert body == {"approved": True}

    def test_reject_event_targets_sub_execution(self):
        """reject(reason, event=...) targets the event's id with reason body."""
        spy = _RespondSpy()
        stream = self._stream(spy)
        stream.reject("not allowed", event=self._waiting_event())

        exec_id, body = spy.calls[0]
        assert exec_id == self.SUB_EXEC
        assert body == {"approved": False, "reason": "not allowed"}

    def test_respond_and_send_event_targets_sub_execution(self):
        """respond(data, event=...) and send(msg, event=...) target the event."""
        spy = _RespondSpy()
        stream = self._stream(spy)
        stream.respond({"selected": "writer"}, event=self._waiting_event())
        stream.send("hi there", event=self._waiting_event())

        assert spy.calls[0] == (self.SUB_EXEC, {"selected": "writer"})
        assert spy.calls[1] == (self.SUB_EXEC, {"message": "hi there"})

    def test_handle_approve_event_targeting(self):
        """The same event-targeting works directly on AgentHandle."""
        spy = _RespondSpy()

        class _FakeRuntime:
            def respond(self, execution_id, output):
                spy(execution_id, output)

        handle = AgentHandle(execution_id=self.TOP_LEVEL, runtime=_FakeRuntime())
        handle.approve(event=self._waiting_event())
        assert spy.calls[0] == (self.SUB_EXEC, {"approved": True})

    def test_event_without_execution_id_raises(self):
        """Targeting an event with no execution_id raises rather than silently
        hitting the wrong endpoint."""
        spy = _RespondSpy()
        stream = self._stream(spy)
        bad_event = AgentEvent(type=EventType.WAITING, execution_id="")
        with pytest.raises(ValueError, match="execution_id"):
            stream.approve(event=bad_event)
        assert spy.calls == [], "No respond call should be made for a bad event."

    # ── Wire format against the live server ───────────────────────────

    def test_respond_url_matches_server_wire_format(self, runtime):
        """The respond URL is /api/agent/{executionId}/respond (Java parity)."""
        url = runtime._agent_api_url(f"/{self.SUB_EXEC}/respond")
        assert url.endswith(f"/agent/{self.SUB_EXEC}/respond"), (
            f"respond must POST to /api/agent/{{id}}/respond; got {url!r}."
        )
        # The configured server base already includes /api.
        assert "/api/agent/" in url, f"URL missing /api/agent prefix: {url!r}"


# ===================================================================
# Gap B — Agent.from_instance
# ===================================================================


class _Team:
    """A collaborator object grouping agents, a tool, and a guardrail."""

    def __init__(self, db_name, model):
        self.db_name = db_name
        self._model = model

    @tool
    def lookup(self, key: str) -> str:
        """Look up a value by key in the team's database."""
        return f"LOOKUP:{self.db_name}:{key}"

    @guardrail
    def no_secrets(self, content: str) -> GuardrailResult:
        """Block content that mentions secrets."""
        return GuardrailResult(passed="secret" not in content)

    # Returns None — attributes-only agent (docstring instructions).
    @agent(model="anthropic/claude-sonnet-4-6")
    def researcher(self):
        """You research topics thoroughly."""

    # Returns a str — dynamic instructions referencing instance state.
    @agent(model="anthropic/claude-sonnet-4-6", agents=["researcher"], strategy=Strategy.HANDOFF)
    def manager(self):
        return f"You manage the researcher. DB={self.db_name}"


class _Factory:
    """Demonstrates a @agent method that returns a full Agent (factory)."""

    @agent
    def custom(self):
        return Agent(
            name="custom_built",
            model="anthropic/claude-sonnet-4-6",
            instructions="Built by a factory method.",
        )


def _agent_def_from_plan(plan_result):
    """Pull metadata.agentDef out of a plan() result."""
    wf = plan_result["workflowDef"]
    return wf["metadata"]["agentDef"]


class TestFromInstance:
    """Resolve @agent methods on an instance into Agent objects."""

    MODEL = "anthropic/claude-sonnet-4-6"

    # ── Discovery ──────────────────────────────────────────────────────

    def test_discovers_all_agent_methods(self):
        """from_instance(obj) returns one Agent per @agent method."""
        team = _Team("mydb", self.MODEL)
        agents = Agent.from_instance(team)
        names = sorted(a.name for a in agents)
        assert names == ["manager", "researcher"], (
            f"Expected both @agent methods discovered; got {names}."
        )
        assert all(isinstance(a, Agent) for a in agents)

    def test_resolve_single_by_name(self):
        """from_instance(obj, name) returns the matching single Agent."""
        team = _Team("mydb", self.MODEL)
        mgr = Agent.from_instance(team, "manager")
        assert isinstance(mgr, Agent)
        assert mgr.name == "manager"

    def test_unknown_name_raises(self):
        team = _Team("mydb", self.MODEL)
        with pytest.raises(ValueError, match="nonexistent"):
            Agent.from_instance(team, "nonexistent")

    def test_no_agent_methods_raises(self):
        class Empty:
            @tool
            def t(self, x: str) -> str:
                """t"""
                return x

        with pytest.raises(ValueError, match="No @agent"):
            Agent.from_instance(Empty())

    # ── Tools & guardrails attached by default ─────────────────────────

    def test_attaches_tools_and_guardrails_by_default(self):
        """All @tool / @guardrail methods attach to each agent by default."""
        team = _Team("mydb", self.MODEL)
        mgr = Agent.from_instance(team, "manager")
        tool_names = [getattr(t, "name", "") for t in mgr.tools]
        assert "lookup" in tool_names, (
            f"@tool method 'lookup' should attach by default; got {tool_names}."
        )
        gr_names = [g.name for g in mgr.guardrails]
        assert "no_secrets" in gr_names, (
            f"@guardrail method 'no_secrets' should attach by default; got {gr_names}."
        )

    def test_bound_tool_executes_with_self(self):
        """The attached tool is bound to the instance (counterfactual).

        Two instances with different state must produce different tool
        outputs — proving the tool callable carries ``self`` rather than
        being an unbound class function.
        """
        team_a = _Team("alpha", self.MODEL)
        team_b = _Team("beta", self.MODEL)
        mgr_a = Agent.from_instance(team_a, "manager")
        mgr_b = Agent.from_instance(team_b, "manager")

        tool_a = next(t for t in mgr_a.tools if getattr(t, "name", "") == "lookup")
        tool_b = next(t for t in mgr_b.tools if getattr(t, "name", "") == "lookup")

        out_a = tool_a.func(key="k")
        out_b = tool_b.func(key="k")
        assert out_a == "LOOKUP:alpha:k", out_a
        assert out_b == "LOOKUP:beta:k", out_b
        assert out_a != out_b, (
            "Bound tools must reflect their instance's state; identical output "
            "would mean self was not bound."
        )

    # ── Sub-agent wiring by name ───────────────────────────────────────

    def test_wires_subagents_by_name(self):
        """agents=['researcher'] resolves to the sibling @agent method."""
        team = _Team("mydb", self.MODEL)
        mgr = Agent.from_instance(team, "manager")
        sub_names = [s.name for s in mgr.agents]
        assert sub_names == ["researcher"], (
            f"manager should wire researcher as a sub-agent; got {sub_names}."
        )
        assert mgr.strategy == Strategy.HANDOFF
        assert isinstance(mgr.agents[0], Agent)

    def test_subagent_inherits_parent_model(self):
        """A sub-agent with no model inherits the parent's model."""

        class T:
            @agent  # no model — inherits
            def child(self):
                """Child."""

            @agent(model="anthropic/claude-sonnet-4-6", agents=["child"])
            def parent(self):
                """Parent."""

        parent = Agent.from_instance(T(), "parent")
        assert parent.agents[0].model == "anthropic/claude-sonnet-4-6", (
            "Sub-agent must inherit the parent's model when it declares none."
        )

    def test_cyclic_subagents_raise(self):
        class Cyclic:
            @agent(model="anthropic/claude-sonnet-4-6", agents=["b"])
            def a(self):
                """A."""

            @agent(model="anthropic/claude-sonnet-4-6", agents=["a"])
            def b(self):
                """B."""

        with pytest.raises(ValueError, match="[Cc]yclic"):
            Agent.from_instance(Cyclic(), "a")

    # ── Method body return types ───────────────────────────────────────

    def test_none_body_uses_docstring_instructions(self):
        """A None-returning @agent method uses the docstring as instructions."""
        team = _Team("mydb", self.MODEL)
        researcher = Agent.from_instance(team, "researcher")
        assert researcher.instructions == "You research topics thoroughly."

    def test_str_body_is_dynamic_instructions(self):
        """A str-returning @agent method provides dynamic instructions."""
        team = _Team("mydb", self.MODEL)
        mgr = Agent.from_instance(team, "manager")
        assert mgr.instructions == "You manage the researcher. DB=mydb", (
            "str return must override docstring with dynamic instructions."
        )

    def test_agent_body_is_factory(self):
        """An Agent-returning @agent method is used as-is (factory)."""
        built = Agent.from_instance(_Factory(), "custom")
        assert built.name == "custom_built", (
            "A method returning an Agent must be used verbatim as the definition."
        )
        assert built.instructions == "Built by a factory method."

    # ── Server round-trip via plan() ───────────────────────────────────

    def test_plan_serializes_from_instance_agent(self, runtime):
        """A from_instance agent compiles via plan() with correct wire shape."""
        team = _Team("mydb", self.MODEL)
        mgr = Agent.from_instance(team, "manager")
        result = runtime.plan(mgr)

        assert "workflowDef" in result, f"plan() missing workflowDef; keys={list(result.keys())}"
        ad = _agent_def_from_plan(result)
        assert ad["name"] == "manager"
        assert ad.get("strategy") == "handoff"
        sub_names = [a["name"] for a in ad.get("agents", [])]
        assert "researcher" in sub_names, (
            f"researcher sub-agent missing from compiled agentDef; got {sub_names}."
        )
