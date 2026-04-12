"""Tests for Google Drive integration tools."""

from __future__ import annotations

import pytest

from autopilot.integrations.google_drive.tools import (
    gdrive_list_files,
    gdrive_read_file,
    gdrive_search,
    get_tools,
)


class TestGDriveCredentialValidation:
    """All Google Drive tools require GOOGLE_DRIVE_TOKEN and must raise when missing."""

    def test_list_files_requires_token(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_DRIVE_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GOOGLE_DRIVE_TOKEN"):
            gdrive_list_files()

    def test_read_file_requires_token(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_DRIVE_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GOOGLE_DRIVE_TOKEN"):
            gdrive_read_file("some-file-id")

    def test_search_requires_token(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_DRIVE_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GOOGLE_DRIVE_TOKEN"):
            gdrive_search("test query")


class TestGDriveToolDefs:
    """Verify tool_def metadata is correct."""

    def test_list_files_credentials(self):
        assert gdrive_list_files._tool_def.credentials == ["GOOGLE_DRIVE_TOKEN"]

    def test_read_file_credentials(self):
        assert gdrive_read_file._tool_def.credentials == ["GOOGLE_DRIVE_TOKEN"]

    def test_search_credentials(self):
        assert gdrive_search._tool_def.credentials == ["GOOGLE_DRIVE_TOKEN"]


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = sorted(t._tool_def.name for t in tools)
        assert names == sorted([
            "gdrive_list_files",
            "gdrive_read_file",
            "gdrive_search",
        ])

    def test_tool_count(self):
        assert len(get_tools()) == 3
