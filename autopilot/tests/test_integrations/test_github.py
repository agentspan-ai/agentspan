"""Tests for GitHub integration tools."""

from __future__ import annotations

import pytest

from autopilot.integrations.github.tools import (
    get_tools,
    github_create_issue,
    github_get_issue,
    github_get_pr,
    github_list_issues,
    github_list_prs,
    github_search_repos,
)


@pytest.mark.network
class TestGithubSearchRepos:
    """github_search_repos uses the public search API (no auth required).

    Marked as network — GitHub rate-limits unauthenticated requests.
    """

    def test_search_returns_results(self):
        results = github_search_repos("python")
        assert isinstance(results, list)
        assert len(results) > 0, "Public repo search for 'python' must return results"

    def test_result_has_expected_keys(self):
        results = github_search_repos("python")
        first = results[0]
        for key in ("name", "full_name", "description", "html_url", "stargazers_count", "language"):
            assert key in first, f"Missing key: {key}"

    def test_search_no_results_for_gibberish(self):
        results = github_search_repos("zzzzz_no_repo_exists_xyzzy_99999")
        assert isinstance(results, list)
        # This may return 0 or very few results; either way it should not error
        assert len(results) < 5


class TestGithubAuthRequired:
    """Tools that require GITHUB_TOKEN raise RuntimeError when it is missing."""

    def test_list_issues_requires_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
            github_list_issues("octocat", "hello-world")

    def test_get_issue_requires_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
            github_get_issue("octocat", "hello-world", 1)

    def test_create_issue_requires_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
            github_create_issue("octocat", "hello-world", "title", "body")

    def test_list_prs_requires_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
            github_list_prs("octocat", "hello-world")

    def test_get_pr_requires_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
            github_get_pr("octocat", "hello-world", 1)


class TestGithubToolDefs:
    """Verify tool_def metadata is correct."""

    def test_credentials_on_search_repos(self):
        assert github_search_repos._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_credentials_on_list_issues(self):
        assert github_list_issues._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_credentials_on_create_issue(self):
        assert github_create_issue._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_credentials_on_list_prs(self):
        assert github_list_prs._tool_def.credentials == ["GITHUB_TOKEN"]

    def test_credentials_on_get_pr(self):
        assert github_get_pr._tool_def.credentials == ["GITHUB_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = sorted(t._tool_def.name for t in tools)
        assert names == sorted([
            "github_search_repos",
            "github_list_issues",
            "github_get_issue",
            "github_create_issue",
            "github_list_prs",
            "github_get_pr",
        ])

    def test_tool_count(self):
        assert len(get_tools()) == 6
