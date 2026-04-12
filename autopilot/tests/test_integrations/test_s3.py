"""Tests for S3 integration tools."""

from __future__ import annotations

import pytest

from autopilot.integrations.s3.tools import (
    get_tools,
    s3_list_buckets,
    s3_list_objects,
    s3_read_object,
    s3_write_object,
)


class TestS3CredentialValidation:
    """All S3 tools require AWS credentials and must raise when missing."""

    def test_list_objects_requires_access_key(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID"):
            s3_list_objects("my-bucket")

    def test_list_objects_requires_secret_key(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AWS_SECRET_ACCESS_KEY"):
            s3_list_objects("my-bucket")

    def test_read_object_requires_credentials(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID"):
            s3_read_object("my-bucket", "key.txt")

    def test_write_object_requires_credentials(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID"):
            s3_write_object("my-bucket", "key.txt", "content")

    def test_list_buckets_requires_credentials(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID"):
            s3_list_buckets()


class TestS3ToolDefs:
    """Verify tool_def metadata is correct."""

    def test_list_objects_credentials(self):
        assert s3_list_objects._tool_def.credentials == [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]

    def test_read_object_credentials(self):
        assert s3_read_object._tool_def.credentials == [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]

    def test_write_object_credentials(self):
        assert s3_write_object._tool_def.credentials == [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]

    def test_list_buckets_credentials(self):
        assert s3_list_buckets._tool_def.credentials == [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = sorted(t._tool_def.name for t in tools)
        assert names == sorted([
            "s3_list_objects",
            "s3_read_object",
            "s3_write_object",
            "s3_list_buckets",
        ])

    def test_tool_count(self):
        assert len(get_tools()) == 4
