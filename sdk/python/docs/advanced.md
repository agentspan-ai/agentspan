# Advanced

- [Runtime init and config](#runtime-init-and-config)
- [run vs start vs stream vs deploy vs serve vs plan](#run-vs-start-vs-stream-vs-deploy-vs-serve-vs-plan)
- [The control-plane AgentClient](#the-control-plane-agentclient)
- [Structured output](#structured-output)
- [Credentials and secrets](#credentials-and-secrets)
- [Plans and PLAN_EXECUTE](#plans-and-plan_execute)
- [Schedules](#schedules)
- [Skills](#skills)

## Runtime init and config

`AgentRuntime` is the entry point. Use it as a context manager so workers shut down
cleanly. Config comes from `AgentConfig.from_env()` by default, or pass overrides.

```python
from conductor.ai.agents import AgentRuntime, AgentConfig

# From env (AGENTSPAN_SERVER_URL etc.)
with AgentRuntime() as runtime:
    runtime.run(agent, "hi")

# Explicit kwargs
with AgentRuntime(server_url="https://prod:6767/api",
                  api_key="...") as runtime:
    ...

# Or an AgentConfig
config = AgentConfig.from_env()
config.auto_start_server = False
with AgentRuntime(config=config) as runtime:
    ...
```

`AgentConfig` is a dataclass; `from_env()` reads the `AGENTSPAN_*` environment
variables (full list in [Getting started](getting-started.md#environment-variables)).
The Conductor `Configuration` object underneath is built from `server_url` and the
auth fields (`api_key`, or `auth_key`/`auth_secret`).

### Module-level convenience functions

For one-off scripts, top-level functions use a shared singleton runtime:

```python
import conductor.ai.agents as ag

ag.configure(server_url="https://prod:6767/api", auto_start_server=False)  # before first run
result = ag.run(agent, "Hello!")
ag.shutdown()    # explicit cleanup; not required for simple scripts
```

`configure(...)` must be called before the first `run`/`start`/`stream`. Available:
`run`, `run_async`, `start`, `start_async`, `stream`, `stream_async`, `resume`,
`resume_async`, `deploy`, `deploy_async`, `serve`, `plan`, `configure`, `shutdown`.

## run vs start vs stream vs deploy vs serve vs plan

| Call | Blocks? | Returns | When |
|---|---|---|---|
| `runtime.run(agent, prompt)` | yes | `AgentResult` | Simplest case — run and get the answer |
| `runtime.start(agent, prompt)` | no | `AgentHandle` | Fire-and-forget; poll/control later |
| `runtime.stream(agent, prompt)` | iterates | `AgentStream` | Watch events live; drive HITL |
| `runtime.deploy(*agents)` | yes | `list[DeploymentInfo]` | CI/CD: compile + register, no execution |
| `runtime.serve(*agents)` | yes (blocks) | — | Long-lived worker process; polls until interrupted |
| `runtime.plan(agent)` | yes | `dict` | Compile to a workflow def without running anything |

`run`/`start`/`stream` accept `media=`, `session_id=`, `idempotency_key=`,
`credentials=`, and extra `**kwargs` as workflow input. `run`/`run_async` also accept
`on_event=` to stream while running synchronously, `timeout=`, and `context=`.

`plan(agent)` returns `{"workflowDef": ..., "requiredWorkers": ...}` — useful to
inspect the compiled Conductor workflow:

```python
result = runtime.plan(agent)
print(result["workflowDef"]["name"])
print(result["workflowDef"]["tasks"])
```

### Deploy once, serve separately (production)

```python
# CI/CD step:
runtime.deploy(agent)
# CLI alternative:
#   agentspan deploy --package my_pkg.my_module
#   agentspan deploy --path ./agents --agents greeter,support

# Long-lived worker process:
runtime.serve(agent)        # blocks, polling for tool tasks
```

`resume(execution_id, agent)` re-attaches to a previously `start`ed execution and
re-registers its tool workers (e.g. after a process restart):

```python
handle = runtime.start(agent, "Long job")
eid = handle.execution_id
# later, even after a restart:
handle = runtime.resume(eid, agent)
result = handle.join(timeout=120)
```

## The control-plane AgentClient

`runtime.client` is the **control-plane** `AgentClient` (formerly `AgentHttpClient` —
the old name is kept as an alias). It talks to the `/agent/*` HTTP endpoints directly:
compile, deploy, start, run, schedule, status, respond, stop, signal, SSE. It is
control-plane only — its `run`/`start` do **not** register or poll local `@tool`
workers, so use it for agents whose tools are all server-side (HTTP/MCP/built-in) or
already deployed.

```python
with AgentRuntime() as runtime:
    client = runtime.client

    result = client.run(agent, "Hello")            # compile + start + poll
    handle = client.start(agent, "Long job")
    infos  = client.deploy(agent)                  # compile + register

    # Cron lifecycle (same surface as runtime.schedules_client()):
    client.schedule(agent, [nightly])              # reconcile schedules
    client.schedules.pause("agent-nightly")
```

Key methods: `run`/`run_async`, `start`/`start_async`, `deploy`/`deploy_async`,
`schedule(agent, schedules)`, `get_status`, `respond`, `stop`, `signal`,
`stream_sse`, and `.schedules` (the `ScheduleClient`). Both sync and async forms
exist. Most users call `runtime.run/start/deploy` instead, which add local-worker
management on top of this client.

## Structured output

Pass `output_type=` a Pydantic model (or dataclass) to get a typed, validated result.
Pydantic is only needed when you use this feature.

```python
from pydantic import BaseModel
from conductor.ai.agents import Agent, AgentRuntime, tool

class WeatherReport(BaseModel):
    city: str
    temperature: float
    condition: str
    recommendation: str

@tool
def get_weather(city: str) -> dict:
    """Get weather data."""
    return {"city": city, "temp_f": 72, "condition": "Sunny"}

agent = Agent(name="reporter", model="openai/gpt-4o",
              tools=[get_weather], output_type=WeatherReport,
              instructions="Report the weather with a recommendation.")

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    print(result.output)        # conforms to WeatherReport's schema
```

## Credentials and secrets

Store secrets in the server's credential store (never in code), then declare them per
tool with `credentials=[...]`. Inside the tool, read the injected value with
`get_secret(name)`.

```python
from conductor.ai.agents import tool, get_secret

@tool(credentials=["OPENAI_API_KEY"])
def call_openai(prompt: str) -> str:
    """Call OpenAI directly using a stored credential."""
    key = get_secret("OPENAI_API_KEY")       # only works inside a credentials-aware tool
    ...
```

You can also declare credentials at the agent level (`Agent(..., credentials=[...])`),
and HTTP/built-in tools resolve `${CRED_NAME}` placeholders in headers from the same
store at execution time. Pass `credentials=[...]` to `runtime.run(...)` to supply
credential names for a specific execution.

`get_secret` raises `CredentialNotFoundError` when the credential is absent. Other
credential errors: `CredentialAuthError`, `CredentialRateLimitError`,
`CredentialServiceError`. Store a credential via the CLI:

```bash
agentspan credentials set OPENAI_API_KEY sk-...
```

## Plans and PLAN_EXECUTE

`Strategy.PLAN_EXECUTE` runs a planner agent that emits a JSON plan, which is then
executed deterministically against a fixed tool set. Build the harness with the
`plan_execute` helper, or the `Agent` named-slot API.

```python
from conductor.ai.agents import plan_execute

harness = plan_execute(
    "report_builder",
    tools=[create_directory, write_file, check_word_count],
    planner_instructions="Plan a multi-section report, then write each section.",
    model="openai/gpt-4o",
)
result = runtime.run(harness, "Write a report on Rust adoption.")
```

Or directly:

```python
from conductor.ai.agents import Agent, Strategy

planner = Agent(name="rb_planner", model="openai/gpt-4o", instructions="Plan it.")
harness = Agent(name="report_builder", strategy=Strategy.PLAN_EXECUTE,
                planner=planner, tools=[write_file, check_word_count])
```

`PLAN_EXECUTE` requires `planner=` (the agent that emits the plan) and `tools=` on the
parent (the canonical executable tools); `fallback=` is optional.

### Static plans (skip the planner)

Build a deterministic plan in Python with the typed builders and pass it to `run`:

```python
from conductor.ai.agents.plans import Plan, Step, Op, Generate, Validation, Ref

plan = Plan(
    steps=[
        Step("setup", operations=[Op("create_directory", args={"path": "out"})]),
        Step("write", depends_on=["setup"], parallel=True, operations=[
            Op("write_file", generate=Generate(
                instructions="Write the introduction.",
                output_schema='{"path": "out/intro.md", "content": "..."}')),
        ]),
        Step("summarize", depends_on=["write"], operations=[
            Op("summarize", args={"document": Ref("write")}),    # wire a prior step's output
        ]),
    ],
    validation=[Validation("check_word_count", args={"path": "out/intro.md", "min_words": 200})],
)

runtime.run(harness, "build it", plan=plan)
```

`Op` takes either `args=` (literal) or `generate=` (LLM-generated args). `Ref("step")`
injects an upstream step's output (the step must be in `depends_on`). `Step.parallel`
runs a step's operations concurrently; `depends_on` expresses cross-step concurrency.

### Planner context

Ground the planner with reference documents via `planner_context=` — inline text or a
URL fetched at planner-run time:

```python
from conductor.ai.agents.plans import Context

harness = plan_execute(
    "kyc", tools=[...],
    planner_instructions="Follow the KYC process.",
    planner_context=[
        "Tier-1 customers skip manual review.",                 # inline string
        Context(url="https://wiki/kyc-rules", headers={"Authorization": "Bearer ${KYC_TOKEN}"}),
    ],
)
```

## Schedules

Attach cron schedules at deploy time, or manage them through the schedule client.

```python
from conductor.ai.agents import Schedule

nightly = Schedule(name="nightly", cron="0 0 * * *", timezone="UTC",
                   input={"prompt": "Daily summary."})

runtime.deploy(agent, schedules=[nightly])     # upsert; [] purges; omit leaves as-is

sc = runtime.schedules_client()                # or runtime.client.schedules
sc.list_for_agent(agent.name)
sc.pause("greeter-nightly")
sc.run_now(sc.get("greeter-nightly"))
print(sc.preview_next("0 0 * * *", n=5))       # next 5 fire times (epoch ms)
```

## Skills

Load an agentskills.io skill directory (with a `SKILL.md`) as an `Agent`:

```python
from conductor.ai.agents import skill, load_skills

researcher = skill("./skills/deep-research", model="openai/gpt-4o",
                   params={"rounds": 3})
all_skills = load_skills("./skills", model="openai/gpt-4o")   # dict: name -> Agent

runtime.run(researcher, "Research durable execution engines.")
```

`skill(path, model="", agent_models=None, search_path=None, params=None)` returns an
ordinary `Agent` you can run, compose (e.g. via `agent_tool`), deploy, and serve.
Sub-agent files (`*-agent.md`), `scripts/`, and resource files are discovered
automatically; cross-skill references resolve from sibling and `~/.agents/skills`
directories plus any `search_path`.
