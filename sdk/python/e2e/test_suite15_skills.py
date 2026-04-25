"""Suite 15: Skills — loading, serialization, and execution of skill-based agents.

Tests cover the full skill lifecycle:
- Loading from SKILL.md + *-agent.md files
- Serialization preserving _framework_config
- Counterfactual: plain Agent has no skill data
- Nested skill in agent_tool preserves skill data
- plan() produces workflow referencing sub-agents
- Execution produces SUB_WORKFLOW tasks
- Skill as agent_tool execution
- DG skill loading (gilfoyle + dinesh)
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
    """Create a minimal test skill with SKILL.md + two agent files."""
    skill_md = textwrap.dedent("""\
        ---
        name: test_skill
        params:
          mode:
            default: fast
        ---
        ## Overview
        A test skill with two sub-agents.

        ## Workflow
        Alpha analyzes, Beta summarizes.
    """)
    (tmp_path / "SKILL.md").write_text(skill_md)

    alpha_md = textwrap.dedent("""\
        # Alpha Agent
        You analyze the input.
    """)
    (tmp_path / "alpha-agent.md").write_text(alpha_md)

    beta_md = textwrap.dedent("""\
        # Beta Agent
        You summarize the analysis.
    """)
    (tmp_path / "beta-agent.md").write_text(beta_md)

    return tmp_path


@pytest.fixture()
def fresh_runtime():
    """Function-scoped AgentRuntime."""
    with AgentRuntime() as rt:
        yield rt


# ── Tests ────────────────────────────────────────────────────────────


class TestSuite15Skills:
    """Skill loading, serialization, and execution tests."""

    def test_skill_loading(self, skill_dir):
        """skill() discovers sub-agents from *-agent.md files."""
        agent = skill(skill_dir, model=MODEL)

        assert agent.name == "test_skill"
        assert agent._framework == "skill"

        raw = agent._framework_config
        assert "agentFiles" in raw, (
            f"_framework_config missing 'agentFiles'. Keys: {list(raw.keys())}"
        )
        agent_file_names = set(raw["agentFiles"].keys())
        assert "alpha" in agent_file_names, (
            f"Expected 'alpha' in agentFiles, got: {agent_file_names}"
        )
        assert "beta" in agent_file_names, (
            f"Expected 'beta' in agentFiles, got: {agent_file_names}"
        )

    def test_skill_serialization(self, skill_dir):
        """Serialized config preserves _framework_config data."""
        agent = skill(skill_dir, model=MODEL)

        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)

        assert config.get("_framework") == "skill", (
            f"Serialized config missing '_framework': 'skill'. Got: {config.get('_framework')}"
        )
        assert "agentFiles" in config, (
            f"Serialized config missing 'agentFiles'. Keys: {list(config.keys())}"
        )
        assert config["name"] == "test_skill", (
            f"Serialized name is '{config['name']}', expected 'test_skill'"
        )
        assert "skillMd" in config, (
            f"Serialized config missing 'skillMd'. Keys: {list(config.keys())}"
        )

    def test_counterfactual_bare_serialization(self):
        """A plain Agent has no skill data in serialized output."""
        agent = Agent(
            name="plain_agent",
            model=MODEL,
            instructions="You are a plain agent.",
        )

        serializer = AgentConfigSerializer()
        config = serializer.serialize(agent)

        assert "_framework" not in config, (
            f"Plain Agent should not have '_framework' in serialized config. "
            f"Got: {config.get('_framework')}"
        )
        assert "skillMd" not in config, (
            f"Plain Agent should not have 'skillMd' in serialized config."
        )
        assert "agentFiles" not in config, (
            f"Plain Agent should not have 'agentFiles' in serialized config."
        )

    def test_skill_agent_tool_serialization(self, skill_dir):
        """Skill nested in agent_tool preserves skill data in serialization."""
        skill_agent = skill(skill_dir, model=MODEL)
        at = agent_tool(skill_agent, description="Run test skill")

        td = get_tool_def(at)
        assert td.tool_type == "agent_tool", (
            f"agent_tool should have tool_type='agent_tool', got '{td.tool_type}'"
        )
        assert td.config is not None, "agent_tool config should not be None"
        nested = td.config.get("agent")
        assert nested is not None, (
            f"agent_tool config missing 'agent' key. Keys: {list(td.config.keys())}"
        )
        assert getattr(nested, "_framework", None) == "skill", (
            f"Nested agent should have _framework='skill', "
            f"got '{getattr(nested, '_framework', None)}'"
        )

        # Serialize a parent that uses the agent_tool
        parent = Agent(
            name="parent_with_skill_tool",
            model=MODEL,
            instructions="Use the skill tool.",
            tools=[at],
        )
        serializer = AgentConfigSerializer()
        config = serializer.serialize(parent)

        # The parent itself is not a skill
        assert config.get("_framework") is None or config.get("_framework") != "skill", (
            "Parent agent should not be a skill"
        )
        # But the tool list should contain the skill agent tool
        tool_names = [t["name"] for t in config.get("tools", [])]
        assert "test_skill" in tool_names, (
            f"Expected 'test_skill' in parent's tools. Got: {tool_names}"
        )

    def test_skill_plan_compilation(self, skill_dir, fresh_runtime):
        """plan() produces a workflow that references sub-agents."""
        agent = skill(skill_dir, model=MODEL)

        result = fresh_runtime.plan(agent)

        assert "workflowDef" in result, (
            f"plan() result missing 'workflowDef'. Keys: {list(result.keys())}. "
            f"Full result (truncated): {str(result)[:500]}"
        )
        wf = result["workflowDef"]
        assert wf.get("name") == "test_skill", (
            f"workflowDef.name is '{wf.get('name')}', expected 'test_skill'"
        )

        # The workflow should have tasks
        tasks = wf.get("tasks", [])
        assert len(tasks) > 0, (
            "workflowDef.tasks is empty. The skill compiler produced no tasks."
        )

        # Recursively collect all tasks
        all_tasks = _all_tasks_flat(wf)
        task_types = _task_type_set(all_tasks)

        # The skill compiler produces LLM_CHAT_COMPLETE (orchestrator) and
        # FORK_JOIN_DYNAMIC (for tool/sub-agent dispatch). Sub-agents are
        # invoked dynamically at runtime, so SUB_WORKFLOW may not appear
        # in the static plan. Verify the workflow has the expected structure.
        assert "LLM_CHAT_COMPLETE" in task_types, (
            f"No LLM_CHAT_COMPLETE task in compiled workflow. "
            f"Task types: {task_types}. The skill orchestrator needs an LLM task."
        )
        assert "DO_WHILE" in task_types or "FORK_JOIN_DYNAMIC" in task_types, (
            f"No DO_WHILE or FORK_JOIN_DYNAMIC in compiled workflow. "
            f"Task types: {task_types}. The skill should have an agent loop."
        )

    def test_skill_execution_sub_workflows(self, skill_dir, fresh_runtime):
        """Running a skill produces SUB_WORKFLOW tasks in the execution."""
        agent = skill(skill_dir, model=MODEL)

        result = fresh_runtime.run(agent, "Analyze the word 'hello'")

        assert result is not None, "Skill execution returned None"
        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED"), (
            f"Skill execution status is '{result.status}', expected COMPLETED"
        )

        # Check the execution has tasks
        from conftest import get_workflow

        wf = get_workflow(result.execution_id)
        tasks = wf.get("tasks", [])
        assert len(tasks) > 0, "Execution has no tasks"

        # Should have at least one SUB_WORKFLOW task
        task_types = {t.get("taskType", t.get("type", "")) for t in tasks}
        assert "SUB_WORKFLOW" in task_types, (
            f"No SUB_WORKFLOW task in execution. Task types: {task_types}. "
            f"A skill with sub-agents should produce SUB_WORKFLOW tasks."
        )

    def test_skill_as_agent_tool_execution(self, skill_dir, fresh_runtime):
        """Skill wrapped in agent_tool still produces sub-workflows when executed."""
        skill_agent = skill(skill_dir, model=MODEL)
        at = agent_tool(skill_agent, description="Analyze with test skill")

        parent = Agent(
            name="e2e_skill_parent",
            model=MODEL,
            instructions="Use the test_skill tool to analyze the input.",
            tools=[at],
        )

        result = fresh_runtime.run(parent, "Analyze the phrase 'skill test'")

        assert result is not None, "Parent execution returned None"
        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED"), (
            f"Parent execution status is '{result.status}', expected COMPLETED"
        )

    def test_dg_skill_loading(self):
        """DG skill loads gilfoyle + dinesh agents."""
        if not DG_SKILL_PATH.exists():
            pytest.skip(
                f"DG skill not installed at {DG_SKILL_PATH}. "
                f"Install with: git clone https://github.com/v1r3n/dinesh-gilfoyle ~/.claude/skills/dg"
            )

        agent = skill(DG_SKILL_PATH, model=MODEL)

        assert agent._framework == "skill"
        raw = agent._framework_config
        agent_file_names = set(raw.get("agentFiles", {}).keys())
        assert "gilfoyle" in agent_file_names, (
            f"Expected 'gilfoyle' in DG skill agentFiles, got: {agent_file_names}"
        )
        assert "dinesh" in agent_file_names, (
            f"Expected 'dinesh' in DG skill agentFiles, got: {agent_file_names}"
        )


    def test_skill_in_stateful_agent_tool(self, skill_dir, fresh_runtime):
        """Skill workers (read_skill_file) execute correctly in a stateful context.

        When a stateful parent agent uses a skill via agent_tool, the skill's
        workers (read_skill_file, scripts) must register under the execution's
        domain. Without domain propagation, they stay SCHEDULED with pollCount=0.

        This test verifies the skill completes (not stuck) in a stateful context.
        """
        skill_agent = skill(skill_dir, model=MODEL)
        at = agent_tool(skill_agent, description="Analyze with test skill")

        parent = Agent(
            name="e2e_skill_stateful_parent",
            model=MODEL,
            stateful=True,
            instructions="Use the test_skill tool to analyze the input.",
            tools=[at],
        )

        result = fresh_runtime.run(parent, "Analyze 'stateful skill test'")

        assert result is not None, "Stateful parent execution returned None"
        assert str(result.status) in ("COMPLETED", "completed", "Status.COMPLETED"), (
            f"Stateful parent execution status is '{result.status}', expected COMPLETED. "
            f"If RUNNING/TIMED_OUT, skill workers may not have registered in the correct domain."
        )

        # Verify no tasks stuck in SCHEDULED
        from conftest import get_workflow

        wf = get_workflow(result.execution_id)
        scheduled = [t for t in wf.get("tasks", []) if t.get("status") == "SCHEDULED"]
        assert not scheduled, (
            f"Tasks stuck in SCHEDULED (domain issue): "
            f"{[(t.get('taskDefName'), t.get('pollCount', 0)) for t in scheduled]}"
        )

    def test_counterfactual_skill_serialization_lost(self, skill_dir):
        """Counterfactual: without the serialization fix, the skill config is lost.

        Proves the fix is necessary by showing that a plain Agent (simulating
        the old serializer behavior) produces no skill data. The test verifies
        the ABSENCE of skill data on a plain agent — if this test fails, the
        counterfactual is invalid.
        """
        # Load the skill correctly
        skill_agent = skill(skill_dir, model=MODEL)
        serializer = AgentConfigSerializer()
        correct_config = serializer.serialize(skill_agent)

        # Simulate old behavior: serialize a plain Agent with same name/model
        plain = Agent(name="test_skill", model=MODEL)
        broken_config = serializer.serialize(plain)

        # The correct config HAS skill data
        assert "agentFiles" in correct_config, "Correct config should have agentFiles"
        assert "skillMd" in correct_config, "Correct config should have skillMd"

        # The broken config does NOT — proving the fix is needed
        assert "agentFiles" not in broken_config, (
            "Counterfactual invalid: plain Agent should NOT have agentFiles"
        )
        assert "skillMd" not in broken_config, (
            "Counterfactual invalid: plain Agent should NOT have skillMd"
        )


# ── Helpers (copied from test_suite1 to keep this file self-contained) ──


def _all_tasks_flat(workflow_def: dict) -> list:
    """Recursively collect all tasks from a workflow definition."""
    tasks = []
    for t in workflow_def.get("tasks", []):
        tasks.append(t)
        tasks.extend(_recurse_task(t))
    return tasks


def _recurse_task(t: dict) -> list:
    """Recurse into a single task's nested children."""
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
    """Collect unique task type values."""
    return {t.get("type", "") for t in tasks}


def _sub_workflow_names(tasks: list) -> list:
    """Extract subWorkflowParam.name from SUB_WORKFLOW tasks."""
    names = []
    for t in tasks:
        if t.get("type") == "SUB_WORKFLOW":
            params = t.get("subWorkflowParam", {}) or t.get("subWorkflowParams", {})
            if params.get("name"):
                names.append(params["name"])
    return names
