# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for ``Context`` + ``Agent.planner_context`` wiring.

Pure dataclass + serialiser tests — no LLM, no server. Validates:

* ``Context`` construction rules (exactly-one-of text/url, type checks)
* ``Context.to_dict`` wire shapes (minimal text/url, full url+headers+
  required+max_bytes)
* ``Agent(planner_context=...)`` normalisation: bare strings auto-wrap
  to ``Context(text=...)``, dicts pass through, mixed lists work
* ``Agent(planner_context=...)`` rejected for non-PLAN_EXECUTE strategies
  with a clear migration message — same shape as the
  ``planner=``/``fallback=`` named-slot guard
* ``config_serializer.serialize_agent`` emits ``plannerContext`` only when
  set, and with each entry serialised via ``Context.to_dict``
* ``plan_execute()`` factory passes ``planner_context`` through to the
  underlying ``Agent``
"""

from __future__ import annotations

import pytest

from conductor.ai.agents import Agent, Context, Strategy, plan_execute, tool
from conductor.ai.agents.config_serializer import AgentConfigSerializer


@tool
def _stub_tool(x: str) -> str:
    """Bare stub tool — satisfies Agent.tools=[...] type checks."""
    return x


def serialize_agent(agent: Agent) -> dict:
    return AgentConfigSerializer().serialize(agent)


# ── Context dataclass ────────────────────────────────────────────────


class TestContext:
    def test_text_only_construction(self) -> None:
        c = Context(text="Onboarding has 3 phases: KYC, setup, training.")
        assert c.text == "Onboarding has 3 phases: KYC, setup, training."
        assert c.url is None

    def test_url_only_construction(self) -> None:
        c = Context(url="https://docs.example.com/rules.md")
        assert c.url == "https://docs.example.com/rules.md"
        assert c.text is None
        assert c.required is True  # default
        assert c.max_bytes == 16384  # default

    def test_rejects_neither_text_nor_url(self) -> None:
        with pytest.raises(ValueError, match="exactly one of text or url"):
            Context()

    def test_rejects_both_text_and_url(self) -> None:
        with pytest.raises(ValueError, match="exactly one of text or url"):
            Context(text="x", url="https://y.example/z")

    def test_rejects_non_string_url(self) -> None:
        with pytest.raises(ValueError, match="Context.url must be a string"):
            Context(url=123)  # type: ignore[arg-type]

    def test_rejects_non_string_text(self) -> None:
        with pytest.raises(ValueError, match="Context.text must be a string"):
            Context(text=42)  # type: ignore[arg-type]

    def test_to_dict_text_only_minimal(self) -> None:
        # Text-only entries must serialise as a single-key dict — no url,
        # no headers, no required, no maxBytes. Keeps the wire payload
        # tight for the common inline-rules case.
        assert Context(text="rule one").to_dict() == {"text": "rule one"}

    def test_to_dict_url_only_minimal(self) -> None:
        # URL entry with all defaults: only the url field on the wire.
        # required and max_bytes default to their canonical values so
        # they're omitted from the payload (the server applies the same
        # defaults).
        assert Context(url="https://x.example/y").to_dict() == {
            "url": "https://x.example/y",
        }

    def test_to_dict_url_full_options(self) -> None:
        # All-options URL entry: headers, required=False, custom
        # max_bytes. The credential placeholder MUST pass through
        # verbatim — escape (${} → #{}) is the server's job.
        d = Context(
            url="https://confluence.example.com/page",
            headers={"Authorization": "Bearer ${CONFLUENCE_TOKEN}"},
            required=False,
            max_bytes=8192,
        ).to_dict()
        assert d == {
            "url": "https://confluence.example.com/page",
            "headers": {"Authorization": "Bearer ${CONFLUENCE_TOKEN}"},
            "required": False,
            "maxBytes": 8192,
        }


# ── Agent.planner_context normalisation + validation ─────────────────


def _planner() -> Agent:
    return Agent(name="planner_sub", instructions="plan it")


class TestAgentPlannerContext:
    def test_bare_strings_auto_wrap_to_context(self) -> None:
        # User convenience: ``planner_context=["rule one", "rule two"]``
        # is identical to ``planner_context=[Context(text="rule one"),
        # Context(text="rule two")]``. Avoids forcing every caller to
        # know about the Context type for the common inline case.
        a = Agent(
            name="h",
            strategy=Strategy.PLAN_EXECUTE,
            planner=_planner(),
            tools=[_stub_tool],
            planner_context=["rule one", "rule two"],
        )
        assert a.planner_context is not None
        assert len(a.planner_context) == 2
        assert all(isinstance(c, Context) for c in a.planner_context)
        assert a.planner_context[0].text == "rule one"
        assert a.planner_context[1].text == "rule two"

    def test_mixed_strings_and_context_objects(self) -> None:
        a = Agent(
            name="h",
            strategy=Strategy.PLAN_EXECUTE,
            planner=_planner(),
            tools=[_stub_tool],
            planner_context=[
                "inline rule",
                Context(url="https://x.example/y", headers={"X-Auth": "abc"}),
            ],
        )
        assert a.planner_context is not None
        assert a.planner_context[0].text == "inline rule"
        assert a.planner_context[1].url == "https://x.example/y"

    def test_dict_entries_pass_through_unchanged(self) -> None:
        # Hand-rolled dicts (matches how ``plan_source`` is typed) — the
        # serialiser uses ``hasattr(entry, 'to_dict')`` to dispatch.
        wire_dict = {"url": "https://x.example/y", "required": False}
        a = Agent(
            name="h",
            strategy=Strategy.PLAN_EXECUTE,
            planner=_planner(),
            tools=[_stub_tool],
            planner_context=[wire_dict],
        )
        assert a.planner_context == [wire_dict]

    def test_rejects_planner_context_on_non_plan_execute_strategy(self) -> None:
        # ``planner_context=`` is only meaningful under PLAN_EXECUTE
        # (it's appended to the planner's prompt). Setting it on any
        # other strategy is a silent bug — reject at construction with
        # a clear message. Matches the planner=/fallback= guard shape.
        with pytest.raises(ValueError, match="planner_context.*only valid with.*PLAN_EXECUTE"):
            Agent(
                name="h",
                strategy=Strategy.HANDOFF,
                agents=[_planner()],
                planner_context=["rule"],
            )

    def test_rejects_unknown_entry_type(self) -> None:
        with pytest.raises(ValueError, match="must be a Context, a string, or a dict"):
            Agent(
                name="h",
                strategy=Strategy.PLAN_EXECUTE,
                planner=_planner(),
                tools=[_stub_tool],
                planner_context=[42],  # type: ignore[list-item]
            )

    def test_none_planner_context_leaves_attribute_none(self) -> None:
        a = Agent(
            name="h",
            strategy=Strategy.PLAN_EXECUTE,
            planner=_planner(),
            tools=[_stub_tool],
        )
        assert a.planner_context is None


# ── Wire serialisation ───────────────────────────────────────────────


class TestConfigSerializer:
    def test_no_planner_context_omits_field(self) -> None:
        # Counterfactual: an agent without planner_context must NOT emit
        # a ``plannerContext`` field on the wire — verifies the
        # serialiser's gating before we trust the positive test below.
        a = Agent(
            name="h",
            strategy=Strategy.PLAN_EXECUTE,
            planner=_planner(),
            tools=[_stub_tool],
        )
        cfg = serialize_agent(a)
        assert "plannerContext" not in cfg

    def test_text_and_url_entries_serialise_to_plannerContext(self) -> None:
        a = Agent(
            name="h",
            strategy=Strategy.PLAN_EXECUTE,
            planner=_planner(),
            tools=[_stub_tool],
            planner_context=[
                "inline rule",
                Context(
                    url="https://confluence.example.com/onboarding",
                    headers={"Authorization": "Bearer ${CONFLUENCE_TOKEN}"},
                    required=False,
                    max_bytes=8192,
                ),
            ],
        )
        cfg = serialize_agent(a)
        assert cfg["plannerContext"] == [
            {"text": "inline rule"},
            {
                "url": "https://confluence.example.com/onboarding",
                "headers": {"Authorization": "Bearer ${CONFLUENCE_TOKEN}"},
                "required": False,
                "maxBytes": 8192,
            },
        ]


# ── plan_execute() factory ───────────────────────────────────────────


class TestPlanExecuteFactory:
    def test_factory_passes_planner_context_through(self) -> None:
        # The factory is the path most users take. It must pipe
        # ``planner_context`` to the harness Agent without losing the
        # Context-wrapping done by Agent.__init__.
        harness = plan_execute(
            name="h",
            tools=[_stub_tool],
            planner_instructions="plan it",
            planner_context=[
                "rule one",
                Context(url="https://x.example/rules.md"),
            ],
        )
        assert harness.planner_context is not None
        assert len(harness.planner_context) == 2
        assert harness.planner_context[0].text == "rule one"
        assert harness.planner_context[1].url == "https://x.example/rules.md"

    def test_factory_omits_planner_context_when_unset(self) -> None:
        # Backwards-compat: existing callers don't pass planner_context.
        harness = plan_execute(
            name="h",
            tools=[_stub_tool],
            planner_instructions="plan it",
        )
        assert harness.planner_context is None
