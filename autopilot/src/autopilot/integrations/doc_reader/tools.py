"""Document reader tools — extract text from various file formats."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from agentspan.agents import tool


_PLAIN_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}


def _read_with_markitdown(path: str) -> str:
    """Try reading with markitdown (handles Office docs, HTML, etc.)."""
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(path)
    return result.text_content


def _read_with_langextract(path: str) -> str:
    """Fallback PDF reader using langextract."""
    import langextract

    result = langextract.extract(path)
    return result.text


@tool
def read_document(path: str) -> str:
    """Read a document and extract its text content.

    Supports PDF, Office documents (docx, xlsx, pptx), HTML, and plain text.
    Uses markitdown as the primary extractor with langextract as a PDF fallback.

    Args:
        path: Path to the document file.

    Returns:
        Extracted text content.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    # Plain text files — read directly
    if p.suffix.lower() in _PLAIN_EXTENSIONS:
        return p.read_text(encoding="utf-8")

    # Try markitdown first
    try:
        text = _read_with_markitdown(str(p))
        if text and text.strip():
            return text
    except Exception:
        pass

    # For PDFs, fall back to langextract
    if p.suffix.lower() == ".pdf":
        try:
            return _read_with_langextract(str(p))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read PDF {p}: neither markitdown nor langextract succeeded"
            ) from exc

    raise RuntimeError(f"Unsupported file format: {p.suffix}")


def get_tools() -> List[Any]:
    """Return all doc_reader tools."""
    return [read_document]
