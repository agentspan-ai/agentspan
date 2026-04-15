"""Tests for local_fs integration tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from autopilot.integrations.local_fs.tools import (
    find_files,
    get_tools,
    list_dir,
    read_file,
    search_in_files,
    write_file,
)


class TestReadFile:
    def test_reads_existing_file(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("world")
        assert read_file(str(f)) == "world"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_file(str(tmp_path / "nope.txt"))


class TestWriteFile:
    def test_writes_and_creates_parents(self, tmp_path: Path):
        target = tmp_path / "sub" / "deep" / "out.txt"
        result = write_file(str(target), "content here")

        assert target.read_text() == "content here"
        assert "12 bytes" in result


class TestListDir:
    def test_lists_entries(self, tmp_path: Path):
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "subdir").mkdir()

        entries = list_dir(str(tmp_path))
        assert "a.txt" in entries
        assert "b.txt" in entries
        assert "subdir" in entries

    def test_not_a_directory_raises(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.touch()
        with pytest.raises(NotADirectoryError):
            list_dir(str(f))


class TestFindFiles:
    def test_finds_matching_files(self, tmp_path: Path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.txt").touch()
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.py").touch()

        results = find_files(str(tmp_path), "*.py")
        assert "a.py" in results
        assert str(Path("sub") / "c.py") in results
        assert "b.txt" not in results


class TestSearchInFiles:
    def test_finds_matching_lines(self, tmp_path: Path):
        (tmp_path / "code.py").write_text("def hello():\n    pass\ndef world():\n    pass\n")

        results = search_in_files(str(tmp_path), "def", "*.py")
        assert len(results) == 2
        assert "code.py:1:" in results[0]
        assert "code.py:3:" in results[1]

    def test_no_matches_returns_empty(self, tmp_path: Path):
        (tmp_path / "code.py").write_text("nothing here\n")
        results = search_in_files(str(tmp_path), "foobar", "*.py")
        assert results == []


class TestGetTools:
    def test_returns_all_tools(self):
        tools = get_tools()
        names = [t._tool_def.name for t in tools]
        assert "read_file" in names
        assert "write_file" in names
        assert "list_dir" in names
        assert "find_files" in names
        assert "search_in_files" in names
