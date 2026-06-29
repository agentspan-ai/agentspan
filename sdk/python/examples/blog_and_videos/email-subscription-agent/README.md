# Email Subscription Finder Agent

An AI agent that scans your email inbox for recurring charges, flags unused or duplicate subscriptions, and tells you exactly what to cancel and where — with a running total of how much you'd save.

Built with [Agentspan](https://agentspan.ai/).

---

## How it works

The agent runs as an interactive chatbot in your terminal. Ask it to find your subscriptions and it will:

1. Search your inbox for billing and renewal emails
2. Read each relevant email
3. Identify every recurring charge
4. Produce a report: what to cancel, what to keep, and how much you'd save

By default it runs on sample inbox data so you can try it immediately with no setup beyond an API key. When you're ready, you can point it at your real Gmail inbox.

---

## Requirements

- Python 3.8+
- An Anthropic API key (or OpenAI if you prefer)

---

## Setup

**1. Install Agentspan**

```bash
pip install conductor-agent-sdk
```

**2. Set your API key**

```bash
export ANTHROPIC_API_KEY=your_key_here
```

**3. Start the Agentspan server**

Agentspan runs on top of Conductor, which needs a local server process running in the background.

```bash
agentspan server start
```

**4. Run the agent**

```bash
python subscription-agent.py
```

Then ask it something like:

```
You: how many subscriptions do I have?
```

---

## Connect to your real Gmail inbox

By default the agent uses sample data. To run it against your actual inbox:

**1. Enable the Gmail API**

Go to [Google Cloud Console](https://console.cloud.google.com), create a project, enable the Gmail API, then create OAuth 2.0 credentials (Desktop app type) and download the file as `credentials.json` into this folder.

**2. Install the Gmail client libraries**

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

**3. Run with the Gmail flag**

```bash
USE_GMAIL=true python subscription-agent.py
```

The first run will open a browser window to authorize access. After that it saves a `token.json` file and won't ask again.

---

## What you can ask it

- `how many subscriptions do I have?`
- `do I have Spotify?`                                                                       
- `what's my most expensive subscription?`                                                   
- `which subscriptions haven't I used?`                                                      
- `am I paying for Adobe?`    
- General questions work too — it won't run a full analysis unless you ask for one

Type `exit`, `quit`, or `bye` to stop.

---

## Project structure

```
subscription-agent.py   # The agent — tools, instructions, and main loop
credentials.json        # Gmail OAuth credentials (not committed)
token.json              # Gmail auth token, created on first run (not committed)
```

---

## Customizing it

The agent definition never changes — only the tools and instructions do. To build a different agent, replace the tool functions with whatever your agent needs to access (a spreadsheet, a database, an API) and rewrite the instructions to describe the new goal.

```python
agent = Agent(
    name="your_agent_name",
    model="anthropic/claude-sonnet-4-6",
    tools=[your_tools_here],
    instructions=YOUR_INSTRUCTIONS
)
```
