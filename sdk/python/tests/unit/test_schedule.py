# Copyright (c) 2026 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the schedule module.

Covers:
- Schedule dataclass validation
- payload mapping (Schedule <-> SaveScheduleRequest / WorkflowSchedule)
- wire-name prefix/unprefix
- declarative reconciliation algorithm (mocked client)
- typed error translation

No network calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from conductor.ai.agents.schedule import (
    InvalidCronExpression,
    Schedule,
    ScheduleInfo,
    ScheduleNameConflict,
    ScheduleNotFound,
    schedules,
)
from conductor.ai.agents.schedule.client import (
    ScheduleClient,
    _check_unique_names,
    _from_workflow_schedule,
    _to_save_request,
    _translate,
)
from conductor.ai.agents.schedule.schedule import _prefix, _unprefix

# ── Schedule dataclass ──────────────────────────────────────────────


class TestScheduleValidation:
    def test_minimal(self):
        s = Schedule(name="daily", cron="0 9 * * *")
        assert s.name == "daily"
        assert s.timezone == "UTC"
        assert s.input == {}
        assert s.catchup is False
        assert s.paused is False

    def test_full(self):
        s = Schedule(
            name="weekly",
            cron="0 9 * * MON",
            timezone="America/Los_Angeles",
            input={"channel": "#eng"},
            catchup=True,
            paused=True,
            start_at=1000,
            end_at=2000,
            description="weekly digest",
        )
        assert s.timezone == "America/Los_Angeles"
        assert s.input == {"channel": "#eng"}
        assert s.catchup and s.paused
        assert s.start_at == 1000 and s.end_at == 2000

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="name"):
            Schedule(name="", cron="0 9 * * *")
        with pytest.raises(ValueError, match="name"):
            Schedule(name="   ", cron="0 9 * * *")

    def test_empty_cron_rejected(self):
        with pytest.raises(ValueError, match="cron"):
            Schedule(name="x", cron="")

    def test_window_inverted_rejected(self):
        with pytest.raises(ValueError, match="start_at"):
            Schedule(name="x", cron="* * * * *", start_at=2000, end_at=1000)

    def test_window_equal_rejected(self):
        with pytest.raises(ValueError, match="start_at"):
            Schedule(name="x", cron="* * * * *", start_at=1000, end_at=1000)

    def test_one_sided_window_ok(self):
        Schedule(name="x", cron="* * * * *", start_at=1000)
        Schedule(name="x", cron="* * * * *", end_at=2000)

    def test_frozen(self):
        s = Schedule(name="x", cron="* * * * *")
        with pytest.raises(Exception):
            s.name = "y"  # frozen dataclass


# ── Wire-name prefix/unprefix ──────────────────────────────────────


class TestNamePrefix:
    def test_prefix_roundtrip(self):
        wire = _prefix("daily_digest", "9am")
        assert wire == "daily_digest-9am"
        assert _unprefix("daily_digest", wire) == "9am"

    def test_unprefix_no_match_returns_input(self):
        # If wire name doesn't carry the prefix, return as-is (defensive).
        assert _unprefix("agent", "unrelated") == "unrelated"

    def test_agent_name_with_hyphen(self):
        wire = _prefix("my-agent", "daily")
        assert wire == "my-agent-daily"
        assert _unprefix("my-agent", wire) == "daily"


# ── Payload mapping ────────────────────────────────────────────────


class TestToSaveRequest:
    def test_minimal(self):
        s = Schedule(name="daily", cron="0 9 * * *")
        req = _to_save_request(s, agent_name="digest")
        assert req.name == "digest-daily"
        assert req.cron_expression == "0 9 * * *"
        assert req.zone_id == "UTC"
        assert req.paused is False
        assert req.run_catchup_schedule_instances is False
        assert req.start_workflow_request.name == "digest"
        assert req.start_workflow_request.input == {}

    def test_full(self):
        s = Schedule(
            name="weekly",
            cron="0 9 * * MON",
            timezone="America/Los_Angeles",
            input={"channel": "#eng", "n": 42},
            catchup=True,
            paused=True,
            start_at=1000,
            end_at=2000,
            description="weekly digest",
        )
        req = _to_save_request(s, agent_name="digest")
        assert req.name == "digest-weekly"
        assert req.zone_id == "America/Los_Angeles"
        assert req.paused is True
        assert req.run_catchup_schedule_instances is True
        assert req.schedule_start_time == 1000
        assert req.schedule_end_time == 2000
        assert req.description == "weekly digest"
        assert req.start_workflow_request.input == {"channel": "#eng", "n": 42}

    def test_input_copied_not_shared(self):
        original = {"a": 1}
        s = Schedule(name="x", cron="* * * * *", input=original)
        req = _to_save_request(s, agent_name="agent")
        req.start_workflow_request.input["mutated"] = True
        assert "mutated" not in original


class TestFromWorkflowSchedule:
    def _ws(self, **overrides):
        from conductor.client.http.models.start_workflow_request import StartWorkflowRequest
        from conductor.client.http.models.workflow_schedule import WorkflowSchedule

        defaults = dict(
            name="digest-daily",
            cron_expression="0 9 * * *",
            zone_id="UTC",
            paused=False,
            run_catchup_schedule_instances=False,
            start_workflow_request=StartWorkflowRequest(name="digest", input={"channel": "#eng"}),
            schedule_start_time=None,
            schedule_end_time=None,
            description=None,
            create_time=111,
            updated_time=222,
            created_by="alice",
            updated_by="bob",
            paused_reason=None,
        )
        defaults.update(overrides)
        return WorkflowSchedule(**defaults)

    def test_basic(self):
        ws = self._ws()
        info = _from_workflow_schedule(ws, agent_name="digest")
        assert info.name == "digest-daily"
        assert info.short_name == "daily"
        assert info.agent == "digest"
        assert info.cron == "0 9 * * *"
        assert info.timezone == "UTC"
        assert info.input == {"channel": "#eng"}
        assert info.paused is False
        assert info.create_time == 111
        assert info.update_time == 222
        assert info.created_by == "alice"

    def test_paused_with_reason(self):
        ws = self._ws(paused=True, paused_reason="rate limit")
        info = _from_workflow_schedule(ws, agent_name="digest")
        assert info.paused is True
        assert info.paused_reason == "rate limit"

    def test_agent_name_derived_when_omitted(self):
        # No hint passed — short_name derived from swr.name.
        ws = self._ws()
        info = _from_workflow_schedule(ws)
        assert info.agent == "digest"
        assert info.short_name == "daily"

    def test_agent_name_hint_wins_for_unprefix(self):
        # Wire name doesn't carry the swr name's prefix — verify hint controls unprefix.
        ws = self._ws(name="other-prefix-daily")
        info = _from_workflow_schedule(ws, agent_name="other-prefix")
        assert info.short_name == "daily"


# ── Unique-name validation ─────────────────────────────────────────


class TestUniqueNames:
    def test_distinct_ok(self):
        _check_unique_names(
            [Schedule(name="a", cron="* * * * *"), Schedule(name="b", cron="* * * * *")]
        )

    def test_duplicate_raises(self):
        with pytest.raises(ScheduleNameConflict):
            _check_unique_names(
                [
                    Schedule(name="a", cron="* * * * *"),
                    Schedule(name="a", cron="0 9 * * *"),
                ]
            )


# ── Error translation ──────────────────────────────────────────────


class TestTranslate:
    def test_404_maps_to_not_found(self):
        exc = Exception("nope")
        exc.status = 404
        exc.body = "schedule not found"
        out = _translate(exc)
        assert isinstance(out, ScheduleNotFound)

    def test_400_cron_maps_to_invalid_cron(self):
        exc = Exception("bad cron")
        exc.status = 400
        exc.body = "Invalid cron expression: blah"
        out = _translate(exc)
        assert isinstance(out, InvalidCronExpression)

    def test_other_passthrough(self):
        exc = RuntimeError("something else")
        assert _translate(exc) is exc


# ── Declarative reconciliation ─────────────────────────────────────


def _mock_clients():
    """Build a ScheduleClient backed by an in-memory fake scheduler client."""
    store: dict = {}

    sc = MagicMock()

    def save(req):
        store[req.name] = req

    def delete(name):
        store.pop(name, None)

    def get_all(workflow_name=None):
        from conductor.client.http.models.workflow_schedule import WorkflowSchedule

        out = []
        for req in store.values():
            if workflow_name and req.start_workflow_request.name != workflow_name:
                continue
            out.append(
                WorkflowSchedule(
                    name=req.name,
                    cron_expression=req.cron_expression,
                    zone_id=req.zone_id,
                    paused=req.paused,
                    run_catchup_schedule_instances=req.run_catchup_schedule_instances,
                    start_workflow_request=req.start_workflow_request,
                    schedule_start_time=req.schedule_start_time,
                    schedule_end_time=req.schedule_end_time,
                    description=req.description,
                )
            )
        return out

    sc.save_schedule.side_effect = save
    sc.delete_schedule.side_effect = delete
    sc.get_all_schedules.side_effect = get_all

    wc = MagicMock()
    return ScheduleClient(sc, wc), sc, store


class TestReconcile:
    def test_none_is_noop(self):
        client, sc, store = _mock_clients()
        store["digest-existing"] = MagicMock()  # placeholder
        client.reconcile("digest", None)
        sc.save_schedule.assert_not_called()
        sc.delete_schedule.assert_not_called()

    def test_empty_list_purges(self):
        client, sc, store = _mock_clients()
        sc.save_schedule(_to_save_request(Schedule(name="a", cron="* * * * *"), "digest"))
        sc.save_schedule(_to_save_request(Schedule(name="b", cron="* * * * *"), "digest"))
        assert len(store) == 2

        client.reconcile("digest", [])
        assert len(store) == 0

    def test_upsert_and_prune(self):
        client, sc, store = _mock_clients()
        sc.save_schedule(_to_save_request(Schedule(name="a", cron="0 1 * * *"), "digest"))
        sc.save_schedule(_to_save_request(Schedule(name="b", cron="0 2 * * *"), "digest"))

        client.reconcile(
            "digest",
            [
                Schedule(name="a", cron="0 9 * * *"),  # updated cron
                Schedule(name="c", cron="0 17 * * *"),  # new
            ],
        )

        assert set(store.keys()) == {"digest-a", "digest-c"}
        assert store["digest-a"].cron_expression == "0 9 * * *"

    def test_only_affects_this_agents_schedules(self):
        client, sc, store = _mock_clients()
        sc.save_schedule(_to_save_request(Schedule(name="x", cron="* * * * *"), "digest"))
        sc.save_schedule(_to_save_request(Schedule(name="x", cron="* * * * *"), "other"))

        client.reconcile("digest", [])  # purge only digest's

        assert "other-x" in store
        assert "digest-x" not in store

    def test_none_vs_empty_list_distinction(self):
        client, sc, store = _mock_clients()
        sc.save_schedule(_to_save_request(Schedule(name="a", cron="* * * * *"), "digest"))

        # None: untouched
        client.reconcile("digest", None)
        assert "digest-a" in store

        # []: purged
        client.reconcile("digest", [])
        assert "digest-a" not in store

    def test_duplicate_names_raise_before_any_io(self):
        client, sc, _ = _mock_clients()
        with pytest.raises(ScheduleNameConflict):
            client.reconcile(
                "digest",
                [
                    Schedule(name="a", cron="* * * * *"),
                    Schedule(name="a", cron="0 9 * * *"),
                ],
            )
        sc.save_schedule.assert_not_called()
        sc.delete_schedule.assert_not_called()


# ── run_now wait-variant returns AgentResult ────────────────────────


def _runnow_runtime(*, wf_status, wf_output):
    """A minimal fake runtime exercising the REAL workflow→AgentResult
    extraction path used by ``schedules.run_now(wait=True)``.

    ``schedules_client()`` returns a mock whose ``get`` yields a ScheduleInfo
    and whose ``run_now`` returns a fixed execution id. The runtime's
    ``_workflow_client`` is mocked so polling returns a terminal workflow.
    The real ``AgentRuntime._build_result_from_workflow`` is bound onto the
    fake runtime so the test drives production extraction logic.
    """
    from conductor.ai.agents.runtime.runtime import AgentRuntime

    exec_id = "exec-123"

    terminal_wf = SimpleNamespace(
        status=wf_status,
        output=wf_output,
        reason_for_incompletion=None,
        tasks=[],
        variables=None,
    )

    wc = MagicMock()
    # Polling endpoint used by run_now's wait loop.
    wc.get_workflow_status.return_value = terminal_wf
    # Enrichment fetch used inside the extraction helper.
    wc.get_workflow.return_value = terminal_wf

    # ``run_now`` only forwards ``info`` to the (mocked) client; a stub suffices.
    info = MagicMock(name="ScheduleInfo")
    sched_client = MagicMock()
    sched_client.get.return_value = info
    sched_client.run_now.return_value = exec_id

    rt = MagicMock()
    rt.schedules_client.return_value = sched_client
    rt._workflow_client = wc
    # Avoid hitting the network for token usage.
    rt._extract_token_usage = MagicMock(return_value=None)
    # Wire the REAL extraction methods so we exercise production logic, not
    # MagicMock stubs. ``_build_result_from_workflow`` delegates to these.
    # Instance methods are bound to ``rt``; staticmethods are attached as-is.
    for meth in ("_build_result_from_workflow", "_extract_tool_calls", "_extract_messages"):
        setattr(rt, meth, getattr(AgentRuntime, meth).__get__(rt))
    for static in (
        "_normalize_output",
        "_extract_failed_task_reason",
        "_derive_finish_reason",
        "_extract_sub_results",
    ):
        setattr(rt, static, getattr(AgentRuntime, static))
    return rt, exec_id


class TestRunNowResult:
    def test_wait_true_returns_agent_result(self):
        from conductor.ai.agents.result import AgentResult, Status

        rt, exec_id = _runnow_runtime(
            wf_status="COMPLETED",
            wf_output={"result": "the digest"},
        )

        result = schedules.run_now("digest-daily", wait=True, runtime=rt, poll_interval=0)

        assert isinstance(result, AgentResult)
        assert result.execution_id == exec_id
        assert result.status == Status.COMPLETED
        assert result.output == {"result": "the digest"}

    def test_no_wait_returns_execution_id_string(self):
        rt, exec_id = _runnow_runtime(
            wf_status="COMPLETED",
            wf_output={"result": "ignored"},
        )

        result = schedules.run_now("digest-daily", runtime=rt)

        assert result == exec_id
        assert isinstance(result, str)


# ── Public surface ──────────────────────────────────────────────────


class TestPublicSurface:
    def test_top_level_exports(self):
        # Verify the package exports everything users will reference.
        assert Schedule is not None
        assert ScheduleInfo is not None
        assert ScheduleNameConflict is not None
        assert ScheduleNotFound is not None
        assert InvalidCronExpression is not None
        # Module-level lifecycle API exposed under `schedules`
        for fn in ("list", "get", "pause", "resume", "delete", "run_now", "preview_next", "save"):
            assert callable(getattr(schedules, fn)), f"schedules.{fn} missing"
