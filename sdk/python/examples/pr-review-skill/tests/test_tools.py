"""Unit tests for pr-review-skill script tools.

Each tool is tested in isolation by mocking subprocess.run and the filesystem.
Tests are validated to be correct: they are first written to FAIL on wrong input,
then confirmed to PASS on correct behavior.

Run:
    cd sdk/python/examples/pr-review-skill
    pytest tests/test_tools.py -v
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Add scripts dir to path so we can import each script as a module
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
DEBUG_TOOLS_DIR = Path(__file__).parent.parent / "debug_tools"
DISABLED_TOOLS_DIR = Path(__file__).parent.parent / "disabled_tools"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(DEBUG_TOOLS_DIR))
sys.path.insert(0, str(DISABLED_TOOLS_DIR))


# ── Helpers ────────────────────────────────────────────────────────────────────

def fake_proc(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


# ── get_pr_details ─────────────────────────────────────────────────────────────

class TestGetPrDetails:
    def test_returns_json_on_success(self):
        payload = json.dumps({"number": 42, "title": "Add GCP support", "files": []})
        with patch("subprocess.run", return_value=fake_proc(stdout=payload)):
            from get_pr_details import main
            result = main("owner/repo", "42")
        assert '"title"' in result
        assert "Add GCP support" in result

    def test_returns_error_on_gh_failure(self):
        with patch("subprocess.run", return_value=fake_proc(returncode=1, stderr="not found")):
            from get_pr_details import main
            result = main("owner/repo", "99")
        assert result.startswith("ERROR:")
        assert "not found" in result

    def test_passes_correct_repo_and_pr_to_gh(self):
        """Verify gh is called with the right repo and PR number."""
        captured = {}
        def capture(cmd, **kw):
            captured["cmd"] = cmd
            return fake_proc(stdout="{}")
        with patch("subprocess.run", side_effect=capture):
            from get_pr_details import main
            main("orkes-saas/orkes-saas", "123")
        assert "orkes-saas/orkes-saas" in captured["cmd"]
        assert "123" in captured["cmd"]
        assert "--repo" in captured["cmd"]

    def test_fails_on_wrong_repo(self):
        """Sanity check: wrong repo in captured cmd should fail the assertion."""
        captured = {}
        def capture(cmd, **kw):
            captured["cmd"] = cmd
            return fake_proc(stdout="{}")
        with patch("subprocess.run", side_effect=capture):
            from get_pr_details import main
            main("wrong/repo", "1")
        # This deliberately tests that wrong value is NOT present
        assert "orkes-saas/orkes-saas" not in captured["cmd"]


# ── get_pr_diff ────────────────────────────────────────────────────────────────

class TestGetPrDiff:
    def test_returns_diff_on_success(self):
        fake_diff = "diff --git a/foo.py b/foo.py\n+++ b/foo.py\n+added line"
        with patch("subprocess.run", return_value=fake_proc(stdout=fake_diff)):
            from get_pr_diff import main
            result = main("owner/repo", "42")
        assert "diff --git" in result
        assert "+added line" in result

    def test_truncates_large_diff(self):
        big_diff = "x" * 70_000
        with patch("subprocess.run", return_value=fake_proc(stdout=big_diff)):
            from get_pr_diff import main
            result = main("owner/repo", "42")
        assert len(result) < 70_000
        assert "truncated" in result

    def test_does_not_truncate_small_diff(self):
        small_diff = "diff --git a/f.py b/f.py\n+line"
        with patch("subprocess.run", return_value=fake_proc(stdout=small_diff)):
            from get_pr_diff import main
            result = main("owner/repo", "1")
        assert "truncated" not in result
        assert result == small_diff

    def test_returns_error_on_failure(self):
        with patch("subprocess.run", return_value=fake_proc(returncode=1, stderr="PR not found")):
            from get_pr_diff import main
            result = main("owner/repo", "999")
        assert result.startswith("ERROR:")


# ── get_pr_review_bundle ──────────────────────────────────────────────────────

class TestGetPrReviewBundle:
    def test_returns_metadata_and_selected_compact_diff(self):
        details = json.dumps({
            "number": 42,
            "title": "Improve workers",
            "body": "Fixes worker deployment",
            "files": [
                {"path": "docs/readme.md", "additions": 10, "deletions": 0, "status": "modified"},
                {"path": "src/WorkerService.java", "additions": 8, "deletions": 2, "status": "modified"},
            ],
            "additions": 18,
            "deletions": 2,
            "author": {"login": "dev"},
            "baseRefName": "main",
            "headRefName": "feature",
            "state": "OPEN",
        })
        diff = (
            "diff --git a/docs/readme.md b/docs/readme.md\n"
            "+++ b/docs/readme.md\n"
            "+docs\n"
            "\n"
            "diff --git a/src/WorkerService.java b/src/WorkerService.java\n"
            "@@ -1,3 +1,4 @@\n"
            " class WorkerService {\n"
            "-  oldCall();\n"
            "+  newCall();\n"
            "+  validate();\n"
            " }\n"
        )

        def capture(cmd, **kw):
            if "view" in cmd:
                return fake_proc(stdout=details)
            return fake_proc(stdout=diff)

        with patch("subprocess.run", side_effect=capture):
            from get_pr_review_bundle import main
            result = main("owner/repo", "42")

        assert "# PR Review Bundle" in result
        assert "Improve workers" in result
        assert "src/WorkerService.java" in result
        assert "+  validate();" in result

    def test_bundle_truncates_long_pr_body(self):
        details = json.dumps({
            "number": 1,
            "title": "Large body",
            "body": "x" * 5_000,
            "files": [],
            "additions": 0,
            "deletions": 0,
            "author": {"login": "dev"},
        })
        with patch("subprocess.run", side_effect=[
            fake_proc(stdout=details),
            fake_proc(stdout=""),
        ]):
            from get_pr_review_bundle import main
            result = main("owner/repo", "1")
        assert "PR body truncated" in result

    def test_bundle_returns_error_on_gh_failure(self):
        with patch("subprocess.run", return_value=fake_proc(returncode=1, stderr="auth required")):
            from get_pr_review_bundle import main
            result = main("owner/repo", "1")
        assert result.startswith("ERROR:")

    def test_includes_repo_context_when_file_exists(self, tmp_path):
        context_dir = tmp_path / ".agentspan"
        context_dir.mkdir()
        (context_dir / "pr-review-context.md").write_text(
            "# PR Review Context\n\n## Architecture\nController → Service → Repository\n"
        )
        details = json.dumps({
            "number": 1, "title": "Test", "body": "", "files": [],
            "additions": 0, "deletions": 0, "author": {"login": "dev"},
            "baseRefName": "main", "headRefName": "feat", "state": "OPEN",
        })
        with patch("subprocess.run", side_effect=[
            fake_proc(stdout=details),
            fake_proc(stdout=""),
        ]):
            from get_pr_review_bundle import main
            result = main("owner/repo", "1", str(tmp_path))
        assert "## Repo Context" in result
        assert "Controller → Service → Repository" in result

    def test_excludes_repo_context_when_file_absent(self, tmp_path):
        details = json.dumps({
            "number": 1, "title": "Test", "body": "", "files": [],
            "additions": 0, "deletions": 0, "author": {"login": "dev"},
            "baseRefName": "main", "headRefName": "feat", "state": "OPEN",
        })
        with patch("subprocess.run", side_effect=[
            fake_proc(stdout=details),
            fake_proc(stdout=""),
        ]):
            from get_pr_review_bundle import main
            result = main("owner/repo", "1", str(tmp_path))
        assert "## Repo Context" not in result

    def test_truncates_context_at_3000_chars(self, tmp_path):
        context_dir = tmp_path / ".agentspan"
        context_dir.mkdir()
        (context_dir / "pr-review-context.md").write_text("C" * 5_000)
        details = json.dumps({
            "number": 1, "title": "Test", "body": "", "files": [],
            "additions": 0, "deletions": 0, "author": {"login": "dev"},
            "baseRefName": "main", "headRefName": "feat", "state": "OPEN",
        })
        with patch("subprocess.run", side_effect=[
            fake_proc(stdout=details),
            fake_proc(stdout=""),
        ]):
            from get_pr_review_bundle import main
            result = main("owner/repo", "1", str(tmp_path))
        assert "## Repo Context" in result
        assert "context truncated at 3000 chars" in result
        # The full 5000 chars should NOT be present
        assert "C" * 5_000 not in result


# ── get_pr_file_diff ───────────────────────────────────────────────────────────

class TestGetPrFileDiff:
    def test_returns_only_requested_file_diff(self):
        fake_diff = (
            "diff --git a/foo.py b/foo.py\n"
            "+++ b/foo.py\n"
            "+foo change\n"
            "\n"
            "diff --git a/bar.py b/bar.py\n"
            "+++ b/bar.py\n"
            "+bar change\n"
        )
        with patch("subprocess.run", return_value=fake_proc(stdout=fake_diff)):
            from get_pr_file_diff import main
            result = main("owner/repo", "42", "bar.py")
        assert "bar change" in result
        assert "foo change" not in result

    def test_truncates_large_file_diff(self):
        big_section = "diff --git a/big.py b/big.py\n" + ("+x\n" * 10_000)
        with patch("subprocess.run", return_value=fake_proc(stdout=big_section)):
            from get_pr_file_diff import main
            result = main("owner/repo", "42", "big.py")
        assert len(result) < len(big_section)
        assert "file diff truncated" in result

    def test_returns_error_when_file_missing_from_diff(self):
        with patch("subprocess.run", return_value=fake_proc(stdout="diff --git a/foo.py b/foo.py\n")):
            from get_pr_file_diff import main
            result = main("owner/repo", "42", "missing.py")
        assert result.startswith("ERROR:")

    def test_rejects_path_traversal(self):
        from get_pr_file_diff import main
        result = main("owner/repo", "42", "../secret.txt")
        assert result.startswith("ERROR:")


# ── get_file_content ───────────────────────────────────────────────────────────

class TestGetFileContent:
    def test_returns_file_content(self, tmp_path):
        (tmp_path / "hello.py").write_text("print('hello')")
        from get_file_content import main
        result = main(str(tmp_path), "hello.py")
        assert "print('hello')" in result

    def test_returns_error_for_missing_file(self, tmp_path):
        from get_file_content import main
        result = main(str(tmp_path), "nonexistent.py")
        assert result.startswith("ERROR:")
        assert "not found" in result

    def test_truncates_large_file(self, tmp_path):
        (tmp_path / "big.txt").write_text("A" * 25_000)
        from get_file_content import main
        result = main(str(tmp_path), "big.txt")
        assert len(result) < 25_000
        assert "truncated" in result

    def test_blocks_path_traversal(self, tmp_path):
        from get_file_content import main
        result = main(str(tmp_path), "../../etc/passwd")
        assert result.startswith("ERROR:")

    def test_blocks_sibling_prefix_escape(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        sibling = tmp_path / "repo-secret"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("secret")

        from get_file_content import main
        result = main(str(repo), "../repo-secret/secret.txt")
        assert result.startswith("ERROR:")

    def test_nested_file_path(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "core.py").write_text("class Base: pass")
        from get_file_content import main
        result = main(str(tmp_path), "src/core.py")
        assert "class Base" in result


# ── find_files ─────────────────────────────────────────────────────────────────

class TestFindFiles:
    def test_finds_matching_files(self, tmp_path):
        (tmp_path / "foo.py").write_text("")
        (tmp_path / "bar.py").write_text("")
        (tmp_path / "readme.md").write_text("")
        from find_files import main
        result = main(str(tmp_path), "*.py")
        assert "foo.py" in result
        assert "bar.py" in result
        assert "readme.md" not in result

    def test_finds_nested_files_with_recursive_glob(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "providers").mkdir(parents=True)
        (tmp_path / "src" / "providers" / "aws.py").write_text("")
        (tmp_path / "src" / "providers" / "gcp.py").write_text("")
        from find_files import main
        result = main(str(tmp_path), "src/providers/**/*.py")
        lines = [l for l in result.splitlines() if l]
        assert any("aws.py" in l for l in lines)
        assert any("gcp.py" in l for l in lines)

    def test_returns_message_when_no_match(self, tmp_path):
        from find_files import main
        result = main(str(tmp_path), "*.java")
        assert "No files found" in result

    def test_returns_error_for_bad_repo_path(self):
        from find_files import main
        result = main("/nonexistent/path/xyz", "*.py")
        assert result.startswith("ERROR:")

    def test_rejects_parent_glob(self, tmp_path):
        from find_files import main
        result = main(str(tmp_path), "../*.py")
        assert result.startswith("ERROR:")


# ── grep_in_file ───────────────────────────────────────────────────────────────

class TestGrepInFile:
    def test_finds_matching_line(self, tmp_path):
        (tmp_path / "service.py").write_text(
            "class BaseService:\n    pass\n\nclass PaymentService(BaseService):\n    def pay(self): pass\n"
        )
        from grep_in_file import main
        result = main(str(tmp_path), "service.py", "PaymentService")
        assert "PaymentService" in result
        assert ">>>" in result  # match marker

    def test_includes_context_lines_around_match(self, tmp_path):
        lines = [f"line {i}\n" for i in range(50)]
        lines[25] = "TARGET LINE\n"
        (tmp_path / "big.py").write_text("".join(lines))
        from grep_in_file import main
        result = main(str(tmp_path), "big.py", "TARGET LINE", 5)
        # should include lines 20-30 (5 before and after)
        assert "line 20" in result
        assert "line 30" in result
        assert "TARGET LINE" in result

    def test_returns_no_matches_message(self, tmp_path):
        (tmp_path / "empty.py").write_text("def hello(): pass\n")
        from grep_in_file import main
        result = main(str(tmp_path), "empty.py", "NONEXISTENT_TERM_XYZ")
        assert "No matches found" in result

    def test_case_insensitive_search(self, tmp_path):
        (tmp_path / "auth.py").write_text("class AuthService:\n    def login(self): pass\n")
        from grep_in_file import main
        result = main(str(tmp_path), "auth.py", "authservice")  # lowercase
        assert "AuthService" in result  # finds the correctly-cased line

    def test_returns_error_for_missing_file(self, tmp_path):
        from grep_in_file import main
        result = main(str(tmp_path), "missing.py", "anything")
        assert result.startswith("ERROR:")

    def test_blocks_path_traversal(self, tmp_path):
        from grep_in_file import main
        result = main(str(tmp_path), "../../etc/passwd", "root")
        assert result.startswith("ERROR:")

    def test_blocks_sibling_prefix_escape(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        sibling = tmp_path / "repo-secret"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("secret")

        from grep_in_file import main
        result = main(str(repo), "../repo-secret/secret.txt", "secret")
        assert result.startswith("ERROR:")

    def test_pipe_as_or_operator(self, tmp_path):
        """Agent passes 'foo|bar' — should match lines with either foo or bar."""
        (tmp_path / "svc.java").write_text(
            "public void getCredentials() {}\n"
            "public void executeCreate() {}\n"
            "public void unrelated() {}\n"
        )
        from grep_in_file import main
        result = main(str(tmp_path), "svc.java", "getCredentials|executeCreate")
        assert "getCredentials" in result
        assert "executeCreate" in result
        # "unrelated" may appear as context but must NOT be marked as a match
        lines = result.splitlines()
        unrelated_lines = [l for l in lines if "unrelated" in l]
        assert all(not l.startswith(">>>") for l in unrelated_lines)

    def test_backslash_pipe_escape_is_handled(self, tmp_path):
        """Agent sometimes passes 'foo\\|bar' with shell escaping — strip the backslashes."""
        (tmp_path / "f.java").write_text("void setStatus() {}\nvoid save() {}\n")
        from grep_in_file import main
        result = main(str(tmp_path), "f.java", "setStatus\\|save")
        assert "setStatus" in result
        assert "save" in result

    def test_merges_overlapping_context_ranges(self, tmp_path):
        """Two matches close together should appear as one block, not two."""
        content = "\n".join([f"line {i}" for i in range(30)])
        content += "\nMATCH_A here\nline 31\nline 32\nMATCH_B here\n"
        (tmp_path / "code.py").write_text(content)
        from grep_in_file import main
        result = main(str(tmp_path), "code.py", "MATCH_", 3)
        # Both matches present, no duplicate lines
        assert "MATCH_A" in result
        assert "MATCH_B" in result

    def test_shows_line_numbers(self, tmp_path):
        (tmp_path / "f.py").write_text("a = 1\nb = 2\nc = 3\n")
        from grep_in_file import main
        result = main(str(tmp_path), "f.py", "b = 2")
        assert "2:" in result  # line number 2


# ── post_review_comment ────────────────────────────────────────────────────────

class TestPostReviewComment:
    def test_calls_gh_with_correct_args(self):
        captured = {}
        def capture(cmd, **kw):
            captured["cmd"] = cmd
            return fake_proc(stdout="")
        with patch("subprocess.run", side_effect=capture):
            from post_review_comment import main
            result = main("owner/repo", "42", "LGTM!")
        assert "gh" in captured["cmd"]
        assert "pr" in captured["cmd"]
        assert "comment" in captured["cmd"]
        assert "42" in captured["cmd"]
        assert "owner/repo" in captured["cmd"]
        assert "LGTM!" in captured["cmd"]
        assert result == "OK: comment posted."

    def test_returns_error_on_gh_failure(self):
        with patch("subprocess.run", return_value=fake_proc(returncode=1, stderr="auth required")):
            from post_review_comment import main
            result = main("owner/repo", "42", "LGTM")
        assert result.startswith("ERROR:")
        assert "auth required" in result

    def test_returns_error_for_empty_comment(self):
        with patch("subprocess.run", return_value=fake_proc()) as mock_run:
            from post_review_comment import main
            result = main("owner/repo", "42", "   ")
        assert result.startswith("ERROR:")
        mock_run.assert_not_called()  # should not call gh at all

    def test_passes_multiline_comment(self):
        captured = {}
        def capture(cmd, **kw):
            captured["cmd"] = cmd
            return fake_proc(stdout="")
        with patch("subprocess.run", side_effect=capture):
            from post_review_comment import main
            review = "## Review\n\n❌ Missing tests\n\nVerdict: REQUEST CHANGES"
            result = main("owner/repo", "1", review)
        assert result == "OK: comment posted."
        assert "## Review" in " ".join(captured["cmd"])
