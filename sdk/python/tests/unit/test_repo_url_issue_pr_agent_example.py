"""Tests for GitHub repo URL -> issue -> PR agent."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SDK_SRC = Path(__file__).resolve().parents[2] / "src"
EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
for path in (SDK_SRC, EXAMPLES_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from agentspan.agents import Strategy


class TestHelpers:
    def test_normalize_repo_input_from_https(self):
        from repo_url_issue_pr_agent import normalize_repo_input

        assert normalize_repo_input("https://github.com/pytest-dev/pytest-asyncio") == (
            "pytest-dev/pytest-asyncio"
        )

    def test_normalize_repo_input_from_ssh(self):
        from repo_url_issue_pr_agent import normalize_repo_input

        assert normalize_repo_input("git@github.com:pytest-dev/pytest-asyncio.git") == (
            "pytest-dev/pytest-asyncio"
        )

    def test_slugify_branch_value(self):
        from repo_url_issue_pr_agent import slugify_branch_value

        assert slugify_branch_value("PytestAssertRewriteWarning due to runpytest") == (
            "pytestassertrewritewarning-due-to-runpyt"
        )

    def test_github_env_aliases_token_and_disables_prompts(self):
        from repo_url_issue_pr_agent import github_env

        with patch.dict(os.environ, {"GITHUB_TOKEN": "secret-token"}, clear=True):
            env = github_env()

        assert env["GITHUB_TOKEN"] == "secret-token"
        assert env["GH_TOKEN"] == "secret-token"
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GH_PROMPT_DISABLED"] == "1"

    def test_credentialed_remote_url_uses_token(self):
        from repo_url_issue_pr_agent import credentialed_remote_url

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token+value"}, clear=True):
            remote_url = credentialed_remote_url("agentspan", "pytest-asyncio")

        assert remote_url == (
            "https://x-access-token:token%2Bvalue@github.com/agentspan/pytest-asyncio.git"
        )

    def test_runtime_timeout_seconds_prefers_shorter_dry_run_default(self):
        from repo_url_issue_pr_agent import runtime_timeout_seconds

        with patch.dict(os.environ, {"AGENTSPAN_DRY_RUN": "true"}, clear=True):
            assert runtime_timeout_seconds() == 1800

    def test_parse_args_sets_timeout_override(self):
        from repo_url_issue_pr_agent import parse_args

        argv = [
            "repo_url_issue_pr_agent.py",
            "https://github.com/pytest-dev/pytest-asyncio",
            "--timeout",
            "600",
        ]
        with patch.object(sys, "argv", argv):
            with patch.dict(os.environ, {}, clear=True):
                repo_url, issue, guidance, timeout_seconds = parse_args()

        assert repo_url == "https://github.com/pytest-dev/pytest-asyncio"
        assert issue == 0
        assert guidance == ""
        assert timeout_seconds == 600

    def test_parse_args_enables_review_branch_mode(self):
        from repo_url_issue_pr_agent import parse_args

        argv = [
            "repo_url_issue_pr_agent.py",
            "https://github.com/pytest-dev/pytest-asyncio",
            "--review-branch",
        ]
        with patch.object(sys, "argv", argv):
            with patch.dict(os.environ, {}, clear=True):
                parse_args()
                assert os.environ["AGENTSPAN_REVIEW_BRANCH_ONLY"] == "true"

    def test_resolve_workdir_recovers_latest_matching_workspace(self, tmp_path):
        from repo_url_issue_pr_agent import resolve_workdir

        newer = tmp_path / "agentspan_newer"
        older = tmp_path / "agentspan_older"
        for path in (older, newer):
            (path / ".git").mkdir(parents=True)
        os.utime(older, (1, 1))
        os.utime(newer, (2, 2))

        with patch(
            "repo_url_issue_pr_agent.tempfile.gettempdir", return_value=str(tmp_path)
        ):
            with patch("repo_url_issue_pr_agent.run_cmd") as mock_cmd:
                mock_cmd.side_effect = [
                    MagicMock(
                        returncode=0,
                        stdout="https://github.com/pytest-dev/pytest-asyncio.git\n",
                    ),
                    MagicMock(
                        returncode=0,
                        stdout="https://github.com/pytest-dev/pytest-asyncio.git\n",
                    ),
                ]
                resolved = resolve_workdir(
                    "/path/to/repo", repo="pytest-dev/pytest-asyncio"
                )

        assert resolved == str(newer)


class TestPrepareRepoWorkspace:
    def test_prepare_repo_workspace_declares_github_token(self):
        from repo_url_issue_pr_agent import prepare_repo_workspace

        assert prepare_repo_workspace._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_prepare_repo_workspace_returns_repo_metadata(self, tmp_path):
        from repo_url_issue_pr_agent import RepoProfile, prepare_repo_workspace

        workdir = tmp_path / "repo"
        workdir.mkdir()

        with patch(
            "repo_url_issue_pr_agent.create_workspace", return_value=str(workdir)
        ):
            with patch("repo_url_issue_pr_agent.run_cmd") as mock_cmd:
                mock_cmd.side_effect = [
                    MagicMock(
                        returncode=0,
                        stdout=json.dumps(
                            {
                                "nameWithOwner": "pytest-dev/pytest-asyncio",
                                "url": "https://github.com/pytest-dev/pytest-asyncio",
                                "defaultBranchRef": {"name": "main"},
                            }
                        ),
                    ),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                with patch("repo_url_issue_pr_agent.RepoProfile.detect") as mock_detect:
                    mock_detect.return_value = RepoProfile(
                        languages=["python"],
                        test_cmd="python -m pytest -x -q --tb=short",
                        lint_cmd="ruff check .",
                        build_cmd=None,
                    )
                    result = prepare_repo_workspace.__wrapped__(
                        "https://github.com/pytest-dev/pytest-asyncio"
                    )

        assert result["repo"] == "pytest-dev/pytest-asyncio"
        assert result["default_branch"] == "main"
        assert result["test_cmd"] == "python -m pytest -x -q --tb=short"


class TestSearchRepoIssues:
    def test_search_repo_issues_declares_github_token(self):
        from repo_url_issue_pr_agent import search_repo_issues

        assert search_repo_issues._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_search_repo_issues_filters_assigned_and_wip(self):
        from repo_url_issue_pr_agent import search_repo_issues

        sample_issues = [
            {
                "number": 1,
                "title": "Good first bug",
                "body": "Clear repro",
                "labels": [{"name": "good first issue"}, {"name": "bug"}],
                "comments": [],
                "assignees": [],
                "updatedAt": "2026-03-01T10:00:00Z",
                "url": "https://github.com/org/repo/issues/1",
            },
            {
                "number": 2,
                "title": "Already taken",
                "body": "Someone is on it",
                "labels": [{"name": "bug"}],
                "comments": [],
                "assignees": [{"login": "dev"}],
                "updatedAt": "2026-03-01T10:00:00Z",
                "url": "https://github.com/org/repo/issues/2",
            },
            {
                "number": 3,
                "title": "WIP in comments",
                "body": "Maybe okay",
                "labels": [{"name": "bug"}],
                "comments": [{"body": "I'm working on this"}],
                "assignees": [],
                "updatedAt": "2026-03-01T10:00:00Z",
                "url": "https://github.com/org/repo/issues/3",
            },
        ]

        with patch("repo_url_issue_pr_agent.run_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(sample_issues),
                stderr="",
            )
            result = search_repo_issues.__wrapped__("org/repo")

        assert [candidate["number"] for candidate in result["candidates"]] == [1]


class TestBranchAndPublicationTools:
    def test_read_issue_detail_declares_github_token(self):
        from repo_url_issue_pr_agent import read_issue_detail

        assert read_issue_detail._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_create_issue_branch_slugifies_title(self):
        from repo_url_issue_pr_agent import create_issue_branch

        with patch("repo_url_issue_pr_agent.run_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = create_issue_branch.__wrapped__(
                workdir="/tmp/test",
                issue_number=1334,
                issue_title="PytestAssertRewriteWarning due to runpytest and pytest_plugins",
                default_branch="main",
            )

        assert result["branch"].startswith("agentspan/issue-1334-")

    def test_configure_git_identity_dry_run(self):
        from repo_url_issue_pr_agent import configure_git_identity

        with patch.dict(os.environ, {"AGENTSPAN_DRY_RUN": "true"}):
            result = configure_git_identity.__wrapped__(workdir="/tmp/test")

        assert result["status"] == "dry_run"
        assert result["would_configure"]["user"] == "AgentSpan"

    def test_create_pull_request_dry_run(self):
        from repo_url_issue_pr_agent import create_pull_request

        with patch.dict(os.environ, {"AGENTSPAN_DRY_RUN": "true"}):
            result = create_pull_request.__wrapped__(
                repo="pytest-dev/pytest-asyncio",
                workdir="/tmp/test",
                branch="agentspan/issue-1334-test",
                base_branch="main",
                title="Fix warning regression",
                body="Fixes #1334",
            )

        assert result["status"] == "dry_run"

    def test_push_review_branch_dry_run(self):
        from repo_url_issue_pr_agent import push_review_branch

        with patch.dict(os.environ, {"AGENTSPAN_DRY_RUN": "true"}):
            result = push_review_branch.__wrapped__(
                repo="pytest-dev/pytest-asyncio",
                workdir="/tmp/test",
                branch="agentspan/issue-1334-test",
            )

        assert result["status"] == "dry_run"
        assert result["would_push"]["branch"] == "agentspan/issue-1334-test"

    def test_push_review_branch_recovers_repo_and_branch(self):
        from repo_url_issue_pr_agent import push_review_branch

        with patch.dict(os.environ, {"GITHUB_TOKEN": "secret-token"}, clear=True):
            with patch("repo_url_issue_pr_agent.resolve_workdir", return_value="/tmp/test"):
                with patch("repo_url_issue_pr_agent.current_github_login", return_value="agentspan"):
                    with patch("repo_url_issue_pr_agent.ensure_fork_remote") as ensure_remote:
                        with patch("repo_url_issue_pr_agent.run_cmd") as mock_cmd:
                            mock_cmd.side_effect = [
                                MagicMock(
                                    returncode=0,
                                    stdout="https://github.com/pytest-dev/pytest-asyncio.git\n",
                                    stderr="",
                                ),
                                MagicMock(
                                    returncode=0,
                                    stdout="agentspan/issue-1334-test\n",
                                    stderr="",
                                ),
                                MagicMock(
                                    returncode=0,
                                    stdout="",
                                    stderr="",
                                ),
                                MagicMock(
                                    returncode=0,
                                    stdout="0123456789abcdef0123456789abcdef01234567\n",
                                    stderr="",
                                ),
                            ]
                            result = push_review_branch.__wrapped__()

        ensure_remote.assert_called_once()
        assert result["status"] == "pushed"
        assert result["branch"] == "agentspan/issue-1334-test"
        assert result["branch_url"].endswith("/agentspan/pytest-asyncio/tree/agentspan%2Fissue-1334-test")
        assert result["commit_sha"] == "0123456789abcdef0123456789abcdef01234567"
        assert result["commit_url"].endswith(
            "/agentspan/pytest-asyncio/commit/0123456789abcdef0123456789abcdef01234567"
        )

    def test_push_review_branch_declares_github_token(self):
        from repo_url_issue_pr_agent import push_review_branch

        assert push_review_branch._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_sync_branch_with_base_success(self):
        from repo_url_issue_pr_agent import sync_branch_with_base

        with patch("repo_url_issue_pr_agent.run_cmd") as mock_cmd:
            mock_cmd.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            result = sync_branch_with_base.__wrapped__(
                workdir="/tmp/test",
                branch="agentspan/issue-1334-test",
                base_branch="main",
            )

        assert result["status"] == "rebased"

    def test_sync_branch_with_base_declares_github_token(self):
        from repo_url_issue_pr_agent import sync_branch_with_base

        assert sync_branch_with_base._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_approve_publication_requires_human_approval(self):
        from repo_url_issue_pr_agent import approve_publication

        assert approve_publication._tool_def.approval_required is True

    def test_create_pull_request_rejects_wrong_login(self):
        from repo_url_issue_pr_agent import create_pull_request

        with patch.dict(
            os.environ,
            {"AGENTSPAN_DRY_RUN": "false", "AGENTSPAN_GITHUB_USER": "agentspan"},
        ):
            with patch(
                "repo_url_issue_pr_agent.current_github_login",
                return_value="someone-else",
            ):
                result = create_pull_request.__wrapped__(
                    repo="pytest-dev/pytest-asyncio",
                    workdir="/tmp/test",
                    branch="agentspan/issue-1334-test",
                    base_branch="main",
                    title="Fix warning regression",
                    body="Fixes #1334",
                )

        assert "Stored GITHUB_TOKEN resolves to 'someone-else'" in result["error"]

    def test_create_pull_request_declares_github_token(self):
        from repo_url_issue_pr_agent import create_pull_request

        assert create_pull_request._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_comment_on_issue_dry_run(self):
        from repo_url_issue_pr_agent import comment_on_issue

        with patch.dict(os.environ, {"AGENTSPAN_DRY_RUN": "true"}):
            result = comment_on_issue.__wrapped__(
                repo="pytest-dev/pytest-asyncio",
                issue_number=1334,
                body="AgentSpan opened PR https://github.com/example/pr/1",
            )

        assert result["status"] == "dry_run"

    def test_comment_on_issue_declares_github_token(self):
        from repo_url_issue_pr_agent import comment_on_issue

        assert comment_on_issue._tool_def.credentials == ["GITHUB_TOKEN"]


class TestPipelineStructure:
    def test_pipeline_builds(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        assert pipeline is not None

    def test_pipeline_has_five_stages(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        assert len(pipeline.agents) == 5

    def test_issue_scout_has_gate(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        assert pipeline.agents[1].gate is not None

    def test_issue_scout_allows_python_execution(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        issue_scout = pipeline.agents[1]
        assert issue_scout.code_execution_config is not None
        assert "python" in issue_scout.code_execution_config.allowed_languages

    def test_repo_analyst_allows_common_file_operations(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        repo_analyst = pipeline.agents[2]
        assert repo_analyst.code_execution_config is not None
        commands = set(repo_analyst.code_execution_config.allowed_commands)
        assert {"rm", "mv", "cp", "mkdir", "touch", "pwd"} <= commands

    def test_repo_analyst_allows_common_shell_helpers(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        repo_analyst = pipeline.agents[2]
        assert repo_analyst.code_execution_config is not None
        commands = set(repo_analyst.code_execution_config.allowed_commands)
        assert {
            "xargs",
            "awk",
            "cut",
            "dirname",
            "basename",
            "tr",
            "which",
            "cd",
        } <= commands

    def test_stage_max_tokens_fit_common_model_limits(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        for agent in pipeline.agents:
            if agent.max_tokens is not None:
                assert agent.max_tokens <= 16000

    def test_dry_run_pipeline_uses_shorter_stage_timeouts(self):
        from repo_url_issue_pr_agent import build_pipeline

        with patch.dict(os.environ, {"AGENTSPAN_DRY_RUN": "true"}, clear=True):
            pipeline = build_pipeline(
                "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
            )

        assert pipeline.agents[3].timeout_seconds == 900

    def test_coding_stage_is_swarm(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        swarm = pipeline.agents[3]
        assert swarm.strategy in (Strategy.SWARM, "swarm")
        assert len(swarm.handoffs) == 2

    def test_coding_loop_subagents_use_fresh_handoff_context(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        fixer = pipeline.agents[3].agents[0]
        reviewer = pipeline.agents[3].agents[1]
        assert fixer.include_contents == "none"
        assert reviewer.include_contents == "none"

    def test_publisher_has_human_approval_tool(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        publisher = pipeline.agents[4]
        tool_names = [tool._tool_def.name for tool in publisher.tools]
        assert "approve_publication" in tool_names
        assert "push_review_branch" in tool_names

    def test_stage_instructions_forbid_placeholder_repo_paths(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        for agent in (pipeline.agents[2], pipeline.agents[4]):
            assert (
                "Never use placeholder paths like /path/to/repo" in agent.instructions
            )
            assert "Never ask the user for the repo path" in agent.instructions

    def test_coding_stage_instructions_require_executable_code_only(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        for agent in (
            pipeline.agents[2],
            pipeline.agents[3].agents[0],
            pipeline.agents[3].agents[1],
        ):
            assert "execute_code tool input must be executable code only" in agent.instructions
            assert "Do not start bash snippets with variable-assignment lines like WORKDIR=..." in agent.instructions

    def test_publisher_has_explicit_blocked_output_contract(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )
        publisher = pipeline.agents[4]
        assert "PUBLICATION_BLOCKED" in publisher.instructions
        assert "do not call any tools" in publisher.instructions
        assert "Never answer conversationally" in publisher.instructions

    def test_review_branch_mode_changes_publisher_contract(self):
        from repo_url_issue_pr_agent import build_pipeline

        with patch.dict(os.environ, {"AGENTSPAN_REVIEW_BRANCH_ONLY": "true"}, clear=True):
            pipeline = build_pipeline(
                "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
            )

        publisher = pipeline.agents[4]
        assert "REVIEW_BRANCH_PUSHED" in publisher.instructions
        assert "Do not open a PR and do not comment on the issue" in publisher.instructions
        assert "Call push_review_branch() immediately as your first action" in publisher.instructions
        assert "COMMIT_SHA:" in publisher.instructions
        assert "COMMIT_URL:" in publisher.instructions
        assert "Never ask the user for REPO, WORKDIR, BRANCH, ISSUE" in publisher.instructions
        assert publisher.required_tools == ["push_review_branch"]
        tool_names = [tool._tool_def.name for tool in publisher.tools]
        assert tool_names == ["push_review_branch"]

    def test_review_branch_mode_tightens_fix_review_loop(self):
        from repo_url_issue_pr_agent import build_pipeline

        with patch.dict(os.environ, {"AGENTSPAN_REVIEW_BRANCH_ONLY": "true"}, clear=True):
            pipeline = build_pipeline(
                "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
            )

        repo_analyst = pipeline.agents[2]
        fixer = pipeline.agents[3]
        publisher = pipeline.agents[4]

        assert "never try to create it again" in fixer.instructions
        assert "Prefer small Python scripts for code edits" in fixer.instructions
        assert "hand off to reviewer with honest results" in fixer.instructions
        assert "Keep analysis tight and practical" in repo_analyst.instructions
        assert fixer.name == "fixer"
        assert publisher.name == "publisher"
        assert all(agent.name != "coding_review_loop" for agent in pipeline.agents)
        assert repo_analyst.max_turns == 8
        assert fixer.max_turns == 12

    def test_forced_issue_skips_issue_search(self):
        from repo_url_issue_pr_agent import build_pipeline

        pipeline = build_pipeline(
            "https://github.com/pytest-dev/pytest-asyncio", 1334, ""
        )

        issue_scout = pipeline.agents[1]
        tool_names = [tool._tool_def.name for tool in issue_scout.tools]
        assert "search_repo_issues" not in tool_names
        assert "read_issue_detail" in tool_names
        assert "create_issue_branch" in tool_names
        assert "Do not call search_repo_issues" in issue_scout.instructions
        assert "Call read_issue_detail exactly once" in issue_scout.instructions
        assert issue_scout.max_turns == 8
