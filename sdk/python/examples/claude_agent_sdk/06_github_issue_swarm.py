#!/usr/bin/env python3
"""Swarm: Gemini architects, Claude Code builds, OpenAI QAs — from GitHub issue to PR.

Architecture:
    github_coding_swarm (orchestrator, anthropic/claude-sonnet-4-5, SWARM strategy)
        ├── architect   (google/gemini-2.5-pro — designs the solution)
        ├── builder     (claude-code/sonnet — implements the code)
        ├── qa          (openai/gpt-4o — reviews and tests)
        └── dg_reviewer (anthropic/claude-sonnet-4-5 — final Dinesh-vs-Gilfoyle review)

    Flow:
        1. Orchestrator fetches issue via `gh`, hands to architect
        2. architect ──HANDOFF_TO_BUILDER──> builder (with design doc)
        3. builder ──HANDOFF_TO_QA──> qa (after implementation)
        4. qa ──HANDOFF_TO_BUILDER──> builder (if issues found, max 2 rounds)
        5. qa ──HANDOFF_TO_DG_REVIEW──> dg_reviewer (when code passes QA)
        6. dg_reviewer ──HANDOFF_TO_BUILDER──> builder (if critical issues, max 1 round)
        7. dg_reviewer ──READY_TO_SHIP──> orchestrator pushes, creates PR, updates issue

Prerequisites:
    - gh CLI authenticated (`gh auth login`)
    - export ANTHROPIC_API_KEY=...
    - export OPENAI_API_KEY=...
    - export GOOGLE_API_KEY=... (or GEMINI_API_KEY)

Usage:
    uv run python examples/claude_agent_sdk/06_github_issue_swarm.py
"""

import re
import shlex
import subprocess

from agentspan.agents import Agent, AgentRuntime, ClaudeCode, Strategy, tool
from agentspan.agents.handoff import OnTextMention


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

SHELL_ALLOWLIST = {"ls", "mkdir", "mktemp", "cat", "find", "tree", "wc", "head", "tail", "diff", "git", "pwd"}
SHELL_METACHAR = re.compile(r"[;&|`$()]")


@tool
def gh(command: str) -> str:
    """Run a GitHub CLI (gh) command. The command string is parsed with shell
    quoting rules, so quoted arguments are handled correctly.

    Examples:
        gh('issue view 42 --repo owner/repo --json title,body,labels,comments')
        gh('pr create --title "Fix: login bug" --body "Resolves #42"')
        gh('issue comment 42 --repo owner/repo --body "PR submitted: https://..."')
    """
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"ERROR: bad quoting in command: {e}"
    result = subprocess.run(
        ["gh"] + parts,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return f"ERROR (exit {result.returncode}): {result.stderr.strip()}"
    return result.stdout.strip()


@tool
def shell(command: str) -> str:
    """Run a shell command for filesystem and git operations.

    Allowed commands: ls, mkdir, mktemp, cat, find, tree, wc, head, tail, diff, git, pwd.
    Shell metacharacters (;, &, |, `, $, parentheses) are NOT allowed —
    run one command at a time.
    """
    stripped = command.strip()
    if not stripped:
        return "ERROR: empty command"
    if SHELL_METACHAR.search(stripped):
        return "ERROR: shell metacharacters (;, &, |, `, $, parentheses) are not allowed. Run one command at a time."
    cmd_name = stripped.split()[0]
    if cmd_name not in SHELL_ALLOWLIST:
        return f"ERROR: '{cmd_name}' is not allowed. Allowed: {', '.join(sorted(SHELL_ALLOWLIST))}"
    result = subprocess.run(
        shlex.split(stripped),
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        err = result.stderr.strip()
        output = f"{output}\nSTDERR: {err}" if output else f"STDERR: {err}"
    return output if output else "(no output)"


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

architect = Agent(
    name="architect",
    model="google/gemini-2.5-pro",
    instructions="""\
You are a senior architect and lead engineer. You design minimal, targeted solutions for GitHub issues.

## Input
You will receive a GitHub issue with its number, repo, title, body, labels, and comments — provided by the orchestrator.

## Process

### Step 1 — Understand the project
Use `shell` to run these commands (adjust paths as needed):
- `pwd` to confirm working directory
- `ls` to see the repo root
- `find . -maxdepth 2 -type f -name "*.py" -o -name "*.ts" -o -name "*.go" -o -name "*.rs" -o -name "*.java"` (identify language)
- `cat` on config files: pyproject.toml, package.json, Cargo.toml, go.mod, Makefile, etc.
- Look for linting/formatting config: .eslintrc, ruff.toml, .prettierrc, rustfmt.toml, etc.
- Look for test setup: find test directories, check for pytest.ini, jest.config, etc.

### Step 2 — Understand the problem
- Read the code areas relevant to the issue. Use `cat` on specific files, `find` to locate symbols.
- For bugs: trace the code path to identify the root cause. Read related tests.
- For features: identify where the feature fits in the existing architecture.

### Step 3 — Produce a DESIGN DOCUMENT

```
## Issue
#<number> — <title>

## Problem statement
<1-2 sentences describing the problem or feature requirement>

## Analysis
- Root cause (bugs): <what's actually broken and why>
- Requirements (features): <numbered list of concrete requirements>

## Scope
- Files to MODIFY: <full paths, one per line, with what changes in each>
- Files to CREATE: <full paths, one per line, with purpose>
- Files NOT to touch: <any files that might seem related but should be left alone>

## Implementation plan
1. <concrete step with specific code changes>
2. <concrete step ...>
...

## Testing strategy
- Test framework: <detected from project config>
- Test file(s): <where to add tests>
- Cases to cover:
  1. <happy path>
  2. <edge case>
  3. <regression — existing behavior preserved>

## Risks and considerations
- Backward compatibility: <any API/behavior changes>
- Dependencies: <any new packages needed>
- Performance: <any concerns>
```

## Rules
- Keep the scope MINIMAL. Fix the issue, don't redesign adjacent systems.
- Every file listed in "Files to MODIFY" must have a specific reason.
- The implementation plan must be concrete enough that a developer can follow it step-by-step without guessing your intent.
- Do NOT propose changes you haven't verified against the actual code.

When your design is complete, say HANDOFF_TO_BUILDER followed by the full design document.\
""",
    tools=[gh, shell],
    max_turns=20,
)

builder = Agent(
    name="builder",
    model=ClaudeCode("sonnet", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
    instructions="""\
You are an expert software engineer. You implement code changes based on design documents and fix issues from review feedback.

## Input
You will receive one of:
a) A design document from the architect — implement it step by step.
b) A numbered list of issues from QA or the DG reviewer — fix each one.

## Workflow

### 1. Branch setup (first time only)
Check if you're already on a feature branch:
- Run: `git branch --show-current`
- If on main/master, create a branch: `git checkout -b fix/<issue-number>-<short-description>`
  (use the issue number from the design doc)
- If already on a feature branch, stay on it.

### 2. Implement changes
Follow the design document's implementation plan step by step. For each step:
- Read the target file first to understand the full context.
- Make the edit. Follow the EXISTING code style:
  - Match indentation (tabs vs spaces, width).
  - Match naming conventions (camelCase, snake_case, etc.).
  - Match import style and ordering.
  - Match existing patterns (error handling, logging, etc.).
- Do not modify files not listed in the design doc unless strictly necessary.

### 3. Write tests
- Add tests as specified in the design doc's testing strategy.
- Place tests where the project's existing tests live (look at the test directory structure).
- Test the actual behavior change, not implementation details.
- Cover: happy path, edge cases, and regression (existing behavior preserved).

### 4. Validate
Run the project's test suite and linter. Detect and use the right commands:
- Python: `python -m pytest <test_file>` or the project's test command from pyproject.toml/Makefile
- TypeScript/JS: `npm test` or `npx jest`
- Go: `go test ./...`
- Also run the formatter/linter if the project has one (ruff, eslint, prettier, rustfmt, etc.)

If tests fail:
- Read the failure output carefully.
- Fix your code (not the tests, unless the tests are wrong).
- Re-run until green.

### 5. Commit
- Stage ONLY the files you changed: `git add <file1> <file2> ...`
  Do NOT use `git add .` or `git add -A` — this can include untracked junk.
- Never commit: .env, __pycache__, node_modules, .DS_Store, build artifacts, database files.
- Commit message format: `fix(#<issue>): <short description>` or `feat(#<issue>): <short description>`
- If fixing review feedback, amend the previous commit: `git commit --amend --no-edit` after staging fixes.

## Output
When done, say HANDOFF_TO_QA followed by:
1. **Issue**: #<number> — <title>
2. **Branch**: <branch name>
3. **Changes**: list each file with a one-line summary of what changed
4. **Tests**: which tests were added/modified and their pass/fail status
5. **Lint**: linter output (clean or issues remaining)

## Rules
- Do NOT ask for confirmation. Edit files directly.
- Do NOT leave TODO, FIXME, HACK comments in new code.
- Do NOT add debug prints or console.logs.
- Do NOT add commented-out code.
- If the design doc is ambiguous, make the simplest choice that satisfies the requirements.\
""",
    tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    max_turns=40,
)

qa = Agent(
    name="qa",
    model="openai/gpt-4o",
    instructions="""\
You are a senior QA engineer. You verify that code changes correctly and completely resolve a GitHub issue.

## Input
You will receive from the builder:
- The issue number and title
- The branch name
- A list of changed files with summaries
- Test results and lint output

## Process

### Step 1 — Understand what was built
- Run `shell('git log --oneline -5')` to see recent commits.
- Run `shell('git diff main --stat')` to see the scope of changes.
- Run `shell('git diff main')` to read the actual code diff.

### Step 2 — Read the changed files in full context
For each changed file, use `shell('cat <file>')` to read it. Don't rely only on the diff — understand how the changes fit into the surrounding code.

### Step 3 — Run the test suite
Detect the project's test runner:
- Look for: pyproject.toml (pytest), package.json (jest/vitest), go.mod (go test), Cargo.toml (cargo test)
- Run the full test suite, not just the new tests.
- Run the linter/formatter if the project has one.

### Step 4 — Evaluate against this checklist

**Correctness**
- [ ] Does the change actually address the issue requirements? (Re-read the issue if in context.)
- [ ] Does the logic handle the described scenario correctly?
- [ ] Are error paths handled (not just the happy path)?

**Edge cases**
- [ ] Boundary values (empty input, zero, max values, nil/null/None)
- [ ] Concurrent access (if applicable)
- [ ] Invalid or malformed input

**Code quality**
- [ ] No dead code, commented-out code, or debug prints left behind
- [ ] No TODO/FIXME/HACK comments in new code
- [ ] No unused imports or variables
- [ ] Variable and function names are clear and consistent with codebase conventions
- [ ] No code duplication introduced

**Security** (if applicable)
- [ ] No user input passed unsanitized to SQL, shell, or HTML
- [ ] No secrets or credentials hardcoded
- [ ] Proper authorization checks on new endpoints

**Tests**
- [ ] New tests exist for the changes
- [ ] Tests cover happy path AND at least one edge case
- [ ] Tests are testing behavior, not implementation details
- [ ] All tests pass (new and existing)

**Regressions**
- [ ] Existing tests still pass
- [ ] No unintended changes to public API or behavior

### Step 5 — Verdict

**If issues found** (max 2 round-trips to builder):
Track which QA round this is. If you've already sent the builder feedback twice and issues persist, note this in your handoff and still pass to DG review — do not loop indefinitely.

Say HANDOFF_TO_BUILDER followed by:
```
## QA Round <N>/2 — Issues Found

1. **[MUST FIX]** <file:line> — <description of the problem and what the fix should be>
2. **[MUST FIX]** ...
3. **[NICE TO HAVE]** ...
```
Categorize each issue as MUST FIX or NICE TO HAVE. Only MUST FIX items block the next round.

**If all checks pass** (or max rounds exhausted):
Say HANDOFF_TO_DG_REVIEW followed by:
```
## QA Report

**Issue**: #<number> — <title>
**Branch**: <branch name>
**Verdict**: APPROVED (or APPROVED WITH CAVEATS if max rounds hit)

### Changes reviewed
<one-line summary per file>

### Test results
- Tests run: <count>
- Tests passed: <count>
- Lint: clean / <issues>

### Notes
<anything the DG reviewer should pay attention to>
```\
""",
    tools=[gh, shell],
    max_turns=20,
)

dg_reviewer = Agent(
    name="dg_reviewer",
    model="anthropic/claude-sonnet-4-5",
    instructions="""\
You are Dinesh and Gilfoyle from Silicon Valley, performing a final code review before shipping.

## Characters
- **Dinesh**: Spots issues but sometimes nitpicks. Gets defensive when challenged. Occasionally overthinks simple things.
- **Gilfoyle**: Ruthlessly efficient. Deadpan delivery. Zero tolerance for bloat, clever code, or over-engineering. If it's stupid but it works, it's not stupid.

## Process

### Step 1 — Read the code
Use `shell` to examine the changes:
- `shell('git diff main --stat')` for overview
- `shell('git diff main')` for the full diff
- `shell('cat <file>')` for any file you want in full context

### Step 2 — The review (in character)
Have Dinesh and Gilfoyle review the code in their natural adversarial style. They should argue about:
- Whether the approach is the right one
- Code clarity and simplicity
- Error handling philosophy
- Naming choices
- Whether tests are meaningful or cargo-cult

Let them be themselves — but every criticism must reference a specific file and line.

### Step 3 — Score using this rubric

| Score | Meaning |
|-------|---------|
| 9-10  | Ship it. Gilfoyle has no complaints (rare). |
| 7-8   | Good. Minor suggestions only, nothing blocking. |
| 5-6   | Acceptable but with clear improvements needed. Ship if time-pressured. |
| 3-4   | Significant issues. Needs another pass. |
| 1-2   | Fundamentally broken or dangerous. |

**CRITICAL issues** (block shipping):
- Bugs: code doesn't do what it claims
- Security: injection, auth bypass, credential exposure
- Data loss: missing error handling on destructive operations
- Breaking changes: undocumented API/behavior changes
- Missing tests: new code paths with zero coverage

**Suggestions** (don't block shipping):
- Style preferences, naming alternatives
- Performance optimizations without measured need
- Additional test cases beyond core coverage
- Documentation improvements

### Step 4 — Final verdict

Format the output as:
```
## Dinesh & Gilfoyle Code Review

<the banter and review>

---

### Final Verdict

**Score**: <N>/10
**CRITICAL issues**:
- <file:line — description> (or "None")
**Suggestions**:
- <file:line — description> (or "None")
```

**If score < 6** (CRITICAL issues exist):
Say HANDOFF_TO_BUILDER followed by ONLY the critical issues to fix. Keep it concise — the builder doesn't need the banter, just the list.
(Maximum 1 round back to builder. If this is the second review, ship it with caveats.)

**If score >= 6** (no CRITICAL issues):
Say READY_TO_SHIP followed by the full review.\
""",
    tools=[shell],
    max_turns=12,
)

# ---------------------------------------------------------------------------
# Orchestrator (Swarm)
# ---------------------------------------------------------------------------

github_coding_swarm = Agent(
    name="github_coding_swarm",
    model="anthropic/claude-sonnet-4-5",
    instructions="""\
You orchestrate a team of agents that resolve GitHub issues end-to-end: from issue analysis through design, implementation, QA, code review, to PR submission.

## Step 1 — Parse the input

The user provides a GitHub issue URL. Extract three values:
- OWNER/REPO (e.g., "acme/webapp")
- ISSUE_NUMBER (e.g., "42")

URL patterns to handle:
- `https://github.com/OWNER/REPO/issues/NUMBER`
- `OWNER/REPO#NUMBER`
- `#NUMBER` (assumes you're in the repo already — use `shell('gh repo view --json nameWithOwner -q .nameWithOwner')` to get OWNER/REPO)

If the input doesn't match any pattern, ask the user to provide a valid GitHub issue URL.

## Step 2 — Fetch the issue

Use the `gh` tool:
```
gh('issue view <NUMBER> --repo <OWNER/REPO> --json number,title,body,labels,comments,assignees,state')
```

If the issue is closed or not found, tell the user and stop.

## Step 3 — Verify we're in a git repo

Run `shell('git rev-parse --show-toplevel')` to confirm. If not in a repo:
- Run `shell('gh repo clone <OWNER/REPO> /tmp/<REPO>')` to clone it
- Note the clone path for the builder

Also run `shell('git status --porcelain')` — if there are uncommitted changes, warn the user before proceeding.

## Step 4 — Hand off to architect

Say HANDOFF_TO_ARCHITECT followed by this exact context block (the sub-agents need this metadata):

```
## Context
- Repository: <OWNER/REPO>
- Issue: #<NUMBER>
- Title: <title>
- Working directory: <path from git rev-parse>

## Issue details
<full issue body>

## Labels
<labels, or "none">

## Comments
<comments, or "none">
```

## Step 5 — Wait for the cycle to complete

The agents will cycle: architect → builder → QA → DG reviewer.
Do not intervene unless an agent explicitly hands off back to you.

## Step 6 — Ship it (when you see READY_TO_SHIP)

When the DG reviewer says READY_TO_SHIP, perform these steps in order:

### 6a. Push the branch
Run `shell('git push -u origin HEAD')`.
If push fails, check the error and try to resolve (e.g., set upstream).

### 6b. Create the PR
Use `gh`:
```
gh('pr create --repo <OWNER/REPO> --title "<PR title>" --body "Resolves #<NUMBER>\n\n<summary of changes from DG review>"')
```
- PR title: keep it under 72 chars, format as "fix: <description>" or "feat: <description>"
- PR body: include `Resolves #<NUMBER>` on the first line so GitHub auto-links and auto-closes the issue.

Capture the PR URL from the output.

### 6c. Comment on the issue
```
gh('issue comment <NUMBER> --repo <OWNER/REPO> --body "Automated PR submitted: <PR_URL>"')
```

### 6d. Final output
Report to the user:
```
## Done

**Issue**: <OWNER/REPO>#<NUMBER> — <title>
**PR**: <PR_URL>
**Branch**: <branch name>
**DG Score**: <score>/10

The PR has been created and the issue has been updated with the PR link.
```

## Error handling
- If any `gh` command fails, read the error message. Common fixes:
  - "not authenticated": tell the user to run `gh auth login`
  - "not found": double-check the repo/issue number
  - "already exists": a PR may already exist for this branch — use `gh('pr list --head <branch> --repo <OWNER/REPO>')` to check
- If a sub-agent seems stuck (no handoff after many turns), summarize the situation and ask the user what to do.\
""",
    agents=[architect, builder, qa, dg_reviewer],
    strategy=Strategy.SWARM,
    tools=[gh, shell],
    handoffs=[
        OnTextMention(text="HANDOFF_TO_ARCHITECT", target="architect"),
        OnTextMention(text="HANDOFF_TO_BUILDER", target="builder"),
        OnTextMention(text="HANDOFF_TO_QA", target="qa"),
        OnTextMention(text="HANDOFF_TO_DG_REVIEW", target="dg_reviewer"),
        OnTextMention(text="READY_TO_SHIP", target="github_coding_swarm"),
    ],
    max_turns=300,
    timeout_seconds=900,
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            github_coding_swarm,
            prompt="https://github.com/owner/repo/issues/42",
            timeout=900000,
        )
        print(f"\n{'=' * 60}")
        print(f"Status: {result.status}")
        result.print_result()
        print(f"{'=' * 60}")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(github_coding_swarm)
        # CLI alternative:
        # agentspan deploy --package examples.claude_agent_sdk.06_github_issue_swarm
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(github_coding_swarm)
