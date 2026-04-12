"""Tests for doc_reader integration tools.

All tests are real e2e — no mocks. Tests that require optional dependencies
(markitdown, langextract) are skipped if those packages are not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.integrations.doc_reader.tools import get_tools, read_document


# Check optional dependency availability
def _has_markitdown() -> bool:
    try:
        import markitdown  # noqa: F401
        return True
    except ImportError:
        return False


def _has_langextract() -> bool:
    try:
        import langextract  # noqa: F401
        return True
    except ImportError:
        return False


class TestReadDocument:
    """Test document reading with real files and real extractors."""

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

    def test_reads_csv_file(self, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25\n")
        result = read_document(str(f))
        assert "Alice" in result
        assert "Bob" in result

    def test_reads_yaml_file(self, tmp_path: Path):
        f = tmp_path / "config.yaml"
        f.write_text("server:\n  port: 8080\n  host: localhost\n")
        result = read_document(str(f))
        assert "port" in result
        assert "8080" in result

    def test_reads_toml_file(self, tmp_path: Path):
        f = tmp_path / "config.toml"
        f.write_text('[project]\nname = "test"\nversion = "1.0"\n')
        result = read_document(str(f))
        assert "test" in result

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_document(str(tmp_path / "nope.pdf"))

    def test_directory_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_document(str(tmp_path))

    @pytest.mark.skipif(not _has_markitdown(), reason="markitdown not installed")
    def test_reads_html_with_markitdown(self, tmp_path: Path):
        """Real test: create an HTML file and extract with markitdown."""
        f = tmp_path / "page.html"
        f.write_text(
            "<html><body><h1>Test Page</h1>"
            "<p>This is a test paragraph with important content.</p>"
            "</body></html>"
        )
        result = read_document(str(f))
        assert "Test Page" in result
        assert "important content" in result

    def test_unsupported_binary_format_raises(self, tmp_path: Path):
        """A truly unsupported format should raise RuntimeError."""
        f = tmp_path / "data.xyz"
        f.write_bytes(b"\x00\x01\x02\x03unknown binary format")
        # This should fail since .xyz is not a plain text extension
        # and markitdown/langextract won't recognize it
        with pytest.raises(RuntimeError):
            read_document(str(f))


class TestGetTools:
    def test_returns_read_document(self):
        tools = get_tools()
        assert len(tools) == 1
        assert tools[0]._tool_def.name == "read_document"

    def test_tool_has_description(self):
        tools = get_tools()
        assert tools[0]._tool_def.description
        assert "document" in tools[0]._tool_def.description.lower()
