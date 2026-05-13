# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``web_fetch`` — read an HTTPS URL as text.

For agents that need to read linked specs/RFCs/issue comments. Sandbox
gates the URL via ``check_url`` (private-network blocking + optional
host allowlist). HTML is stripped to text. Output capped at ``MAX_CHARS``
so a giant page doesn't blow the budget.
"""

from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from typing import Any, Callable, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..contract import Tool, ToolResult, ToolUseContext


MAX_CHARS = 16_000
TIMEOUT_SEC = 30
USER_AGENT = "agentspan-harness/1.0"


class WebFetch(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch an https:// URL and return its body as text. HTML pages "
            "are stripped to plain text. Output is capped at 16K chars; "
            "if you need more, fetch a sub-page or specific anchor. The "
            "sandbox blocks private networks and may restrict hosts."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return True

    def is_open_world(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[Dict[str, Any]]:
        url = input["url"]
        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_url(url)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        try:
            text, content_type, status = await asyncio.to_thread(_fetch, url)
        except URLError as exc:
            return ToolResult.error(f"fetch failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(f"fetch failed: {type(exc).__name__}: {exc}")

        if "html" in (content_type or "").lower():
            body = _html_to_text(text)
        else:
            body = text

        truncated = False
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS]
            truncated = True
            body += f"\n\n[truncated at {MAX_CHARS} chars]"

        return ToolResult.ok(
            content=body,
            output={
                "url": url, "status": status, "content_type": content_type,
                "truncated": truncated, "length": len(body),
            },
        )


def _fetch(url: str) -> "tuple[str, str, int]":
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/*, */*"})
    with urlopen(req, timeout=TIMEOUT_SEC) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        status = getattr(resp, "status", 200)
    text = body.decode("utf-8", errors="replace")
    return text, ctype, status


class _TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0 and data:
            self._chunks.append(data)

    def text(self) -> str:
        joined = "".join(self._chunks)
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", joined).strip()


def _html_to_text(html: str) -> str:
    p = _TextStripper()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        return html
    return p.text()
