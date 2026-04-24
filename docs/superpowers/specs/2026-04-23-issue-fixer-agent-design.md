# Issue Fixer Agent — Design Spec

**Date:** 2026-04-23
**Status:** Draft
**Author:** Viren + Claude

## Overview

A multi-agent coding agent that takes a GitHub issue number, analyzes the codebase, implements a fix with tests, and creates a pull request — fully autonomously.

Built on the Agentspan SDK using a **pipeline-wrapped swarm** architecture: deterministic bookend stages handle issue fetching and PR creation, while a SWARM of specialized agents handles the iterative core work of planning, coding, reviewing, and testing.

## Configuration Constants

All project-specific values are stored as constants at the top of the file. To adapt this agent to your own repo, change these values:

```python
# ── Project-Specific Configuration ────────────────────────────
REPO = "agentspan-ai/agentspan"            # GitHub owner/repo
REPO_URL = f"https://github.com/{REPO}"    # Full repo URL
BRANCH_PREFIX = "fix/issue-"               # Branch naming: fix/issue-42

# ── Models ────────────────────────────────────────────────────
OPUS = "anthropic/claude-opus-4-6"         # For deep reasoning (Tech Lead, Gilfoyle)
SONNET = "anthropic/claude-sonnet-4-6"     # For fast iteration (Coder, QA, etc.)

# ── Credentials ──────────────────────────────────────────────
GITHUB_CREDENTIAL = "GITHUB_TOKEN"         # Credential name stored via: agentspan credentials set GITHUB_TOKEN <token>

# ── Skill Paths ──────────────────────────────────────────────
DG_SKILL_PATH = "~/.claude/skills/dg"      # Path to cloned dinesh-gilfoyle skill

# ── Server ───────────────────────────────────────────────────
SERVER_URL = "http://localhost:6767"        # Agentspan server URL
MCP_TESTKIT_PORT = 3001                    # MCP testkit port for e2e tests

# ── Timeouts & Limits ────────────────────────────────────────
SWARM_MAX_TURNS = 500                      # Max iterations in the coding swarm
SWARM_TIMEOUT = 14400                      # 4 hours — e2e alone is ~45 min
E2E_TOOL_TIMEOUT = 5400                    # 90 min — full e2e suite with margin
MAX_REVIEW_CYCLES = 3                      # Max code review → fix loops before escalation
MAX_E2E_RETRIES = 3                        # Max e2e fail → fix → rerun loops
```

**To adapt to your repo:** Change `REPO`, `GITHUB_CREDENTIAL`, and optionally the models and skill path. Everything else (agent definitions, tools, handoffs) references these constants.

## Architecture

### Topology: Pipeline-Wrapped Swarm

```
Issue Analyst  >>  [SWARM: Tech Lead <-> Coder <-> DG <-> QA Lead]  >>  PR Creator
  (Stage 1)                     (Stage 2)                               (Stage 3)
```

- **Stage 1 (Pipeline):** Issue Analyst — fetch issue, clone repo, create branch, identify module. One-shot, no iteration.
- **Stage 2 (Swarm):** Core work. Four agents iterate until all tests pass.
- **Stage 3 (Pipeline):** PR Creator — commit, push, create PR. One-shot, no iteration.

### Swarm Handoff Flow

```
                    ┌─────────────────────────────────────────────┐
                    │              CODING SWARM                   │
                    │                                             │
Issue Analyst ──>>──│  Tech Lead ──→ Coder ──→ DG ──→ QA Lead     │──>>── PR Creator
                    │       ↑          ↑   ←──┘         │         │
                    │       │          └────────────────┘         │
                    │       └── (if fundamental rethink needed)   │
                    └─────────────────────────────────────────────┘
```

**Handoff conditions (all `OnTextMention`):**

| Trigger Text | Source | Target | When |
|---|---|---|---|
| `HANDOFF_TO_CODER` | Tech Lead, DG, QA Lead | Coder | Plan ready, review issues to fix, test issues to fix |
| `HANDOFF_TO_DG` | Coder | DG Reviewer | Implementation ready for review |
| `HANDOFF_TO_QA` | DG, Coder | QA Lead | Code approved, or tests written for review |
| `HANDOFF_TO_TECH_LEAD` | Any | Tech Lead | Fundamental approach needs rethinking |
| `SWARM_COMPLETE` | QA Lead | (exits swarm) | All e2e tests pass |

### Typical Execution Flow

1. **Tech Lead** reads issue context, explores codebase, writes implementation plan + test strategy to contextbook
2. **Coder** reads plan, implements fix, runs lint + build check, hands off to DG
3. **DG (Code Reviewer)** runs adversarial review (Dinesh vs Gilfoyle), writes findings
   - If critical issues → back to Coder
   - If approved → forward to QA Lead
4. **QA Lead** plans test suite, hands off to Coder to write tests
5. **Coder** writes tests per QA Lead's plan, hands off to QA Lead
6. **QA Lead** reviews tests (no mocks, e2e, algorithmic assertions), then runs full e2e suite
   - If test quality issues → back to Coder
   - If e2e fails → back to Coder with failure details
   - If all tests pass → `SWARM_COMPLETE`

## Exact Pipeline Construction

```python
from agentspan.agents import Agent, AgentRuntime, Strategy, skill, agent_tool
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.termination import TextMentionTermination

# All constants defined above (REPO, OPUS, SONNET, etc.)

# --- Tools defined here (see Tool Inventory) ---

# --- Stage 1: Issue Analyst ---
issue_analyst = Agent(
    name="issue_analyst",
    model=SONNET,
    stateful=True,
    max_turns=20,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp", "ls", "find"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[contextbook_write, contextbook_read],
    stop_when=_issue_analyzed,
    instructions=ISSUE_ANALYST_INSTRUCTIONS,
)

# --- Stage 2: Swarm agents ---
tech_lead = Agent(
    name="tech_lead",
    model=OPUS,
    stateful=True,
    max_turns=30,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_log, git_blame, run_command,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=TECH_LEAD_INSTRUCTIONS,
)

coder = Agent(
    name="coder",
    model=SONNET,
    stateful=True,
    max_turns=100,
    max_tokens=60000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["git"],
        allow_shell=True,
        timeout=120,
    ),
    tools=[
        read_file, write_file, edit_file, apply_patch,
        grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_diff, git_log, run_command,
        lint_and_format, build_check, run_unit_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=CODER_INSTRUCTIONS,
)

# DG skill loaded from cloned repo, wrapped in coordinator (see DG Integration)
dg_skill = skill(
    DG_SKILL_PATH,
    model=SONNET,
    agent_models={"gilfoyle": OPUS, "dinesh": SONNET},
)

dg_reviewer = Agent(
    name="dg_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=15,
    max_tokens=60000,
    tools=[
        agent_tool(dg_skill, description="Run adversarial Dinesh vs Gilfoyle code review"),
        read_file, grep_search, git_diff, file_outline,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=DG_REVIEWER_INSTRUCTIONS,
)

qa_lead = Agent(
    name="qa_lead",
    model=SONNET,
    stateful=True,
    max_turns=40,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_LEAD_INSTRUCTIONS,
)

# Assemble swarm
coding_swarm = Agent(
    name="coding_swarm",
    model=SONNET,
    stateful=True,
    strategy=Strategy.SWARM,
    agents=[tech_lead, coder, dg_reviewer, qa_lead],
    handoffs=[
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
        OnTextMention(text="HANDOFF_TO_DG", target="dg_reviewer"),
        OnTextMention(text="HANDOFF_TO_QA", target="qa_lead"),
        OnTextMention(text="HANDOFF_TO_TECH_LEAD", target="tech_lead"),
    ],
    termination=TextMentionTermination("SWARM_COMPLETE"),
    max_turns=SWARM_MAX_TURNS,
    max_tokens=60000,
    timeout_seconds=SWARM_TIMEOUT,
    instructions="Start with tech_lead. Iterate until QA Lead confirms ALL_TESTS_PASS.",
)

# --- Stage 3: PR Creator ---
pr_creator = Agent(
    name="pr_creator",
    model=SONNET,
    stateful=True,
    max_turns=10,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[git_diff, git_log, contextbook_read],
    stop_when=_pr_created,
    instructions=PR_CREATOR_INSTRUCTIONS,
)

# --- Full pipeline ---
pipeline = issue_analyst >> coding_swarm >> pr_creator
```

**Key design notes:**
- Agents use BOTH custom `@tool` functions AND `cli_config` simultaneously — the SDK supports this. Custom tools are passed via `tools=[]`, CLI commands are enabled via `cli_config`.
- The DG reviewer is a **coordinator agent** that wraps the DG **skill** as an `agent_tool()`. The skill handles the internal Dinesh/Gilfoyle debate; the coordinator handles contextbook integration and handoff logic.
- `contextbook_*` tools are custom `@tool(stateful=True)` functions (see Contextbook section). They work alongside `cli_config` commands.
- Pipeline stages share context: output of stage N becomes input text for stage N+1.

## Agents

### Issue Analyst (Pipeline Stage 1)

| Property | Value |
|---|---|
| **Model** | `anthropic/claude-sonnet-4-6` — cheap, mostly CLI commands |
| **Role** | Fetch issue, clone repo, create branch, identify affected module |
| **Tools** | `run_command` (via cli_config: gh, git, mktemp, ls, find) + `contextbook_write`, `contextbook_read` |
| **Credentials** | `GITHUB_CREDENTIAL` (gh CLI uses this via `GH_TOKEN` alias internally) |
| **Max turns** | 20 |

**Steps:**
1. `gh issue view <N> --repo REPO --json number,title,body,author,labels,comments`
2. Clone repo, create branch `BRANCH_PREFIX<N>`, push empty branch
3. Scan top-level directories to identify affected module(s)
4. Write `issue_context` and initial `module_map` to contextbook
5. Output: `REPO`, `BRANCH`, `ISSUE`, `MODULE`

**Stop condition:** `_issue_analyzed` — contextbook has `issue_context` written and output contains `MODULE:`.

**Error handling:** If no matching module is found, set `MODULE: unknown` and let the Tech Lead determine the correct module(s) during planning.

### Tech Lead (Swarm)

| Property | Value |
|---|---|
| **Model** | `anthropic/claude-opus-4-6` — highest reasoning quality for architectural analysis |
| **Role** | Analyze codebase, create detailed implementation plan + testing strategy |
| **Tools** | `read_file`, `grep_search`, `glob_find`, `list_directory`, `file_outline`, `search_symbols`, `find_references`, `git_log`, `git_blame`, `run_command`, `contextbook_*` |
| **Max turns** | 30 — planning is deep but bounded; if 30 turns isn't enough, the plan is too complex |

**Steps:**
1. Read `issue_context` and `module_map` from contextbook
2. Deep-dive into affected module — read code, trace call chains, understand architecture
3. Review `e2e/` test patterns (conftest, existing suites, assertion patterns)
4. Write to contextbook:
   - `implementation_plan`: root cause, step-by-step fix, specific files/functions, risks, edge cases
   - `test_plan` skeleton: which existing tests, what new tests, acceptance criteria
5. `HANDOFF_TO_CODER`

### Coder (Swarm)

| Property | Value |
|---|---|
| **Model** | `anthropic/claude-sonnet-4-6` — fast, cost-effective for iterative coding |
| **Role** | Implement fix, write tests, respond to review feedback |
| **Tools** | All 21 tools (full read + write + git + test + contextbook) |
| **Credentials** | `GITHUB_CREDENTIAL` |
| **Max turns** | 100 — high because the coder does the most work (implement, test, fix feedback loops) |

**Steps (implementation mode):**
1. Read `implementation_plan` from contextbook
2. Implement fix step by step
3. Run `lint_and_format` and `build_check` after edits
4. Update `change_log` in contextbook
5. `HANDOFF_TO_DG`

**Steps (test writing mode):**
1. Read `test_plan` from contextbook
2. Write tests following e2e patterns (no mocks, deterministic, algorithmic)
3. Run `run_unit_tests` for quick feedback
4. `HANDOFF_TO_QA`

**Steps (fix feedback mode):**
1. Read `review_findings` from contextbook
2. Fix issues, re-lint, re-build
3. Update `change_log`
4. Hand off to whoever requested the fix

### DG Code Reviewer (Swarm — Skill Agent)

| Property | Value |
|---|---|
| **Model** | Wrapper: `anthropic/claude-sonnet-4-6`, Gilfoyle: `anthropic/claude-opus-4-6`, Dinesh: `anthropic/claude-sonnet-4-6` |
| **Role** | Adversarial code review via Dinesh vs Gilfoyle debate |
| **Tools** | `agent_tool(dg_skill)`, `read_file`, `grep_search`, `git_diff`, `file_outline`, `contextbook_*` |
| **Max turns** | 15 |
| **Source** | [github.com/v1r3n/dinesh-gilfoyle](https://github.com/v1r3n/dinesh-gilfoyle) |

The DG skill is loaded via `skill()` and wrapped in a coordinator agent that:
1. Reads `implementation_plan` and `change_log` from contextbook
2. Runs `git_diff` to collect all changes
3. Invokes the DG skill (adversarial review)
4. Writes findings to `review_findings` in contextbook
5. If critical issues → `HANDOFF_TO_CODER`
6. If approved → `HANDOFF_TO_QA`

### QA Lead (Swarm)

| Property | Value |
|---|---|
| **Model** | `anthropic/claude-sonnet-4-6` |
| **Role** | Plan test suite, review test quality, run full e2e, gate the PR |
| **Tools** | `read_file`, `grep_search`, `glob_find`, `list_directory`, `file_outline`, `git_diff`, `run_command`, `run_unit_tests`, `run_e2e_tests`, `contextbook_*` |
| **Max turns** | 40 |

**Test planning mode (after DG approves):**
1. Read contextbook: `implementation_plan`, `change_log`, `review_findings`
2. Study existing e2e test patterns in `sdk/python/e2e/`
3. Write `test_plan` to contextbook with specific test cases and acceptance criteria
4. `HANDOFF_TO_CODER`

**Test review mode (after Coder writes tests):**
1. Read new test files, validate against rules:
   - No mocks — real e2e with live server
   - No LLM output parsing for assertions
   - Algorithmic/deterministic validation only
   - Tests must be able to fail (counterfactual verification)
2. If quality issues → write `review_findings`, `HANDOFF_TO_CODER`
3. If tests look good → run `run_e2e_tests` (full suite, ~45 min)
4. If e2e passes → `SWARM_COMPLETE`
5. If e2e fails → write failure details to `test_results`, `HANDOFF_TO_CODER`

### PR Creator (Pipeline Stage 3)

| Property | Value |
|---|---|
| **Model** | `anthropic/claude-sonnet-4-6` |
| **Role** | Commit changes, push branch, create PR |
| **Tools** | `run_command` (via cli_config: gh, git), `git_diff`, `git_log`, `contextbook_read` |
| **Credentials** | `GITHUB_CREDENTIAL` |
| **Max turns** | 10 |

**Steps:**
1. Read contextbook: `issue_context`, `implementation_plan`, `change_log`, `test_results`
2. Stage and commit all changes with descriptive message
3. Push branch
4. `gh pr create` with title referencing issue, body with fix summary, "Fixes #N"
5. Output PR URL

**Stop condition:** Output contains `github.com` and `/pull/`.

## Contextbook: Durable Team Memory

### The Problem

In a long-running swarm (potentially hours), three things erode agent context:

1. **Context compaction** — LLM conversation history gets truncated
2. **Crashes + resume** — workflow resumes but agent "working memory" is gone
3. **Many handoff turns** — earlier details (like the plan) get diluted

### Solution

A file-backed, section-aware shared document (`.contextbook/` directory) that acts as the team's persistent whiteboard. Three tools provide access:

| Tool | Purpose |
|---|---|
| `contextbook_write(section, content, append)` | Write/append to a named section |
| `contextbook_read(section)` | Read a section, or table of contents if empty |
| `contextbook_summary()` | Condensed summary of all sections for re-orientation |

### Sections

| Section | Written by | Content |
|---|---|---|
| `issue_context` | Issue Analyst | Full issue body, requirements, acceptance criteria, author |
| `module_map` | Tech Lead | Affected modules, key files, dependencies |
| `implementation_plan` | Tech Lead | Root cause, step-by-step fix, files/functions, risks |
| `test_plan` | QA Lead | What to test, which suites, new tests needed, acceptance criteria |
| `change_log` | Coder | Cumulative log of files changed and why (append mode) |
| `review_findings` | DG / QA Lead | Review issues, what's resolved, what's outstanding |
| `test_results` | QA Lead / Coder | Latest test run results, pass/fail, failure details |
| `decisions` | Any agent | Key decisions with rationale (append mode) |
| `status` | Any agent | Current phase, what's done, what's next |

### Recovery Pattern

Every agent's instructions include:

```
FIRST: Call contextbook_read() to see the current state of the project.
If resuming from a crash or after context compaction, call contextbook_summary()
to re-orient before doing anything else.

ALWAYS update the contextbook when you:
- Make a decision → append to 'decisions'
- Change a file → append to 'change_log'
- Complete a phase → update 'status'
```

## Tool Inventory

### File Operations (6 tools)

| Tool | Description |
|---|---|
| `read_file(path, start_line, end_line)` | Read file contents with optional line range |
| `write_file(path, content)` | Create or overwrite a file |
| `edit_file(path, old_string, new_string)` | Precise string replacement — fails if not unique match |
| `apply_patch(patch, working_dir)` | Apply unified diff for coordinated multi-file changes |
| `list_directory(path, max_depth)` | Tree-structured directory browsing |
| `file_outline(path)` | Show classes, functions, methods — polyglot (Python, Go, Java, TS, React) |

### Search & Navigation (4 tools)

| Tool | Description |
|---|---|
| `glob_find(pattern, path)` | Find files by glob pattern |
| `grep_search(pattern, path, glob_filter, max_results)` | Regex content search with file:line output |
| `search_symbols(name, kind, path)` | Find definitions (class, func, type, interface, struct) |
| `find_references(symbol, path)` | Find all usages of a symbol — blast radius analysis |

### Git (3 tools)

| Tool | Description |
|---|---|
| `git_diff(base, path)` | Diff vs branch/commit, optionally scoped to file/dir |
| `git_log(path, max_count)` | Commit history, optionally for a specific file |
| `git_blame(path, start_line, end_line)` | Line-by-line authorship |

### Build & Test (4 tools)

| Tool | Description |
|---|---|
| `lint_and_format(module, path)` | Auto-format + lint per module (ruff, eslint, gofmt, etc.) |
| `build_check(module)` | Compile/type-check without running tests |
| `run_unit_tests(module, command)` | Module-specific unit tests (pytest, vitest, go test, gradle) |
| `run_e2e_tests(suite, sdk)` | Full e2e via `e2e/orchestrator.sh` (~45 min) |

### Execution & Context (4 tools)

| Tool | Description |
|---|---|
| `run_command(command, working_dir, timeout)` | General shell execution |
| `contextbook_write(section, content, append)` | Write to team contextbook |
| `contextbook_read(section)` | Read from contextbook (or table of contents) |
| `contextbook_summary()` | Condensed summary for re-orientation |

### Tool Assignment Matrix

| Tool | Issue Analyst | Tech Lead | Coder | DG Reviewer | QA Lead | PR Creator |
|---|---|---|---|---|---|---|
| `read_file` | | X | X | X | X | |
| `write_file` | | | X | | | |
| `edit_file` | | | X | | | |
| `apply_patch` | | | X | | | |
| `list_directory` | | X | X | | X | |
| `file_outline` | | X | X | X | X | |
| `glob_find` | | X | X | | X | |
| `grep_search` | | X | X | X | X | |
| `search_symbols` | | X | X | | | |
| `find_references` | | X | X | | | |
| `git_diff` | | | X | X | X | X |
| `git_log` | | X | X | | | X |
| `git_blame` | | X | | | | |
| `lint_and_format` | | | X | | | |
| `build_check` | | | X | | | |
| `run_unit_tests` | | | X | | X | |
| `run_e2e_tests` | | | | | X | |
| `run_command` | X (cli_config) | X | X | | X | X (cli_config) |
| `contextbook_write` | X | X | X | X | X | |
| `contextbook_read` | X | X | X | X | X | X |
| `contextbook_summary` | | X | X | X | X | |

## Target Repository Structure

The default configuration targets the [agentspan-ai/agentspan](https://github.com/agentspan-ai/agentspan) monorepo. Adapt the `REPO` constant and module table below for your own repo:

| Module | Language | Test Runner | Key Paths |
|---|---|---|---|
| `server/` | Java 21 | Gradle (JUnit) | `server/src/main/java/`, `server/src/test/java/` |
| `sdk/python/` | Python | pytest | `sdk/python/src/agentspan/`, `sdk/python/e2e/` |
| `sdk/typescript/` | TypeScript | Vitest | `sdk/typescript/src/`, `sdk/typescript/tests/e2e/` |
| `cli/` | Go | go test | `cli/cmd/`, `cli/internal/` |
| `ui/` | React/TS | Playwright | `ui/src/`, `ui/e2e/` |

## Testing Rules

These rules are enforced by the QA Lead during test review:

1. **No mocks** — all tests must be real end-to-end with a live server
2. **No LLM output parsing** — assertions must be algorithmic/deterministic
3. **Counterfactual verification** — write the test, make it fail, assert it fails to prove correctness
4. **Full e2e gate** — `e2e/orchestrator.sh` must pass before PR creation (all SDKs, all suites)
5. **E2e patterns** — follow existing patterns in `sdk/python/e2e/conftest.py` and `test_suite*.py`

## File Location

```
sdk/python/examples/100_issue_fixer_agent.py
```

## DG Skill Integration

The DG code reviewer uses a **coordinator pattern**: the DG skill (loaded from the cloned repo) is wrapped as an `agent_tool()` inside a coordinator agent that handles contextbook and handoff logic.

### Why a Coordinator Wrapper?

The DG skill is a self-contained multi-agent system (orchestrator + Gilfoyle + Dinesh). It accepts code to review and returns findings. But it doesn't know about:
- The contextbook (our custom persistence layer)
- The swarm handoff protocol (`HANDOFF_TO_CODER`, `HANDOFF_TO_QA`)
- The implementation plan or change log

The coordinator bridges these concerns:

```python
# 1. Load the skill — returns an Agent with internal Gilfoyle/Dinesh sub-agents
dg_skill = skill(
    DG_SKILL_PATH,
    model=SONNET,
    agent_models={"gilfoyle": OPUS, "dinesh": SONNET},
)

# 2. Wrap in coordinator — adds contextbook + handoff awareness
dg_reviewer = Agent(
    name="dg_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=15,
    tools=[
        agent_tool(dg_skill, description="Run adversarial Dinesh vs Gilfoyle code review"),
        read_file, grep_search, git_diff, file_outline,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=DG_REVIEWER_INSTRUCTIONS,
)
```

### Execution Flow

When `dg_reviewer` runs in the swarm:
1. Coordinator reads contextbook (`implementation_plan`, `change_log`)
2. Coordinator runs `git_diff` to collect all changes
3. Coordinator calls `agent_tool(dg_skill)` with the diff + context → this spawns a SUB_WORKFLOW
4. Inside the SUB_WORKFLOW, the DG skill orchestrates its Gilfoyle/Dinesh debate
5. DG skill returns review findings to the coordinator
6. Coordinator writes findings to `review_findings` in contextbook
7. Coordinator says `HANDOFF_TO_CODER` or `HANDOFF_TO_QA`

### Conductor Execution DAG

```
coding_swarm (SWARM)
└── dg_reviewer (agent turn)
    ├── [LLM_CHAT_COMPLETE] coordinator reads contextbook, runs git_diff
    ├── [SUB_WORKFLOW] dg_skill (execution_id: abc-...)
    │   ├── [LLM_CHAT_COMPLETE] orchestrator dispatches gilfoyle
    │   ├── [SUB_WORKFLOW] gilfoyle — code critique
    │   ├── [SUB_WORKFLOW] dinesh — defense/concession
    │   ├── [LLM_CHAT_COMPLETE] orchestrator (round 2...)
    │   └── [LLM_CHAT_COMPLETE] orchestrator synthesizes verdict
    ├── [LLM_CHAT_COMPLETE] coordinator writes to contextbook
    └── [LLM_CHAT_COMPLETE] coordinator outputs HANDOFF_TO_*
```

## Polyglot Tool Behavior

The monorepo contains Go, Java, Python, TypeScript, and React. Tools that are language-aware auto-detect the module based on directory structure and file extensions.

### `lint_and_format(module, path)`

Auto-detects and runs the appropriate linter/formatter:

| Module | Lint | Format |
|---|---|---|
| `sdk/python/` | `ruff check --fix` | `ruff format` |
| `sdk/typescript/` | `eslint --fix` | `prettier --write` |
| `cli/` | `go vet ./...` | `gofmt -w` |
| `server/` | (uses Gradle checkstyle if configured) | (Gradle spotlessApply if configured) |
| `ui/` | `eslint --fix` | `prettier --write` |

If `module` is empty, auto-detects from `path` by checking which top-level directory the path falls under.

### `build_check(module)`

Compile/type-check without running tests:

| Module | Command |
|---|---|
| `sdk/python/` | `cd sdk/python && uv run ruff check` |
| `sdk/typescript/` | `cd sdk/typescript && npm run build` (or `tsc --noEmit`) |
| `cli/` | `cd cli && go build ./...` |
| `server/` | `cd server && gradle compileJava -x test` |
| `ui/` | `cd ui && pnpm run build` |

### `run_unit_tests(module, command)`

If `command` is empty, auto-detects:

| Module | Default Command |
|---|---|
| `sdk/python/` | `cd sdk/python && uv run pytest tests/ -x` |
| `sdk/typescript/` | `cd sdk/typescript && npm test` |
| `cli/` | `cd cli && go test ./... -race` |
| `server/` | `cd server && gradle test` |
| `ui/` | `cd ui && pnpm test` |

If `command` is provided, it overrides the default (useful for running a specific test file).

### `run_e2e_tests(suite, sdk)`

Wraps `e2e/orchestrator.sh`:

```bash
# Full suite (default)
./e2e/orchestrator.sh --sdk both

# Filtered
./e2e/orchestrator.sh --sdk python --suite suite9
```

**Behavior:**
- **Blocking call** — runs synchronously, returns when complete (~45 min for full suite)
- **Structured output** — parses JUnit XML results and returns: total/passed/failed/skipped counts + failure details per test
- **Timeout** — tool timeout set to `E2E_TOOL_TIMEOUT` (90 min) to accommodate full suite with margin
- **Prerequisites** — assumes Agentspan server is running, MCP testkit available on `MCP_TESTKIT_PORT`

### `file_outline(path)`

Uses regex patterns per language to extract definitions:

| Language | Extensions | Patterns |
|---|---|---|
| Python | `.py` | `class`, `def`, `async def` |
| Go | `.go` | `func`, `type ... struct`, `type ... interface` |
| Java | `.java` | `class`, `interface`, `enum`, `public/private ... method` |
| TypeScript | `.ts`, `.tsx` | `class`, `interface`, `type`, `function`, `const ... =`, `export` |
| React | `.tsx`, `.jsx` | Same as TypeScript + component patterns |

Returns: `line_number | kind | name | signature`

### `search_symbols(name, kind, path)` and `find_references(symbol, path)`

Both use `ripgrep` (`rg`) with language-aware regex patterns:
- `search_symbols` finds **definitions** — where a symbol is declared
- `find_references` finds **usages** — where a symbol is used (excludes the definition itself)

## Error Handling & Recovery

### Iteration Limits

To prevent infinite loops in the swarm:

| Cycle | Max Iterations | Escalation |
|---|---|---|
| Coder → DG → Coder (fix review issues) | `MAX_REVIEW_CYCLES` (3) | After N failed reviews, `HANDOFF_TO_TECH_LEAD` for plan revision |
| Coder → QA → Coder (fix test issues) | `MAX_REVIEW_CYCLES` (3) | After N failed test reviews, `HANDOFF_TO_TECH_LEAD` |
| QA runs e2e → fails → Coder fixes → QA re-runs | `MAX_E2E_RETRIES` (3) | After N failed e2e runs, swarm exits with `SWARM_FAILED` |
| Overall swarm | `SWARM_MAX_TURNS` (500) | Hard timeout at `SWARM_TIMEOUT` (4 hours) |

These limits are enforced via agent instructions, not SDK-level constraints.

### Failure Modes

| Failure | Impact | Recovery |
|---|---|---|
| **GitHub repo unreachable** | Issue Analyst fails | Pipeline fails at stage 1; `gate` prevents swarm from starting |
| **Issue doesn't exist** | Issue Analyst can't fetch | Issue Analyst outputs error; pipeline stops |
| **Branch already exists** | Clone/checkout fails | Issue Analyst checks for existing branch, uses it if found |
| **Build fails after edits** | Coder's changes break compilation | Coder runs `build_check` after every edit cycle; DG won't receive broken code |
| **E2e server not running** | `run_e2e_tests` fails | QA Lead detects "connection refused" in output, writes to contextbook, coder must start server |
| **E2e timeout (>90 min)** | `run_e2e_tests` tool times out | QA Lead retries with `--suite` filter for relevant suites only |
| **Agent crash mid-swarm** | Worker dies | Agentspan durability: workflow persists on server, `serve()` re-registers workers, swarm resumes from last completed task |
| **Context compaction** | Agent loses earlier context | Agent calls `contextbook_summary()` to re-orient (enforced by instruction preamble) |
| **Fix spans multiple modules** | Single module assumption breaks | Tech Lead identifies all affected modules in `module_map`; coder works across modules |

### Stateful Durability Guarantees

With `stateful=True` on all agents:

1. Each execution gets a **unique domain UUID** — workers register under this domain
2. **No task stealing** — concurrent runs of the same agent don't interfere
3. **Crash recovery** — on restart, `start()` with same `idempotency_key` returns the existing execution; `serve()` re-registers workers under the original domain
4. **Workflow persistence** — Conductor server maintains workflow state (RUNNING, PAUSED, COMPLETED) independently of worker lifecycle
5. **Contextbook persistence** — `.contextbook/` files on disk survive worker restarts

## Entry Point & Idempotency (Detailed)

### Idempotency Behavior

```python
idempotency_key = f"issue-{issue_number}"
```

| Scenario | What Happens |
|---|---|
| **First run** | `start()` creates new execution, returns handle |
| **Same key, execution RUNNING** | `start()` returns handle to existing execution (no duplicate) |
| **Same key, execution COMPLETED** | `start()` returns handle to completed execution (no re-run) |
| **Same key, execution FAILED** | `start()` returns handle to failed execution |
| **Force restart needed** | Use a different key: `f"issue-{issue_number}-retry-{attempt}"` |

### Idempotency TTL

The idempotency key is tied to the Conductor execution lifetime. Completed executions are retained by the server per its configured retention policy (default: 90 days). After that, the key is available for reuse.

### Full Entry Point

```python
#!/usr/bin/env python3
"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

Usage:
    python 100_issue_fixer_agent.py <issue_number>
    python 100_issue_fixer_agent.py 42

Requirements:
    - Agentspan server running (SERVER_URL)
    - GITHUB_CREDENTIAL: agentspan credentials set <credential_name> <token>
    - gh CLI installed and authenticated
    - DG skill cloned to DG_SKILL_PATH
    - Full build toolchain (Go, Java 21, Python 3.10+, Node.js, pnpm, uv)
    - MCP testkit available (for e2e tests)
"""

import sys

from agentspan.agents import AgentRuntime

# ... agent definitions ...

def main():
    if len(sys.argv) < 2:
        print("Usage: python 100_issue_fixer_agent.py <issue_number>")
        sys.exit(1)

    issue_number = int(sys.argv[1])
    idempotency_key = f"issue-{issue_number}"

    pipeline = issue_analyst >> coding_swarm >> pr_creator

    with AgentRuntime() as rt:
        handle = rt.start(
            pipeline,
            f"Fix issue #{issue_number} from {REPO}",
            idempotency_key=idempotency_key,
        )
        print(f"Execution started: {handle.execution_id}")
        print(f"Idempotency key: {idempotency_key}")
        print(f"Monitor at: {SERVER_URL}/execution/{handle.execution_id}")

        # join() blocks until the pipeline completes (or times out).
        # Workers were already registered by start() under the execution's
        # domain — calling serve() would re-register them in the default
        # domain, causing stateful tool tasks to stay SCHEDULED.
        result = handle.join(timeout=SWARM_TIMEOUT)
        result.print_result()


if __name__ == "__main__":
    main()
```

## Dependencies

- Agentspan server running (`SERVER_URL`, default `http://localhost:6767`)
- GitHub credential stored: `agentspan credentials set GITHUB_TOKEN <token>` (name must match `GITHUB_CREDENTIAL` constant)
- `gh` CLI installed and authenticated
- DG skill cloned to `DG_SKILL_PATH`: `git clone https://github.com/v1r3n/dinesh-gilfoyle ~/.claude/skills/dg`
- Full build toolchain (Go, Java 21, Python 3.10+, Node.js, pnpm, uv)
- MCP testkit available on `MCP_TESTKIT_PORT` (default 3001, for e2e tests)
- No other Agentspan processes using the server port
- `ripgrep` (`rg`) installed for `grep_search`, `search_symbols`, `find_references`
