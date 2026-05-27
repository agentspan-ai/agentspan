"""Suite 16: CLI Skills — real CLI skill run/load/serve paths.

No mocks. Requires:
- a live AgentSpan server
- an installed/built agentspan CLI (AGENTSPAN_CLI_PATH or PATH)
- an LLM provider configured for AGENTSPAN_LLM_MODEL
"""

import json
import os
import re
import shutil
import subprocess
import textwrap
import time
import uuid
from pathlib import Path

import pytest
import requests
from conftest import BASE_URL, CLI_PATH, MODEL, get_workflow

pytestmark = [pytest.mark.e2e, pytest.mark.xdist_group("cli-skills")]


def _cli_server_url() -> str:
    """Use IPv4 loopback for local CLI calls to avoid localhost resolving to ::1."""
    return BASE_URL.replace("http://localhost", "http://127.0.0.1")


@pytest.fixture()
def cli_path() -> str:
    """Return a runnable agentspan CLI path or skip when it is not available."""
    candidate = Path(CLI_PATH).expanduser()
    if candidate.parent != Path(".") or os.sep in CLI_PATH:
        if candidate.exists():
            return str(candidate)
        pytest.skip(f"AGENTSPAN_CLI_PATH not found: {CLI_PATH}")

    found = shutil.which(CLI_PATH)
    if not found:
        pytest.skip(f"agentspan CLI not found on PATH: {CLI_PATH}")
    return found


@pytest.fixture()
def cli_skill_dir(tmp_path):
    """Create a deterministic skill that must call a local script worker."""
    skill_name = f"cli_skill_e2e_{uuid.uuid4().hex[:8]}"
    skill_dir = tmp_path / skill_name
    skill_dir.mkdir()

    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {skill_name}
            description: CLI skill e2e fixture.
            ---
            ## Workflow
            If no prior tool result is available, call the {skill_name}__echo_args
            tool exactly once. Pass the original user's request as the command argument.

            After the tool returns any line beginning with CLI_SKILL_ECHO:, produce
            a final answer containing that exact line and do not call any tool again.

            If the current request is "Please continue where you left off.", do not
            call a tool. Return the most recent CLI_SKILL_ECHO: line from the
            conversation exactly.
            """
        )
    )

    (skill_dir / "alpha-agent.md").write_text("# Alpha Agent\nAnalyze the request.\n")
    (skill_dir / "beta-agent.md").write_text("# Beta Agent\nSummarize the analysis.\n")

    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "guide.md").write_text("# CLI_REFERENCE_GUIDE\nUse this guide.\n")

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    echo_script = scripts_dir / "echo_args.py"
    echo_script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "no-args"
            print(f"CLI_SKILL_ECHO:{args}")
            """
        )
    )
    echo_script.chmod(0o755)
    return skill_name, skill_dir


def _run_cli(cli_path: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    server_url = _cli_server_url()
    env = {**os.environ, "AGENTSPAN_SERVER_URL": server_url}
    return subprocess.run(
        [cli_path, "--server", server_url, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _start_cli(cli_path: str, *args: str) -> subprocess.Popen:
    server_url = _cli_server_url()
    env = {**os.environ, "AGENTSPAN_SERVER_URL": server_url}
    return subprocess.Popen(
        [cli_path, "--server", server_url, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _execution_id(output: str) -> str:
    match = re.search(r"Execution:\s*([^\s)]+)", output)
    assert match, f"could not find execution id in CLI output:\n{output}"
    return match.group(1)


def _json_from_cli(output: str) -> dict:
    start = output.find("{")
    assert start >= 0, f"could not find JSON object in CLI output:\n{output}"
    return json.loads(output[start:])


def _wait_terminal(execution_id: str, timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = get_workflow(execution_id)
        status = last.get("status")
        if status in {"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"}:
            return last
        time.sleep(2)
    pytest.fail(f"execution {execution_id} did not finish; last={last}")


def _assert_echo_worker_completed(workflow: dict, marker: str) -> None:
    tasks = workflow.get("tasks", [])
    scheduled = [
        (t.get("taskDefName"), t.get("referenceTaskName"), t.get("pollCount", 0))
        for t in tasks
        if t.get("status") == "SCHEDULED"
    ]
    assert not scheduled, f"worker tasks stuck in SCHEDULED: {scheduled}"

    echo_tasks = [t for t in tasks if "echo_args" in t.get("taskDefName", "")]
    task_names = [t.get("taskDefName") for t in tasks]
    assert echo_tasks, f"echo_args was not invoked. Tasks: {task_names}"
    assert all(t.get("status") == "COMPLETED" for t in echo_tasks), echo_tasks
    assert any(marker in str(t.get("outputData", {})) for t in echo_tasks), [
        t.get("outputData", {}) for t in echo_tasks
    ]


def _assert_loaded_skill_raw_config(output: str, skill_name: str) -> None:
    data = json.loads(output)
    assert skill_name in data.get("skillMd", "")

    agent_files = data.get("agentFiles", {})
    assert {"alpha", "beta"}.issubset(agent_files.keys()), agent_files

    scripts = data.get("scripts", {})
    assert "echo_args" in scripts, scripts

    resources = data.get("resourceFiles", [])
    assert "references/guide.md" in resources, resources

    serialized = json.dumps(data)
    assert "_skillPath" not in serialized
    assert "_skillSections" not in serialized


def _write_registered_dependency_skills(tmp_path):
    suffix = uuid.uuid4().hex[:8]
    child_name = f"child-skill-{suffix}"
    parent_name = f"parent-skill-{suffix}"

    child_v1 = tmp_path / f"{child_name}-v1"
    child_v1.mkdir()
    (child_v1 / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {child_name}
            description: Child skill v1.
            ---
            ## Workflow
            Child dependency version one.
            """
        )
    )
    scripts = child_v1 / "scripts"
    scripts.mkdir()
    script = scripts / "echo_args.py"
    script.write_text(
        "#!/usr/bin/env python3\nimport sys\nprint('CHILD_V1:' + ' '.join(sys.argv[1:]))\n"
    )
    script.chmod(0o755)
    refs = child_v1 / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("CHILD_GUIDE_V1\n")

    parent = tmp_path / parent_name
    parent.mkdir()
    (parent / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {parent_name}
            description: Parent skill.
            ---
            ## Workflow
            Use the {child_name} skill for the request.
            """
        )
    )

    child_v2 = tmp_path / f"{child_name}-v2"
    child_v2.mkdir()
    (child_v2 / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {child_name}
            description: Child skill v2.
            ---
            ## Workflow
            Child dependency version two.
            """
        )
    )

    return parent_name, parent, child_name, child_v1, child_v2


def _stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)


class TestSuite16CliSkills:
    def test_cli_skill_register_list_get_pull_and_delete(self, cli_path, cli_skill_dir, tmp_path):
        """Server registry lifecycle is deterministic and does not require an LLM call."""
        skill_name, skill_dir = cli_skill_dir
        version = f"v-{uuid.uuid4().hex[:8]}"

        register = _run_cli(
            cli_path,
            "skill",
            "register",
            str(skill_dir),
            "--version",
            version,
            "--model",
            MODEL,
            timeout=60,
        )
        assert register.returncode == 0, f"stdout:\n{register.stdout}\nstderr:\n{register.stderr}"
        detail = _json_from_cli(register.stdout)
        assert detail["name"] == skill_name
        assert detail["version"] == version
        assert detail["status"] == "READY"
        assert detail["rawConfig"]["scripts"]["echo_args"]["filename"] == "echo_args.py"

        listed = _run_cli(cli_path, "skill", "list", "--all-versions", timeout=60)
        assert listed.returncode == 0, f"stdout:\n{listed.stdout}\nstderr:\n{listed.stderr}"
        assert skill_name in listed.stdout
        assert version[:12] in listed.stdout

        got = _run_cli(cli_path, "skill", "get", skill_name, "--version", version, timeout=60)
        assert got.returncode == 0, f"stdout:\n{got.stdout}\nstderr:\n{got.stderr}"
        got_detail = json.loads(got.stdout)
        assert got_detail["checksum"] == detail["checksum"]

        pulled = tmp_path / "pulled-skill"
        pull = _run_cli(cli_path, "skill", "pull", skill_name, str(pulled), "--version", version, timeout=60)
        assert pull.returncode == 0, f"stdout:\n{pull.stdout}\nstderr:\n{pull.stderr}"
        assert (pulled / "SKILL.md").exists()
        assert (pulled / "references" / "guide.md").read_text() == "# CLI_REFERENCE_GUIDE\nUse this guide.\n"

        deleted = _run_cli(cli_path, "skill", "delete", skill_name, "--version", version, "--yes", timeout=60)
        assert deleted.returncode == 0, f"stdout:\n{deleted.stdout}\nstderr:\n{deleted.stderr}"

        missing = _run_cli(cli_path, "skill", "get", skill_name, "--version", version, timeout=60)
        assert missing.returncode != 0

    def test_registered_cross_skill_dependency_versions_are_pinned(self, cli_path, tmp_path):
        """Registered parent skills compile against dependency versions pinned at registration."""
        parent_name, parent_dir, child_name, child_v1, child_v2 = _write_registered_dependency_skills(tmp_path)

        child_v1_version = f"v1-{uuid.uuid4().hex[:8]}"
        parent_version = f"v1-{uuid.uuid4().hex[:8]}"
        child_v2_version = f"v2-{uuid.uuid4().hex[:8]}"

        child_register = _run_cli(
            cli_path,
            "skill",
            "register",
            str(child_v1),
            "--version",
            child_v1_version,
            "--model",
            MODEL,
            timeout=60,
        )
        assert child_register.returncode == 0, (
            f"stdout:\n{child_register.stdout}\nstderr:\n{child_register.stderr}"
        )

        parent_register = _run_cli(
            cli_path,
            "skill",
            "register",
            str(parent_dir),
            "--version",
            parent_version,
            "--model",
            MODEL,
            timeout=60,
        )
        assert parent_register.returncode == 0, (
            f"stdout:\n{parent_register.stdout}\nstderr:\n{parent_register.stderr}"
        )
        parent_detail = _json_from_cli(parent_register.stdout)
        pinned = parent_detail["rawConfig"]["crossSkillRefs"][child_name]["skillRef"]
        assert pinned["version"] == child_v1_version

        child_v2_register = _run_cli(
            cli_path,
            "skill",
            "register",
            str(child_v2),
            "--version",
            child_v2_version,
            "--model",
            MODEL,
            timeout=60,
        )
        assert child_v2_register.returncode == 0, (
            f"stdout:\n{child_v2_register.stdout}\nstderr:\n{child_v2_register.stderr}"
        )

        compile_response = requests.post(
            f"{BASE_URL}/api/agent/compile",
            json={
                "framework": "skill",
                "skillRef": {
                    "name": parent_name,
                    "version": parent_version,
                    "model": MODEL,
                },
            },
            timeout=30,
        )
        assert compile_response.status_code == 200, compile_response.text
        compiled = compile_response.json()
        agent_def = compiled["workflowDef"]["metadata"]["agentDef"]
        child_ref = agent_def["crossSkillRefs"][child_name]
        assert child_ref["skillRef"]["version"] == child_v1_version
        assert "Child dependency version one" in child_ref["skillMd"]
        assert "Child dependency version two" not in child_ref["skillMd"]
        assert "echo_args" in child_ref["scripts"]
        assert "references/guide.md" in child_ref["resourceFiles"]

    def test_cli_skill_run_registered_executes_downloaded_script_worker(self, cli_path, cli_skill_dir):
        """`agentspan skill run <name>` downloads a registered skill and runs its script workers."""
        skill_name, skill_dir = cli_skill_dir
        version = f"run-{uuid.uuid4().hex[:8]}"

        register = _run_cli(
            cli_path,
            "skill",
            "register",
            str(skill_dir),
            "--version",
            version,
            "--model",
            MODEL,
            timeout=60,
        )
        assert register.returncode == 0, f"stdout:\n{register.stdout}\nstderr:\n{register.stderr}"

        result = _run_cli(
            cli_path,
            "skill",
            "run",
            skill_name,
            "registered_run_proof",
            "--version",
            version,
            "--model",
            MODEL,
            "--timeout",
            "120",
            timeout=180,
        )

        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        execution_id = _execution_id(result.stdout)
        workflow = get_workflow(execution_id)
        assert workflow.get("status") == "COMPLETED", workflow
        _assert_echo_worker_completed(workflow, "CLI_SKILL_ECHO:")

    def test_cli_skill_run_ephemeral_executes_script_worker(self, cli_path, cli_skill_dir):
        """`agentspan skill run` starts local workers and completes a real execution."""
        _skill_name, skill_dir = cli_skill_dir

        result = _run_cli(
            cli_path,
            "skill",
            "run",
            str(skill_dir),
            "ephemeral_proof",
            "--model",
            MODEL,
            "--timeout",
            "120",
            timeout=180,
        )

        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        execution_id = _execution_id(result.stdout)
        workflow = get_workflow(execution_id)
        assert workflow.get("status") == "COMPLETED", workflow
        _assert_echo_worker_completed(workflow, "CLI_SKILL_ECHO:")

    def test_cli_skill_load_serve_and_run_by_name(self, cli_path, cli_skill_dir):
        """Production path: load deploys, serve polls workers, run --name starts framework skill."""
        skill_name, skill_dir = cli_skill_dir

        load = _run_cli(
            cli_path,
            "skill",
            "load",
            str(skill_dir),
            "--model",
            MODEL,
            timeout=60,
        )
        assert load.returncode == 0, f"stdout:\n{load.stdout}\nstderr:\n{load.stderr}"
        assert skill_name in load.stdout

        loaded = _run_cli(cli_path, "agent", "get", skill_name, timeout=60)
        assert loaded.returncode == 0, f"stdout:\n{loaded.stdout}\nstderr:\n{loaded.stderr}"
        _assert_loaded_skill_raw_config(loaded.stdout, skill_name)

        serve = _start_cli(cli_path, "skill", "serve", str(skill_dir))
        try:
            time.sleep(2)
            if serve.poll() is not None:
                stdout, stderr = serve.communicate(timeout=1)
                pytest.fail(f"skill serve exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")

            run = _run_cli(
                cli_path,
                "agent",
                "run",
                "--name",
                skill_name,
                "--no-stream",
                "served_proof",
                timeout=60,
            )
            assert run.returncode == 0, f"stdout:\n{run.stdout}\nstderr:\n{run.stderr}"
            execution_id = _execution_id(run.stdout)
            workflow = _wait_terminal(execution_id)
            assert workflow.get("status") == "COMPLETED", workflow
            _assert_echo_worker_completed(workflow, "CLI_SKILL_ECHO:")
        finally:
            _stop_process(serve)
