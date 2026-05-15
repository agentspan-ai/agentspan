"""Reusable @tool functions for the Deep Research Agent.

Tools used in the pipeline:
- Shared state: contextbook_write, contextbook_read
- Output: create_google_doc (Google Docs with OAuth)

Standalone tools (available for reuse, not wired into the default pipeline):
- Search: sonar_search (Perplexity), web_search (Tavily)
- Extraction: scrape_page (Jina Reader)

The default pipeline uses Perplexity Sonar as a native model (not a tool)
for all web search — every LLM call is automatically a real-time web search.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from agentspan.agents import tool

# ── Working directory & contextbook ──────────────────────────

_working_dir: str = ""


def set_working_dir(path: str) -> None:
    """Set the shared working directory for contextbook storage."""
    global _working_dir
    _working_dir = path
    os.makedirs(path, exist_ok=True)


def _contextbook_dir() -> str:
    d = os.path.join(_working_dir or "/tmp/deep-research", ".contextbook")
    os.makedirs(d, exist_ok=True)
    return d


@tool
def contextbook_write(key: str, content: str) -> str:
    """Write a named section to the shared contextbook.

    The contextbook is a key-value store shared across all agents in the
    pipeline. Use it to pass structured data between stages.

    Args:
        key: Section name (e.g. "research_plan", "verified_findings").
        content: The full text content to store.
    """
    path = os.path.join(_contextbook_dir(), f"{key}.md")
    with open(path, "w") as f:
        f.write(content)
    return f"wrote '{key}' ({len(content)} chars)"


@tool
def contextbook_read(key: str) -> str:
    """Read a named section from the shared contextbook.

    Args:
        key: Section name to read (e.g. "research_plan", "verified_findings").
    """
    path = os.path.join(_contextbook_dir(), f"{key}.md")
    if not os.path.exists(path):
        return f"'{key}' not found in contextbook"
    with open(path) as f:
        return f.read()


# ── Search tools ─────────────────────────────────────────────


@tool(credentials=["PERPLEXITY_API_KEY"])
def sonar_search(query: str) -> dict:
    """Deep web search via Perplexity Sonar Pro.

    Returns a synthesized answer with source citations. Use for broad
    research questions, fact-finding, and verification. The citations
    are real URLs that can be scraped for more detail.

    Args:
        query: Natural language research query.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"query": query, "error": "PERPLEXITY_API_KEY not set"}

    payload = json.dumps({
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": query}],
    }).encode()

    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        choice = data.get("choices", [{}])[0]
        answer = choice.get("message", {}).get("content", "")
        citations = data.get("citations", [])

        return {
            "query": query,
            "answer": answer,
            "citations": citations,
            "model": data.get("model", "sonar-pro"),
        }
    except Exception as exc:
        return {"query": query, "error": str(exc), "answer": "", "citations": []}


@tool(credentials=["TAVILY_API_KEY"])
def web_search(query: str, max_results: int = 10) -> dict:
    """Search the web for specific pages and URLs.

    Returns a ranked list of URLs with titles and content snippets.
    Use when you need to FIND specific pages (pricing pages, articles,
    documentation) rather than synthesized answers.

    Args:
        query: Search query string.
        max_results: Maximum number of results (1-20, default 10).
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return {"query": query, "error": "TAVILY_API_KEY not set"}

    max_results = max(1, min(max_results, 20))

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }).encode()

    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (r.get("content") or "")[:500],
                "score": r.get("score", 0),
            }
            for r in data.get("results", [])
        ]
        return {"query": query, "results": results, "count": len(results)}
    except Exception as exc:
        return {"query": query, "error": str(exc), "results": []}


# ── Extraction tools ─────────────────────────────────────────


@tool
def scrape_page(url: str) -> dict:
    """Fetch and extract clean text content from a web page.

    Uses Jina Reader to convert the page to clean markdown. Returns the
    full text content, truncated to ~15000 chars to avoid token overflow.

    Args:
        url: The full URL of the page to scrape.
    """
    # Jina Reader: prepend r.jina.ai/ to any URL for markdown extraction
    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(
        jina_url,
        headers={
            "Accept": "text/markdown",
            "User-Agent": "Mozilla/5.0 (deep-research-agent/1.0)",
            "X-Return-Format": "markdown",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Truncate to avoid token explosion
        truncated = len(content) > 15000
        if truncated:
            content = content[:15000] + "\n\n[... truncated, page continues ...]"

        return {
            "url": url,
            "content": content,
            "length": len(content),
            "truncated": truncated,
        }
    except urllib.error.HTTPError as exc:
        return {"url": url, "error": f"HTTP {exc.code}: {exc.reason}", "content": ""}
    except Exception as exc:
        return {"url": url, "error": str(exc), "content": ""}


# ── Google Docs output ───────────────────────────────────────

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_google_creds():
    """Get Google credentials for Docs/Drive API.

    Tries in order:
    1. OAuth token file (GOOGLE_OAUTH_TOKEN env var) — for end users
    2. Application Default Credentials (gcloud auth) — for developers
    3. Service account (GOOGLE_APPLICATION_CREDENTIALS) — for automation

    Returns (credentials, None) on success, or (None, error_message) on failure.
    """
    try:
        from google.auth.transport.requests import Request
    except ImportError:
        return None, "google-auth not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client"

    errors = []

    # 1. OAuth token file — saved from google_oauth_setup()
    token_path = os.environ.get("GOOGLE_OAUTH_TOKEN", "")
    if not token_path:
        default = _default_token_path()
        if os.path.exists(default):
            token_path = default
    if token_path and os.path.exists(token_path):
        try:
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(token_path, GOOGLE_SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
            if creds and creds.valid:
                return creds, None
            errors.append(f"OAuth token at {token_path} is invalid or expired (no refresh token)")
        except Exception as exc:
            errors.append(f"OAuth token at {token_path}: {exc}")
    else:
        errors.append(f"No OAuth token file found (checked GOOGLE_OAUTH_TOKEN env and {_default_token_path()})")

    # 2. Application Default Credentials (gcloud auth application-default login)
    try:
        import google.auth

        creds, _ = google.auth.default(scopes=GOOGLE_SCOPES)
        if hasattr(creds, "expired") and creds.expired and hasattr(creds, "refresh"):
            creds.refresh(Request())
        if creds and creds.valid:
            return creds, None
        errors.append("Application Default Credentials found but not valid after refresh")
    except Exception as exc:
        errors.append(f"Application Default Credentials: {exc}")

    # 3. Service account (explicit path)
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if sa_path and os.path.exists(sa_path):
        try:
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                sa_path, scopes=GOOGLE_SCOPES
            )
            return creds, None
        except Exception as exc:
            errors.append(f"Service account at {sa_path}: {exc}")
    elif sa_path:
        errors.append(f"GOOGLE_APPLICATION_CREDENTIALS={sa_path} but file not found")

    return None, "No valid Google credentials found. Tried: " + "; ".join(errors)


def _default_token_path() -> str:
    """Default location for the user's Google OAuth token."""
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "agentspan")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "google_token.json")


def google_oauth_setup(client_secrets: str = "", token_path: str = ""):
    """One-time interactive Google sign-in for end users.

    Opens a browser → user logs in with their Google account → grants
    permission to create Docs → token saved locally. No Google Cloud
    Console access needed by the end user.

    The OAuth client credentials (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)
    are configured by the app deployer, not the end user.

    Auth resolution order:
    1. GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET env vars (set by deployer)
    2. client_secrets JSON file path (for development)

    Args:
        client_secrets: Path to OAuth client_secret.json (dev use only).
                        End users don't need this — the deployer sets
                        GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET instead.
        token_path: Where to save the token. Defaults to
                    ~/.config/agentspan/google_token.json.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing dependency. Run: pip install google-auth-oauthlib")
        return None

    if not token_path:
        token_path = _default_token_path()

    # Option 1: Client ID/secret from env vars (deployed app)
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    if client_id and client_secret:
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, GOOGLE_SCOPES)

    # Option 2: Client secrets JSON file (development)
    else:
        if not client_secrets:
            client_secrets = os.environ.get("GOOGLE_OAUTH_CLIENT", "client_secret.json")

        if not os.path.exists(client_secrets):
            print("Google OAuth not configured.")
            print("")
            print("For deployers / admins:")
            print("  1. Create an OAuth client at console.cloud.google.com/apis/credentials")
            print("     (Application type: Desktop)")
            print("  2. Enable Google Docs API and Google Drive API")
            print("  3. Set these env vars for your users:")
            print("       GOOGLE_CLIENT_ID=<your-client-id>")
            print("       GOOGLE_CLIENT_SECRET=<your-client-secret>")
            print("")
            print("For developers:")
            print("  Download client_secret.json and pass --google-client-secret path")
            return None

        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, GOOGLE_SCOPES)

    print("Opening browser for Google sign-in...")
    creds = flow.run_local_server(port=0, open_browser=True)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    abs_path = os.path.abspath(token_path)
    print(f"\nSigned in successfully.")
    print(f"Token saved to: {abs_path}")
    print(f"\nYou're all set. Run the research agent and it will create")
    print(f"Google Docs directly in your Google Drive.")
    return abs_path


def _markdown_to_docs_requests(content: str) -> list:
    """Convert markdown to Google Docs batchUpdate requests.

    Handles: headings (#/##/###), bold (**text**), bullet lists (- item),
    and regular paragraphs. Tables are inserted as tab-separated text.
    """
    import re

    full_text = ""
    heading_ranges = []   # (start, end, named_style)
    bold_ranges = []      # (start, end)
    bullet_ranges = []    # (start, end)

    for line in content.split("\n"):
        start = len(full_text) + 1  # Docs body starts at index 1

        # Determine paragraph style
        heading = None
        bullet = False
        text = line

        if line.startswith("### "):
            heading, text = "HEADING_3", line[4:]
        elif line.startswith("## "):
            heading, text = "HEADING_2", line[3:]
        elif line.startswith("# "):
            heading, text = "HEADING_1", line[2:]
        elif re.match(r"^[-*] ", line):
            bullet, text = True, line[2:]
        elif re.match(r"^  [-*] ", line):
            bullet, text = True, line[4:]
        elif line.startswith("---"):
            text = "—" * 40  # horizontal rule as em-dashes

        # Convert table rows: | col | col | → tab-separated
        if text.startswith("|") and text.endswith("|"):
            cells = [c.strip() for c in text.strip("|").split("|")]
            # Skip separator rows like |---|---|
            if all(c.replace("-", "").replace(":", "") == "" for c in cells):
                continue
            text = "\t".join(cells)

        # Parse **bold** markers
        clean_text = ""
        for part in re.split(r"(\*\*.*?\*\*)", text):
            if part.startswith("**") and part.endswith("**"):
                inner = part[2:-2]
                bold_start = len(full_text) + len(clean_text) + 1
                bold_ranges.append((bold_start, bold_start + len(inner)))
                clean_text += inner
            else:
                clean_text += part

        full_text += clean_text + "\n"
        end = len(full_text) + 1

        if heading:
            heading_ranges.append((start, end, heading))
        if bullet:
            bullet_ranges.append((start, end))

    if not full_text.strip():
        return []

    # Build requests: insert text, then apply styles
    requests = [
        {"insertText": {"location": {"index": 1}, "text": full_text}}
    ]

    for start, end, style in heading_ranges:
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": style},
                "fields": "namedStyleType",
            }
        })

    for start, end in bold_ranges:
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {"bold": True},
                "fields": "bold",
            }
        })

    for start, end in bullet_ranges:
        requests.append({
            "createParagraphBullets": {
                "range": {"startIndex": start, "endIndex": end},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        })

    return requests


@tool
def create_google_doc(title: str, content: str, share_with: str = "") -> dict:
    """Create a Google Doc with formatted research content.

    Converts markdown content to a formatted Google Doc with headings,
    bold text, and bullet lists. Returns the document URL.

    Authentication (tried in order):
    1. OAuth token — set GOOGLE_OAUTH_TOKEN to path of token file
       (created by google_oauth_setup() or gcloud auth)
    2. Application Default Credentials — gcloud auth application-default login
    3. Service account — set GOOGLE_APPLICATION_CREDENTIALS to key JSON path

    For end users, run: python 102_deep_research_agent.py --google-auth

    Requires: pip install google-auth google-auth-oauthlib google-api-python-client

    Args:
        title: Document title.
        content: Markdown-formatted content for the document body.
        share_with: Email address to share the doc with as editor.
                    If empty, the doc is created in the user's own Drive.
    """
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return {
            "error": "Missing dependencies. Run: pip install google-auth google-auth-oauthlib google-api-python-client",
        }

    creds, creds_error = _get_google_creds()
    if not creds:
        return {
            "error": f"Google credentials failed: {creds_error}. Run: python 102_deep_research_agent.py --google-auth",
        }

    try:
        docs = build("docs", "v1", credentials=creds)
        drive = build("drive", "v3", credentials=creds)

        # 1. Create empty document
        doc = docs.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        # 2. Convert markdown to Docs formatting and apply
        fmt_requests = _markdown_to_docs_requests(content)
        if fmt_requests:
            docs.documents().batchUpdate(
                documentId=doc_id, body={"requests": fmt_requests}
            ).execute()

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

        # 3. Share if requested (only needed for service accounts;
        #    OAuth users already own the doc in their Drive)
        if share_with:
            drive.permissions().create(
                fileId=doc_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": share_with,
                },
                sendNotificationEmail=True,
            ).execute()

        return {
            "document_id": doc_id,
            "url": doc_url,
            "title": title,
            "shared_with": share_with or "owner (you)",
        }

    except Exception as exc:
        return {"error": str(exc), "title": title}
