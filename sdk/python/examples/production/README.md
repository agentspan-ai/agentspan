# Production Deployment Examples

Agentspan agents have three lifecycle phases:

```
define → deploy → serve → run
```

| Phase | What it does | Who runs it |
|---|---|---|
| **Define** | Create agent definitions in Python | Developer |
| **Deploy** | Push definitions to the server | CI/CD pipeline |
| **Serve** | Start workers that execute tools | Runtime service |
| **Run** | Trigger an agent by name | Client / API |

## Quick Start (all-in-one)

Most examples in `../` use `runtime.run(agent, prompt)` which deploys, serves, and runs in one call. That's great for prototyping. For production, separate these concerns.

## Examples

### `github_coding_agent/` — GitHub Issue → PR Pipeline

A three-stage pipeline: fetch issue → code + QA (SWARM) → create PR.
Uses CLI tools, code execution, credentials, gates, and handoffs.

```bash
cd github_coding_agent

# Step 1: Deploy (or: agentspan deploy agents)
python deploy.py

# Step 2: Serve workers (separate terminal)
python serve.py

# Step 3: Trigger
python run.py
# or: agentspan run github_pipeline "Pick an open issue and create a PR."
```

### `ml_pipeline/` — ML Engineering Pipeline

A five-stage pipeline: data analysis → parallel model exploration → evaluation → iterative refinement → report.

```bash
cd ml_pipeline

# Step 1: Deploy
python deploy.py

# Step 2: Serve workers (separate terminal)
python serve.py

# Step 3: Trigger
python run.py
# or: agentspan run ml_pipeline "Build a model for California housing prices."
```

## CLI Deployment (Recommended for CI/CD)

```bash
# Deploy all agents from a Python module
agentspan deploy examples.production.github_coding_agent.agents

# Start workers
agentspan serve examples.production.github_coding_agent.agents

# Trigger by name
agentspan run github_pipeline "Pick an open issue and create a PR."
```
