# Agentspan Claw — Integrations

## Overview

19 builtin integrations + MCP (dynamic). Each integration provides a set of `@tool`-decorated functions that the orchestrator can assign to agents. Credentials are injected via environment variables — workers read them at call time.

**Tier 1 — Builtin**: Ships with Claw. Tools are Python functions decorated with `@tool`. No API key required for `web_search`, `doc_reader`, `local_fs`, and `imessage`.

**Tier 2 — MCP (dynamic)**: Any MCP-compatible server can be connected at runtime. The `mcp` integration wraps Agentspan's native `mcp_tool()` to discover and expose tools automatically.

---

## Integration Catalog

### 1. Web Search

**When to use:** Searching the web, fetching page content, deep research.

**Algorithm:** Uses DuckDuckGo via the `ddgs` library as the default engine (no API key required). DDG search runs in a subprocess to avoid fork+Rust crashes in Conductor worker processes. If `BRAVE_API_KEY` is set, also queries the Brave Search API (`https://api.search.brave.com/res/v1/web/search`) and merges results — Brave first, then DDG for unseen URLs. `fetch_page` uses `trafilatura` for content extraction from HTML. Content is truncated at a configurable max (default 10,000 chars).

**Tools:**

| Tool | Description |
|------|-------------|
| `web_search` | Search the web via DDG (+ optional Brave). Returns titles, URLs, snippets. Max 20 results. |
| `fetch_page` | Fetch a URL and extract clean text via trafilatura. Max 50,000 chars. |
| `search_and_read` | Search + fetch top results (up to 5) in one call. The power tool for deep research. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `BRAVE_API_KEY` | Optional | Brave Search API subscription token for enhanced results | https://brave.com/search/api/ |

---

### 2. Gmail

**When to use:** Reading, searching, and sending emails via a Google Gmail account.

**Algorithm:** Calls Gmail API v1 at `https://gmail.googleapis.com/gmail/v1/users/me`. Authentication via OAuth2 Bearer token. Message bodies are base64url-decoded from the API response. Sending constructs a MIME message, base64url-encodes it, and POSTs to `/messages/send`.

**Tools:**

| Tool | Description |
|------|-------------|
| `gmail_list_messages` | List or search emails. Accepts Gmail query syntax. Returns message IDs and thread IDs. |
| `gmail_read_message` | Read full email content — subject, from, to, body (plain text decoded from base64). |
| `gmail_send_message` | Send an email. Builds a MIMEText message, base64-encodes, and sends via API. |
| `gmail_search` | Search with Gmail query syntax (e.g. `"is:unread from:boss"`). Wrapper around `gmail_list_messages`. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `GMAIL_ACCESS_TOKEN` | Yes | Google OAuth2 access token with `gmail.modify` or `gmail.send` scopes | Google Cloud Console > APIs & Services > Credentials > OAuth2 client. Use `https://www.googleapis.com/auth/gmail.modify` scope. |

---

### 3. Outlook

**When to use:** Reading, searching, and sending emails via Microsoft 365 / Outlook.

**Algorithm:** Calls Microsoft Graph API v1.0 at `https://graph.microsoft.com/v1.0/me`. Authentication via OAuth2 Bearer token. Lists messages from mail folders, searches via `$search` OData parameter, sends via `/sendMail` endpoint.

**Tools:**

| Tool | Description |
|------|-------------|
| `outlook_list_messages` | List emails in a mailbox folder (default: inbox). Returns id, subject, from, receivedDateTime, bodyPreview. |
| `outlook_read_message` | Read full email content by message ID. |
| `outlook_send_message` | Send an email via Microsoft Graph `/sendMail`. |
| `outlook_search` | Search emails using Microsoft Graph `$search` syntax. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `OUTLOOK_ACCESS_TOKEN` | Yes | Microsoft Graph OAuth2 access token with `Mail.ReadWrite` and `Mail.Send` permissions | Azure Portal > App Registrations > API Permissions > Microsoft Graph > `Mail.ReadWrite`, `Mail.Send`. Use MSAL or OAuth2 auth code flow. |

---

### 4. GitHub

**When to use:** Searching repos, managing issues and pull requests on GitHub.

**Algorithm:** Calls GitHub REST API at `https://api.github.com`. Uses `X-GitHub-Api-Version: 2022-11-28` header. Search endpoints are public (no auth needed for `github_search_repos`), but all issue/PR endpoints require authentication. PR diff is fetched via `Accept: application/vnd.github.diff` header.

**Tools:**

| Tool | Description |
|------|-------------|
| `github_search_repos` | Search repositories by query (e.g. `"language:python stars:>100"`). Returns top 10. |
| `github_list_issues` | List issues for a repo. Filter by state: open/closed/all. |
| `github_get_issue` | Get full issue details including body, labels, timestamps. |
| `github_create_issue` | Create a new issue with title and Markdown body. |
| `github_list_prs` | List pull requests for a repo. Filter by state. |
| `github_get_pr` | Get PR details including the full diff. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token (classic or fine-grained) | https://github.com/settings/tokens > Generate new token. Scopes: `repo` for private repos, `public_repo` for public only. |

---

### 5. Slack

**When to use:** Sending messages, reading channels, and searching across a Slack workspace.

**Algorithm:** Calls Slack Web API at `https://slack.com/api`. Authenticates with Bot Token (`xoxb-` prefix). All responses are checked for `"ok": true` — Slack returns HTTP 200 even on API errors, so the integration validates the `ok` field. Uses `chat.postMessage`, `conversations.list`, `conversations.history`, and `search.messages` endpoints.

**Tools:**

| Tool | Description |
|------|-------------|
| `slack_send_message` | Send a message to a channel (by ID or `#name`). Returns timestamp for threading. |
| `slack_list_channels` | List channels the bot is a member of (public + private). |
| `slack_read_messages` | Read recent messages from a channel. Max 100. |
| `slack_search_messages` | Search messages across Slack. Returns text, username, channel, permalink. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `SLACK_BOT_TOKEN` | Yes | Slack Bot User OAuth Token (starts with `xoxb-`) | https://api.slack.com/apps > Create App > OAuth & Permissions. Scopes: `chat:write`, `channels:read`, `channels:history`, `search:read`. Install to workspace. |

---

### 6. Document Reader

**When to use:** Extracting text from PDF, Office documents (docx, xlsx, pptx), HTML, and plain text files.

**Algorithm:** For plain text files (`.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini`), reads directly. For all other formats, uses `markitdown` as the primary extractor. For PDFs, falls back to `langextract` if markitdown fails. No external API calls — all processing is local.

**Tools:**

| Tool | Description |
|------|-------------|
| `read_document` | Read a document and extract text. Supports PDF, Office docs, HTML, plain text. |

**Credentials:**

None required. All processing is local.

---

### 7. Local Filesystem

**When to use:** Reading, writing, and searching files on the local filesystem.

**Algorithm:** Pure Python using `pathlib` and `os.walk`. All paths are resolved via `Path.expanduser().resolve()`. `find_files` walks directories recursively with `fnmatch` glob matching. `search_in_files` does line-by-line substring search with `os.walk` + `fnmatch`. No external dependencies.

**Tools:**

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents as UTF-8 text. |
| `write_file` | Write content to a file, creating parent directories if needed. |
| `list_dir` | List entries in a directory. Returns sorted names. |
| `find_files` | Recursively find files matching a glob pattern. |
| `search_in_files` | Search for a text pattern in files matching a glob. Returns `file:line: text` matches. |

**Credentials:**

None required. Operates on the local filesystem.

---

### 8. Google Calendar

**When to use:** Listing upcoming events, creating new events, and searching calendar entries.

**Algorithm:** Calls Google Calendar API v3 at `https://www.googleapis.com/calendar/v3`. Operates on the `primary` calendar. Authentication via OAuth2 Bearer token. `gcal_list_events` uses `timeMin`/`timeMax` parameters with ISO 8601 timestamps. Events are returned as singleEvents (recurring events expanded), ordered by start time.

**Tools:**

| Tool | Description |
|------|-------------|
| `gcal_list_events` | List upcoming events for the next N days (default 7). Max 50 events. |
| `gcal_create_event` | Create a new event with summary, start/end times (ISO 8601), and optional description. |
| `gcal_search_events` | Search events by free-text query. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `GOOGLE_CALENDAR_TOKEN` | Yes | Google OAuth2 access token with Calendar scope | Google Cloud Console > Enable Calendar API > OAuth2 client. Scope: `https://www.googleapis.com/auth/calendar`. |

---

### 9. Google Drive

**When to use:** Listing, reading, and searching files in Google Drive. Reads Google Docs/Sheets/Slides as text.

**Algorithm:** Calls Google Drive API v3 at `https://www.googleapis.com/drive/v3`. Lists files with Drive query syntax. For Google-native docs (Docs, Sheets, Slides), exports as plain text/CSV via the `/export` endpoint. For regular files, downloads raw content via `?alt=media`. File metadata includes `webViewLink` for browser access.

**Tools:**

| Tool | Description |
|------|-------------|
| `gdrive_list_files` | List files in a folder (default: root). Supports Drive query filters. |
| `gdrive_read_file` | Read file content. Google Docs exported as text, Sheets as CSV, others downloaded raw. |
| `gdrive_search` | Full-text search across Drive (matches filename and content). |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `GOOGLE_DRIVE_TOKEN` | Yes | Google OAuth2 access token with Drive scope | Google Cloud Console > Enable Drive API > OAuth2 client. Scope: `https://www.googleapis.com/auth/drive.readonly` (or `drive` for read-write). |

---

### 10. AWS S3

**When to use:** Listing buckets/objects, reading and writing files in Amazon S3.

**Algorithm:** Uses `boto3` S3 client. Authenticates with AWS access key credentials. Supports listing buckets, listing objects with prefix filter, reading objects as UTF-8 text, and writing text content. Region defaults to `us-east-1` unless `AWS_REGION` is set.

**Tools:**

| Tool | Description |
|------|-------------|
| `s3_list_objects` | List objects in a bucket, optionally filtered by key prefix. Max 100. |
| `s3_read_object` | Read an S3 object's content as UTF-8 text. |
| `s3_write_object` | Write text content to an S3 object. |
| `s3_list_buckets` | List all S3 buckets accessible with the configured credentials. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `AWS_ACCESS_KEY_ID` | Yes | AWS access key ID | AWS Console > IAM > Users > Security Credentials > Create Access Key. |
| `AWS_SECRET_ACCESS_KEY` | Yes | AWS secret access key | Generated alongside the access key ID. |
| `AWS_REGION` | Optional | AWS region (default: `us-east-1`) | Set to your preferred region (e.g. `us-west-2`). |

---

### 11. Jira

**When to use:** Searching, creating, and updating issues in Atlassian Jira (Cloud).

**Algorithm:** Calls Jira REST API v3 at `{JIRA_URL}/rest/api/3`. Authenticates via HTTP Basic Auth with email + API token. Searches use JQL (Jira Query Language). Issue descriptions use Atlassian Document Format (ADF) — the integration constructs ADF paragraph nodes for text content.

**Tools:**

| Tool | Description |
|------|-------------|
| `jira_search` | Search issues using JQL (e.g. `"project = ENG AND status = Open"`). |
| `jira_get_issue` | Get full issue details — summary, description, status, assignee, priority, timestamps. |
| `jira_create_issue` | Create a new issue with project key, summary, description, and type (default: Task). |
| `jira_update_issue` | Update fields on an existing issue. |
| `jira_add_comment` | Add a comment to an issue (ADF format). |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `JIRA_URL` | Yes | Jira Cloud instance URL (e.g. `https://yourteam.atlassian.net`) | Your Jira instance base URL. |
| `JIRA_EMAIL` | Yes | Atlassian account email address | The email you log in with. |
| `JIRA_API_TOKEN` | Yes | Atlassian API token | https://id.atlassian.net/manage-profile/security/api-tokens > Create API token. |

---

### 12. Linear

**When to use:** Listing, creating, and updating issues in Linear.

**Algorithm:** Uses Linear's GraphQL API at `https://api.linear.app/graphql`. Authentication via API key in the `Authorization` header (no Bearer prefix). Filters issues by team key and state name using GraphQL filter syntax. Creating issues requires resolving team key to team ID first. Updating state requires resolving state name to workflow state ID.

**Tools:**

| Tool | Description |
|------|-------------|
| `linear_list_issues` | List issues, optionally filtered by team key and/or state name. |
| `linear_get_issue` | Get full issue details including description, labels, timestamps. |
| `linear_create_issue` | Create a new issue. Resolves team key to ID, supports priority levels 0-4. |
| `linear_update_issue` | Update issue state or assignee. Resolves state names to workflow state IDs. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `LINEAR_API_KEY` | Yes | Linear personal API key | https://linear.app/settings/api > Personal API keys > Create key. |

---

### 13. Notion

**When to use:** Searching pages, reading page content, querying databases, and creating pages in Notion.

**Algorithm:** Calls Notion API v1 at `https://api.notion.com/v1` with `Notion-Version: 2022-06-28`. Authentication via Bearer token (internal integration token). Page content is read by fetching block children and extracting `rich_text` -> `plain_text` from each block. Database queries support Notion's filter object format. New pages are created with title property and optional paragraph blocks.

**Tools:**

| Tool | Description |
|------|-------------|
| `notion_search` | Search pages and databases by text query. Returns id, type, title, URL. |
| `notion_read_page` | Read a page's content as plain text by fetching and concatenating block children. |
| `notion_query_database` | Query a Notion database with optional filter. Returns page objects. |
| `notion_create_page` | Create a new page under a parent page/database with title and optional content. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `NOTION_API_KEY` | Yes | Notion internal integration token (starts with `ntn_` or `secret_`) | https://www.notion.so/my-integrations > Create integration > Internal integration token. Share target pages/databases with the integration. |

---

### 14. HubSpot

**When to use:** Searching contacts, managing deals, and creating contacts in HubSpot CRM.

**Algorithm:** Calls HubSpot API v3 at `https://api.hubapi.com/crm/v3/objects`. Authentication via Bearer token (private app access token). Contact search uses the `/search` endpoint with property filters. Deals are listed via the standard objects endpoint with property selection.

**Tools:**

| Tool | Description |
|------|-------------|
| `hubspot_search_contacts` | Search contacts by query (matches name, email, etc.). Returns id, email, name. |
| `hubspot_get_contact` | Get full contact details with properties. |
| `hubspot_list_deals` | List deals with dealname, amount, dealstage, closedate. |
| `hubspot_get_deal` | Get full deal details with properties including pipeline. |
| `hubspot_create_contact` | Create a new contact with email, optional first/last name. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `HUBSPOT_ACCESS_TOKEN` | Yes | HubSpot private app access token | HubSpot > Settings > Integrations > Private Apps > Create. Scopes: `crm.objects.contacts.read`, `crm.objects.contacts.write`, `crm.objects.deals.read`. |

---

### 15. Salesforce

**When to use:** Querying, creating, and updating records in Salesforce (any SObject type).

**Algorithm:** Calls Salesforce REST API v59.0 at `{SALESFORCE_INSTANCE_URL}/services/data/v59.0`. Authentication via OAuth2 Bearer token. Queries use SOQL (Salesforce Object Query Language). CRUD operations are per-SObject type (Account, Contact, Opportunity, etc.). Updates use HTTP PATCH.

**Tools:**

| Tool | Description |
|------|-------------|
| `sf_query` | Run a SOQL query (e.g. `"SELECT Id, Name FROM Account LIMIT 10"`). |
| `sf_get_record` | Get a specific record by SObject type and record ID. |
| `sf_create_record` | Create a new record for any SObject type with field values. |
| `sf_update_record` | Update an existing record's fields via PATCH. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `SALESFORCE_INSTANCE_URL` | Yes | Salesforce instance URL (e.g. `https://yourorg.my.salesforce.com`) | Found in your Salesforce org URL or via OAuth2 token response. |
| `SALESFORCE_ACCESS_TOKEN` | Yes | Salesforce OAuth2 access token | Salesforce Setup > App Manager > New Connected App. Use OAuth2 flow (web server or JWT bearer). |

---

### 16. Google Analytics

**When to use:** Running analytics reports (metrics/dimensions) and checking realtime active users.

**Algorithm:** Calls Google Analytics Data API v1beta at `https://analyticsdata.googleapis.com/v1beta/properties/{propertyId}`. Authentication via OAuth2 Bearer token. Reports are built with metrics (e.g. `activeUsers`, `sessions`) and optional dimensions (e.g. `date`, `country`). Date ranges use Google's relative format (`7daysAgo`, `30daysAgo`, etc.) through `today`. Realtime uses the `:runRealtimeReport` endpoint.

**Tools:**

| Tool | Description |
|------|-------------|
| `ga_run_report` | Run a GA report with metrics, optional dimensions, and date range. |
| `ga_get_realtime` | Get realtime active users count. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `GA_ACCESS_TOKEN` | Yes | Google OAuth2 access token with Analytics scope | Google Cloud Console > Enable Analytics Data API > OAuth2 client. Scope: `https://www.googleapis.com/auth/analytics.readonly`. |
| `GA_PROPERTY_ID` | Yes | GA4 property ID (numeric, e.g. `"123456789"`) | Google Analytics > Admin > Property Settings > Property ID. |

---

### 17. WhatsApp

**When to use:** Sending text messages and template messages via WhatsApp Business.

**Algorithm:** Calls WhatsApp Business Cloud API via Meta's Graph API at `https://graph.facebook.com/v18.0/{phone_number_id}/messages`. Authentication via Bearer token. Text messages set `type: "text"` with a body. Template messages set `type: "template"` with a template name, language code, and optional parameter components.

**Tools:**

| Tool | Description |
|------|-------------|
| `whatsapp_send_message` | Send a text message to a phone number (international format, e.g. `"+1234567890"`). |
| `whatsapp_send_template` | Send a pre-approved template message with optional parameters. |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| `WHATSAPP_TOKEN` | Yes | WhatsApp Business Cloud API access token | Meta for Developers > WhatsApp > Getting Started > Temporary/Permanent access token. |
| `WHATSAPP_PHONE_ID` | Yes | WhatsApp Business phone number ID | Meta for Developers > WhatsApp > Getting Started > Phone number ID (not the phone number itself). |

---

### 18. iMessage

**When to use:** Sending iMessages from a macOS machine.

**Algorithm:** macOS-only. Uses `osascript` to execute AppleScript that tells the Messages app to send an iMessage. The recipient is addressed via phone number or Apple ID email. Text and recipient strings are escaped for AppleScript. Runs as a subprocess with a 10-second timeout. No API credentials needed — uses the local macOS Messages app and the signed-in Apple ID.

**Tools:**

| Tool | Description |
|------|-------------|
| `imessage_send` | Send an iMessage via macOS Messages app. Recipient can be phone number or Apple ID. |

**Credentials:**

None required. Requires macOS with Messages app and a signed-in Apple ID. Raises `RuntimeError` on non-macOS platforms.

---

### 19. MCP (Dynamic)

**When to use:** Connecting any MCP (Model Context Protocol) server to dynamically discover and expose its tools. This is the escape hatch — if a builtin integration does not exist for a service, point to an MCP server that provides it.

**Algorithm:** Wraps Agentspan's native `mcp_tool()` function. The `add_mcp_integration` tool registers an MCP server URL in an in-memory registry. When agents are created, `create_mcp_integration()` calls `mcp_tool(server_url=...)` which discovers tools via the MCP protocol and returns `ToolDef` instances. Optional credential names can be specified for servers that require authentication headers. An optional tool name whitelist filters which discovered tools to expose.

**Note:** Agentspan already supports `mcp_tool()` natively at the SDK level. This integration wraps it so the orchestrator can discover and connect MCP servers dynamically at runtime, without requiring code changes.

**Tools:**

| Tool | Description |
|------|-------------|
| `add_mcp_integration` | Register an MCP server URL. Tools from that server become available for agent creation. |

**Programmatic API (not exposed as tools):**

| Function | Description |
|----------|-------------|
| `create_mcp_integration(server_url, credentials, tool_names)` | Discover tools from an MCP server. Returns list of `ToolDef`. |
| `get_configured_servers()` | Return all registered MCP servers. |
| `get_mcp_tools_for_server(server_url)` | Discover and return tools from a server (used during Tier 2 integration resolution). |

**Credentials:**

| Name | Required | Description | How to get |
|------|----------|-------------|------------|
| (varies) | Depends on MCP server | Passed as comma-separated string to `add_mcp_integration`, forwarded to `mcp_tool()` | Depends on the specific MCP server being connected. |

---

## Credential Summary

Quick reference of all environment variables across all integrations:

| Integration | Environment Variable | Required |
|-------------|---------------------|----------|
| Web Search | `BRAVE_API_KEY` | Optional |
| Gmail | `GMAIL_ACCESS_TOKEN` | Yes |
| Outlook | `OUTLOOK_ACCESS_TOKEN` | Yes |
| GitHub | `GITHUB_TOKEN` | Yes |
| Slack | `SLACK_BOT_TOKEN` | Yes |
| Doc Reader | (none) | — |
| Local FS | (none) | — |
| Google Calendar | `GOOGLE_CALENDAR_TOKEN` | Yes |
| Google Drive | `GOOGLE_DRIVE_TOKEN` | Yes |
| AWS S3 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | Yes, Yes, Optional |
| Jira | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | Yes, Yes, Yes |
| Linear | `LINEAR_API_KEY` | Yes |
| Notion | `NOTION_API_KEY` | Yes |
| HubSpot | `HUBSPOT_ACCESS_TOKEN` | Yes |
| Salesforce | `SALESFORCE_INSTANCE_URL`, `SALESFORCE_ACCESS_TOKEN` | Yes, Yes |
| Google Analytics | `GA_ACCESS_TOKEN`, `GA_PROPERTY_ID` | Yes, Yes |
| WhatsApp | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` | Yes, Yes |
| iMessage | (none — macOS only) | — |
| MCP | (varies per server) | Varies |
