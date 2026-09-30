"""Google Drive integration tools — file listing, reading, and search."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool

_BASE_URL = "https://www.googleapis.com/drive/v3"

# Google Docs MIME types that should be exported as plain text
_GOOGLE_DOC_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _gdrive_headers() -> Dict[str, str]:
    """Return headers for Google Drive API, raising if token is missing."""
    token = os.environ.get("GOOGLE_DRIVE_TOKEN", "")
    if not token:
        raise RuntimeError("GOOGLE_DRIVE_TOKEN environment variable is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _format_file(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant fields from a Drive file resource."""
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "mimeType": item.get("mimeType", ""),
        "modifiedTime": item.get("modifiedTime", ""),
        "size": item.get("size", ""),
        "webViewLink": item.get("webViewLink", ""),
    }


@tool(credentials=["GOOGLE_DRIVE_TOKEN"])
def gdrive_list_files(folder_id: str = "root", query: str = "") -> List[Dict[str, Any]]:
    """List files in a Google Drive folder.

    Args:
        folder_id: Drive folder ID (default ``"root"`` for top-level).
        query: Optional additional Drive query filter.

    Returns:
        List of file dicts with ``id``, ``name``, ``mimeType``,
        ``modifiedTime``, ``size``, and ``webViewLink`` keys.
    """
    headers = _gdrive_headers()

    q_parts = [f"'{folder_id}' in parents", "trashed = false"]
    if query:
        q_parts.append(query)
    q = " and ".join(q_parts)

    resp = httpx.get(
        f"{_BASE_URL}/files",
        params={
            "q": q,
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
            "pageSize": 50,
        },
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()

    return [_format_file(f) for f in resp.json().get("files", [])]


@tool(credentials=["GOOGLE_DRIVE_TOKEN"])
def gdrive_read_file(file_id: str) -> str:
    """Read the content of a Google Drive file.

    For Google Docs/Sheets/Slides, the content is exported as plain text.
    For regular files, the raw content is downloaded.

    Args:
        file_id: The Drive file ID.

    Returns:
        The file content as a string.
    """
    headers = _gdrive_headers()

    # First get file metadata to determine type
    meta_resp = httpx.get(
        f"{_BASE_URL}/files/{file_id}",
        params={"fields": "id,name,mimeType"},
        headers=headers,
        timeout=15.0,
    )
    meta_resp.raise_for_status()
    mime_type = meta_resp.json().get("mimeType", "")

    # Google Docs types need export
    export_mime = _GOOGLE_DOC_TYPES.get(mime_type)
    if export_mime:
        resp = httpx.get(
            f"{_BASE_URL}/files/{file_id}/export",
            params={"mimeType": export_mime},
            headers=headers,
            timeout=30.0,
        )
    else:
        resp = httpx.get(
            f"{_BASE_URL}/files/{file_id}",
            params={"alt": "media"},
            headers=headers,
            timeout=30.0,
        )

    resp.raise_for_status()
    return resp.text


@tool(credentials=["GOOGLE_DRIVE_TOKEN"])
def gdrive_search(query: str) -> List[Dict[str, Any]]:
    """Search files in Google Drive.

    Args:
        query: Search query (matched against file name and content).

    Returns:
        List of matching file dicts.
    """
    headers = _gdrive_headers()

    resp = httpx.get(
        f"{_BASE_URL}/files",
        params={
            "q": f"fullText contains '{query}' and trashed = false",
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
            "pageSize": 20,
        },
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()

    return [_format_file(f) for f in resp.json().get("files", [])]


def get_tools() -> List[Any]:
    """Return all Google Drive tools."""
    return [gdrive_list_files, gdrive_read_file, gdrive_search]
