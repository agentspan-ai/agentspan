# Agent Skills Integration Design

**Date:** 2026-03-30
**Status:** Draft
**Authors:** Viren, Claude

## Overview

Integrate [Agent Skills](https://agentskills.io/specification) as a first-class capability in Agentspan. A skill directory is loaded as a standard `Agent` — composable, durable, and fully observable.

### Design Principles

1. **Developer UX is paramount** — `skill("./dg")` works out of the box. No manifests, no config files, no wiring. Convention-based discovery handles everything.
2. **Durability + visibility is non-negotiable** — every sub-agent is a real sub-agent execution, every script call is a named task, every file read is a tracked operation. Full execution DAG with per-component I/O, timing, and retry.
3. **Skills mix freely with regular agents** — `skill()` returns `Agent`. Compose with `>>`, `agent_tool()`, strategy-based teams, deploy, serve, stream. No special-casing.

### What is an Agent Skill?

An [agentskills.io](https://agentskills.io/specification)-compatible directory containing:

```
skill-name/
├── SKILL.md              # Required: YAML frontmatter + markdown instructions
├── *-agent.md            # Optional: sub-agent definitions
├── scripts/              # Optional: executable scripts
├── references/           # Optional: on-demand documentation
├── examples/             # Optional: usage examples
└── assets/               # Optional: templates, resources
```

Real-world examples:
- **[/dg](https://github.com/v1r3n/dinesh-gilfoyle)** — orchestrator + 2 sub-agents + HTML template
- **[conductor](https://github.com/conductor-oss/conductor-skills)** — instructions + Python CLI script + 6 reference/example docs
- **[superpowers](https://github.com/obra/superpowers)** — 14 instruction-only skills with cross-skill references

---

## Architecture

### Core Concept

A skill is an Agent. The `skill()` function reads an agentskills.io-compatible directory and returns a standard Agentspan `Agent`. No new runtime primitive. No new compilation path. Skills enter the existing pipeline through a `SkillNormalizer` on the server — a new normalizer alongside the existing ones (OpenAI, LangGraph, LangChain, Google ADK, Vercel AI, Claude Agent SDK).

```
skill directory → SDK packages contents → Server SkillNormalizer → AgentConfig → AgentCompiler → Conductor
```

Because the output is `Agent`, skills automatically get:
- **Durability** — Conductor-backed execution, crash recovery
- **Visibility** — per-tool and per-sub-agent tasks in the execution DAG
- **Composability** — sequential `>>`, parallel, router, swarm, `agent_tool()`, deploy, serve, stream
- **Observability** — execution IDs, SSE streaming, token tracking, execution history

### System Flow

```
CLI path:     agentspan skill run ./dg "Review PR"
                  ↓ reads dir, packages, sends to server
                  ↓
SDK path:     skill("./dg") → rt.run(dg, "Review PR")
                  ↓ reads dir, packages, sends to server
                  ↓
              NormalizerRegistry("skill") → SkillNormalizer
                  ↓
              AgentConfig (canonical)
                  ↓
              AgentCompiler.compile()
                  ↓
              Conductor execution (durable, observable)
```

### Thin SDK, Thick Server

All parsing and normalization logic lives server-side in `SkillNormalizer`. This enables multi-SDK support — Python, TypeScript, Go, and CLI all send the same raw config format to the server.

**SDK responsibilities (replicated per language):**
- Read skill directory contents from local filesystem
- Package file contents into raw config dict
- Register script and `read_skill_file` workers (must run user-side)
- Send `{"framework": "skill", "config": {...}}` to server

**Server responsibilities (shared, single implementation):**
- Parse SKILL.md frontmatter
- Build orchestrator AgentConfig from SKILL.md body
- Create sub-agent AgentConfigs from `*-agent.md` contents
- Generate ToolConfigs for scripts and `read_skill_file`
- Resolve cross-skill references recursively
- Apply model inheritance and overrides
- Return canonical AgentConfig for compilation

---

## Convention-Based Discovery

The SDK reads a skill directory and packages its contents. All discovery is convention-based — no manifest required.

### Discovery Rules

| Convention | Detection | What it becomes |
|---|---|---|
| `SKILL.md` | Required, exact name | Frontmatter → skill metadata. Body → orchestrator `Agent.instructions` |
| `*-agent.md` | Glob `*-agent.md` in skill root | Each becomes a sub-agent. Filename minus `-agent.md` = agent name |
| `scripts/*` | Directory exists | Each executable file becomes a named tool. Filename minus extension = tool name |
| `references/*` | Directory exists | File paths listed (not contents). Available via `read_skill_file` tool |
| `examples/*` | Directory exists | Same — paths listed, loaded on demand |
| All other files in root | Glob remaining files | Paths listed. Available via `read_skill_file` tool |
| Cross-skill references | Skill names in SKILL.md matched against search path | Resolved recursively, packaged as nested skill configs |

### Search Path for Cross-Skill Resolution

In order:
1. Sibling directories of the skill being loaded
2. `./.agents/skills/` (project-level)
3. `~/.agents/skills/` (user-level)
4. Explicit `search_path` parameter if provided

### Model Inheritance

Sub-agents inherit the parent agent's model by default. Users override at the `skill()` call site:

```python
dg = skill("./dg",
    model="anthropic/claude-sonnet-4-6",                # orchestrator + default
    agent_models={"gilfoyle": "openai/gpt-4o"},  # per-sub-agent override
)
```

### Raw Config Format (SDK → Server)

```json
{
  "framework": "skill",
  "config": {
    "model": "anthropic/claude-sonnet-4-6",
    "agentModels": {"gilfoyle": "openai/gpt-4o"},
    "skillMd": "---\nname: dg\ndescription: ...\n---\n# Dinesh vs Gilfoyle...",
    "agentFiles": {
      "gilfoyle": "# You Are Gilfoyle\n...",
      "dinesh": "# You Are Dinesh\n..."
    },
    "scripts": {
      "scan_deps": {"filename": "scan_deps.sh", "language": "bash"}
    },
    "resourceFiles": ["comic-template.html"],
    "crossSkillRefs": {
      "writing-plans": {"skillMd": "...", "agentFiles": {}, "scripts": {}, "resourceFiles": []}
    }
  }
}
```

Script contents are NOT sent to the server — scripts run as workers on the user's machine. Resource file contents are also not sent — they're read on demand by the `read_skill_file` worker.

---

## Server-Side SkillNormalizer

Implements `AgentConfigNormalizer` — same interface as the 6 existing normalizers.

### Normalization Steps

**Step 1: Parse SKILL.md frontmatter**

Extract `name`, `description`, `allowed-tools`, `metadata` from YAML frontmatter. Body becomes the orchestrator agent's instructions.

**Step 2: Build orchestrator AgentConfig**

```java
AgentConfig orchestrator = new AgentConfig();
orchestrator.setName(frontmatter.get("name"));
orchestrator.setModel(rawConfig.get("model"));
orchestrator.setInstructions(skillMdBody);
orchestrator.setDescription(frontmatter.get("description"));
```

**Step 3: Build sub-agents from `*-agent.md` files**

Each entry in `agentFiles` becomes a child `AgentConfig`. Model is inherited from orchestrator unless overridden via `agentModels`.

```java
for (Map.Entry<String, String> entry : agentFiles.entrySet()) {
    AgentConfig sub = new AgentConfig();
    sub.setName(entry.getKey());
    sub.setInstructions(entry.getValue());
    sub.setModel(agentModels.getOrDefault(entry.getKey(), orchestrator.getModel()));
    // Wrap as agent_tool on orchestrator — child AgentConfig goes in config map
    // (matches pattern used by OpenAINormalizer, GoogleADKNormalizer, etc.)
    Map<String, Object> toolConfig = new LinkedHashMap<>();
    toolConfig.put("agentConfig", sub);
    ToolConfig agentTool = ToolConfig.builder()
        .name(sub.getName())
        .description("Invoke the " + sub.getName() + " agent")
        .toolType("agent_tool")
        .config(toolConfig)
        .build();
    tools.add(agentTool);
}
```

**Conductor mapping:** `agent_tool` compiles to a `SUB_WORKFLOW` task. `AgentService.registerAgentToolWorkflows()` pre-registers the child agent's workflow definition, and `ToolCompiler` references it by name. Each sub-agent gets its own DoWhile agentic loop, LLM calls, and task history. Existing behavior, no changes.

**Step 4: Build tools from scripts**

Each entry in `scripts` becomes a `ToolConfig` with `toolType = "worker"`.

```java
for (Map.Entry<String, Object> entry : scripts.entrySet()) {
    ToolConfig scriptTool = new ToolConfig();
    scriptTool.setName(entry.getKey());
    scriptTool.setDescription("Run " + entry.getKey() + " script");
    scriptTool.setToolType("worker");
    scriptTool.setInputSchema(Map.of(
        "type", "object",
        "properties", Map.of(
            "command", Map.of("type", "string",
                "description", "Arguments to pass to the script")),
        "required", List.of("command")));
    tools.add(scriptTool);
}
```

**Conductor mapping:** `toolType = "worker"` compiles to a `SIMPLE` task. Each script invocation is a separate, named Conductor task with its own I/O, timing, and retry policy.

**Step 5: Build `read_skill_file` tool**

A worker tool that reads resource files on demand from the skill directory on the user's machine.

```java
ToolConfig readFileTool = new ToolConfig();
readFileTool.setName("read_skill_file");
readFileTool.setDescription("Read a reference or resource file from the skill directory");
readFileTool.setToolType("worker");
readFileTool.setInputSchema(Map.of(
    "type", "object",
    "properties", Map.of(
        "path", Map.of("type", "string",
            "description", "Relative path within the skill directory",
            "enum", rawConfig.get("resourceFiles"))),
    "required", List.of("path")));
tools.add(readFileTool);
```

The `enum` constraint means the LLM can only read files that actually exist in the skill directory.

**Step 6: Wire cross-skill references**

Each entry in `crossSkillRefs` is recursively normalized and added as an `agent_tool`.

```java
// Cycle detection: maintain a set of skill names being normalized
// to prevent infinite recursion (A references B, B references A)
Set<String> normalizingSkills = getNormalizingStack();
for (Map.Entry<String, Object> entry : crossSkillRefs.entrySet()) {
    String refName = entry.getKey();
    if (normalizingSkills.contains(refName)) {
        throw new IllegalArgumentException(
            "Circular skill reference detected: " + refName + " is already being normalized");
    }
    normalizingSkills.add(refName);
    AgentConfig refAgent = this.normalize(entry.getValue());
    normalizingSkills.remove(refName);

    Map<String, Object> refToolConfig = new LinkedHashMap<>();
    refToolConfig.put("agentConfig", refAgent);
    ToolConfig refTool = ToolConfig.builder()
        .name(refAgent.getName())
        .description(refAgent.getDescription())
        .toolType("agent_tool")
        .config(refToolConfig)
        .build();
    tools.add(refTool);
}
```

**Step 7: Assemble final AgentConfig**

```java
orchestrator.setTools(tools);
return orchestrator;
```

### Normalizer Output Examples

**For /dg:**
```
AgentConfig(name="dg", model="claude-sonnet-4-6", instructions=<SKILL.md body>)
├── ToolConfig(name="gilfoyle", type="agent_tool")
│   └── AgentConfig(name="gilfoyle", instructions=<gilfoyle-agent.md>)
├── ToolConfig(name="dinesh", type="agent_tool")
│   └── AgentConfig(name="dinesh", instructions=<dinesh-agent.md>)
└── ToolConfig(name="read_skill_file", type="worker")
```

**For conductor:**
```
AgentConfig(name="conductor", instructions=<SKILL.md body>)
├── ToolConfig(name="conductor_api", type="worker")
└── ToolConfig(name="read_skill_file", type="worker")
```

**For brainstorming (with cross-skill ref to writing-plans):**
```
AgentConfig(name="brainstorming", instructions=<SKILL.md body>)
├── ToolConfig(name="writing-plans", type="agent_tool")
│   └── AgentConfig(name="writing-plans", instructions=<writing-plans SKILL.md body>)
└── ToolConfig(name="read_skill_file", type="worker")
```

No changes to `AgentCompiler`, `ToolCompiler`, or `MultiAgentCompiler`. The normalizer produces the same `AgentConfig` structure the compiler already handles.

---

## SDK Implementation

### `skill()` function

```python
def skill(path, model="", agent_models=None, search_path=None):
    path = Path(path).resolve()

    # 1. Read SKILL.md
    skill_md = (path / "SKILL.md").read_text()
    name = parse_frontmatter(skill_md)["name"]

    # 2. Discover *-agent.md files
    agent_files = {}
    for f in path.glob("*-agent.md"):
        agent_name = f.stem.removesuffix("-agent")
        agent_files[agent_name] = f.read_text()

    # 3. Discover scripts
    scripts = {}
    scripts_dir = path / "scripts"
    if scripts_dir.exists():
        for f in scripts_dir.iterdir():
            if f.is_file():
                scripts[f.stem] = {
                    "filename": f.name,
                    "language": detect_language(f),
                    "path": str(f),
                }

    # 4. List resource files (paths only)
    resource_files = []
    for subdir in ["references", "examples", "assets"]:
        d = path / subdir
        if d.exists():
            resource_files.extend(
                str(f.relative_to(path)) for f in d.rglob("*") if f.is_file()
            )
    for f in path.iterdir():
        if f.is_file() and f.name != "SKILL.md" and not f.name.endswith("-agent.md"):
            resource_files.append(f.name)

    # 5. Resolve cross-skill references
    cross_refs = resolve_cross_skills(skill_md, path, search_path)

    # 6. Build raw config
    raw_config = {
        "model": model,
        "agentModels": agent_models or {},
        "skillMd": skill_md,
        "agentFiles": agent_files,
        "scripts": {k: {"filename": v["filename"], "language": v["language"]}
                    for k, v in scripts.items()},
        "resourceFiles": resource_files,
        "crossSkillRefs": cross_refs,
    }

    # 7. Return Agent with framework marker
    agent = Agent(name=name, model=model)
    agent._framework = "skill"
    agent._framework_config = raw_config
    agent._skill_path = path
    agent._skill_scripts = scripts
    return agent
```

### Worker Registration

When `rt.run()` or `rt.serve()` is called, the runtime registers workers for skill tools:

```python
def _register_skill_workers(agent, tool_registry):
    # Script workers — one per script file
    for tool_name, script_info in agent._skill_scripts.items():
        script_path = script_info["path"]
        language = script_info["language"]

        @tool(name=tool_name)
        def run_script(command: str, _path=script_path, _lang=language) -> str:
            interpreter = {"python": "python3", "bash": "bash", "node": "node"}[_lang]
            result = subprocess.run(
                [interpreter, _path, *shlex.split(command)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return f"ERROR (exit {result.returncode}):\n{result.stderr}"
            return result.stdout

        tool_registry.register(run_script)

    # read_skill_file worker
    skill_dir = agent._skill_path
    allowed = set(agent._framework_config["resourceFiles"])

    @tool(name="read_skill_file")
    def read_skill_file(path: str) -> str:
        if path not in allowed:
            return f"ERROR: '{path}' not found. Available: {sorted(allowed)}"
        return (skill_dir / path).read_text()

    tool_registry.register(read_skill_file)
```

Each script worker registers as a separate Conductor task type (e.g., `scan_deps`, `conductor_api`). The `AgentCompiler` generates `SIMPLE` tasks with these names. Workers poll for their specific task type.

### `load_skills()` function

```python
def load_skills(path, model="", agent_models=None):
    path = Path(path).resolve()
    skills = {}
    for d in sorted(path.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            overrides = (agent_models or {}).get(d.name, {})
            skills[d.name] = skill(d, model=model, agent_models=overrides)
    return skills
```

### Serialization Hook

```python
def detect_framework(agent_obj):
    if hasattr(agent_obj, "_framework") and agent_obj._framework == "skill":
        return "skill"
    # ... existing detection logic
```

When framework is `"skill"`, the serializer sends `{"framework": "skill", "config": agent._framework_config}` to the server.

### SDK Code per Language

| Component | Lines | What it does |
|-----------|-------|-------------|
| `skill()` function | ~100 | Read directory, package config |
| `load_skills()` function | ~30 | Batch load, cross-ref resolution |
| Script worker registration | ~50 | One worker per script |
| `read_skill_file` worker | ~20 | Read files from skill dir |
| Cross-skill resolver | ~50 | Scan search path, match names |
| Serialization hook | ~10 | Detect `framework="skill"` |
| **Total** | **~260** | Per-language SDK footprint |

---

## CLI Support

### Ephemeral — `agentspan skill run`

```bash
agentspan skill run <path> "<prompt>" [flags]
    --model <model>                    # Orchestrator + default model
    --agent-model <name>=<model>       # Sub-agent override (repeatable)
    --search-path <dir>                # Cross-skill search dir (repeatable)
    --timeout <seconds>                # Execution timeout
    --stream                           # Stream SSE events
```

Internally: reads dir → packages config → sends to server → starts workers in background → waits for result → stops workers → exits.

### Production — `agentspan skill load` + `agentspan skill serve`

```bash
# Deploy skill definition to server
agentspan skill load <path> --model <model> [--agent-model <name>=<model>]

# Start workers (blocks, like rt.serve())
agentspan skill serve <path>

# Trigger by name (existing command, unchanged)
agentspan run <skill-name> "<prompt>"
```

### CLI Implementation

New `cli/cmd/skill.go` subcommand. Same directory reading conventions as the Python SDK. Raw config format is identical — the `SkillNormalizer` handles both SDK and CLI inputs.

---

## Composition with Regular Agents

Since `skill()` returns `Agent`, all composition patterns work naturally.

### Skills as sub-agents in a team

```python
dg = skill("./dg", model="anthropic/claude-sonnet-4-6")
conductor_skill = skill("./conductor", model="anthropic/claude-sonnet-4-6")
coder = Agent(name="coder", model="openai/gpt-4o", tools=[my_tools])

team = Agent(
    name="dev_team",
    agents=[dg, coder, conductor_skill],
    strategy="router",
    router=Agent(name="router", model="openai/gpt-4o-mini",
                 instructions="Route: review → dg, code → coder, deploy → conductor"),
)
```

### Skills as tools on a regular agent

```python
dg = skill("./dg", model="anthropic/claude-sonnet-4-6")

lead = Agent(
    name="tech_lead",
    model="anthropic/claude-sonnet-4-6",
    instructions="You manage the team. Use code review for PRs.",
    tools=[agent_tool(dg), my_jira_tool, my_slack_tool],
)
```

### Skills in pipelines

```python
reviewer = skill("./dg", model="anthropic/claude-sonnet-4-6")
fixer = Agent(name="fixer", model="openai/gpt-4o", tools=[edit_file, run_tests])

pipeline = reviewer >> fixer
result = rt.run(pipeline, "Review and fix auth.ts")
```

### Skills alongside framework agents

```python
from agents import Agent as OpenAIAgent

dg = skill("./dg", model="anthropic/claude-sonnet-4-6")
oai_coder = OpenAIAgent(name="coder", instructions="Write code.", model="gpt-4o")
deployer = Agent(name="deployer", model="openai/gpt-4o", cli_commands=True)

team = Agent(name="ship_it", agents=[dg, oai_coder, deployer], strategy="sequential")
```

Skill-based, OpenAI SDK, and native Agentspan agents in one team. Each goes through its own normalizer, all produce `AgentConfig`, all compile to the same Conductor execution.

---

## End-to-End Execution Trace: /dg

### Execution DAG

```
dg (execution_id: abc-123)
├── [LLM_CHAT_COMPLETE] orchestrator — reads SKILL.md instructions, dispatches gilfoyle
├── [SUB_AGENT] gilfoyle — own agentic loop, own LLM calls
│   └── [LLM_CHAT_COMPLETE] gilfoyle produces round 1 findings
├── [LLM_CHAT_COMPLETE] orchestrator — checks convergence, dispatches dinesh
├── [SUB_AGENT] dinesh — own agentic loop, own LLM calls
│   └── [LLM_CHAT_COMPLETE] dinesh responds with [concede]/[defend]/[dismiss]
├── [LLM_CHAT_COMPLETE] orchestrator — round 2, dispatches gilfoyle
├── [SUB_AGENT] gilfoyle — dismantles dinesh's defenses
├── [LLM_CHAT_COMPLETE] orchestrator — dispatches dinesh round 2
├── [SUB_AGENT] dinesh — all [concede] — CONVERGED
├── [LLM_CHAT_COMPLETE] orchestrator — convergence detected
├── [SIMPLE] read_skill_file — reads comic-template.html
└── [LLM_CHAT_COMPLETE] orchestrator — synthesizes verdict
```

### Detailed Task Trace

```
Execution: dg (execution_id: abc-123)
Status: COMPLETED
Duration: 45s

Task Execution Timeline:
─────────────────────────────────────────────────────────────────────

#1  dg_llm_0                LLM_CHAT_COMPLETE     COMPLETED  2.1s
    system:  "# Dinesh vs Gilfoyle Code Review\n## Invocation..."
    user:    "Review the latest git diff"
    output:  tool_call: gilfoyle(request: "Review this code:\n```diff...")

#2  gilfoyle                 SUB_AGENT             COMPLETED  8.3s
    input:   {request: "Review this code:\n```diff..."}
    #2a  gilfoyle_llm_0     LLM_CHAT_COMPLETE     COMPLETED  8.1s
         system:  "# You Are Gilfoyle\nYou are Bertram Gilfoyle..."
         output:  "### BANTER\nLine 47. Raw SQL with string concat...\n
                   ### FINDINGS\n- [severity:critical] [auth.ts:47]..."

#3  dg_llm_1                LLM_CHAT_COMPLETE     COMPLETED  1.8s
    context: gilfoyle findings received, dispatch dinesh
    output:  tool_call: dinesh(request: "Respond to Gilfoyle:\n...")

#4  dinesh                   SUB_AGENT             COMPLETED  7.1s
    input:   {request: "Respond to Gilfoyle:\n..."}
    #4a  dinesh_llm_0       LLM_CHAT_COMPLETE     COMPLETED  6.9s
         output:  "### BANTER\nOK first of all, that endpoint is behind
                   three layers of auth middleware...\n
                   ### FINDINGS\n- [concede] [auth.ts:47]...\n
                   - [defend] [api.ts:112]..."

#5  dg_llm_2                LLM_CHAT_COMPLETE     COMPLETED  1.5s
    context: dinesh has [defend] items — not converged, round 2
    output:  tool_call: gilfoyle(request: "Round 2. Dismantle defenses:\n...")

#6  gilfoyle                 SUB_AGENT             COMPLETED  7.8s
    #6a  gilfoyle_llm_0     LLM_CHAT_COMPLETE     COMPLETED  7.6s
         output:  "### FINDINGS\n- [severity:important] [api.ts:112]
                   nginx.conf has no limit_req directive..."

#7  dg_llm_3                LLM_CHAT_COMPLETE     COMPLETED  1.4s
    output:  tool_call: dinesh(request: "Round 2. Gilfoyle's counter:\n...")

#8  dinesh                   SUB_AGENT             COMPLETED  6.5s
    #8a  dinesh_llm_0       LLM_CHAT_COMPLETE     COMPLETED  6.3s
         output:  "### FINDINGS\n- [concede] [auth.ts:47]...\n
                   - [concede] [api.ts:112]..."

#9  dg_llm_4                LLM_CHAT_COMPLETE     COMPLETED  1.2s
    context: all findings are [concede] — CONVERGED
    output:  tool_call: read_skill_file(path: "comic-template.html")

#10 read_skill_file          SIMPLE                COMPLETED  0.1s
    input:   {path: "comic-template.html"}
    output:  {result: "<!DOCTYPE html>...{{PANELS}}..."}

#11 dg_llm_5                LLM_CHAT_COMPLETE     COMPLETED  3.2s
    output:  "## Dinesh vs Gilfoyle Review\n### Verdict\n..."

─────────────────────────────────────────────────────────────────────
Summary:
  Gilfoyle invocations:  2 sub-agent executions (8,700 tokens)
  Dinesh invocations:    2 sub-agent executions (7,400 tokens)
  File reads:            1 (comic-template.html)
  Orchestrator calls:    6 (12,500 tokens)
  Total tokens:          28,600
  Total duration:        45s
```

### Crash Recovery

If the process crashes after task #4 (dinesh round 1):
- Conductor execution abc-123 remains in RUNNING state
- Tasks 1-4 are COMPLETED (durable)
- `rt.serve()` restarts workers
- Execution resumes from task #5
- No work is lost, no rounds are repeated

---

## End-to-End Execution Trace: conductor

```
Execution: conductor (execution_id: def-456)
Status: COMPLETED

Task Execution Timeline:
─────────────────────────────────────────────────────────────────────

#1  conductor_llm_0         LLM_CHAT_COMPLETE     COMPLETED  2.5s
    user: "Create a data pipeline workflow and run it"

#2  conductor_api            SIMPLE                COMPLETED  1.2s
    input:  {command: "workflow create workflow.json"}
    output: {result: "Workflow my_pipeline created"}

#3  conductor_llm_1         LLM_CHAT_COMPLETE     COMPLETED  1.8s

#4  conductor_api            SIMPLE                COMPLETED  0.8s
    input:  {command: "workflow start -w my_pipeline -i '{\"data\": \"test\"}'"}
    output: {result: "Started execution: xyz-789"}

#5  conductor_llm_2         LLM_CHAT_COMPLETE     COMPLETED  1.3s

#6  read_skill_file          SIMPLE                COMPLETED  0.1s
    input:  {path: "references/workflow-definition.md"}
    output: {result: "# Workflow Definition Reference\n..."}

#7  conductor_llm_3         LLM_CHAT_COMPLETE     COMPLETED  2.1s

#8  conductor_api            SIMPLE                COMPLETED  0.5s
    input:  {command: "workflow get-execution xyz-789"}
    output: {result: "{\"status\": \"COMPLETED\", ...}"}

─────────────────────────────────────────────────────────────────────
```

Every `conductor_api` call is a distinct, named task. Each `read_skill_file` call is tracked. Full I/O visibility.

---

## Public API Surface

### Python SDK

Two new functions added to `agentspan.agents`:

```python
from agentspan.agents import skill, load_skills

# Load single skill
dg = skill(
    path="./dg",                                         # skill directory
    model="anthropic/claude-sonnet-4-6",                 # orchestrator + default
    agent_models={"gilfoyle": "openai/gpt-4o"},  # per-sub-agent override
    search_path=["~/.agents/skills/"],                   # cross-skill resolution
)

# Load all skills from directory
skills = load_skills(
    path="~/.agents/skills/",
    model="anthropic/claude-sonnet-4-6",
    agent_models={"dg": {"gilfoyle": "openai/gpt-4o"}},
)
```

### CLI Commands

```bash
# Ephemeral
agentspan skill run <path> "<prompt>" \
    --model <model> \
    --agent-model <name>=<model> \
    --search-path <dir> \
    --timeout <seconds> \
    --stream

# Production
agentspan skill load <path> --model <model> --agent-model <name>=<model>
agentspan skill serve <path>
agentspan run <skill-name> "<prompt>"
```

### Server API

No new endpoints. Skills use existing endpoints with `framework: "skill"`:

| Endpoint | Usage |
|----------|-------|
| `POST /api/agent/start` | Ephemeral: `{"framework": "skill", "config": {...}, "prompt": "..."}` |
| `POST /api/agent/compile` | Production load: `{"framework": "skill", "config": {...}}` |
| `GET /api/agent/stream/{executionId}` | SSE streaming — unchanged |
| `GET /api/agent/{executionId}/status` | Status polling — unchanged |
| `GET /api/agent/list` | Lists skill-based agents alongside regular agents |

---

## Implementation Scope

### New Components

| Component | Location | Lines | Purpose |
|-----------|----------|-------|---------|
| `skill()` function | `sdk/python/src/agentspan/agents/skill.py` | ~100 | Read directory, package config |
| `load_skills()` function | Same file | ~30 | Batch load with cross-ref resolution |
| Script worker registration | Same file | ~50 | One worker per script file |
| `read_skill_file` worker | Same file | ~20 | On-demand file reads |
| Cross-skill resolver | Same file | ~50 | Scan search path, match names |
| Serialization hook | `sdk/python/.../serializer.py` | ~10 | Detect `framework="skill"` |
| `SkillNormalizer.java` | `server/src/.../normalizer/` | ~200 | Parse + normalize to AgentConfig |
| CLI `skill` subcommand | `cli/cmd/skill.go` | ~150 | CLI entry point |
| **Total new code** | | **~610** | |

### Reused Components (unchanged)

| Component | Why it works |
|-----------|-------------|
| `AgentConfigSerializer` | Existing framework detection path |
| `NormalizerRegistry` | Auto-discovers new `@Component` normalizer |
| `AgentCompiler` | Receives canonical AgentConfig, compiles as usual |
| `ToolCompiler` | Handles `worker` and `agent_tool` types already |
| `MultiAgentCompiler` | Handles sub-agent compilation already |
| Conductor runtime | Executes the compiled workflow |
| SSE streaming | Streams events per execution |
| Worker polling | Script and read_skill_file workers poll normally |
| `agent_tool()` | Wraps sub-agents — existing function |

---

## Compatibility

### agentskills.io Specification

Full compatibility with the [agentskills.io specification](https://agentskills.io/specification). No extensions required. All frontmatter fields supported:

| Field | How it's used |
|-------|--------------|
| `name` | Agent name |
| `description` | Agent description, used for discovery |
| `license` | Stored in metadata, not enforced |
| `compatibility` | Stored in metadata |
| `metadata` | Passed through to `Agent.metadata` |
| `allowed-tools` | Stored in metadata. Not enforced at runtime (future enhancement) |

### Tested Skill Patterns

| Skill | Pattern | Status |
|-------|---------|--------|
| [/dg](https://github.com/v1r3n/dinesh-gilfoyle) | Orchestrator + 2 sub-agents + HTML asset | Works as-is |
| [conductor](https://github.com/conductor-oss/conductor-skills) | Instructions + Python CLI + references + examples | Works as-is |
| [superpowers](https://github.com/obra/superpowers) | 14 instruction-only skills with cross-skill refs | Works as-is |

No modification to any existing skill required.

---

## Edge Cases and Error Handling

### Worker Task Name Collisions

When multiple skills are composed (e.g., `skill("./skill-a")` and `skill("./skill-b")`), both may have `read_skill_file` workers or scripts with the same name. Worker task names are prefixed with the skill name to avoid collisions:

- `dg__read_skill_file`
- `conductor__read_skill_file`
- `dg__scan_deps`
- `conductor__conductor_api`

The `SkillNormalizer` applies this prefix when generating `ToolConfig` names. The SKILL.md instructions reference the unprefixed tool name (e.g., `read_skill_file`), and the normalizer maps accordingly.

### Error Handling

| Scenario | Behavior |
|----------|----------|
| `SKILL.md` not found in directory | Raise `SkillLoadError("Directory {path} is not a valid skill: SKILL.md not found")` |
| Malformed YAML frontmatter | Lenient: warn and attempt to extract name/description. Skip if unparseable. |
| Missing `name` in frontmatter | Raise `SkillLoadError("SKILL.md missing required 'name' field")` |
| Missing `description` in frontmatter | Warn, use empty string (skill still loads) |
| Empty `model` parameter | Raise `SkillLoadError("model is required for skill-based agents")` |
| Script exits non-zero during execution | Worker returns `ERROR (exit N): {stderr}` — LLM can retry or report |
| Cross-skill reference not found | Raise `SkillLoadError("Cross-skill reference '{name}' not found in search path")` |
| Circular cross-skill reference | Raise `IllegalArgumentException("Circular skill reference detected: {name}")` |
| `read_skill_file` path not in allowed list | Returns `ERROR: '{path}' not found. Available: [...]` |

### Language Detection for Scripts

`detect_language()` uses file extension mapping:

| Extension | Language | Interpreter |
|-----------|----------|-------------|
| `.py` | python | `python3` |
| `.sh` | bash | `bash` |
| `.js`, `.mjs` | node | `node` |
| `.ts` | node | `npx tsx` |
| `.rb` | ruby | `ruby` |
| `.go` | go | `go run` |
| No extension | bash | Check shebang line, default to `bash` |

### Cross-Skill Reference Resolution

`resolve_cross_skills()` scans the SKILL.md body for patterns that indicate skill invocation:
- `invoke <skill-name> skill` / `invoke the <skill-name> skill`
- `use <skill-name> skill`
- `call <skill-name> skill`

Matched names are searched in the search path (sibling dirs → `.agents/skills/` → `~/.agents/skills/`). If a matching directory with `SKILL.md` is found, it's packaged as a nested skill config. This is a best-effort heuristic — users can always compose explicitly via the SDK for precise control.

### Script Security

Script arguments come from LLM tool calls. While `shlex.split` prevents shell injection (no `shell=True`), the LLM can pass arbitrary arguments to scripts. Skill authors should validate arguments within their scripts. The `subprocess.run` call uses `timeout=300` to prevent runaway scripts.

---

## Known Limitations

### `read_skill_file` is scoped to the skill directory

The `read_skill_file` tool can only read files within the skill directory (paths listed in `resourceFiles` and virtual `skill_section:*` entries). Skills designed for Claude Code or similar tools that assume full filesystem access (e.g., scanning for `package.json` or `requirements.txt` in the project being reviewed) will not work via `read_skill_file` alone.

**Workaround:** Skills that need project filesystem access should use `cli_commands=True` on the parent agent, or provide additional `@tool` functions that expose the needed project-level operations. This is an intentional security boundary — skills should not have implicit access to the full filesystem.

### Task reference names are LLM-generated tool call IDs

When the LLM invokes a tool, the tool call ID (e.g., `call_ElaXTiouRe9HY6VtHGf43E6X`) is used as the Conductor task reference name. This makes execution DAG task names opaque in the UI. This is existing behavior across all Agentspan agent types (not specific to skills) and is required for correct tool call response routing.

### Pipeline workflow names are auto-generated

When skills are composed using the `>>` operator, the resulting pipeline workflow name is auto-generated by concatenating agent names (e.g., `dg_fixer_deployer`). This is existing behavior for all pipeline agents and is not specific to skills. Users can wrap the pipeline in a named `Agent` if a specific workflow name is needed.

### Token tracking for skill-based agents

Token usage aggregation in skill-based agent results follows the same path as regular agents. Token counts are aggregated from LLM task outputs during workflow execution. If token counts appear as 0 or None in the SDK's `AgentResult`, this is a pre-existing gap in token aggregation, not specific to skills.
