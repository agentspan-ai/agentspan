# Agent Skills

Load [agentskills.io](https://agentskills.io) skill directories as durable, observable Agentspan agents. Skills work everywhere an `Agent` works — standalone, in pipelines, as sub-agents, as tools on other agents.

---

## Quick Start

```python
from agentspan.agents import skill, AgentRuntime

# Load a skill directory as an Agent
dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")

# Run it like any other agent
with AgentRuntime() as rt:
    result = rt.run(dg, "Review this code for security issues:\n\ndef login(user, pw):\n    return db.execute(f\"SELECT * FROM users WHERE name='{user}'\")")
    print(f"Execution ID: {result.execution_id}")
    print(f"Status: {result.status}")
    print(f"Tokens: {result.token_usage}")
    result.print_result()
```

```bash
# Or via CLI from a local directory
agentspan skill run ~/.claude/skills/dg "Review this code..." --model openai/gpt-4o

# Register the full skill package on the server for browsing/reuse
agentspan skill register ~/.claude/skills/dg --model openai/gpt-4o
```

---

## What is a Skill?

A skill is a directory following the [agentskills.io specification](https://agentskills.io/specification). At minimum, it contains a `SKILL.md` file with YAML frontmatter and markdown instructions:

```
my-skill/
├── SKILL.md              # Required: metadata + instructions
├── *-agent.md            # Optional: sub-agent definitions
├── scripts/              # Optional: executable tools
├── references/           # Optional: on-demand documentation
├── examples/             # Optional: usage examples
└── assets/               # Optional: templates, resources
```

Agentspan auto-discovers everything by convention — no manifest or config file needed.

---

## `skill()` Function

```python
from agentspan.agents import skill

agent = skill(
    path="~/.claude/skills/dg",
    model="openai/gpt-4o",
    agent_models={"gilfoyle": "anthropic/claude-sonnet-4-6"},
    search_path=["~/.claude/skills/"],
    params={"rounds": 5},
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path` | **required** | Path to skill directory containing `SKILL.md`. Supports `~` expansion. Can also be a skill name resolved from `search_path`. |
| `model` | `str` | `""` | Model for the orchestrator agent. Also the default for sub-agents. Format: `"provider/model"`. |
| `agent_models` | `dict[str, str]` | `None` | Per-sub-agent model overrides. Keys are agent names (from `*-agent.md` filenames). |
| `search_path` | `list[str]` | `None` | Additional directories to search for cross-skill references. Defaults to `./.agents/skills/`, `~/.agents/skills/`. |
| `params` | `dict[str, Any]` | `None` | Runtime parameter overrides. Merged on top of defaults declared in the SKILL.md frontmatter `params` section. |

### Returns

An `Agent` instance. Composable everywhere an Agent is accepted.

### Raises

| Exception | When |
|-----------|------|
| `SkillLoadError` | `SKILL.md` not found in directory |
| `ValueError` | `SKILL.md` frontmatter missing required `name` field |

---

## `load_skills()` Function

Load all skills from a directory at once. Cross-skill references are auto-resolved.

```python
from agentspan.agents import load_skills

skills = load_skills(
    path="~/.claude/skills/",
    model="openai/gpt-4o",
    agent_models={"dg": {"gilfoyle": "anthropic/claude-sonnet-4-6"}},
)

# Use any skill by name
dg = skills["dg"]
conductor = skills["conductor"]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path` | **required** | Directory containing skill subdirectories. |
| `model` | `str` | `""` | Default model for all skills. |
| `agent_models` | `dict[str, dict[str, str]]` | `None` | Per-skill, per-sub-agent model overrides. Outer key is skill name, inner key is agent name. |

### Returns

`dict[str, Agent]` — mapping skill name to Agent.

---

## Convention-Based Discovery

`skill()` reads the directory and discovers components automatically:

| Convention | What it becomes |
|-----------|----------------|
| `SKILL.md` | Orchestrator agent instructions (from the markdown body) |
| `*-agent.md` | Sub-agents. Filename minus `-agent.md` = agent name. Each becomes a Conductor SUB_WORKFLOW with its own LLM calls. |
| `scripts/*` | Named tools. Filename minus extension = tool name. Each becomes a Conductor SIMPLE task with full I/O logging. |
| `references/*`, `examples/*`, `assets/*` | Available on demand via `read_skill_file` tool. Not loaded upfront. |
| Other files in root | Also available via `read_skill_file`. |

### Model Inheritance

Sub-agents inherit the parent's model by default. Override per sub-agent:

```python
dg = skill("~/.claude/skills/dg",
    model="openai/gpt-4o-mini",                          # orchestrator + default
    agent_models={"gilfoyle": "anthropic/claude-sonnet-4-6"},  # gilfoyle gets a bigger model
)
```

### Cross-Skill References

If a SKILL.md references another skill (e.g., "invoke the writing-plans skill"), Agentspan resolves it automatically from:

1. Sibling directories of the skill
2. `./.agents/skills/` (project-level)
3. `~/.agents/skills/` (user-level)
4. Explicit `search_path`

---

## Skill Parameters

Skills can declare parameters in the SKILL.md frontmatter. Parameters allow callers to customize skill behavior without editing the skill itself.

### Declaring parameters

Add a `params` section to the SKILL.md frontmatter:

```yaml
---
name: dg
description: Adversarial code review
params:
  rounds:
    type: integer
    default: 3
    description: Number of debate rounds
  style:
    type: string
    default: concise
    description: Output verbosity
---
```

Each parameter can be a full definition (with `type`, `default`, `description`) or a bare default value:

```yaml
params:
  rounds: 3
  verbose: true
```

### Passing parameters (Python SDK)

Pass `params` to the `skill()` function. Runtime values override frontmatter defaults:

```python
# Use frontmatter defaults (rounds=3)
dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")

# Override rounds to 5
dg = skill("~/.claude/skills/dg", model="openai/gpt-4o", params={"rounds": 5})
```

You can also format parameters into a prompt manually using the helper functions:

```python
from agentspan.agents import format_prompt_with_params

prompt = format_prompt_with_params("Review this code", {"rounds": 5})
# "[Skill Parameters]\nrounds: 5\n\n[User Request]\nReview this code"
```

### Passing parameters (CLI)

Use the `--param key=value` flag (repeatable):

```bash
agentspan skill run ~/.claude/skills/dg "Review auth.py" \
    --model openai/gpt-4o \
    --param rounds=5 \
    --param style=verbose
```

### How it works

Parameters are merged with frontmatter defaults and packaged into the skill instructions as a structured block:

```
[Skill Parameters]
rounds: 5
style: verbose
```

The skill's orchestrator agent sees both the parameters and the original request, and can adjust its behavior accordingly (e.g., running more debate rounds, changing output format). The prompt-formatting helpers are still available when you explicitly want to include the same block in a user prompt.

---

## Composition Patterns

Since `skill()` returns `Agent`, all composition patterns work naturally.

### Standalone

```python
dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")

with AgentRuntime() as rt:
    result = rt.run(dg, "Review this PR")
    result.print_result()
```

### Pipeline (`>>`)

```python
reviewer = skill("~/.claude/skills/dg", model="openai/gpt-4o")
fixer = Agent(name="fixer", model="openai/gpt-4o",
              instructions="Fix the issues found in the code review.")

pipeline = reviewer >> fixer
result = rt.run(pipeline, "Review and fix auth.py")
```

### Router Team

```python
dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")
conductor = skill("~/.claude/skills/conductor", model="anthropic/claude-sonnet-4-6")
coder = Agent(name="coder", model="openai/gpt-4o", instructions="Write code.")

team = Agent(
    name="devops_team",
    agents=[dg, coder, conductor],
    strategy="router",
    router=Agent(name="router", model="openai/gpt-4o-mini",
                 instructions="Route: review→dg, code→coder, workflows→conductor"),
)
```

### Parallel Review

```python
dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")
security = Agent(name="security", model="openai/gpt-4o",
                 instructions="Review ONLY for security issues.")

parallel = Agent(name="review", agents=[dg, security], strategy="parallel")
```

### Skills as Tools (`agent_tool`)

```python
from agentspan.agents import agent_tool

dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")

lead = Agent(
    name="tech_lead",
    model="openai/gpt-4o",
    instructions="Use the code review tool when PRs come in.",
    tools=[
        agent_tool(dg, description="Run adversarial code review"),
        my_jira_tool,
    ],
)
```

### Swarm (Handoff)

```python
from agentspan.agents.handoff import OnTextMention

dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")
architect = Agent(name="architect", model="openai/gpt-4o",
    instructions="Design the system. Say HANDOFF_TO_DG when ready for review.")

swarm = Agent(
    name="design_loop",
    agents=[architect, dg],
    strategy="swarm",
    handoffs=[
        OnTextMention(text="HANDOFF_TO_DG", target="dg"),
        OnTextMention(text="HANDOFF_TO_ARCHITECT", target="architect"),
    ],
)
```

### Mixed with Framework Agents

```python
from agents import Agent as OpenAIAgent

dg = skill("~/.claude/skills/dg", model="openai/gpt-4o")
oai_agent = OpenAIAgent(name="coder", instructions="Write code.", model="gpt-4o")

team = Agent(name="team", agents=[dg, oai_agent], strategy="sequential")
```

---

## CLI Usage

### Ephemeral (run and exit)

```bash
agentspan skill run <path-or-name> "<prompt>" [flags]
```

| Flag | Description |
|------|-------------|
| `--model <model>` | Orchestrator + default model |
| `--agent-model <name>=<model>` | Per-sub-agent override (repeatable) |
| `--search-path <dir>` | Cross-skill search directory (repeatable) |
| `--param <key>=<value>` | Skill parameter override (repeatable) |
| `--timeout <seconds>` | Execution timeout |
| `--stream` | Stream SSE events to stdout |
| `--version <version>` | Registered skill version or checksum prefix when running by name |
| `--script-timeout <seconds>` | Per-script worker timeout. Default: `300`. |
| `--script-output-limit <bytes>` | Maximum stdout/stderr captured from each script call. Default: `10485760`. |
| `--workspace <dir>` | Local workspace root exposed to workspace tools. Default: current directory. |
| `--no-workspace` | Disable local workspace exposure for this run. |
| `--filesystem <name>=<path>` | Additional read-only filesystem root exposed to workspace tools (repeatable). |
| `--workspace-file-limit <bytes>` | Maximum bytes returned by workspace file tools. Default: `1048576`. |

Examples:

```bash
# Run /dg review
agentspan skill run ~/.claude/skills/dg "Review auth.py" --model openai/gpt-4o

# With sub-agent model override
agentspan skill run ~/.claude/skills/dg "Review PR #42" \
    --model openai/gpt-4o-mini \
    --agent-model gilfoyle=anthropic/claude-sonnet-4-6

# With skill parameters
agentspan skill run ~/.claude/skills/dg "Review auth.py" \
    --model openai/gpt-4o \
    --param rounds=5 --param style=verbose

# Stream events
agentspan skill run ~/.claude/skills/conductor "List all workflows" \
    --model anthropic/claude-sonnet-4-6 --stream

# Run a registered code review skill against the current checkout
agentspan skill run code-review "Review current changes" \
    --model openai/gpt-4o \
    --workspace .

# Expose extra read-only filesystem roots
agentspan skill run code-review "Review code and docs" \
    --model openai/gpt-4o \
    --workspace . \
    --filesystem docs=./docs
```

### Server registry

Registering a skill uploads the skill folder as an immutable server-side package. The CLI excludes generated directories, common secret files such as `.env` and private keys, and paths matched by `.agentspanignore`. The server validates the zip, derives the runtime skill config from the package contents, stores owner-scoped metadata with a content checksum, exposes it in the UI under **Definitions → Skills**, and can later resolve it by name for that owner.

```bash
# Register a skill package on the server
agentspan skill register ~/.claude/skills/dg --model openai/gpt-4o

# List registered skills
agentspan skill list

# Inspect a registered skill and its file manifest
agentspan skill get dg

# Download a registered skill package
agentspan skill pull dg ./dg

# Delete a registered skill version
agentspan skill delete dg --version 2026.05.21 --yes

# Run a registered skill by name
agentspan skill run dg "Review auth.py" --model openai/gpt-4o

# Serve workers for a registered skill by name
agentspan skill serve dg
```

Registered skill execution uses a compact `skillRef` on the server. The server resolves defaults and registered cross-skill references from the registry at compile time. Referenced skill versions are pinned when the parent is registered, so a parent version keeps using the same child version even if the child is updated later. When a registered skill or referenced skill has script tools or resource-file reads, the CLI downloads each package to `~/.agentspan/skills/<name>/<version>/files`, verifies the package checksum, and starts the same local workers used for path-based execution. The cached package is reused until the server checksum changes.

For local context, `skill run` exposes the current directory as a read-only `workspace` root by default. The server compiles workspace tools for listing files, reading files, searching text, and reading git status/diff; the CLI serves those tools locally and enforces root boundaries. Additional read-only roots can be exposed with `--filesystem <name>=<path>`. Script workers run with the skill root as their working directory, expose `AGENTSPAN_SKILL_DIR`, expose `AGENTSPAN_WORKSPACE_DIR` when a workspace root is available, and expose each configured root as `AGENTSPAN_FILESYSTEM_ROOT_<NAME>`.

### Registry storage

The server separates registry metadata from package blob storage. Configure the package store with:

| Property | Default | Description |
|----------|---------|-------------|
| `agentspan.skills.package-store.type` | `filesystem` | `filesystem` for local or mounted-volume deployments; `conductor-payload` for Conductor external payload storage. |
| `agentspan.skills.storage.directory` | `${java.io.tmpdir}/agentspan/skills` | Owner-scoped metadata root and default filesystem package root parent. |
| `agentspan.skills.package-store.filesystem.directory` | `${agentspan.skills.storage.directory}/packages` | Filesystem package blob directory. |
| `agentspan.skills.max-package-bytes` | `52428800` | Maximum compressed package upload size. |
| `agentspan.skills.max-uncompressed-bytes` | `209715200` | Maximum expanded zip payload size. |
| `agentspan.skills.max-file-count` | `2000` | Maximum files per package. |

### Production (deploy + serve)

```bash
# Deploy skill definition to server
agentspan skill load ~/.claude/skills/dg --model openai/gpt-4o

# Start workers for script tools and read_skill_file (blocks)
agentspan skill serve ~/.claude/skills/dg [--search-path <dir>]

# Or serve workers from a registered server-side package
agentspan skill serve dg

# Trigger by name (existing command)
agentspan agent run --name dg "Review the latest PR"
```

---

## Observability

Every skill component maps to a distinct Conductor task — visible in the execution DAG with full I/O, timing, and retry.

### What you see in the execution trace

| Skill Component | Conductor Task Type | Visibility |
|----------------|--------------------|-----------|
| Orchestrator LLM calls | `LLM_CHAT_COMPLETE` | System prompt, user message, tool calls, output |
| Sub-agents (`*-agent.md`) | `SUB_WORKFLOW` | Own execution ID, own LLM calls, own task tree |
| Script tools (`scripts/*`) | `SIMPLE` (named per script) | Command input, stdout output, timing |
| File reads | `SIMPLE` (`read_skill_file`) | File path, content returned |

### Example: /dg execution trace

```
Workflow: dg (execution_id: 59ad0af2-...)
  #1  LLM_CHAT_COMPLETE  dg_llm__1                    → dispatches gilfoyle
  #2  SUB_WORKFLOW        gilfoyle (id: 4bd54431-...)  → own LLM call, finds SQL injection
  #3  LLM_CHAT_COMPLETE  dg_llm__2                    → dispatches dinesh
  #4  SUB_WORKFLOW        dinesh (id: 980da933-...)    → defends, concedes SQL injection
  #5  LLM_CHAT_COMPLETE  dg_llm__3                    → convergence detected
  #6  SIMPLE             read_skill_file               → loads comic-template.html
  #7  LLM_CHAT_COMPLETE  dg_llm__4                    → synthesizes verdict
```

### Token tracking

Token usage is aggregated across all LLM calls in the execution tree (including sub-agents):

```python
result = rt.run(dg, "Review this code")
print(result.token_usage)
# TokenUsage(prompt_tokens=15309, completion_tokens=1389, total_tokens=16698)
```

Works with both `rt.run()` and `rt.stream().get_result()`.

### Crash recovery

Each sub-agent execution is independently durable. If the process crashes mid-review:
- Completed sub-agents (gilfoyle round 1) are preserved
- Workflow resumes from the next pending task
- No work is lost, no rounds are repeated

---

## Progressive Disclosure

Skills manage context efficiently through progressive disclosure:

1. **Metadata** (~100 tokens): Skill name and description — always loaded
2. **Instructions** (<5K tokens): SKILL.md body — loaded when skill activates
3. **Resources** (on demand): References, examples, assets — loaded via `read_skill_file` when needed

### Auto-splitting large skills

When a SKILL.md body exceeds 50,000 characters, it's automatically split into sections by `##` headings. The orchestrator receives a compact table of contents and loads sections on demand:

```
Instructions (loaded):
  "You are the conductor skill. Available sections:
   - skill_section:workflow-definitions — Workflow Definitions
   - skill_section:running-workflows — Running Workflows
   ..."

Sections (on demand via read_skill_file):
  "skill_section:workflow-definitions" → full section content
```

This keeps the initial context within model limits even for comprehensive skills.

---

## Installing Skills

### From GitHub

```bash
# Clone a skill repository
git clone https://github.com/v1r3n/dinesh-gilfoyle ~/.claude/skills/dg
git clone https://github.com/conductor-oss/conductor-skills ~/.claude/skills/conductor-skills
```

### Standard locations

| Location | Scope |
|----------|-------|
| `./.agents/skills/` | Project-level (checked into repo) |
| `~/.agents/skills/` | User-level (personal skills) |
| `~/.claude/skills/` | Claude Code compatible |

### Creating your own skill

A minimal skill:

```
my-skill/
└── SKILL.md
```

```markdown
---
name: my-skill
description: Does X when the user asks for Y.
---

# My Skill

Instructions for the agent...
```

A skill with sub-agents and scripts:

```
code-review/
├── SKILL.md                # Orchestration logic
├── reviewer-agent.md       # Sub-agent: reviews code
├── fixer-agent.md          # Sub-agent: fixes issues
└── scripts/
    └── lint.sh             # Tool: runs linter
```

See the [agentskills.io specification](https://agentskills.io/specification) for the full format reference.

---

## Known Limitations

### Filesystem scope

The `read_skill_file` tool can only read files within the skill directory. Skills designed for Claude Code that assume full filesystem access (e.g., scanning for `package.json` in the project) won't work via `read_skill_file` alone.

**Workaround:** Add `cli_commands=True` to the parent agent, or provide additional `@tool` functions for project-level operations.

### Model context windows

Large skills or skills that produce large tool outputs may exceed smaller models' context windows. Use models with larger context (claude-sonnet-4-6 at 1M tokens) for comprehensive skills, or rely on the auto-splitting feature for large SKILL.md files.

### Task reference names

Tool call IDs from the LLM (e.g., `call_ElaXTiouRe9HY6VtHGf43E6X`) are used as Conductor task reference names. The task *type* shows the meaningful name (`dg__gilfoyle`), but reference names in DAG visualizations may appear opaque.
