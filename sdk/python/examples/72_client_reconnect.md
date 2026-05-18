# Client Reconnect Demo

This demo proves that an agent execution survives a hard kill of the local SDK process.

## Prerequisites

Start the Agentspan server with Docker Compose from the deployment branch or worktree:

```bash
cd deployment/docker-compose
cp .env.example .env
# set OPENAI_API_KEY in .env
docker compose up -d
```

Create a clean virtual environment and install the published package:

```bash
cd sdk/python/examples
python3 -m venv .venv-pypi
source .venv-pypi/bin/activate
pip install --upgrade pip
pip install agentspan
```

Set the server URL and model:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
```

## Terminal 1: Start the agent

```bash
python 72_client_reconnect.py start
```

Wait for:

```text
Agent is durably paused on the server.
Now hard-kill this client from another terminal with:
  python 72_client_reconnect.py kill-client --client-info-file /tmp/agentspan_client_reconnect.client.json
```

## Terminal 2: Hard-kill the client

```bash
python 72_client_reconnect.py kill-client
```

This sends `SIGKILL` to the original SDK process. There is no graceful shutdown.

## Terminal 3: Reconnect and continue

```bash
python 72_client_reconnect.py resume --approve
```

Optional: inspect status without approving:

```bash
python 72_client_reconnect.py status
```

## What this proves

- The local Python SDK process can die abruptly
- The agent execution remains durable on the server
- A fresh process can re-register the tool worker
- A fresh process can reconnect later by `execution_id`
- The same agent execution continues and completes after approval is sent
