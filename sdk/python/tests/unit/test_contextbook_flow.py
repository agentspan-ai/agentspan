"""Deterministic tests for the issue-fixer contextbook data flow.

Proves that every agent in the pipeline can read/write contextbook sections
correctly and that the full data flow can be represented without chat history.

No server, no LLM, no mocks. Pure filesystem operations.
"""

import json
import os
import subprocess
import sys

import pytest

# Ensure the examples directory is importable
_EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "examples"
)
sys.path.insert(0, os.path.abspath(_EXAMPLES_DIR))

import _issue_fixer_tools as tools  # noqa: E402


def _init_git_repo(path, branch="fix/issue-42"):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-B", branch], cwd=path, check=True, capture_output=True, text=True)


@pytest.fixture(autouse=True)
def isolated_workdir(tmp_path):
    """Give every test a fresh working directory."""
    tools.set_working_dir(str(tmp_path))
    yield tmp_path
    # Reset module state without calling set_working_dir (avoids makedirs(""))
    tools._WORKING_DIR = ""
    tools._last_execution_id = ""
    tools._file_read_hashes.clear()
    tools._grep_cache.clear()


# ── Section validation ──────────────────────────────────────


class TestSectionValidation:
    """Contextbook enforces a fixed set of section names."""

    VALID = {
        "issue_pr", "repo_conventions", "design", "coder_context", "qa_findings",
        "pr_result", "architecture_design_test", "coder_plan", "implementation",
        "implementation_report", "qa_testing",
        # Inner-reviewer verdict for the plan→execute→review loop.
        "review_feedback",
    }

    def test_valid_sections_match(self):
        assert tools._VALID_SECTIONS == self.VALID

    def test_write_invalid_section_returns_error(self):
        result = tools.contextbook_write("bogus", "content")
        assert "Error" in result
        assert "invalid section" in result

    def test_read_invalid_section_returns_error(self):
        # Need contextbook dir to exist, otherwise read returns "empty" early
        tools.contextbook_write("issue_pr", "seed")
        result = tools.contextbook_read("bogus")
        assert "Error" in result
        assert "invalid section" in result

    def test_write_each_valid_section_succeeds(self):
        for section in self.VALID:
            result = tools.contextbook_write(section, f"content for {section}")
            assert "wrote" in result or "appended" in result, f"Failed for {section}: {result}"

    def test_read_unwritten_section_returns_not_yet(self):
        # Need contextbook dir to exist first
        tools.contextbook_write("issue_pr", "seed")
        result = tools.contextbook_read("implementation")
        assert "not been written yet" in result

    def test_validate_issue_workspace_returns_json_string(self, isolated_workdir):
        _init_git_repo(isolated_workdir, branch="fix/issue-42")
        tools.contextbook_write(
            "issue_pr",
            "# Issue #42\nRepo: acme/app\nBranch: fix/issue-42\nMode: new issue fix\n",
        )
        tools.contextbook_write("repo_conventions", "content for repo_conventions")

        result = json.loads(tools.validate_issue_workspace())

        assert result["passed"] is True
        assert result["missing"] == []
        assert result["current_branch"] == "fix/issue-42"

    def test_validate_issue_workspace_rejects_stale_contextbook_sections(
        self, isolated_workdir
    ):
        _init_git_repo(isolated_workdir, branch="fix/issue-42")
        tools.contextbook_write(
            "issue_pr",
            "# Issue #42\nRepo: acme/app\nBranch: fix/issue-42\nMode: new issue fix\n",
        )
        tools.contextbook_write("repo_conventions", "content for repo_conventions")
        tools.contextbook_write("architecture_design_test", "old design")

        result = json.loads(tools.validate_issue_workspace())

        assert result["passed"] is False
        assert result["unexpected"] == ["architecture_design_test"]

    def test_validate_issue_workspace_rejects_new_issue_on_main_branch(
        self, isolated_workdir
    ):
        _init_git_repo(isolated_workdir, branch="main")
        tools.contextbook_write(
            "issue_pr",
            "# Issue #42\nRepo: acme/app\nBranch: main\nMode: new issue fix\n",
        )
        tools.contextbook_write("repo_conventions", "content for repo_conventions")

        result = json.loads(tools.validate_issue_workspace())

        assert result["passed"] is False
        assert "new issue fix is on default branch 'main'" in result["branch_errors"]

    def test_validate_pr_result_returns_json_string(self):
        tools.contextbook_write(
            "pr_result",
            '{"passed": true, "status": "created", "url": "https://github.com/acme/app/pull/1"}',
        )

        result = json.loads(tools.validate_pr_result())

        assert result["passed"] is True
        assert result["status"] == "created"

    def test_reset_contextbook_removes_stale_sections(self):
        tools.contextbook_write("architecture_design_test", "old design")
        tools.contextbook_write("qa_testing", "old qa")

        tools._reset_contextbook()

        toc = tools.contextbook_read("")
        assert "empty" in toc.lower()
        assert "old design" not in toc

    def test_read_file_repeat_limit_blocks_fourth_read(self, isolated_workdir):
        path = isolated_workdir / "target.txt"
        path.write_text("one\ntwo\n", encoding="utf-8")

        assert "one" in tools.read_file("target.txt")
        assert "REPEAT READ #2" in tools.read_file("target.txt")
        assert "REPEAT READ #3" in tools.read_file("target.txt")

        result = tools.read_file("target.txt")

        assert "repeat read limit exceeded" in result


# ── Write and read round-trip ───────────────────────────────


class TestWriteReadRoundTrip:
    """contextbook_write followed by contextbook_read returns exact content."""

    def test_write_then_read(self):
        tools.contextbook_write("issue_pr", "# Issue #42: Fix the bug\nBody here")
        content = tools.contextbook_read("issue_pr")
        assert content == "# Issue #42: Fix the bug\nBody here"

    def test_append_mode(self):
        tools.contextbook_write("implementation", "## Changes\n- file1.py")
        tools.contextbook_write("implementation", "## Tests\n- test_thing", append=True)
        content = tools.contextbook_read("implementation")
        assert "## Changes" in content
        assert "## Tests" in content
        assert content.index("## Changes") < content.index("## Tests")

    def test_overwrite_mode(self):
        tools.contextbook_write("qa_testing", "first version")
        tools.contextbook_write("qa_testing", "second version", append=False)
        content = tools.contextbook_read("qa_testing")
        assert content == "second version"
        assert "first version" not in content

    def test_empty_contextbook_read_toc(self):
        result = tools.contextbook_read("")
        assert "empty" in result.lower()

    def test_toc_shows_written_sections(self):
        tools.contextbook_write("issue_pr", "Issue content")
        tools.contextbook_write("repo_conventions", "Conventions")
        toc = tools.contextbook_read("")
        assert "[issue_pr]" in toc
        assert "[repo_conventions]" in toc
        assert "(empty)" in toc  # unwritten sections show as empty


# ── get_coder_context ────────────────────────────────────────


class TestGetCoderContext:
    """Legacy get_coder_context reads 4 sections (skips repo_conventions)."""

    CODER_SECTIONS = ("issue_pr", "architecture_design_test", "implementation", "qa_testing")

    def test_returns_nothing_when_empty(self):
        result = tools.get_coder_context()
        assert "no contextbook sections written yet" in result.lower()

    def test_returns_only_written_sections(self):
        tools.contextbook_write("issue_pr", "Issue data")
        tools.contextbook_write("architecture_design_test", "Design data")
        result = tools.get_coder_context()
        assert "ISSUE_PR" in result
        assert "ARCHITECTURE_DESIGN_TEST" in result
        assert "IMPLEMENTATION" not in result  # not written
        assert "QA_TESTING" not in result  # not written

    def test_skips_repo_conventions(self):
        """get_coder_context deliberately omits repo_conventions."""
        tools.contextbook_write("repo_conventions", "This should NOT appear")
        tools.contextbook_write("issue_pr", "Issue data")
        result = tools.get_coder_context()
        assert "REPO_CONVENTIONS" not in result
        assert "This should NOT appear" not in result

    def test_returns_all_4_when_all_written(self):
        for section in self.CODER_SECTIONS:
            tools.contextbook_write(section, f"Content for {section}")
        result = tools.get_coder_context()
        for section in self.CODER_SECTIONS:
            assert section.upper() in result


# ── contextbook_summary ──────────────────────────────────────


class TestContextbookSummary:
    """contextbook_summary returns preview of all written sections."""

    def test_empty_summary(self):
        result = tools.contextbook_summary()
        assert "empty" in result.lower()

    def test_summary_includes_previews(self):
        tools.contextbook_write("issue_pr", "A" * 600)
        tools.contextbook_write("qa_testing", "B" * 100)
        result = tools.contextbook_summary()
        assert "ISSUE_PR" in result
        assert "QA_TESTING" in result
        assert "chars total" in result  # issue_pr > 500 chars so truncated


# ── Full pipeline simulation ─────────────────────────────────


class TestFullPipelineFlow:
    """Simulate the exact contextbook operations each agent performs.

    This is the core test: proves the data flows correctly through
    the entire 5-agent pipeline.
    """

    def test_full_pipeline_data_flow(self):
        """Simulate all 5 agents writing/reading contextbook in order."""

        # ── Agent 1: issue_pr_fetcher (via setup_repo internals) ──
        issue_pr_content = (
            "# Issue #42: Fix authentication bypass\n"
            "Author: attacker-reporter\n"
            "Labels: security, bug\n"
            "Repo: acme/webapp\n"
            "Branch: fix/issue-42\n"
            "\n"
            "## Issue Body\n"
            "The login endpoint accepts empty passwords.\n"
            "\n"
            "## TODO\n"
            "- [ ] IMPLEMENT: Validate password is non-empty\n"
            "- [ ] TEST: Add test for empty password rejection\n"
        )
        conventions_content = (
            "Default branch: main\n\n"
            "--- CLAUDE.md ---\n"
            "Use pytest for tests.\n\n"
            "--- pyproject.toml ---\n"
            "[tool.pytest]\ntestpaths = ['tests']\n\n"
            "--- Detected Commands ---\n"
            "  lint: ruff format . && ruff check --fix .\n"
            "  test: pytest tests/ -x -q\n"
        )

        result1 = tools.contextbook_write("issue_pr", issue_pr_content)
        assert "wrote" in result1
        result2 = tools.contextbook_write("repo_conventions", conventions_content)
        assert "wrote" in result2

        # ── Agent 2: tech_lead reads issue_pr + repo_conventions ──
        issue_pr_read = tools.contextbook_read("issue_pr")
        assert "Fix authentication bypass" in issue_pr_read
        assert "empty passwords" in issue_pr_read

        conventions_read = tools.contextbook_read("repo_conventions")
        assert "pytest" in conventions_read
        assert "Detected Commands" in conventions_read

        # Tech lead writes architecture_design_test
        design_content = (
            "## Architecture\n"
            "N/A — bug fix\n\n"
            "## Design\n"
            "Root cause: login_handler() in auth/login.py passes password directly\n"
            "to verify_password() without checking for empty string.\n"
            "Fix: Add validation in login_handler() before calling verify_password().\n"
            "Files: auth/login.py (modify login_handler)\n\n"
            "## Testing Strategy\n"
            "- test_empty_password_rejected: POST /login with empty password → 400\n"
            "- test_none_password_rejected: POST /login with null password → 400\n"
            "- test_valid_password_still_works: POST /login with correct password → 200\n"
            "Command: pytest tests/ -x -q\n\n"
            "## Documentation\n"
            "None required.\n"
        )
        result3 = tools.contextbook_write("architecture_design_test", design_content)
        assert "wrote" in result3
        result3b = tools.contextbook_write("design", design_content)
        assert "wrote" in result3b
        result3c = tools.contextbook_write(
            "coder_context",
            "# Coder Context\n\n## Checklist\n- [ ] IMPLEMENT\n- [ ] TEST\n",
        )
        assert "wrote" in result3c

        # ── Agent 3: coder reads via get_coder_context ──
        coder_ctx = tools.get_coder_context()
        # Must see issue_pr
        assert "Fix authentication bypass" in coder_ctx
        assert "empty passwords" in coder_ctx
        # Must see architecture_design_test
        assert "login_handler" in coder_ctx
        assert "verify_password" in coder_ctx
        # Must NOT see repo_conventions (coder reads that via contextbook_read if needed)
        assert "Detected Commands" not in coder_ctx
        # implementation and qa_testing not written yet, so absent
        assert "IMPLEMENTATION" not in coder_ctx
        assert "QA_TESTING" not in coder_ctx

        # Coder writes implementation
        impl_content = (
            "## Changes\n"
            "| File | Action | Description |\n"
            "|------|--------|-------------|\n"
            "| auth/login.py | Modified | Added empty password check |\n"
            "| tests/test_auth.py | Added | 3 new tests |\n\n"
            "## Tests Added\n"
            "- test_empty_password_rejected: verifies 400 on empty password\n"
            "- test_none_password_rejected: verifies 400 on null password\n"
            "- test_valid_password_still_works: verifies 200 on correct password\n\n"
            "## TODO Checklist\n"
            "- [x] IMPLEMENT: Validate password is non-empty — done\n"
            "- [x] TEST: Add test for empty password rejection — done\n"
        )
        result4 = tools.contextbook_write("implementation", impl_content)
        assert "wrote" in result4

        # ── Agent 4: qa_agent reads 3 sections + writes qa_testing ──
        qa_issue = tools.contextbook_read("issue_pr")
        assert "Fix authentication bypass" in qa_issue

        qa_design = tools.contextbook_read("architecture_design_test")
        assert "login_handler" in qa_design

        qa_impl = tools.contextbook_read("implementation")
        assert "test_empty_password_rejected" in qa_impl
        assert "auth/login.py" in qa_impl

        qa_testing_content = (
            "## Test Results\n"
            "- tests/test_auth.py: PASS (3 tests)\n\n"
            "## Code Review\n"
            "### Critical Issues (must fix)\n"
            "(none)\n\n"
            "### Recommendations (nice to have)\n"
            "- [ ] `auth/login.py:15` — consider logging failed empty-password attempts\n\n"
            "## Security Review\n"
            "Fix correctly addresses the authentication bypass. No new vulnerabilities.\n\n"
            "## Verdict\n"
            "QA_APPROVED — all tests pass, fix is correct, TODO checklist complete.\n"
        )
        result5 = tools.contextbook_write("qa_testing", qa_testing_content)
        assert "wrote" in result5
        result5b = tools.contextbook_write(
            "qa_findings",
            '{"status": "pass", "blockers": [], "tests_run": ["pytest"], "summary": "ok"}',
        )
        assert "wrote" in result5b

        # Write the additional sections added for coder pipeline
        result6 = tools.contextbook_write("coder_plan", "## Coder Plan\n- Fix login handler")
        assert "wrote" in result6
        result7 = tools.contextbook_write("implementation_report", "## Report\nAll changes applied")
        assert "wrote" in result7
        result7b = tools.contextbook_write(
            "pr_result",
            '{"passed": true, "status": "created", "url": "https://github.com/acme/webapp/pull/1"}',
        )
        assert "wrote" in result7b
        # Inner-reviewer verdict (plan→execute→review loop).
        result8 = tools.contextbook_write(
            "review_feedback", "## Verdict: DONE\nImplementation matches design."
        )
        assert "wrote" in result8

        # ── Agent 5: pr_updater reads ALL sections ──
        pr_issue = tools.contextbook_read("issue_pr")
        assert "Fix authentication bypass" in pr_issue

        pr_design = tools.contextbook_read("architecture_design_test")
        assert "login_handler" in pr_design

        pr_impl = tools.contextbook_read("implementation")
        assert "auth/login.py" in pr_impl

        pr_qa = tools.contextbook_read("qa_testing")
        assert "QA_APPROVED" in pr_qa

        pr_conventions = tools.contextbook_read("repo_conventions")
        assert "pytest" in pr_conventions

        # All 5 sections exist and are non-empty
        toc = tools.contextbook_read("")
        for section in tools._VALID_SECTIONS:
            assert f"[{section}]" in toc
            # None should show "(empty)"
            # Extract the line for this section
            for line in toc.split("\n"):
                if f"[{section}]" in line:
                    assert "(empty)" not in line, f"Section {section} should not be empty"

    def test_qa_rework_loop_appends(self):
        """Simulate coder→qa→coder→qa rework loop with contextbook updates."""

        # Initial coder work
        tools.contextbook_write("issue_pr", "Fix bug #10")
        tools.contextbook_write("architecture_design_test", "Design for bug #10")
        tools.contextbook_write("implementation", "## Changes\n- first attempt")

        # QA finds issues
        tools.contextbook_write("qa_testing",
            "## Verdict\nNEEDS_REWORK\n- [ ] Missing edge case test")

        # Coder reads qa_testing, sees rework needed
        coder_ctx = tools.get_coder_context()
        assert "NEEDS_REWORK" in coder_ctx
        assert "Missing edge case test" in coder_ctx

        # Coder rewrites implementation (overwrite, not append)
        tools.contextbook_write("implementation",
            "## Changes\n- first attempt\n- added edge case test")

        # QA re-reviews
        qa_impl = tools.contextbook_read("implementation")
        assert "edge case test" in qa_impl

        # QA approves
        tools.contextbook_write("qa_testing",
            "## Verdict\nQA_APPROVED — edge case addressed")

        # pr_updater sees final state
        final_qa = tools.contextbook_read("qa_testing")
        assert "QA_APPROVED" in final_qa
        assert "NEEDS_REWORK" not in final_qa  # overwritten

    def test_pr_feedback_mode_preserves_existing_contextbook(self):
        """When handling PR feedback, existing sections get overwritten with fresh data."""

        # Simulate a prior run left contextbook
        tools.contextbook_write("issue_pr", "Old issue data")
        tools.contextbook_write("implementation", "Old implementation")

        # New run (PR feedback mode) overwrites issue_pr
        tools.contextbook_write("issue_pr",
            "# Issue #42 with PR #100 feedback\nReviewer wants changes")

        # Old implementation is still there until coder overwrites
        impl = tools.contextbook_read("implementation")
        assert "Old implementation" in impl

        # New issue_pr is fresh
        issue = tools.contextbook_read("issue_pr")
        assert "PR #100 feedback" in issue
        assert "Old issue data" not in issue


# ── Filesystem isolation ─────────────────────────────────────


class TestFilesystemIsolation:
    """Contextbook is scoped to _WORKING_DIR — different dirs are independent."""

    def test_different_workdirs_are_isolated(self, tmp_path):
        dir_a = tmp_path / "repo_a"
        dir_b = tmp_path / "repo_b"
        dir_a.mkdir()
        dir_b.mkdir()

        tools.set_working_dir(str(dir_a))
        tools.contextbook_write("issue_pr", "Issue for repo A")

        tools.set_working_dir(str(dir_b))
        tools.contextbook_write("issue_pr", "Issue for repo B")

        # Read from B
        content_b = tools.contextbook_read("issue_pr")
        assert content_b == "Issue for repo B"

        # Switch back to A
        tools.set_working_dir(str(dir_a))
        content_a = tools.contextbook_read("issue_pr")
        assert content_a == "Issue for repo A"

    def test_contextbook_dir_path(self, tmp_path):
        tools.set_working_dir(str(tmp_path))
        cb_dir = tools._contextbook_dir()
        assert cb_dir == tmp_path / ".contextbook"

    def test_contextbook_creates_dir_on_write(self, tmp_path):
        tools.set_working_dir(str(tmp_path))
        cb_dir = tmp_path / ".contextbook"
        assert not cb_dir.exists()
        tools.contextbook_write("issue_pr", "test")
        assert cb_dir.exists()
        assert (cb_dir / "issue_pr.md").exists()


# ── Build command detection ──────────────────────────────────


class TestBuildCommandDetection:
    """_detect_build_commands populates _REPO_COMMANDS from build files."""

    def test_python_uv_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "uv.lock").write_text("")
        tools._detect_build_commands(tmp_path)
        assert "uv run ruff" in tools._REPO_COMMANDS.get("lint", "")
        assert "uv run pytest" in tools._REPO_COMMANDS.get("test", "")

    def test_python_poetry_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")
        tools._detect_build_commands(tmp_path)
        assert "poetry run" in tools._REPO_COMMANDS.get("lint", "")

    def test_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"scripts": {"lint": "eslint .", "build": "tsc", "test": "jest"}}')
        tools._detect_build_commands(tmp_path)
        assert tools._REPO_COMMANDS.get("lint") == "npm run lint"
        assert tools._REPO_COMMANDS.get("build") == "npm run build"
        assert tools._REPO_COMMANDS.get("test") == "npm test"

    def test_monorepo_package_without_scripts_falls_through_to_nested_projects(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {"prepare": "husky"}}')
        server = tmp_path / "server"
        server.mkdir()
        (server / "gradlew").write_text("#!/bin/sh\n")
        cli = tmp_path / "cli"
        cli.mkdir()
        (cli / "go.mod").write_text("module example.com/cli\n")

        tools._detect_build_commands(tmp_path)

        assert "cd server && ./gradlew testClasses" in tools._REPO_COMMANDS.get("build", "")
        assert "cd cli && go build ./..." in tools._REPO_COMMANDS.get("build", "")
        assert "cd server && ./gradlew test" in tools._REPO_COMMANDS.get("test", "")
        assert "cd cli && go test ./..." in tools._REPO_COMMANDS.get("test", "")

    def test_build_tools_redetect_commands_after_worker_state_reset(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {"prepare": "husky"}}')
        server = tmp_path / "server"
        server.mkdir()
        (server / "gradlew").write_text("#!/bin/sh\n")
        cli = tmp_path / "cli"
        cli.mkdir()
        (cli / "go.mod").write_text("module example.com/cli\n")

        tools.set_working_dir(str(tmp_path))
        tools._REPO_COMMANDS.clear()
        tools._ensure_repo_commands()

        assert "cd server && ./gradlew testClasses" in tools._REPO_COMMANDS.get("build", "")
        assert "cd cli && go build ./..." in tools._REPO_COMMANDS.get("build", "")

    def test_go_project(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        tools._detect_build_commands(tmp_path)
        assert "go build" in tools._REPO_COMMANDS.get("build", "")
        assert "go test" in tools._REPO_COMMANDS.get("test", "")

    def test_rust_project(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        tools._detect_build_commands(tmp_path)
        assert tools._REPO_COMMANDS.get("lint") == "cargo fmt"
        assert tools._REPO_COMMANDS.get("test") == "cargo test"

    def test_makefile_overrides(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "uv.lock").write_text("")
        (tmp_path / "Makefile").write_text("lint:\n\tmake-lint\ntest:\n\tmake-test\n")
        tools._detect_build_commands(tmp_path)
        assert tools._REPO_COMMANDS.get("lint") == "make lint"
        assert tools._REPO_COMMANDS.get("test") == "make test"

    def test_empty_project(self, tmp_path):
        tools._detect_build_commands(tmp_path)
        assert tools._REPO_COMMANDS == {}


# ── run_command safety ───────────────────────────────────────


class TestRunCommandSafety:
    def test_blocks_shell_file_inspection_without_terminating_tool(self):
        result = tools.run_command("git show HEAD:server/src/main/java/Foo.java")
        assert result.startswith("Blocked: run_command")
        assert "read_file" in result
        assert "git_diff" in result

    def test_validation_tools_block_shell_inspection_without_running_it(self):
        grep_result = tools.run_unit_tests("grep -n deleteExecutions server/src/main/java/Foo.java")
        diff_result = tools.run_unit_tests("git diff --stat")

        assert grep_result.startswith("Blocked: validation tools")
        assert diff_result.startswith("Blocked: validation tools")
        assert "git_diff" in diff_result

    def test_coder_inspection_budget_blocks_before_successful_edit(self, isolated_workdir):
        ctx = tools.ToolContext(
            execution_id="coder-budget-before-edit",
            agent_name="issue_fixer_coder",
        )
        (isolated_workdir / "src").mkdir()
        (isolated_workdir / "src" / "app.py").write_text("def app():\n    return 1\n")

        for _ in range(tools._CODER_INSPECTION_BUDGET_BEFORE_EDIT):
            result = tools.list_directory(context=ctx)
            assert not result.startswith("Blocked: coder inspection budget")

        blocked = tools.list_directory(context=ctx)

        assert blocked.startswith("Blocked: coder inspection budget exceeded")
        assert "edit_files" in blocked

    def test_successful_edit_reopens_inspection_budget(self, isolated_workdir):
        ctx = tools.ToolContext(
            execution_id="coder-budget-after-edit",
            agent_name="issue_fixer_coder",
        )
        target = isolated_workdir / "src" / "app.py"
        target.parent.mkdir()
        target.write_text("def app():\n    return 1\n")

        for _ in range(tools._CODER_INSPECTION_BUDGET_BEFORE_EDIT + 1):
            tools.list_directory(context=ctx)

        edit_result = tools.edit_file(
            "src/app.py",
            "return 1",
            "return 2",
            context=ctx,
        )
        after_edit = tools.list_directory(context=ctx)

        assert edit_result.startswith("Edited")
        assert not after_edit.startswith("Blocked: coder inspection budget")

    def test_subagent_validation_budget_blocks_endless_test_loops(self):
        ctx = tools.ToolContext(
            execution_id="coder-validation-budget",
            agent_name="issue_fixer_coder",
        )

        for _ in range(tools._SUBAGENT_VALIDATION_BUDGET):
            result = tools.run_unit_tests("true", context=ctx)
            assert not result.startswith("Blocked: validation budget")

        blocked = tools.run_unit_tests("true", context=ctx)

        assert blocked.startswith("Blocked: validation budget exceeded")

    def test_implementation_report_requires_edit_and_validation_for_coder(
        self, isolated_workdir
    ):
        ctx = tools.ToolContext(
            execution_id="coder-report-gate",
            agent_name="issue_fixer_coder",
        )
        target = isolated_workdir / "src" / "app.py"
        target.parent.mkdir()
        target.write_text("def app():\n    return 1\n")

        no_edit = tools.write_implementation_report("done", context=ctx)
        tools.edit_file("src/app.py", "return 1", "return 2", context=ctx)
        no_validation = tools.write_implementation_report("done", context=ctx)
        tools.run_unit_tests("true", context=ctx)
        ok = tools.write_implementation_report("done", context=ctx)

        assert no_edit.startswith("Error: implementation_report is blocked")
        assert "validation" in no_validation
        assert ok.startswith("Contextbook: wrote 'implementation_report'")

    def test_allows_status_and_diff_commands(self, isolated_workdir):
        _init_git_repo(isolated_workdir)
        result = tools.run_command("git status --short && git diff --stat")
        assert result.startswith("[exit 0]")
        assert "Blocked:" not in result


# ── Repo URL normalization ───────────────────────────────────


class TestRepoNormalization:
    """setup_repo normalizes various repo URL formats to owner/name."""

    def _extract_normalized_repo(self, input_repo: str) -> str:
        """Apply the same normalization logic as setup_repo."""
        import re
        repo = re.sub(r"^https?://", "", input_repo)
        repo = re.sub(r"^github\.com/", "", repo)
        repo = re.sub(r"\.git$", "", repo)
        repo = repo.strip("/")
        return repo

    def test_already_owner_name(self):
        assert self._extract_normalized_repo("acme/webapp") == "acme/webapp"

    def test_full_https_url(self):
        assert self._extract_normalized_repo("https://github.com/acme/webapp") == "acme/webapp"

    def test_http_url(self):
        assert self._extract_normalized_repo("http://github.com/acme/webapp") == "acme/webapp"

    def test_github_dot_com_prefix(self):
        assert self._extract_normalized_repo("github.com/acme/webapp") == "acme/webapp"

    def test_git_suffix(self):
        assert self._extract_normalized_repo("github.com/acme/webapp.git") == "acme/webapp"

    def test_full_url_with_git(self):
        assert self._extract_normalized_repo("https://github.com/acme/webapp.git") == "acme/webapp"

    def test_trailing_slash(self):
        assert self._extract_normalized_repo("acme/webapp/") == "acme/webapp"
