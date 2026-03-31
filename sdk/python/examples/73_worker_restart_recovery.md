# Worker Restart Recovery Demo

This demo proves that an agent execution survives worker-service outage and continues after the worker service comes back.

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

## Terminal 1: Deploy the agent definition

```bash
python 73_worker_restart_recovery.py deploy
```

## Terminal 2: Start the worker service

```bash
python 73_worker_restart_recovery.py serve
```

This writes the worker PID and process group to `/tmp/agentspan_worker_restart.worker.json`.

## Terminal 3: Kill the worker service

```bash
python 73_worker_restart_recovery.py kill-worker
```

This sends `SIGKILL` to the worker process group, including the polling child processes.

## Terminal 4: Start the agent while workers are down

```bash
python 73_worker_restart_recovery.py start
```

You should see the agent stay `RUNNING` with `attempts=none` because no worker service is available to execute the tool.

## Terminal 5: Restart the worker service

```bash
python 73_worker_restart_recovery.py serve
```

## Optional: Watch status separately

```bash
python 73_worker_restart_recovery.py status
```

The attempt history file at `/tmp/agentspan_worker_restart.attempts.json` should eventually show:

- no attempts while the worker service is down
- attempt 1 starts and completes after the worker service comes back

## What this proves

- Agent definitions can be deployed separately from worker processes
- The agent execution remains durable while the worker service is down
- After the worker returns, the queued tool task runs and the same execution finishes
- Recovery is from durable execution state, not from keeping the original Python process alive
