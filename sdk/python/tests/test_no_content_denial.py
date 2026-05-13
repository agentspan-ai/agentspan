"""Verify the inspection tools never *deny content* on dedup/repeat paths.

The pattern bug: a tool detects "you already saw this" and replaces the
result with a short "use content from your context window" string with no
data. After condensation drops the prior message, the agent retries —
gets the same stub — and is stuck. This test file pins the contract that
every repeat path returns the actual content alongside any warning.

Three regressions covered:
  1. grep_search dedup (was clipping cached result to 500 chars).
  2. read_symbol dedup (was returning a "unchanged" string with no body).
  3. read_file repeat-read cap (was returning a bare error on the 4th read).

All exercised with the real ``@tool``-decorated functions; no fakes.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXAMPLES_DIR = (Path(__file__).resolve().parent.parent / "examples").resolve()
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

import _issue_fixer_tools as ift  # noqa: E402


def _setup(tmp_path: Path) -> Path:
    """Configure the tools to use ``tmp_path`` as the repo workdir; create
    a small file with enough content to make truncation/denial visible.
    """
    ift.set_working_dir(str(tmp_path))
    # Clear any cross-test state that lives in process globals.
    ift._grep_cache.clear()
    ift._symbol_read_hashes.clear()
    ift._read_file_count.clear()
    return tmp_path


def test_grep_search_repeat_returns_full_cached_result(tmp_path: Path) -> None:
    """Issuing the same grep twice must return the FULL cached result the
    second time, not a 500-char stub. Tests the dedup path at line 899.
    """
    _setup(tmp_path)
    # Big file so the grep result is well over 500 chars.
    big = tmp_path / "big.py"
    body_lines = [f"def function_{i}_marker():  pass" for i in range(120)]
    big.write_text("\n".join(body_lines), encoding="utf-8")

    first = ift.grep_search(
        pattern="function_.*_marker", path=".", glob_filter="*.py", max_results=200
    )
    # The grep result references the file path on every match line, so it's
    # easily over a few thousand chars for 120 matches.
    assert "function_0_marker" in first
    assert "function_119_marker" in first
    assert len(first) > 500, f"first result expected > 500 chars, got {len(first)}"

    second = ift.grep_search(
        pattern="function_.*_marker", path=".", glob_filter="*.py", max_results=200
    )

    assert "REPEAT SEARCH" in second, "must warn that this is a repeat"
    # Both ends of the match range must be present on the repeat — proves
    # we're not clipping to a 500-char head.
    assert "function_0_marker" in second
    assert "function_119_marker" in second, (
        "repeat path must return the FULL cached result, not a 500-char clip "
        f"(got {len(second)} chars)"
    )
    # And concretely: the cached body must appear in full inside the
    # second response.
    assert first in second


def test_read_symbol_repeat_returns_full_body(tmp_path: Path) -> None:
    """Re-reading the same symbol must return the symbol body again, with a
    repeat warning header — NOT a bare "unchanged since last read" stub.
    """
    _setup(tmp_path)
    src = tmp_path / "mod.py"
    src.write_text(
        "\n".join(
            [
                "def small_fn():",
                "    return 1",
                "",
                "def my_target():",
                "    body_line_a = 1",
                "    body_line_b = 2",
                "    body_line_c = 3",
                "    return body_line_a + body_line_b + body_line_c",
                "",
            ]
        ),
        encoding="utf-8",
    )

    first = ift.read_symbol(path="mod.py", name="my_target")
    assert "body_line_a" in first
    assert "body_line_b" in first
    assert "body_line_c" in first

    second = ift.read_symbol(path="mod.py", name="my_target")

    assert "REPEAT READ of symbol" in second
    # Body MUST still be present on the repeat.
    assert "body_line_a" in second, (
        "repeat read must return the symbol body, not just an 'unchanged' stub"
    )
    assert "body_line_b" in second
    assert "body_line_c" in second


def test_read_file_past_repeat_limit_still_returns_content(tmp_path: Path) -> None:
    """The 4th and later reads must keep returning the file body with a
    stronger warning header — NOT an "Error: repeat read limit exceeded"
    with no content.
    """
    _setup(tmp_path)
    f = tmp_path / "fixture.py"
    body = "DISTINCTIVE_MARKER_LINE\n" + ("filler line\n" * 50)
    f.write_text(body, encoding="utf-8")

    results = []
    for _ in range(5):  # past _MAX_REPEAT_FILE_READS = 3
        results.append(ift.read_file(path="fixture.py"))

    # Every read returns the file body (no Error replacement).
    for i, r in enumerate(results):
        assert "DISTINCTIVE_MARKER_LINE" in r, (
            f"read #{i + 1} must return the file body, not a bare error. got:\n{r[:300]}"
        )
        assert not r.startswith("Error:"), (
            f"read #{i + 1} must NOT be replaced by an Error message; got:\n{r[:200]}"
        )

    # The 4th read should carry the stronger STOP RE-READING signal.
    assert "STOP RE-READING" in results[3] or "STOP RE-READING" in results[4]
