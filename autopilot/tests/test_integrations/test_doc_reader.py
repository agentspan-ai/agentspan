"""Tests for doc_reader integration tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopilot.integrations.doc_reader.tools import get_tools, read_document


class TestReadDocument:
    def test_reads_plain_text(self, tmp_path: Path):
        f = tmp_path / "readme.md"
        f.write_text("# Hello World\nSome content.")

        result = read_document(str(f))
        assert "Hello World" in result

    def test_reads_txt_file(self, tmp_path: Path):
        f = tmp_path / "notes.txt"
        f.write_text("Plain text notes.")

        result = read_document(str(f))
        assert result == "Plain text notes."

    def test_reads_json_file(self, tmp_path: Path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')

        result = read_document(str(f))
        assert '"key"' in result

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_document(str(tmp_path / "nope.pdf"))

    def test_uses_markitdown_for_docx(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "report.docx"
        f.write_bytes(b"fake docx content")

        mock_md = MagicMock()
        mock_result = MagicMock()
        mock_result.text_content = "Extracted document text"
        mock_md.convert.return_value = mock_result

        monkeypatch.setattr(
            "autopilot.integrations.doc_reader.tools._read_with_markitdown",
            lambda path: "Extracted document text",
        )

        result = read_document(str(f))
        assert result == "Extracted document text"

    def test_pdf_falls_back_to_langextract(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "paper.pdf"
        f.write_bytes(b"fake pdf content")

        # markitdown fails
        monkeypatch.setattr(
            "autopilot.integrations.doc_reader.tools._read_with_markitdown",
            MagicMock(side_effect=ImportError("no markitdown")),
        )
        # langextract succeeds
        monkeypatch.setattr(
            "autopilot.integrations.doc_reader.tools._read_with_langextract",
            lambda path: "PDF text from langextract",
        )

        result = read_document(str(f))
        assert result == "PDF text from langextract"

    def test_unsupported_format_raises(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "data.xyz"
        f.write_bytes(b"unknown format")

        # markitdown fails
        monkeypatch.setattr(
            "autopilot.integrations.doc_reader.tools._read_with_markitdown",
            MagicMock(side_effect=ImportError("nope")),
        )

        with pytest.raises(RuntimeError, match="Unsupported file format"):
            read_document(str(f))


class TestGetTools:
    def test_returns_read_document(self):
        tools = get_tools()
        assert len(tools) == 1
        assert tools[0]._tool_def.name == "read_document"
