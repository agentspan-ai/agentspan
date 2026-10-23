# On-call triage agent

An Agentspan agent that triages Orkes SaaS cluster health-check alerts. It listens on
the Slack alert channel, reads the failing `health_check` execution, runs **read-only**
agent-handler commands to investigate, and replies in the alert thread with a
root-cause hypothesis.

**It is advisory and strictly read-only** — it never takes a remediating action. SQL is
gated by a deterministic SELECT-only guard ([`sql_guard.py`](src/oncall_agent/sql_guard.py)),
not by trusting the model.

## How it works

```
Slack health-check alert  ──►  oncall-agent (polls the channel, Web API)
        │  parse executionId from the alert URL
        ▼
   Agentspan agent (Claude) reasoning loop
        │  tools = read-only agent-handler commands, dispatched to ah5r-prod Conductor
        │    get_incident_details · get_cluster_metrics · get_pods_data · get_pod_events
        │    get_top_output · pull_pod_logs · run_sql_select (SELECT-guarded) · …
        ▼
   threaded reply: Issue / Findings / Likely root cause / Suggested next step
```

The agent reads `organizationId` / `clusterName` / `cloudEnvironmentTag` off the failing
execution, so the LLM only threads the **executionId** into each tool — it cannot target
the wrong cluster, and no secrets pass through tool arguments. The agent-handler workflows
mint the customer-cluster JWT themselves via their `prepare_agent_handler` task.

## Setup (local / laptop)

```bash
cd oncall-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../sdk/python        # Agentspan SDK (editable)
pip install -r requirements.txt
cp .env.example .env                # fill in the blanks
```

You also need:
- the **Agentspan server** running locally (default `http://localhost:6767/api`) with
  `ANTHROPIC_API_KEY` set in its environment (it makes the Claude calls);
- a **Conductor application** on ah5r-prod with workflow read + execute access — put its
  key/secret in `.env`;
- a **Slack app** with a bot token (`xoxb-…`) that has `channels:history` + `chat:write`,
  added to the alert channel; set `SLACK_ALERT_CHANNEL` to that channel id. (Same Web API
  approach as `sdk/python/examples/91_slack_autofix_agent.py` — no Socket Mode.)

## Run

```bash
# Poll the alert channel once
python -m oncall_agent.main

# Poll continuously (interval from ONCALL_POLL_INTERVAL, default 300s)
python -m oncall_agent.main --loop

# Triage a single execution id directly (no Slack needed — great for testing/replay)
python -m oncall_agent.main triage 364b459a-689f-11f1-94b6-de01f12a4ed9
```

## Tests

Deterministic, no LLM in the assertion path (per repo `CLAUDE.md`):

```bash
PYTHONPATH=src python -m pytest -q
```

- `test_sql_guard.py` — the SELECT-only guard accepts read queries and rejects every
  mutation / multi-statement / comment-smuggling case.
- `test_alert.py` — alert parsing extracts the execution id + severity and ignores
  non-alert chatter.

## Scope (v1)

Triage + read-only investigation only. Remediation (restart, scale, rollback) is
deliberately **out of scope** — when added it must go behind the Agentspan HITL approval
gate. Run it in dry-run on all alerts first and score its hypotheses before trusting it.
