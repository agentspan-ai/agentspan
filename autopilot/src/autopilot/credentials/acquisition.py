"""Credential acquisition — OAuth flows, API key browser open, AWS credential reading.

Handles credential acquisition for ALL integration types:

1. **OAuth2 (Google)** — Gmail, Google Calendar, Google Drive, Google Analytics.
   Starts a temporary local HTTP server, opens the user's browser to Google's
   consent URL, captures the redirect with the auth code, exchanges it for an
   access + refresh token, and stores it via ``agentspan credentials set``.

2. **OAuth2 (Microsoft)** — Outlook.
   Same flow but against the Microsoft identity platform.

3. **API key** — GitHub, Linear, Notion, Slack, HubSpot, Jira, Brave.
   Opens the browser directly to the service's token-creation page and reads
   the pasted key from stdin.

4. **AWS** — S3.
   Reads ``~/.aws/credentials`` when available; otherwise opens the IAM console
   and prompts the user to paste keys.
"""

from __future__ import annotations

import configparser
import http.server
import os
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Credential registry — maps credential names to how they are acquired
# ---------------------------------------------------------------------------

@dataclass
class CredentialInfo:
    """Metadata describing how a single credential is acquired."""

    name: str
    service: str
    acquisition_type: str  # "oauth_google", "oauth_microsoft", "api_key", "aws", "manual"
    scopes: list[str] = field(default_factory=list)  # for OAuth
    url: str = ""  # for API key browser open
    instructions: str = ""  # human-readable instructions


# -- API key URLs (opened in the browser for the user) ---------------------

_API_KEY_URLS: dict[str, str] = {
    "GITHUB_TOKEN": "https://github.com/settings/tokens/new?description=AgentspanClaw&scopes=repo,read:org",
    "LINEAR_API_KEY": "https://linear.app/settings/api",
    "NOTION_API_KEY": "https://www.notion.so/my-integrations",
    "SLACK_BOT_TOKEN": "https://api.slack.com/apps",
    "HUBSPOT_ACCESS_TOKEN": "https://app.hubspot.com/api-key",
    "JIRA_API_TOKEN": "https://id.atlassian.com/manage-profile/security/api-tokens",
    "BRAVE_API_KEY": "https://brave.com/search/api/",
    "WHATSAPP_TOKEN": "https://developers.facebook.com/apps/",
    "SALESFORCE_ACCESS_TOKEN": "https://login.salesforce.com/",
}


# -- Full credential registry ---------------------------------------------

CREDENTIAL_REGISTRY: dict[str, CredentialInfo] = {
    # ── Google OAuth2 ────────────────────────────────────────────────────
    "GMAIL_ACCESS_TOKEN": CredentialInfo(
        name="GMAIL_ACCESS_TOKEN",
        service="Gmail",
        acquisition_type="oauth_google",
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ],
        instructions="Gmail read and send access",
    ),
    "GOOGLE_CALENDAR_TOKEN": CredentialInfo(
        name="GOOGLE_CALENDAR_TOKEN",
        service="Google Calendar",
        acquisition_type="oauth_google",
        scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        instructions="Google Calendar read and event management",
    ),
    "GOOGLE_DRIVE_TOKEN": CredentialInfo(
        name="GOOGLE_DRIVE_TOKEN",
        service="Google Drive",
        acquisition_type="oauth_google",
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        instructions="Google Drive read access",
    ),
    "GA_ACCESS_TOKEN": CredentialInfo(
        name="GA_ACCESS_TOKEN",
        service="Google Analytics",
        acquisition_type="oauth_google",
        scopes=[
            "https://www.googleapis.com/auth/analytics.readonly",
        ],
        instructions="Google Analytics read access",
    ),

    # ── Microsoft OAuth2 ─────────────────────────────────────────────────
    "OUTLOOK_ACCESS_TOKEN": CredentialInfo(
        name="OUTLOOK_ACCESS_TOKEN",
        service="Outlook",
        acquisition_type="oauth_microsoft",
        scopes=[
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Mail.Send",
        ],
        instructions="Outlook email read and send access",
    ),

    # ── API keys ─────────────────────────────────────────────────────────
    "GITHUB_TOKEN": CredentialInfo(
        name="GITHUB_TOKEN",
        service="GitHub",
        acquisition_type="api_key",
        url=_API_KEY_URLS["GITHUB_TOKEN"],
        instructions="GitHub personal access token with repo and read:org scopes",
    ),
    "LINEAR_API_KEY": CredentialInfo(
        name="LINEAR_API_KEY",
        service="Linear",
        acquisition_type="api_key",
        url=_API_KEY_URLS["LINEAR_API_KEY"],
        instructions="Linear personal API key",
    ),
    "NOTION_API_KEY": CredentialInfo(
        name="NOTION_API_KEY",
        service="Notion",
        acquisition_type="api_key",
        url=_API_KEY_URLS["NOTION_API_KEY"],
        instructions="Notion internal integration token",
    ),
    "SLACK_BOT_TOKEN": CredentialInfo(
        name="SLACK_BOT_TOKEN",
        service="Slack",
        acquisition_type="api_key",
        url=_API_KEY_URLS["SLACK_BOT_TOKEN"],
        instructions="Slack bot OAuth token (xoxb-...)",
    ),
    "HUBSPOT_ACCESS_TOKEN": CredentialInfo(
        name="HUBSPOT_ACCESS_TOKEN",
        service="HubSpot",
        acquisition_type="api_key",
        url=_API_KEY_URLS["HUBSPOT_ACCESS_TOKEN"],
        instructions="HubSpot private app access token",
    ),
    "JIRA_API_TOKEN": CredentialInfo(
        name="JIRA_API_TOKEN",
        service="Jira",
        acquisition_type="api_key",
        url=_API_KEY_URLS["JIRA_API_TOKEN"],
        instructions="Atlassian API token for Jira",
    ),
    "BRAVE_API_KEY": CredentialInfo(
        name="BRAVE_API_KEY",
        service="Brave Search",
        acquisition_type="api_key",
        url=_API_KEY_URLS["BRAVE_API_KEY"],
        instructions="Brave Search API subscription key",
    ),
    "WHATSAPP_TOKEN": CredentialInfo(
        name="WHATSAPP_TOKEN",
        service="WhatsApp",
        acquisition_type="api_key",
        url=_API_KEY_URLS["WHATSAPP_TOKEN"],
        instructions="WhatsApp Business API access token",
    ),
    "SALESFORCE_ACCESS_TOKEN": CredentialInfo(
        name="SALESFORCE_ACCESS_TOKEN",
        service="Salesforce",
        acquisition_type="api_key",
        url=_API_KEY_URLS["SALESFORCE_ACCESS_TOKEN"],
        instructions="Salesforce connected app access token",
    ),

    # ── Manual / multi-field credentials ─────────────────────────────────
    "JIRA_URL": CredentialInfo(
        name="JIRA_URL",
        service="Jira",
        acquisition_type="manual",
        instructions="Your Jira instance URL (e.g. https://yourcompany.atlassian.net)",
    ),
    "JIRA_EMAIL": CredentialInfo(
        name="JIRA_EMAIL",
        service="Jira",
        acquisition_type="manual",
        instructions="Email address associated with your Jira account",
    ),
    "SALESFORCE_INSTANCE_URL": CredentialInfo(
        name="SALESFORCE_INSTANCE_URL",
        service="Salesforce",
        acquisition_type="manual",
        instructions="Your Salesforce instance URL (e.g. https://yourcompany.my.salesforce.com)",
    ),
    "GA_PROPERTY_ID": CredentialInfo(
        name="GA_PROPERTY_ID",
        service="Google Analytics",
        acquisition_type="manual",
        instructions="Google Analytics property ID (e.g. 123456789)",
    ),
    "WHATSAPP_PHONE_ID": CredentialInfo(
        name="WHATSAPP_PHONE_ID",
        service="WhatsApp",
        acquisition_type="manual",
        instructions="WhatsApp Business phone number ID",
    ),

    # ── AWS ──────────────────────────────────────────────────────────────
    "AWS_ACCESS_KEY_ID": CredentialInfo(
        name="AWS_ACCESS_KEY_ID",
        service="AWS S3",
        acquisition_type="aws",
        instructions="AWS access key ID for S3 operations",
    ),
    "AWS_SECRET_ACCESS_KEY": CredentialInfo(
        name="AWS_SECRET_ACCESS_KEY",
        service="AWS S3",
        acquisition_type="aws",
        instructions="AWS secret access key for S3 operations",
    ),
}


# ---------------------------------------------------------------------------
# Credential store helper — calls ``agentspan credentials set``
# ---------------------------------------------------------------------------

def _store_credential(name: str, value: str) -> bool:
    """Store a credential via the ``agentspan`` CLI.

    Returns True on success, False otherwise.
    """
    try:
        result = subprocess.run(
            ["agentspan", "credentials", "set", name, value],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# OAuth2 callback server
# ---------------------------------------------------------------------------

class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Tiny HTTP handler that captures the OAuth redirect's ``code`` and ``state`` parameters."""

    auth_code: Optional[str] = None
    returned_state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            _OAuthCallbackHandler.returned_state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            _OAuthCallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = params["error"][0].encode()
            self.wfile.write(
                b"<html><body><h2>Authorization failed</h2><p>" + msg + b"</p></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default stderr logging from the HTTP server."""
        pass


def _run_oauth_callback_server(
    port: int, timeout: float = 120.0, expected_state: Optional[str] = None
) -> Optional[str]:
    """Start a one-shot HTTP server on *port*, wait for the callback, return the auth code.

    If *expected_state* is provided, the returned ``state`` parameter must match;
    otherwise the auth code is rejected (returns ``None``).
    """
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.returned_state = None
    _OAuthCallbackHandler.error = None

    server = http.server.HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.timeout = timeout

    # Handle exactly one request (the OAuth redirect)
    server.handle_request()
    server.server_close()

    if _OAuthCallbackHandler.error:
        return None

    # Verify state parameter when provided (CSRF protection)
    if expected_state is not None:
        if _OAuthCallbackHandler.returned_state != expected_state:
            return None

    return _OAuthCallbackHandler.auth_code


def _find_free_port() -> int:
    """Find and return a free TCP port on localhost."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Google OAuth2
# ---------------------------------------------------------------------------

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def acquire_google_oauth(
    credential_name: str,
    scopes: list[str],
    client_id: str = "",
    client_secret: str = "",
) -> str:
    """Run OAuth2 flow for Google services. Opens browser, captures token.

    Args:
        credential_name: The credential key (e.g. ``GMAIL_ACCESS_TOKEN``).
        scopes: OAuth2 scopes to request.
        client_id: Google OAuth client ID.  Falls back to
            ``GOOGLE_CLIENT_ID`` env var, then prompts.
        client_secret: Google OAuth client secret.  Falls back to
            ``GOOGLE_CLIENT_SECRET`` env var, then prompts.

    Returns:
        Human-readable status message.
    """
    import httpx

    client_id = client_id or os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = client_secret or os.environ.get("GOOGLE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        # Guide the user to provide these values
        return (
            "To set up Gmail access, I need your Google OAuth credentials.\n\n"
            "1. Go to https://console.cloud.google.com/apis/credentials\n"
            "2. Create an OAuth 2.0 Client ID (type: Desktop App)\n"
            "3. Copy the Client ID and Client Secret\n"
            "4. Set them as credentials:\n"
            "   agentspan credentials set GOOGLE_CLIENT_ID <your-client-id>\n"
            "   agentspan credentials set GOOGLE_CLIENT_SECRET <your-client-secret>\n\n"
            "Or provide them in the chat:\n"
            "   'my google client id is <id> and secret is <secret>'\n\n"
            "Once set, ask me again to set up Gmail."
        )

    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\nOpening browser for {credential_name} authorization...")
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for the callback (verify state for CSRF protection)
    auth_code = _run_oauth_callback_server(port, expected_state=state)
    if not auth_code:
        return f"Error: OAuth authorization failed or timed out for {credential_name}."

    # Exchange auth code for tokens
    token_data = {
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    resp = httpx.post(_GOOGLE_TOKEN_URL, data=token_data, timeout=15.0)
    if resp.status_code != 200:
        return f"Error: Token exchange failed ({resp.status_code}): {resp.text}"

    tokens = resp.json()
    access_token = tokens.get("access_token", "")
    if not access_token:
        return "Error: No access token in response from Google."

    stored = _store_credential(credential_name, access_token)

    # Store refresh token if provided
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        _store_credential(f"{credential_name}_REFRESH", refresh_token)

    if stored:
        return f"{credential_name} acquired and stored successfully."
    else:
        # Fall back to setting the env var for the current session
        os.environ[credential_name] = access_token
        return (
            f"{credential_name} acquired. Could not store via CLI — "
            f"set for current session only."
        )


# ---------------------------------------------------------------------------
# Microsoft OAuth2
# ---------------------------------------------------------------------------

_MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def acquire_microsoft_oauth(
    credential_name: str,
    scopes: list[str],
    client_id: str = "",
    client_secret: str = "",
) -> str:
    """Run OAuth2 flow for Microsoft services. Opens browser, captures token.

    Args:
        credential_name: The credential key (e.g. ``OUTLOOK_ACCESS_TOKEN``).
        scopes: OAuth2 scopes to request.
        client_id: Microsoft app (client) ID.  Falls back to
            ``MICROSOFT_CLIENT_ID`` env var, then prompts.
        client_secret: Microsoft app client secret.  Falls back to
            ``MICROSOFT_CLIENT_SECRET`` env var, then prompts.

    Returns:
        Human-readable status message.
    """
    import httpx

    client_id = client_id or os.environ.get("MICROSOFT_CLIENT_ID", "")
    client_secret = client_secret or os.environ.get("MICROSOFT_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        return (
            "To set up Outlook access, I need your Microsoft OAuth credentials.\n\n"
            "1. Go to https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps\n"
            "2. Register an app, add a redirect URI: http://localhost\n"
            "3. Copy the Application (client) ID and create a Client Secret\n"
            "4. Set them as credentials:\n"
            "   agentspan credentials set MICROSOFT_CLIENT_ID <your-client-id>\n"
            "   agentspan credentials set MICROSOFT_CLIENT_SECRET <your-client-secret>\n\n"
            "Or provide them in the chat:\n"
            "   'my microsoft client id is <id> and secret is <secret>'\n\n"
            "Once set, ask me again to set up Outlook."
        )

    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "response_mode": "query",
        "state": state,
    }
    auth_url = f"{_MS_AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\nOpening browser for {credential_name} authorization...")
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    auth_code = _run_oauth_callback_server(port, expected_state=state)
    if not auth_code:
        return f"Error: OAuth authorization failed or timed out for {credential_name}."

    token_data = {
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    resp = httpx.post(_MS_TOKEN_URL, data=token_data, timeout=15.0)
    if resp.status_code != 200:
        return f"Error: Token exchange failed ({resp.status_code}): {resp.text}"

    tokens = resp.json()
    access_token = tokens.get("access_token", "")
    if not access_token:
        return "Error: No access token in response from Microsoft."

    stored = _store_credential(credential_name, access_token)

    # Store refresh token if provided
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        _store_credential(f"{credential_name}_REFRESH", refresh_token)

    if stored:
        return f"{credential_name} acquired and stored successfully."
    else:
        os.environ[credential_name] = access_token
        return (
            f"{credential_name} acquired. Could not store via CLI — "
            f"set for current session only."
        )


# ---------------------------------------------------------------------------
# API key acquisition
# ---------------------------------------------------------------------------

def acquire_api_key(credential_name: str) -> str:
    """Open browser to API key page, prompt user to paste the key.

    Args:
        credential_name: The credential key (e.g. ``GITHUB_TOKEN``).

    Returns:
        Human-readable status message.
    """
    info = CREDENTIAL_REGISTRY.get(credential_name)
    url = _API_KEY_URLS.get(credential_name, "")

    service = info.service if info else credential_name
    instructions = info.instructions if info else f"API key for {credential_name}"

    if url:
        print(f"\nOpening browser to create {service} API key...")
        print(f"  {url}\n")
        webbrowser.open(url)
    else:
        print(f"\nPlease obtain your {service} API key.")

    print(f"Instructions: {instructions}")
    print(f"Paste your {credential_name} here: ", end="", flush=True)
    value = input().strip()

    if not value:
        return f"Error: No value provided for {credential_name}."

    stored = _store_credential(credential_name, value)
    if stored:
        return f"{credential_name} acquired and stored successfully."
    else:
        os.environ[credential_name] = value
        return (
            f"{credential_name} acquired. Could not store via CLI — "
            f"set for current session only."
        )


# ---------------------------------------------------------------------------
# AWS credentials
# ---------------------------------------------------------------------------

_AWS_IAM_CONSOLE_URL = "https://console.aws.amazon.com/iam/home#/security_credentials"


def read_aws_credentials_file(
    profile: str = "default",
    credentials_path: Optional[Path] = None,
) -> dict[str, str]:
    """Read AWS credentials from an INI-format credentials file.

    Args:
        profile: The AWS profile to read (default ``"default"``).
        credentials_path: Path to the credentials file.  Defaults to
            ``~/.aws/credentials``.

    Returns:
        Dict with ``aws_access_key_id`` and ``aws_secret_access_key`` keys,
        or an empty dict if the file/profile is not found.
    """
    if credentials_path is None:
        credentials_path = Path.home() / ".aws" / "credentials"

    if not credentials_path.is_file():
        return {}

    parser = configparser.ConfigParser()
    parser.read(credentials_path)

    if profile not in parser:
        return {}

    section = parser[profile]
    access_key = section.get("aws_access_key_id", "")
    secret_key = section.get("aws_secret_access_key", "")

    if access_key and secret_key:
        return {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }
    return {}


def acquire_aws_credentials(credential_name: str) -> str:
    """Acquire AWS credentials — read from ~/.aws/credentials or prompt.

    Args:
        credential_name: Either ``AWS_ACCESS_KEY_ID`` or ``AWS_SECRET_ACCESS_KEY``.

    Returns:
        Human-readable status message.
    """
    # Try reading from ~/.aws/credentials first
    creds = read_aws_credentials_file()
    if creds:
        access_key = creds["aws_access_key_id"]
        secret_key = creds["aws_secret_access_key"]

        stored_ak = _store_credential("AWS_ACCESS_KEY_ID", access_key)
        stored_sk = _store_credential("AWS_SECRET_ACCESS_KEY", secret_key)

        if not stored_ak:
            os.environ["AWS_ACCESS_KEY_ID"] = access_key
        if not stored_sk:
            os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key

        return (
            "AWS credentials read from ~/.aws/credentials and stored. "
            "Both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are now available."
        )

    # No local file — open IAM console and prompt
    print(f"\nNo ~/.aws/credentials file found.")
    print(f"Opening AWS IAM console to create access keys...")
    print(f"  {_AWS_IAM_CONSOLE_URL}\n")
    webbrowser.open(_AWS_IAM_CONSOLE_URL)

    print("Paste your AWS Access Key ID: ", end="", flush=True)
    access_key = input().strip()
    print("Paste your AWS Secret Access Key: ", end="", flush=True)
    secret_key = input().strip()

    if not access_key or not secret_key:
        return "Error: Both AWS Access Key ID and Secret Access Key are required."

    stored_ak = _store_credential("AWS_ACCESS_KEY_ID", access_key)
    stored_sk = _store_credential("AWS_SECRET_ACCESS_KEY", secret_key)

    if not stored_ak:
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
    if not stored_sk:
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key

    return "AWS credentials acquired and stored. Both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are now available."


# ---------------------------------------------------------------------------
# Manual credential acquisition
# ---------------------------------------------------------------------------

def _acquire_manual(credential_name: str) -> str:
    """Prompt the user to type a credential value manually.

    Args:
        credential_name: The credential key.

    Returns:
        Human-readable status message.
    """
    info = CREDENTIAL_REGISTRY.get(credential_name)
    instructions = info.instructions if info else f"Value for {credential_name}"

    print(f"\n{instructions}")
    print(f"Enter value for {credential_name}: ", end="", flush=True)
    value = input().strip()

    if not value:
        return f"Error: No value provided for {credential_name}."

    stored = _store_credential(credential_name, value)
    if stored:
        return f"{credential_name} stored successfully."
    else:
        os.environ[credential_name] = value
        return (
            f"{credential_name} set for current session. "
            f"Could not store via CLI."
        )


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def acquire_credential(credential_name: str) -> str:
    """Acquire a credential by name, using the appropriate method.

    Looks up the credential in :data:`CREDENTIAL_REGISTRY` and dispatches
    to the correct acquisition function (OAuth, API key, AWS, or manual).

    Args:
        credential_name: The credential key (e.g. ``GMAIL_ACCESS_TOKEN``).

    Returns:
        Human-readable status message describing the outcome.
    """
    info = CREDENTIAL_REGISTRY.get(credential_name)

    if info is None:
        # Unknown credential — fall back to manual prompt
        print(f"\nUnknown credential: {credential_name}")
        print(f"Enter value for {credential_name}: ", end="", flush=True)
        value = input().strip()
        if not value:
            return f"Error: No value provided for {credential_name}."
        stored = _store_credential(credential_name, value)
        if stored:
            return f"{credential_name} stored successfully."
        else:
            os.environ[credential_name] = value
            return f"{credential_name} set for current session."

    acq_type = info.acquisition_type

    if acq_type == "oauth_google":
        return acquire_google_oauth(credential_name, info.scopes)
    elif acq_type == "oauth_microsoft":
        return acquire_microsoft_oauth(credential_name, info.scopes)
    elif acq_type == "api_key":
        return acquire_api_key(credential_name)
    elif acq_type == "aws":
        return acquire_aws_credentials(credential_name)
    elif acq_type == "manual":
        return _acquire_manual(credential_name)
    else:
        return _acquire_manual(credential_name)
