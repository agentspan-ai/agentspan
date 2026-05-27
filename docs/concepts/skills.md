---
title: Skills
description: Load, register, run, and test agentskills.io skill folders with Agentspan
---

# Skills

Skills let you package a reusable agent as a folder. A skill can include
instructions, sub-agents, scripts, examples, references, and assets. Agentspan
loads that folder as a durable `Agent`, compiles it to Conductor, and makes each
component visible in the execution graph.

## Skill Folder Layout

At minimum, a skill contains `SKILL.md` with YAML frontmatter and markdown
instructions:

```text
my-skill/
+-- SKILL.md
+-- reviewer-agent.md
+-- scripts/
|   +-- lint.sh
+-- references/
|   +-- rubric.md
+-- examples/
+-- assets/
```

Agentspan discovers files by convention:

| File or directory | Runtime behavior |
|---|---|
| `SKILL.md` | Main skill instructions and metadata |
| `*-agent.md` | Sub-agent workflow definitions |
| `scripts/*` | Worker tools executed by the local SDK or CLI worker process |
| `references/*`, `examples/*`, `assets/*` | Read on demand through `read_skill_file` |
| Other root files | Read on demand through `read_skill_file` |

Script and file-read tools are real Conductor `SIMPLE` tasks. They are not
inlined into the prompt, and their input/output is visible in the UI.

## CLI Workflow

Run a local skill folder:

```bash
agentspan skill run ~/.claude/skills/dg "Review auth.py" --model openai/gpt-4o
```

Register a skill package on the server:

```bash
agentspan skill register ~/.claude/skills/dg --model openai/gpt-4o --version 2026.05.21
agentspan skill list --all-versions
agentspan skill get dg --version 2026.05.21
```

Run a registered skill by name:

```bash
agentspan skill run dg "Review auth.py" --model openai/gpt-4o --version 2026.05.21
```

When the CLI runs a registered skill, it downloads the package into
`~/.agentspan/skills/<name>/<version>/files` and reuses that cached copy until
the server checksum changes. Registered cross-skill references are resolved
from the server registry at compile time. The CLI also downloads referenced
packages before execution so their script tools and packaged resources have
local workers. Dependency versions are pinned when the parent skill is
registered, so `parent@v1` continues to use the same child version even if that
child skill is updated later.

Use `skill load` when you want to deploy a skill as an agent definition and run
it later through regular agent commands:

```bash
agentspan skill load ~/.claude/skills/dg --model openai/gpt-4o
agentspan skill serve dg
agentspan agent run --name dg "Review the current PR"
```

## Workspace Context

Code review and development skills often need project context. `skill run` and
`skill serve` expose the current directory as a read-only `workspace` root by
default.

```bash
agentspan skill run code-review "Review the entire codebase" \
  --model openai/gpt-4o \
  --workspace .
```

Add more read-only roots with `--filesystem`:

```bash
agentspan skill run code-review "Review code and docs" \
  --model openai/gpt-4o \
  --workspace . \
  --filesystem docs=./docs
```

The generated workspace tools can list files, read files, search text, and read
git status/diff. The CLI enforces configured root boundaries.

## SDK Usage

### Python

```python
from agentspan.agents import Agent, AgentRuntime, agent_tool, skill

reviewer = skill("~/.claude/skills/dg", model="openai/gpt-4o")

with AgentRuntime() as runtime:
    result = runtime.run(reviewer, "Review auth.py")
    result.print_result()

lead = Agent(
    name="tech_lead",
    model="openai/gpt-4o",
    instructions="Use the review skill for code review requests.",
    tools=[agent_tool(reviewer, description="Run code review")],
)
```

### TypeScript

```typescript
import { Agent, AgentRuntime, agentTool, skill } from "@agentspan-ai/sdk";

const reviewer = skill("~/.claude/skills/dg", {
  model: "openai/gpt-4o",
});

const runtime = new AgentRuntime();
const result = await runtime.run(reviewer, "Review auth.py");
result.printResult();

const lead = new Agent({
  name: "tech_lead",
  model: "openai/gpt-4o",
  instructions: "Use the review skill for code review requests.",
  tools: [agentTool(reviewer, { description: "Run code review" })],
});
```

### Java

```java
import ai.agentspan.Agent;
import ai.agentspan.AgentTool;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;
import ai.agentspan.skill.Skill;

import java.nio.file.Paths;
import java.util.List;

Agent reviewer = Skill.skill(Paths.get(System.getProperty("user.home"), ".claude", "skills", "dg"),
    "openai/gpt-4o");

AgentResult direct = Agentspan.run(reviewer, "Review auth.py");
direct.printResult();

Agent lead = Agent.builder()
    .name("tech_lead")
    .model("openai/gpt-4o")
    .instructions("Use the review skill for code review requests.")
    .tools(List.of(AgentTool.from(reviewer, "Run code review")))
    .build();
```

### .NET

```csharp
using Agentspan;

var reviewer = Skill.Load("~/.claude/skills/dg", "openai/gpt-4o");

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(reviewer, "Review auth.py");
result.PrintResult();

var lead = new Agent("tech_lead")
{
    Model        = "openai/gpt-4o",
    Instructions = "Use the review skill for code review requests.",
    Tools        = [AgentTool.Create(reviewer, description: "Run code review")],
};
```

## Server Registry And UI

`agentspan skill register` uploads the skill folder as an immutable server-side
package. The CLI excludes generated directories, common secret files such as
`.env` and private keys, and any paths matched by `.agentspanignore`. The server
stores owner-scoped metadata separately from the package blob, validates size
and file-count limits, derives the runtime skill config from package contents,
and exposes the package in the UI under Skills. Registered package downloads are
verified against the server checksum before the CLI caches or executes them.

Package storage is configurable:

| Property | Default | Description |
|---|---|---|
| `agentspan.skills.package-store.type` | `filesystem` | `filesystem` for local deployments or `conductor-payload` for Conductor external payload storage |
| `agentspan.skills.storage.directory` | `${java.io.tmpdir}/agentspan/skills` | Owner-scoped metadata root and default filesystem package root parent |
| `agentspan.skills.package-store.filesystem.directory` | `${agentspan.skills.storage.directory}/packages` | Filesystem package blob directory |
| `agentspan.skills.max-package-bytes` | `52428800` | Maximum compressed upload size |
| `agentspan.skills.max-uncompressed-bytes` | `209715200` | Maximum expanded package size |
| `agentspan.skills.max-file-count` | `2000` | Maximum files per package |

## Testing

Skills should have deterministic end-to-end tests against a real Agentspan
server. The repository includes skill e2e suites for Python, TypeScript, Java,
and .NET:

```bash
cd sdk/python && AGENTSPAN_SERVER_URL=http://localhost:6767/api \
  python3 -m pytest e2e/test_suite15_skills.py -q

cd sdk/typescript && AGENTSPAN_SERVER_URL=http://localhost:6767/api \
  npm test -- tests/e2e/test_suite15_skills.test.ts

cd sdk/java && AGENTSPAN_SERVER_URL=http://localhost:6767/api \
  ./gradlew :test --tests Suite15Skills -Pe2e

cd sdk/csharp && AGENTSPAN_SERVER_URL=http://localhost:6767/api \
  dotnet test tests/AgentspanE2eTests/AgentspanE2eTests.csproj --filter Suite16_Skills
```

These tests prove skill loading, script workers, resource-file reads,
multi-agent skill files, `agent_tool` nesting, and real worker execution.

## Security Boundaries

`read_skill_file` can only read files that are part of the skill package.
Workspace tools can only read configured filesystem roots. Script workers run
locally, so skill authors should validate script arguments and avoid assuming
unbounded filesystem access.
