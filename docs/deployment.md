---
title: Deployment
description: Deploy Agentspan locally with SQLite, with Docker Compose, or on Kubernetes
---

# Deployment

Agentspan runs on a persistent server that manages durable execution. Your Python workers connect to the server and execute tools as distributed tasks.

## Local Development (SQLite — zero setup)

The default setup uses SQLite with WAL mode. No external database needed.

```bash
agentspan server start
```

Data is stored in `agent-runtime.db` in the working directory. The UI and API are both at `http://localhost:6767`.

## Production (PostgreSQL + Docker Compose)

For production workloads, use PostgreSQL for durability and concurrent access.

**1. Clone the repo and start the compose stack:**

```bash
cd deployment/docker-compose
cp .env.example .env
# Set at least one LLM provider key in .env (e.g. OPENAI_API_KEY)
docker compose up -d
```

The compose stack starts two services:
- `agentspan` — the Agentspan server (port 6767)
- `postgres` — PostgreSQL 16

Open `http://localhost:6767` for the UI. Health check: `http://localhost:6767/actuator/health`.

**2. Point your Python workers at the running server:**

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767
python my_agent.py
```

Workers are stateless Python processes that poll the server for tasks. Scale them independently.

## PostgreSQL (without Docker)

Start PostgreSQL separately and configure the server:

```bash
export SPRING_DATASOURCE_URL=jdbc:postgresql://your-host:5432/conductor
export SPRING_DATASOURCE_USERNAME=your_user
export SPRING_DATASOURCE_PASSWORD=your_password
export SPRING_PROFILES_ACTIVE=postgres
agentspan server start
```

## Kubernetes

Kubernetes manifests and a Helm chart are included in the repo under `deployment/k8s/` and `deployment/helm/`.

For a minimal single-node deployment:

```yaml
# agentspan-server Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentspan-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: agentspan-server
  template:
    metadata:
      labels:
        app: agentspan-server
    spec:
      containers:
        - name: agentspan-server
          image: ghcr.io/agentspan-ai/agentspan-server:latest
          ports:
            - containerPort: 6767
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: postgres
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: agentspan-secrets
                  key: db-url
            - name: SPRING_DATASOURCE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: agentspan-secrets
                  key: db-username
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: agentspan-secrets
                  key: db-password
---
apiVersion: v1
kind: Service
metadata:
  name: agentspan-server
spec:
  selector:
    app: agentspan-server
  ports:
    - port: 6767
      targetPort: 6767
```

Worker pods connect via `AGENTSPAN_SERVER_URL`:

```python
import os
os.environ["AGENTSPAN_SERVER_URL"] = "http://agentspan-server:6767"

from agentspan.agents import Agent, run
agent = Agent(name="my_agent", model="openai/gpt-4o")
result = run(agent, "Hello")
```

Workers are stateless — run as many replicas as you need. The server queues tasks; workers poll and execute them.

## Authentication

For remote servers (non-localhost), set auth credentials:

```bash
export AGENTSPAN_SERVER_URL=https://my-server.example.com
export AGENTSPAN_AUTH_KEY=my-key
export AGENTSPAN_AUTH_SECRET=my-secret
```

Or via code:

```python
from agentspan.agents import configure

configure(
    server_url="https://my-server.example.com",
    auth_key="my-key",
    auth_secret="my-secret",
)
```

No other code changes needed. Your agents run exactly the same — the only difference is where the server runs.

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `SERVER_PORT` | `6767` | Server port |
| `SPRING_PROFILES_ACTIVE` | `default` (SQLite) | Set to `postgres` for PostgreSQL |
| `SPRING_DATASOURCE_URL` | `jdbc:sqlite:agent-runtime.db` | Database URL |
| `SPRING_DATASOURCE_USERNAME` | `postgres` | Database user |
| `SPRING_DATASOURCE_PASSWORD` | `postgres` | Database password |
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767` | Server URL (used by SDK/workers) |
| `AGENTSPAN_AUTH_KEY` | — | Auth key (required for non-localhost) |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret (required for non-localhost) |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `MISTRAL_API_KEY` | — | Mistral API key |
| `GROQ_API_KEY` | — | Groq API key |

## Production Checklist

Before going to production:

- [ ] Switch from SQLite to a managed PostgreSQL (RDS, Cloud SQL, etc.)
- [ ] Set `AGENTSPAN_AUTH_KEY` and `AGENTSPAN_AUTH_SECRET` for all workers
- [ ] Configure `max_turns` and timeouts for long-running agents
- [ ] Add guardrails for all user-facing agents
- [ ] Test agents with `mock_run` before deploying
- [ ] Use `AgentHandle.get_status()` to monitor long-running executions
- [ ] Set up alerting via the Agentspan UI or Prometheus metrics
