"""Unit tests for the checks-only sandbox."""

from __future__ import annotations

import os
import tempfile

import pytest

from agentspan.harness.sandbox import ChecksOnlySandbox


@pytest.fixture
def repo_root():
    with tempfile.TemporaryDirectory() as td:
        # Create a known structure
        os.makedirs(os.path.join(td, "src"))
        with open(os.path.join(td, "src", "main.py"), "w") as f:
            f.write("x = 1\n")
        yield td


def test_path_read_allowed_under_root(repo_root):
    sb = ChecksOnlySandbox(allowed_read_roots=[repo_root])
    res = sb.check_path_read(os.path.join(repo_root, "src", "main.py"))
    assert res.allowed, res.reason


def test_path_read_denied_outside_root(repo_root):
    sb = ChecksOnlySandbox(allowed_read_roots=[repo_root])
    res = sb.check_path_read("/etc/passwd")
    assert not res.allowed
    assert "not under" in res.reason


def test_path_write_requires_explicit_root(repo_root):
    sb = ChecksOnlySandbox(allowed_read_roots=[repo_root], allowed_write_roots=[])
    res = sb.check_path_write(os.path.join(repo_root, "src", "main.py"))
    assert not res.allowed
    assert "no allowed_write_roots" in res.reason


def test_denied_paths_take_precedence(repo_root):
    secret = os.path.join(repo_root, ".env")
    with open(secret, "w") as f:
        f.write("SECRET=1")
    sb = ChecksOnlySandbox(
        allowed_read_roots=[repo_root],
        denied_paths=[secret],
    )
    assert not sb.check_path_read(secret).allowed


def test_command_allowlist():
    sb = ChecksOnlySandbox(allowed_commands=["git", "gh"])
    assert sb.check_command("git status").allowed
    assert sb.check_command("git log --oneline").allowed
    assert not sb.check_command("rm -rf /").allowed
    assert not sb.check_command("curl bad.com").allowed


def test_always_blocked_commands_require_explicit_allow():
    sb = ChecksOnlySandbox(allowed_commands=["git"])
    assert not sb.check_command("sudo rm /etc/passwd").allowed
    sb_with_sudo = ChecksOnlySandbox(allowed_commands=["sudo"])
    # 'sudo' in allowlist overrides the always-block rule
    assert sb_with_sudo.check_command("sudo ls").allowed


def test_command_with_env_prefix():
    sb = ChecksOnlySandbox(allowed_commands=["git"])
    assert sb.check_command("FOO=bar git status").allowed


def test_url_https_allowed_when_no_allowlist():
    sb = ChecksOnlySandbox(block_private_networks=True)
    assert sb.check_url("https://api.github.com/repos/foo/bar").allowed


def test_url_blocks_private_networks():
    sb = ChecksOnlySandbox(block_private_networks=True)
    assert not sb.check_url("http://localhost:8080/admin").allowed
    assert not sb.check_url("http://127.0.0.1/").allowed
    assert not sb.check_url("http://192.168.1.1/").allowed
    assert not sb.check_url("http://10.0.0.1/").allowed


def test_url_host_allowlist():
    sb = ChecksOnlySandbox(allowed_url_hosts=["api.github.com", "*.example.com"])
    assert sb.check_url("https://api.github.com/x").allowed
    assert sb.check_url("https://foo.example.com/bar").allowed
    assert not sb.check_url("https://malicious.com/").allowed


def test_url_rejects_unknown_scheme():
    sb = ChecksOnlySandbox()
    assert not sb.check_url("file:///etc/passwd").allowed
    assert not sb.check_url("ftp://example.com").allowed
