@ -0,0 +1,530 @@
# Sentinel Agents: Always-On, Event-Driven, Omnipresent AI Agents

**Status**: Draft
**Author**: Agent SDK Team
**Date**: March 2026

---
<!-- TOC -->
* [Sentinel Agents: Always-On, Event-Driven, Omnipresent AI Agents](#sentinel-agents--always-on-event-driven-omnipresent-ai-agents)
  * [1. Problem Statement](#1-problem-statement)
  * [2. Landscape Analysis](#2-landscape-analysis)
    * [2.1 AutoGen v0.4 (AG2)](#21-autogen-v04--ag2-)
    * [2.2 CrewAI](#22-crewai)
    * [2.3 LangGraph Platform](#23-langgraph-platform)
    * [2.4 OmniDaemon (Research Pattern)](#24-omnidaemon--research-pattern-)
    * [2.5 Microsoft Sentinel (Security)](#25-microsoft-sentinel--security-)
    * [2.6 Summary: The Gap](#26-summary--the-gap)
  * [3. Conceptual Model](#3-conceptual-model)
    * [3.1 The Sentinel Agent](#31-the-sentinel-agent)
    * [3.2 The Activation Layer](#32-the-activation-layer)
    * [3.3 Trigger Types](#33-trigger-types)
      * [Schedule](#schedule)
      * [Event Trigger](#event-trigger)
      * [Webhook Trigger](#webhook-trigger)
      * [File Watch](#file-watch)
      * [Stream Watch](#stream-watch)
    * [3.4 Prompt Templating](#34-prompt-templating)
  * [4. Deployment Architecture](#4-deployment-architecture)
    * [4.1 Server-Side Triggers (Schedule, Event, Webhook)](#41-server-side-triggers--schedule-event-webhook-)
    * [4.2 Local Source Watchers (FileWatch, StreamWatch)](#42-local-source-watchers--filewatch-streamwatch-)
    * [4.3 How You Install and Run This](#43-how-you-install-and-run-this)
    * [4.4 Multi-Instance / HA Deployment](#44-multi-instance--ha-deployment)
  * [5. Lifecycle Management](#5-lifecycle-management)
    * [5.1 Deployment Handle](#51-deployment-handle)
    * [5.2 Observability](#52-observability)
  * [6. Concrete Examples](#6-concrete-examples)
    * [6.1 Log Sentinel](#61-log-sentinel)
    * [6.2 PR Review Sentinel](#62-pr-review-sentinel)
    * [6.3 Incident Responder](#63-incident-responder)
    * [6.4 Omnipresent Ops Agent](#64-omnipresent-ops-agent)
  * [7. Execution Plan](#7-execution-plan)
    * [Phase 1: Foundation (Schedule + Deploy/Undeploy)](#phase-1--foundation--schedule--deployundeploy-)
    * [Phase 2: Event & Webhook Triggers](#phase-2--event--webhook-triggers)
    * [Phase 3: Local File Watching](#phase-3--local-file-watching)
    * [Phase 4: Stream Watching](#phase-4--stream-watching)
    * [Phase 5: CLI & Observability](#phase-5--cli--observability)
    * [Phase 6: Advanced Patterns](#phase-6--advanced-patterns)
  * [8. Open Design Questions](#8-open-design-questions)
<!-- TOC -->
## 1. Problem Statement

Today's agentic frameworks are **request-response**: a human types a prompt, the agent runs, returns a result. But real-world automation needs agents that are **always watching**:

- A log sentinel that tails application logs and creates tickets when it detects critical errors
- A news monitor that checks for breaking stories every hour and sends digests
- An incident responder that wakes up when PagerDuty fires a critical alert
- A deployment watcher that reviews every PR merge and validates the rollout
- An ops agent that monitors Kubernetes pods, restarts crashed services, and pages on-call

These aren't "chatbot" agents. They are **autonomous background processes with LLM brains**. They need:

1. **Activation** — something to wake them up (schedule, event, file change, webhook)
2. **Context** — the triggering data injected into their prompt (log lines, event payload, PR diff)
3. **Tools** — actions they can take (create ticket, send alert, restart service, query DB)
4. **Durability** — retry on failure, audit trail, timeout protection
5. **Lifecycle management** — deploy, pause, resume, undeploy, observe

No current framework provides a clean, unified model for all of this.

## 2. Landscape Analysis

### 2.1 AutoGen v0.4 (AG2)

AutoGen v0.4 (January 2025) adopted an async, event-driven, actor-model architecture. Agents exchange messages asynchronously with rich event surfacing (model calls, tool invocations, terminations).

**Relevant**: Core event-driven architecture
**Gap**: No deployment model. No external triggers (cron, file, webhook). You run it; it runs once.

### 2.2 CrewAI

CrewAI distinguishes **Crews** (autonomous agent groups) from **Flows** (event-driven pipelines). Flows provide deterministic, event-driven orchestration with conditional branching and state management.

**Relevant**: Event-driven Flows with production-grade control
**Gap**: "Events" are internal flow routing, not external activation. No scheduled execution, no file watchers, no webhook triggers out of the box.

### 2.3 LangGraph Platform

LangGraph Platform (GA October 2025) supports background runs with polling/streaming/webhooks for status monitoring. Includes a task queue for bursty workloads. Mentions cron support.

**Relevant**: Background execution model, task queue, webhook status callbacks
**Gap**: Platform is a managed deployment service, not a framework primitive. Event sources are limited. No local daemon patterns (file watching, stream tailing).

### 2.4 OmniDaemon (Research Pattern)

Event-driven runtime where agents subscribe to "Topics" (e.g. Redis streams). When a message arrives on a topic, the daemon triggers the agent callback.

**Relevant**: Closest to the sentinel pattern — daemon process + event stream subscription
**Gap**: Single event source type (Redis streams). No scheduling, no file watching.

### 2.5 Microsoft Sentinel (Security)

Microsoft Sentinel evolved from SIEM to an "agentic platform" with AI agents for security operations. Sentinel agents deploy as **sidecars** alongside primary systems — intercepting, filtering, and pre-validating communications.

**Relevant**: Sidecar deployment model. Continuous behavioral monitoring. Hybrid rule-based + LLM auditing.
**Gap**: Domain-specific (security). Not a general-purpose framework.

### 2.6 Summary: The Gap

| Capability | AutoGen | CrewAI | LangGraph | **Ours (Goal)** |
|---|---|---|---|---|
| Cron scheduling | - | - | Partial | **Yes** |
| Event triggers | Internal | Internal | Webhooks | **Yes (Conductor events)** |
| Webhook triggers | - | - | Status only | **Yes** |
| File/log watching | - | - | - | **Yes (local daemon)** |
| Stream watching (Kafka/Redis) | - | - | - | **Yes (local consumer)** |
| Multi-trigger per agent | - | - | - | **Yes** |
| Durable execution (retry, audit) | - | - | Yes | **Yes (Conductor)** |
| Simple deployment | - | - | Managed service | **Yes (pip + one command)** |

## 3. Conceptual Model

### 3.1 The Sentinel Agent

A **Sentinel Agent** is a regular agent (model + tools + instructions) with one addition: **triggers** that define when and how it activates.

```
Sentinel Agent = Agent + Triggers
```

The agent definition describes **what** it does. Triggers describe **when** it runs.

### 3.2 The Activation Layer

```
┌──────────────────────────────────────────────────────────────┐
│                     ACTIVATION LAYER                          │
│                                                               │
│   ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌───────────────┐  │
│   │ Schedule  │ │  Event    │ │ Webhook │ │  Source Watch  │  │
│   │ (cron)   │ │ (pub/sub) │ │ (HTTP)  │ │ (file/stream) │  │
│   └────┬─────┘ └─────┬─────┘ └────┬────┘ └───────┬───────┘  │
│        │              │            │              │           │
│        └──────────────┴────────────┴──────────────┘           │
│                           │                                   │
│                    ┌──────▼──────┐                             │
│                    │   TRIGGER   │ ← context injected          │
│                    │   (prompt)  │   into prompt template       │
│                    └──────┬──────┘                             │
│                           │                                   │
│              ┌────────────▼─────────────┐                     │
│              │    AGENT EXECUTION       │                     │
│              │  ┌─────┐ ┌─────┐ ┌────┐ │                     │
│              │  │ LLM │→│Tools│→│ LLM│ │                     │
│              │  └─────┘ └─────┘ └────┘ │                     │
│              │  + guardrails + memory   │                     │
│              └────────────┬─────────────┘                     │
│                           │                                   │
│                    ┌──────▼──────┐                             │
│                    │   ACTION    │ (alert, fix, report,        │
│                    │   (output)  │  create ticket, restart...) │
│                    └─────────────┘                             │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Trigger Types

#### Schedule
Runs the agent on a cron expression. Server-side — the orchestration platform handles timing.

```
Schedule:
  cron: "*/5 * * * *"          # every 5 minutes
  prompt: "Run health checks on all production services."
  timezone: "UTC"               # optional
  start_time: null              # optional window start
  end_time: null                # optional window end
  catch_up: false               # run missed executions?
```

**Maps to**: Conductor `SchedulerClient.save_schedule()` / any execution engine's cron scheduler.

#### Event Trigger
Runs the agent when a named event fires. The event payload is injected into the prompt.

```
EventTrigger:
  event: "pagerduty:incident"   # event source/name
  condition: "event.severity == 'critical'"  # optional filter
  prompt: "Critical incident: ${event.title}\nDetails: ${event.description}"
```

**Maps to**: Conductor `EventHandler` / Kafka consumer / any pub-sub system.

#### Webhook Trigger
Runs the agent when an HTTP request arrives matching certain criteria.

```
WebhookTrigger:
  matches:                      # payload matching criteria
    type: "pull_request"
    action: "opened"
  prompt: "New PR opened: ${webhook.payload}"
```

**Maps to**: Conductor webhook receiver / any HTTP endpoint that starts a workflow.

#### File Watch
Runs the agent when a local file matches a pattern. Requires a local watcher process.

```
FileWatch:
  path: "/var/log/myapp/*.log"  # file path or glob
  pattern: "(ERROR|CRITICAL)"   # regex to match
  prompt: "Log error detected:\n\n{matched_lines}"
  debounce: 30                  # seconds between triggers (prevent storm)
  lookback: 50                  # lines of context around match
```

**Maps to**: Local daemon thread that tails files → calls workflow start API on match.

#### Stream Watch
Runs the agent when a message appears on a message stream.

```
StreamWatch:
  source: "kafka://alerts-topic"   # or redis://stream, sqs://queue, etc.
  filter: "message.level == 'error'"
  prompt: "Alert from stream: {message}"
```

**Maps to**: Local consumer thread → calls workflow start API on message.

### 3.4 Prompt Templating

Triggers inject context into the agent's prompt via template variables:

| Trigger Type | Available Variables |
|---|---|
| Schedule | `{run_time}`, `{run_count}`, `{last_run_time}` |
| EventTrigger | `${event.*}` (event payload fields) |
| WebhookTrigger | `${webhook.payload}`, `${webhook.headers}` |
| FileWatch | `{matched_lines}`, `{filepath}`, `{line_number}`, `{match}` |
| StreamWatch | `{message}`, `{topic}`, `{offset}`, `{timestamp}` |

Server-side triggers use `${...}` (Conductor expression syntax, resolved server-side).
Local triggers use `{...}` (resolved by the local watcher before workflow start).

## 4. Deployment Architecture

### 4.1 Server-Side Triggers (Schedule, Event, Webhook)

These are fully managed by the orchestration server. No local process needed beyond initial registration.

```
Developer                    Orchestration Server
    │                              │
    │  deploy(agent, triggers)     │
    │─────────────────────────────►│
    │                              │  1. Register workflow definition
    │                              │  2. Create schedule (cron)
    │                              │  3. Register event handlers
    │                              │  4. Start tool workers
    │  DeploymentHandle            │
    │◄─────────────────────────────│
    │                              │
    │                              │  [cron fires / event arrives]
    │                              │  → Start agent execution
    │                              │  → LLM + tools execute
    │                              │  → Result stored
    │                              │
    │  handle.executions()         │
    │─────────────────────────────►│
    │  [list of past runs]         │
    │◄─────────────────────────────│
```

### 4.2 Local Source Watchers (FileWatch, StreamWatch)

These require a local daemon process that watches the source and triggers the agent.

```
┌─────────────────────────────────┐       ┌───────────────────────┐
│      Local Watcher Process       │       │  Orchestration Server │
│                                  │       │                       │
│  ┌────────────────────────────┐  │       │                       │
│  │ FileWatch Thread           │  │       │                       │
│  │  tail -F /var/log/app.log  │──┼─match─┼──► start_workflow()   │
│  │  pattern: "ERROR"          │  │       │      prompt = "..."   │
│  │  debounce: 30s             │  │       │      → Agent runs     │
│  └────────────────────────────┘  │       │                       │
│                                  │       │                       │
│  ┌────────────────────────────┐  │       │                       │
│  │ StreamWatch Thread         │  │       │                       │
│  │  Kafka consumer: alerts    │──┼──msg──┼──► start_workflow()   │
│  │  filter: level == 'error'  │  │       │      prompt = "..."   │
│  └────────────────────────────┘  │       │                       │
│                                  │       │                       │
│  ┌────────────────────────────┐  │       │                       │
│  │ Tool Workers               │  │       │                       │
│  │  Serving @tool functions   │◄─┼───────┼── poll for tasks      │
│  └────────────────────────────┘  │       │                       │
│                                  │       │                       │
│  runtime.wait() ← blocks here   │       │                       │
└─────────────────────────────────┘       └───────────────────────┘
```

The local process runs:
1. **Watcher threads** — one per FileWatch/StreamWatch trigger
2. **Tool workers** — serving the agent's @tool functions to the orchestration server
3. **Main thread** — `runtime.wait()` blocks, keeping everything alive

### 4.3 How You Install and Run This

**Scenario: "Tail a log file and trigger an agent on errors"**

```bash
# 1. Install
pip install agentspan-sdk   # or: npm install @agentspan-ai/sdk

# 2. Write the sentinel (sentinel.py / sentinel.ts)
#    Define agent + tools + FileWatch trigger

# 3. Run
python sentinel.py             # foreground, for dev/testing
# or
conductor-agent deploy sentinel.py    # daemonize (future CLI)
# or
docker run -v /var/log:/var/log:ro my-sentinel   # containerized
# or
systemctl start conductor-sentinel@log_monitor   # systemd service
```

**What `runtime.wait()` does:**
- Blocks the main thread
- Keeps file watchers alive (local threads)
- Keeps tool workers polling for tasks
- Handles graceful shutdown on SIGTERM/SIGINT
- Logs trigger events and agent executions

### 4.4 Multi-Instance / HA Deployment

| Trigger Type | Multi-Instance Behavior |
|---|---|
| **Schedule** | Orchestration server ensures exactly-once execution. Safe to run multiple instances. |
| **Event** | Event handler registered once. Server routes to one execution instance. |
| **Webhook** | Server-side. Single handler. |
| **FileWatch** | Local — each instance watches independently. Needs **distributed lock** or **leader election** to prevent duplicate triggers. |
| **StreamWatch** | Use consumer groups (Kafka) or competing consumers (SQS) for natural dedup. |

## 5. Lifecycle Management

### 5.1 Deployment Handle

When an agent is deployed, a handle is returned for ongoing management:

```
DeploymentHandle:
  name: string                   # agent name
  registered_name: string        # compiled workflow name
  triggers: Trigger[]            # active triggers
  status: "running" | "paused" | "stopped"

  pause()                        # pause all triggers
  resume()                       # resume triggers
  undeploy()                     # stop + remove all triggers + cleanup

  executions(limit=10)           # list recent agent runs
  last_execution()               # most recent run result
```

### 5.2 Observability

Deployed sentinels should expose:

- **Execution history** — when it ran, what triggered it, what it did, outcome
- **Trigger status** — is each trigger active? Last fire time? Error count?
- **Metrics** — runs per hour, avg duration, LLM tokens used, tool calls made
- **Logs** — structured logs for each trigger fire and agent execution

Access via:
- **API**: `handle.executions()`, `handle.status`
- **CLI**: `conductor-agent status`, `conductor-agent logs <name>`
- **Web UI**: Conductor's workflow execution UI (already exists)

## 6. Concrete Examples

### 6.1 Log Sentinel

```
Agent:
  name: log_sentinel
  model: openai/gpt-4o
  tools: [read_log_context, create_jira_ticket, send_slack_alert]
  instructions: |
    You are a production log sentinel. When triggered with log errors:
    1. Read surrounding context to understand the error
    2. Assess severity (transient vs. real bug vs. critical outage)
    3. Transient: ignore. Bug: create JIRA ticket. Critical: Slack alert + ticket.

Triggers:
  - FileWatch:
      path: /var/log/myapp/error.log
      pattern: (ERROR|CRITICAL|FATAL)
      debounce: 30
      prompt: |
        Log error detected in {filepath} at line {line_number}:

        {matched_lines}

        Analyze this error, check context, and take appropriate action.

  - Schedule:
      cron: "0 9 * * 1"   # Monday 9am
      prompt: Compile a weekly summary of all errors from the past week.
```

### 6.2 PR Review Sentinel

```
Agent:
  name: pr_reviewer
  model: anthropic/claude-sonnet
  tools: [list_open_prs, fetch_pr_diff, post_review_comment]
  instructions: |
    Review pull requests for code quality, bugs, and security issues.
    Post constructive review comments. Approve clean PRs.

Triggers:
  - WebhookTrigger:
      matches: {action: "opened", pull_request: {base: {ref: "main"}}}
      prompt: "New PR to main: ${webhook.payload.pull_request.title}. Review it."

  - Schedule:
      cron: "*/30 * * * *"
      prompt: "Check for any unreviewed PRs in the last 30 minutes."
```

### 6.3 Incident Responder

```
Agent:
  name: incident_responder
  model: openai/gpt-4o
  tools: [get_metrics, get_logs, restart_service, scale_replicas, notify_oncall]
  instructions: |
    You are the first responder for production incidents.
    1. Gather metrics and logs to understand the issue
    2. If it's a known pattern (OOM, connection pool), apply the fix
    3. If unknown, gather diagnostics and escalate to on-call

Triggers:
  - EventTrigger:
      event: pagerduty:incident
      condition: "event.severity == 'critical'"
      prompt: |
        CRITICAL INCIDENT: ${event.title}
        Service: ${event.service}
        Description: ${event.description}
        Triggered at: ${event.created_at}

  - EventTrigger:
      event: prometheus:alert
      condition: "event.labels.severity == 'warning'"
      prompt: |
        Warning alert: ${event.labels.alertname}
        ${event.annotations.description}
```

### 6.4 Omnipresent Ops Agent

The most ambitious pattern — a single agent with multiple trigger types:

```
Agent:
  name: ops_sentinel
  model: openai/gpt-4o
  tools: [
    check_health, get_metrics, query_logs,
    restart_pod, scale_service,
    create_ticket, send_alert,
    run_db_query, check_cert_expiry
  ]
  instructions: |
    You are the AI ops team member. You have multiple responsibilities:
    - Health checks (scheduled)
    - Error triage (log watching)
    - Alert response (event-driven)
    - Deployment verification (webhook-driven)
    Fix what you can autonomously. Escalate what you can't.

Triggers:
  - Schedule:
      cron: "*/5 * * * *"
      prompt: "Run health checks on all production services."

  - Schedule:
      cron: "0 8 * * *"
      prompt: "Morning report: summarize overnight incidents, current system health, upcoming cert expirations."

  - FileWatch:
      path: /var/log/k8s/*.log
      pattern: "OOMKilled|CrashLoopBackOff|ImagePullBackOff"
      prompt: "K8s issue detected:\n\n{matched_lines}\n\nDiagnose and fix if possible."

  - EventTrigger:
      event: prometheus:alert
      prompt: "Alert: ${event.labels.alertname}\n${event.annotations.description}"

  - WebhookTrigger:
      matches: {source: "github", action: "deployment"}
      prompt: "Deployment to ${webhook.payload.environment}: verify health."
```

## 7. Execution Plan

### Phase 1: Foundation (Schedule + Deploy/Undeploy)
- `Schedule` trigger class
- `runtime.deploy(agent, triggers=[Schedule(...)])` → registers cron with orchestration server
- `runtime.undeploy()` → removes schedule
- `DeploymentHandle` with pause/resume/executions
- `runtime.wait()` to keep process alive for tool workers
- **Example**: News monitor that checks every hour

### Phase 2: Event & Webhook Triggers
- `EventTrigger` class → registers event handler with orchestration server
- `WebhookTrigger` class → registers webhook handler
- Prompt template interpolation with event/webhook payload
- **Example**: Incident responder triggered by PagerDuty events

### Phase 3: Local File Watching
- `FileWatch` trigger class
- Local file tailing engine (efficient, handles rotation, glob patterns)
- Pattern matching + debounce logic
- On match → `runtime.start(agent, prompt=rendered_template)`
- **Example**: Log sentinel watching error.log

### Phase 4: Stream Watching
- `StreamWatch` trigger class
- Connector interface for Kafka, Redis Streams, SQS, etc.
- Consumer group support for multi-instance dedup
- **Example**: Data pipeline monitor on Kafka topic

### Phase 5: CLI & Observability
- `conductor-agent deploy <file>` — daemonize a sentinel
- `conductor-agent status` — list deployed sentinels
- `conductor-agent logs <name>` — stream execution logs
- `conductor-agent pause/resume/undeploy <name>`
- Dashboard integration with execution history

### Phase 6: Advanced Patterns
- **Cost controls**: Max runs per hour, spend threshold, auto-pause
- **Concurrency policy**: Skip-if-running / queue / parallel
- **State across runs**: Automatic memory injection for scheduled agents
- **Multi-instance coordination**: Distributed locking for FileWatch in HA deployments
- **Chained sentinels**: Output of one sentinel triggers another

## 8. Open Design Questions

1. **Prompt templating syntax**: Server-side triggers naturally use orchestration engine expressions (`${event.field}`). Local triggers resolve before the workflow starts (`{matched_lines}`). Should we unify or keep the natural split?

2. **Concurrency on schedule overlap**: If a cron fires while the previous run is still executing — skip, queue, or parallel? Default recommendation: **skip-if-running** to prevent agent pile-up and runaway costs.

3. **State persistence across scheduled runs**: Should sentinel agents automatically get conversation memory so they "remember" previous runs? Or is this opt-in via the memory parameter? Recommendation: **opt-in** — memory adds cost and complexity.

4. **FileWatch reliability**: The local watcher process is a single point of failure. Options: (a) watchdog/health checks, (b) systemd auto-restart, (c) heartbeat to orchestration server that alerts on missed heartbeats.

5. **Cost guardrails**: LLM calls cost money. Sentinel agents can run thousands of times per day. Should triggers support: max executions per hour? Monthly spend cap? Auto-pause on threshold?

6. **Trigger composition**: Can triggers have dependencies? E.g., "Only trigger on FileWatch if the last Schedule run found issues." This adds complexity — defer to Phase 6.

7. **Multi-SDK consistency**: Design should work across Python, TypeScript, Java, Go SDKs. Trigger classes and deployment API should be identical in structure, differing only in language idiom.