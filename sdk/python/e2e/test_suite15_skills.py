"""Suite 15: Skills — loading, serialization, and execution of skill-based agents.

Tests cover the full skill lifecycle:
- Loading from SKILL.md + *-agent.md files
- Serialization preserving _framework_config
- Counterfactual: plain Agent has no skill data
- Nested skill in agent_tool preserves skill data
- plan() produces workflow referencing sub-agents
- Skill as agent_tool: workers registered and polled (regression for pre-deploy fix)
- Skill as agent_tool in stateful context: workers registered with domain
- DG skill loading (gilfoyle + dinesh)
- Script discovery, params injection, worker creation
"""

import os
import textwrap
from pathlib import Path

import pytest

from agentspan.agents import Agent, AgentRuntime, agent_tool, skill
from agentspan.agents.config_serializer import AgentConfigSerializer
from agentspan.agents.tool import get_tool_def

pytestmark = pytest.mark.e2e

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")

DG_SKILL_PATH = Path("~/.claude/skills/dg").expanduser()

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def skill_dir(tmp_path):
    """Create a minimal test skill with SKILL.md + two agent files + a script."""
    skill_md = textwrap.dedent("""\
        ---
        name: test_skill
        params:
          mode:
            default: fast
        ---
        ## Overview
        A test skill with two sub-agents and a script tool.

        ## Workflow
        1. Call the echo_args tool once with the user's input as the argument.
        2. Return the echo_args result to the user. Do NOT call any more tools after echo_args.
    """)
    (tmp_path / "SKILL.md").write_text(skill_md)

    (tmp_path / "alpha-agent.md").write_text("# Alpha Agent\nYou analyze the input.\n")
    (tmp_path / "beta-agent.md").write_text("# Beta Agent\nYou summarize the analysis.\n")

    # Script tool: echoes args with a deterministic prefix for algorithmic validation
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    echo_script = scripts_dir / "echo_args.py"
    echo_script.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import sys
        args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "no-args"
        print(f"ECHO_ARGS_RESULT:{args}")
    """))
    echo_script.chmod(0o755)

    return tmp_path


@pytest.fixture()
def fresh_runtime():
    """Function-scoped AgentRuntime."""
    with AgentRuntime() as rt:
        yield rt


# ── Helpers ──────────────────────────────────────────────────────────


def _verify_skill_sub_workflow(execution_id: str, skill_task_name: str = "test_skill"):
    """Fetch a skill sub-workflow from a parent execution and verify:
    1. The skill SUB_WORKFLOW task exists and COMPLETED
    2. No tasks stuck in SCHEDULED inside the sub-workflow (pollCount=0 regression)
    3. If echo_args was invoked, it COMPLETED with ECHO_ARGS_RESULT marker

    Returns (sub_wf_id, sub_tasks) for further inspection.
    """
    from conftest import get_workflow

    wf = get_workflow(execution_id)
    all_tasks = wf.get("tasks", [])

    # Find the skill SUB_WORKFLOW task
    skill_tasks = [
        t for t in all_tasks
        if skill_task_name in t.get("taskDefName", "")
    ]
    assert len(skill_tasks) > 0, (
        f"{skill_task_name} sub-workflow never invoked in {execution_id}. "
        f"Task defs: {[t.get('taskDefName') for t in all_tasks]}"
    )
    for t in skill_tasks:
        assert t.get("status") == "COMPLETED", (
            f"{skill_task_name} status='{t.get('status')}' pollCount={t.get('pollCount', 0)} "
            f"in {execution_id}"
        )

    # Fetch the sub-workflow
    sub_wf_id = skill_tasks[0].get("outputData", {}).get("subWorkflowId", "")
    assert sub_wf_id, f"No subWorkflowId in {skill_task_name} output"

    sub_wf = get_workflow(sub_wf_id)
    sub_tasks = sub_wf.get("tasks", [])

    # CRITICAL: no tasks stuck in SCHEDULED — the original bug symptom.
    # If workers aren't registered/polling, tool tasks stay SCHEDULED with pollCount=0.
    scheduled = [t for t in sub_tasks if t.get("status") == "SCHEDULED"]
    assert not scheduled, (
        f"Tasks stuck in SCHEDULED in sub-workflow {sub_wf_id} — "
        f"workers were NOT registered! "
        f"{[(t.get('taskDefName'), t.get('pollCount', 0)) for t in scheduled]}"
    )

    # If echo_args was invoked, verify it completed with deterministic marker
    echo_tasks = [
        t for t in sub_tasks if "echo_args" in t.get("taskDefName", "")
    ]
    if echo_tasks:
        for t in echo_tasks:
            assert t.get("status") == "COMPLETED", (
                f"echo_args status='{t.get('status')}' pollCount={t.get('pollCount', 0)} "
                f"in sub-workflow {sub_wf_id}"
            )
        any_marker = any(
            "ECHO_ARGS_RESULT:" in str(t.get("outputData", {}))
            for t in echo_tasks
        )
        assert any_marker, (
            f"echo_args completed but no ECHO_ARGS_RESULT marker in {sub_wf_id}. "
            f"Outputs: {[t.get('outputData') for t in echo_tasks]}"
        )

    return sub_wf_id, sub_tasks


def _all_tasks_flat(workflow_def: dict) -> list:
    """Recursively collect all tasks from a workflow definition."""
    tasks = []
    for t in workflow_def.get("tasks", []):
        tasks.append(t)
        tasks.extend(_recurse_task(t))
    return tasks


def _recurse_task(t: dict) -> list:
    children = []
    for nested in t.get("loopOver", []):
        children.append(nested)
        children.extend(_recurse_task(nested))
    for case_tasks in t.get("decisionCases", {}).values():
        for ct in case_tasks:
            children.append(ct)
            children.extend(_recurse_task(ct))
    for ct in t.get("defaultCase", []):
        children.append(ct)
        children.extend(_recurse_task(ct))
    for fork_list in t.get("forkTasks", []):
        for ft in fork_list:
            children.append(ft)
            children.extend(_recurse_task(ft))
    return children


def _task_type_set(tasks: list) -> set:
    return {t.get("type", "") for t in tasks}


# ── Tests ────────────────────────────────────────────────────────────


class TestSuite15Skills:
    """Skill loading, serialization, and execution tests."""

    # ── Loading & serialization (no server, instant) ──────────────

    def test_skill_loading(self, skill_dir):
        """skill() discovers sub-agents from *-agent.md files."""
        agent = skill(skill_dir, model=MODEL)

        assert agent.name == "test_skill"
        assert agent._framework == "skill"

        raw = agent._framework_config
        assert "agentFiles" in raw
        agent_file_names = set(raw["agentFiles"].keys())
        assert "alpha" in agent_file_names
        assert "beta" in agent_file_names

    def test_skill_serialization(self, skill_dir):
        """Serialized config preserves _framework_config data."""
        agent = skill(skill_dir, model=MODEL)
        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)

        assert config.get("_framework") == "skill"
        assert "agentFiles" in config
        assert config["name"] == "test_skill"
        assert "skillMd" in config

    def test_counterfactual_bare_serialization(self):
        """A plain Agent has no skill data in serialized output."""
        agent = Agent(name="plain_agent", model=MODEL, instructions="You are a plain agent.")
        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)

        assert "_framework" not in config
        assert "skillMd" not in config
        assert "agentFiles" not in config

    def test_skill_agent_tool_serialization(self, skill_dir):
        """Skill nested in agent_tool preserves skill data in serialization."""
        skill_agent = skill(skill_dir, model=MODEL)
        at = agent_tool(skill_agent, description="Run test skill")

        td = get_tool_def(at)
        assert td.tool_type == "agent_tool"
        assert td.config is not None
        nested = td.config.get("agent")
        assert nested is not None
        assert getattr(nested, "_framework", None) == "skill"

        parent = Agent(
            name="parent_with_skill_tool", model=MODEL,
            instructions="Use the skill tool.", tools=[at],
        )
        serializer = AgentConfigSerializer()
        config = serializer.serialize(parent)

        assert config.get("_framework") != "skill"
        tool_names = [t["name"] for t in config.get("tools", [])]
        assert "test_skill" in tool_names

    def test_counterfactual_skill_serialization_lost(self, skill_dir):
        """Counterfactual: plain Agent with same name produces no skill data."""
        skill_agent = skill(skill_dir, model=MODEL)
        serializer = AgentConfigSerializer()
        correct_config = serializer.serialize(skill_agent)

        plain = Agent(name="test_skill", model=MODEL)
        broken_config = serializer.serialize(plain)

        assert "agentFiles" in correct_config
        assert "skillMd" in correct_config
        assert "agentFiles" not in broken_config
        assert "skillMd" not in broken_config

    def test_skill_script_discovery(self, skill_dir):
        """skill() discovers scripts from the scripts/ directory."""
        agent = skill(skill_dir, model=MODEL)
        scripts = agent._framework_config.get("scripts", {})

        assert "echo_args" in scripts
        assert scripts["echo_args"].get("language") == "python"
        assert scripts["echo_args"].get("filename") == "echo_args.py"

    def test_skill_params_injection(self, skill_dir):
        """Params are injected into SKILL.md for server visibility."""
        agent = skill(skill_dir, model=MODEL, params={"mode": "turbo", "rounds": 1})
        config = agent._framework_config
        skill_md = config.get("skillMd", "")

        assert "[Skill Parameters]" in skill_md
        assert "mode: turbo" in skill_md
        assert "rounds: 1" in skill_md

        raw_params = config.get("params", {})
        assert raw_params.get("mode") == "turbo"
        assert raw_params.get("rounds") == 1

    def test_skill_params_default_override(self, skill_dir):
        """Runtime params override SKILL.md frontmatter defaults."""
        agent_default = skill(skill_dir, model=MODEL)
        assert agent_default._skill_params.get("mode") == "fast"

        agent_override = skill(skill_dir, model=MODEL, params={"mode": "slow"})
        assert agent_override._skill_params.get("mode") == "slow"

    def test_skill_script_worker_creation(self, skill_dir):
        """Skill scripts produce worker functions that execute with arguments."""
        from agentspan.agents.skill import create_skill_workers

        agent = skill(skill_dir, model=MODEL)
        workers = create_skill_workers(agent)

        worker_names = [w.name for w in workers]
        assert any("echo_args" in n for n in worker_names)

        echo_worker = next(w for w in workers if "echo_args" in w.name)
        result = echo_worker.func(command="hello world")
        assert "ECHO_ARGS_RESULT:hello world" in result

    def test_skill_script_no_args(self, skill_dir):
        """Script called without arguments returns the default marker."""
        from agentspan.agents.skill import create_skill_workers

        agent = skill(skill_dir, model=MODEL)
        workers = create_skill_workers(agent)
        echo_worker = next(w for w in workers if "echo_args" in w.name)

        result = echo_worker.func()
        assert "ECHO_ARGS_RESULT:no-args" in result

    def test_dg_skill_loading(self):
        """DG skill loads gilfoyle + dinesh agents."""
        if not DG_SKILL_PATH.exists():
            pytest.skip(f"DG skill not installed at {DG_SKILL_PATH}")

        agent = skill(DG_SKILL_PATH, model=MODEL)
        assert agent._framework == "skill"
        agent_file_names = set(agent._framework_config.get("agentFiles", {}).keys())
        assert "gilfoyle" in agent_file_names
        assert "dinesh" in agent_file_names

    # ── Compilation (server call, no LLM) ─────────────────────────

    def test_skill_plan_compilation(self, skill_dir, fresh_runtime):
        """plan() produces a workflow with LLM_CHAT_COMPLETE and agent loop."""
        agent = skill(skill_dir, model=MODEL)
        result = fresh_runtime.plan(agent)

        assert "workflowDef" in result
        wf = result["workflowDef"]
        assert wf.get("name") == "test_skill"

        all_tasks = _all_tasks_flat(wf)
        task_types = _task_type_set(all_tasks)
        assert "LLM_CHAT_COMPLETE" in task_types
        assert "DO_WHILE" in task_types or "FORK_JOIN_DYNAMIC" in task_types

    def test_skill_params_in_compiled_workflow(self, skill_dir, fresh_runtime):
        """Params injected into SKILL.md appear in the compiled workflow."""
        agent = skill(skill_dir, model=MODEL, params={"mode": "turbo", "rounds": 1})
        result = fresh_runtime.plan(agent)

        wf_str = str(result.get("workflowDef", {}))
        assert "Skill Parameters" in wf_str or "mode" in wf_str, (
            "Compiled workflow does not contain skill params"
        )

    # ── Execution (real LLM calls) ────────────────────────────────

    def test_agent_tool_skill_workers_registered(self, skill_dir, fresh_runtime):
        """Skill workers are registered and polled when skill is nested in agent_tool.

        Regression test for the _pre_deploy_nested_skills + worker polling fix.
        The bug: skill workers were registered but polling never started because
        the parent agent had no @tool workers. Result: echo_args task stuck in
        SCHEDULED with pollCount=0.

        Validates:
        - Parent execution COMPLETED
        - Skill SUB_WORKFLOW COMPLETED
        - Zero tasks stuck in SCHEDULED inside the sub-workflow
        - echo_args task COMPLETED with ECHO_ARGS_RESULT marker (if invoked)
        """
        skill_agent = skill(skill_dir, model=MODEL)
        at = agent_tool(skill_agent, description="Run test skill with echo_args")

        parent = Agent(
            name="e2e_skill_at_worker_reg",
            model=MODEL,
            instructions=(
                "You have one tool: test_skill. "
                "Call it once with the user's request, then return the result."
            ),
            tools=[at],
            max_turns=3,
        )

        result = fresh_runtime.run(parent, "Echo 'proof42'", timeout=60)

        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED"), (
            f"execution_id={result.execution_id} status={result.status}. "
            f"TIMED_OUT = skill workers not registered or not polling."
        )

        _verify_skill_sub_workflow(result.execution_id)

    def test_agent_tool_skill_workers_with_domain(self, skill_dir, fresh_runtime):
        """Skill workers register with correct domain in stateful context.

        When a stateful parent uses a skill via agent_tool, the skill's workers
        must register under the execution's domain. Without domain propagation,
        they poll in the wrong domain and tasks stay SCHEDULED with pollCount=0.

        Validates:
        - Stateful parent COMPLETED (not TIMED_OUT from missing workers)
        - Skill SUB_WORKFLOW COMPLETED
        - Zero tasks stuck in SCHEDULED (domain mismatch would cause this)
        """
        skill_agent = skill(skill_dir, model=MODEL)
        at = agent_tool(skill_agent, description="Run test skill with echo_args")

        parent = Agent(
            name="e2e_skill_at_domain",
            model=MODEL,
            stateful=True,
            instructions=(
                "You have one tool: test_skill. "
                "Call it once with the user's request, then return the result."
            ),
            tools=[at],
            max_turns=3,
        )

        result = fresh_runtime.run(parent, "Echo 'domain_proof'", timeout=60)

        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED"), (
            f"execution_id={result.execution_id} status={result.status}. "
            f"TIMED_OUT = skill workers not registered in correct domain."
        )

        _verify_skill_sub_workflow(result.execution_id)
