from conductor.ai.agents import Agent, AgentRuntime, tool, EventType
import sys
import os
import logging

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
logging.getLogger("conductor.ai.agents.runtime").setLevel(logging.ERROR)
logging.getLogger("conductor.ai.agents.run").setLevel(logging.ERROR)
logging.getLogger("conductor.ai.agents.worker_manager").setLevel(logging.ERROR)
logging.getLogger("conductor.client.automator.task_handler").setLevel(logging.ERROR)
logging.getLogger("conductor.client.automator.task_runner").setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# GMAIL MODE
# Set USE_GMAIL=true to use your real Gmail inbox.
# Otherwise the agent runs on sample data so you can try it without any setup.
#
# To connect Gmail:
#   1. Go to Google Cloud Console and enable the Gmail API
#   2. Create OAuth 2.0 credentials (Desktop app) and download as credentials.json
#   3. pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
#   4. Run with: USE_GMAIL=true python subscription-agent.py
#
# The first run will open a browser to authorize access. After that it saves
# a token.json so it won't ask again.
# ---------------------------------------------------------------------------

USE_GMAIL = os.environ.get("USE_GMAIL", "false").lower() == "true"

## Sample inbox data that you can swap for real Gmail API calls when you're ready
SAMPLE_RECEIPTS = [
    {
        "id": "msg_8821",
        "subject": "Your Spotify Family plan renewal",
        "body": "Spotify Family. We charged $15.99 to your card on Apr 28. Last listened: yesterday.",
    },
    {
        "id": "msg_8456",
        "subject": "Spotify Premium receipt",
        "body": "Spotify Premium ($9.99) renewed on Apr 28. Account inactive: no plays in 90 days.",
    },
    {
        "id": "msg_9134",
        "subject": "Adobe Creative Cloud renewed",
        "body": "Your free trial converted to Creative Cloud paid plan on Apr 1. Charged $52.99/mo. Last sign-in: never.",
    },
    {
        "id": "msg_7402",
        "subject": "Equinox monthly billing",
        "body": "Equinox membership charged $39.00 on Apr 15. Last gym check-in: Dec 12, 2024.",
    },
    {
        "id": "msg_9011",
        "subject": "Calm subscription renewed",
        "body": "Calm subscription ($14.99) renewed on Apr 22. Last app open: Sep 2024.",
    },
    {
        "id": "msg_7711",
        "subject": "Netflix Premium",
        "body": "Netflix Premium ($22.99) charged on Apr 18. Last watched: yesterday.",
    },
    {
        "id": "msg_8432",
        "subject": "NYT Digital",
        "body": "New York Times Digital ($4.25/mo) renewed Apr 10. Articles read this month: 23.",
    },
    {
        "id": "msg_9999",
        "subject": "ChatGPT Plus",
        "body": "ChatGPT Plus ($20.00) renewed Apr 5. Last used: today.",
    },
    {
        "id": "msg_5544",
        "subject": "iCloud+ storage",
        "body": "iCloud+ ($2.99) renewed Apr 1. Storage used: 87%.",
    },
    {                                                                                      
        "id": "msg_1001",                                                                  
        "subject": "Your order has shipped!",                                            
        "body": "Your Amazon order #112-3456789 has shipped. Estimated delivery: May 10.", 
    },                                                                                     
    {                                                                                      
        "id": "msg_1002",                                                                  
        "subject": "Maria, someone liked your post",                                       
        "body": "John Doe liked your photo on Instagram.",                               
    },                                                                                     
    {
        "id": "msg_1003",                                                                  
        "subject": "Your flight is confirmed",                                           
        "body": "Booking confirmation for AA1234 New York to LA on May 15. Seat 14A.",     
    },                                                                                     
    {                                                                                      
        "id": "msg_1004",                                                                  
        "subject": "Weekly newsletter: top stories this week",                           
        "body": "Here are the top stories from The Hustle this week: AI is changing everything...",                                                                            
    }
]

## Tools your agent can use. This is where the "build any agent" point lives. Swap these functions for whatever tools your agent needs. Just rewrite the instructions below and you will have a different agent. The agent definition itself doesn't change. The important bit here that makes this into a tool is the @tool decorator above each function.

if USE_GMAIL:
    import base64
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    @tool
    def get_inbox_stats() -> dict:
        """Get basic stats about the inbox: total emails and email address."""
        service = _get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        inbox = service.users().labels().get(userId="me", id="INBOX").execute()
        return {
            "inbox_conversations": inbox.get("threadsTotal", 0),
            "inbox_unread": inbox.get("threadsUnread", 0),
            "email_address": profile.get("emailAddress", ""),
        }

    def _get_gmail_service():
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as f:
                f.write(creds.to_json())
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    @tool
    def search_emails(query: str) -> list:
        """Search the inbox for emails matching a query.

        Returns a list of email summaries: [{id, subject}, ...].
        """
        service = _get_gmail_service()
        # Run multiple focused searches and deduplicate
        all_messages = []
        seen_ids = set()
        queries = [
            # Generic billing terms — one at a time so Gmail parses them correctly
            "invoice",
            "receipt",
            "subscription",
            "renewal",
            # Known dev/SaaS vendors
            "Vercel OR Anthropic OR Supabase OR OpenAI OR Railway",
            "GitHub OR Notion OR Figma OR Linear OR Cursor",
            "Searchable OR Stripe OR AWS OR Google Cloud",
        ]
        for q in queries:
            r = service.users().messages().list(userId="me", q=q, maxResults=3, includeSpamTrash=False).execute()
            for m in r.get("messages", []):
                if m["id"] not in seen_ids:
                    all_messages.append(m)
                    seen_ids.add(m["id"])
        messages = all_messages[:15]
        summaries = []
        for msg in messages:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata", metadataHeaders=["Subject"]
            ).execute()
            headers = detail.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(no subject)")
            snippet = detail.get("snippet", "")
            summaries.append({"id": msg["id"], "subject": subject, "preview": snippet})
        return summaries

    @tool
    def get_email_body(email_id: str) -> str:
        """Fetch the full text body of a specific email by ID."""
        import time
        import re
        time.sleep(1)
        service = _get_gmail_service()
        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        payload = msg.get("payload", {})

        text = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part["body"].get("data", "")
                    text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        # Strip HTML tags, collapse whitespace, and trim
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]

else:
    @tool
    def search_emails(query: str) -> list:
        """Search the inbox for emails matching a query.

        Returns a list of email summaries: [{id, subject}, ...].
        """
        return [{"id": r["id"], "subject": r["subject"]} for r in SAMPLE_RECEIPTS]

    @tool
    def get_email_body(email_id: str) -> str:
        """Fetch the full text body of a specific email by ID."""
        for receipt in SAMPLE_RECEIPTS:
            if receipt["id"] == email_id:
                return receipt["body"]
        return ""

## Your agent instructions
INSTRUCTIONS = """
  You are a subscription analyst with access to the user's email inbox.

  First, decide what kind of question this is:

  - GENERAL KNOWLEDGE / CHITCHAT (math, definitions, greetings, anything unrelated to email):
    Answer directly. Do not call any tools.

  - SIMPLE INBOX QUESTION (how many emails, unread count, what account):
    Call get_inbox_stats and answer in one or two sentences. Done.

  - GENERAL EMAIL QUESTION (what emails did I get this month, emails from a sender,
    recent emails, search for something specific):
    Call search_emails with an appropriate query, then summarize what you found
    conversationally. No report format, just answer the question directly.

  - SIMPLE SUBSCRIPTION QUESTION (how many subscriptions do I have, do I have [specific service],
    what is my most expensive subscription, which subscriptions haven't I used, am I paying for X):
    Call search_emails ONCE with "invoice receipt subscription renewal", then call get_email_body
    only for emails that clearly suggest a recurring charge. Answer the specific question directly
    in a few sentences. No report format, no sections, just answer what was asked.

  - SUBSCRIPTION ANALYSIS (find all my subscriptions, what should I cancel, billing charges,
    recurring payments, full spending breakdown, what am I wasting money on):
    Do the full analysis below.

  For subscription analysis, do exactly this in order:
  1. Call search_emails ONCE with the query "invoice receipt subscription renewal".
  2. Look at the subject line and preview of each email returned.
     Only call get_email_body for emails whose subject or preview clearly suggests
     a recurring charge, subscription, renewal, or billing — skip anything else.
  3. After reading each qualifying email, output a line in this format:
     FOUND: <vendor> | $<amount> | <monthly/annual/per-usage> | <one sentence about usage or suspicion>
  4. After going through all emails, write a final report with these sections:

  💸 SPENDING SUMMARY
  List each subscription found with the amount, how often they are charged (monthly,
  annually, per usage, etc), and the estimated annual cost.
  If the same vendor appears more than once, flag it as a duplicate and show both charges.

  ⚠️ CANCEL THESE
  For each subscription worth canceling (unused, duplicate, or suspicious), say why
  and include the cancellation URL or where to go to cancel it (account settings page,
  app settings, etc). Be specific — don't just say "go to settings".

  ✅ KEEP THESE
  Subscriptions that show clear active usage — just list them briefly.

  💰 POTENTIAL SAVINGS
  Total monthly and annual savings if they cancel everything in the cancel list.

  Use emojis throughout to make it engaging. Write in a friendly, conversational tone —
  like a helpful friend going through your bills with you. No markdown tables.
  """

## Your agent definition. You put the agent together here

tools = [search_emails, get_email_body]
if USE_GMAIL:
    tools.append(get_inbox_stats)

agent = Agent(
  name="subscription_finder",
  model="anthropic/claude-sonnet-4-6",
  tools=tools,
  instructions=INSTRUCTIONS
)


def handle_events(handle):
    email_subjects = {}
    for event in handle.stream():
        if event.type == EventType.TOOL_CALL:
            if event.tool_name == "search_emails":
                print(f"\n  🔍 Searching: {event.args.get('query', '')}")
            elif event.tool_name == "get_email_body":
                email_id = event.args.get("email_id", "")
                subject = email_subjects.get(email_id, email_id)
                print(f"  📧 Reading: {subject}")
            elif event.tool_name == "get_inbox_stats":
                print(f"\n  📊 Checking inbox stats...")

        elif event.type == EventType.TOOL_RESULT:
            if event.tool_name == "search_emails" and isinstance(event.result, list):
                for item in event.result:
                    if isinstance(item, dict) and "id" in item:
                        email_subjects[item["id"]] = item.get("subject", item["id"])
                print(f"  Found {len(event.result)} emails to review\n")

        elif event.type == EventType.THINKING:
            if event.content:
                for line in event.content.splitlines():
                    if line.strip().startswith("FOUND:"):
                        print(f"  {line.strip()}")

        elif event.type == EventType.DONE:
            result = event.output.get("result", event.output) if isinstance(event.output, dict) else event.output
            result = str(result).strip()
            found_lines = [l.strip() for l in result.splitlines() if l.strip().startswith("FOUND:")]
            summary_lines = [l for l in result.splitlines() if not l.strip().startswith("FOUND:")]
            for line in found_lines:
                print(f"  {line}")
            summary = "\n".join(summary_lines).strip()
            if summary:
                print("\n" + summary)


with AgentRuntime() as runtime:
    print("\n📬 Hey! I'm your Gmail subscription analyst.")
    print("I can find your subscriptions, spot duplicates, flag unused services,")
    print("and tell you exactly what to cancel and where to cancel it.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye! 👋")
            break
        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit", "bye"):
            print("\nGoodbye! 👋")
            break
        print()
        handle_events(runtime.start(agent, prompt))
        print()