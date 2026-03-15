"""Locate the nearest .env file by walking up from CWD."""

from pathlib import Path


def find_dotenv() -> str:
    """Walk up from CWD to find .env. Returns path string for pydantic-settings."""
    d = Path.cwd().resolve()
    while d != d.parent:
        if (d / ".env").is_file():
            return str(d / ".env")
        d = d.parent
    return ""
