# PR Review Skill

An AgentSpan skill that automatically reviews pull requests against 8 criteria:
Logic Correctness, Code Quality, Security, PR Does What It Claims, Test Coverage,
Performance, Error Handling, and Observability.

**Token efficiency:** ~20–50k tokens per review (vs 400k+ for naive approaches) using a
single token-bounded bundle call that scores and selects the highest-risk files.

---

## How it works

1. **`get_pr_review_bundle`** — fetches PR metadata, the full changed-file list, and compact
   diffs for the top 4 highest-risk files (scored by change volume + file type).
2. **Optional `grep_in_file`** — one targeted search to verify a critical finding on a
   modified file (never on newly added files).
3. The agent writes a structured review immediately. No more tool calls.

If the repo contains a `.agentspan/pr-review-context.md` file, it is automatically injected
into the bundle so the agent reviews against repo-specific architecture, patterns, and gotchas
— not just generic rules.

---

## Part 1 — Using the skill locally

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | `python --version` |
| AgentSpan SDK | `pip install -e sdk/python` (from repo root) |
| AgentSpan server | Running at `http://localhost:6767` by default |
| `gh` CLI | [Install](https://cli.github.com/) — must be authenticated: `gh auth login` |
| GitHub token | Needs `repo` scope (read PR + diff) |
| LLM API key | Stored in AgentSpan server (Anthropic or OpenAI) |

### Step 1 — Install the SDK

```bash
# From the agentspan repo root
pip install -e sdk/python
```

### Step 2 — Store your GitHub token in AgentSpan

The skill calls `gh` CLI to fetch PR data. AgentSpan injects the token into the worker
environment at runtime.

```bash
agentspan credentials set GH_TOKEN <your-github-token>
```

The token needs at minimum: `repo` read access (public repos: `public_repo`).
To also post review comments later, add `pull-requests: write`.

### Step 3 — Run the review

```bash
cd sdk/python/examples/pr-review-skill

python run_review.py <pr_number> <owner/repo>
```

**Examples:**

```bash
# Review PR #42 in agentspan-ai/agentspan (repo not checked out locally)
python run_review.py 42 agentspan-ai/agentspan

# Review PR #5243 with the repo already checked out (enables grep_in_file)
python run_review.py 5243 orkes-io/orkes-saas /tmp/orkes-saas
```

> **Why pass `repo_path`?**  
> The optional grep tool reads files from disk. If you pass a checked-out repo path,
> the agent can verify critical findings by grepping source files. Without it, verification
> is skipped and the agent works from the diff only.

### Environment variable overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767` | AgentSpan server URL |
| `AGENTSPAN_LLM_MODEL` | `anthropic/claude-sonnet-4-6` | Model to use for the review |
| `AGENTSPAN_REVIEW_MAX_TURNS` | `6` | Max LLM turns per review |
| `AGENTSPAN_REVIEW_MAX_TOKENS` | `3000` | Max completion tokens per LLM response |

```bash
# Use a different model
AGENTSPAN_LLM_MODEL=openai/gpt-4o python run_review.py 42 owner/repo

# Use a remote AgentSpan server
AGENTSPAN_SERVER_URL=https://my-agentspan.example.com python run_review.py 42 owner/repo
```

### Adding a repo context file (recommended)

For the agent to review against your repo's specific architecture and patterns, add a context
file to the repo being reviewed:

```bash
mkdir -p <your-repo>/.agentspan
cp example-repo-context.md <your-repo>/.agentspan/pr-review-context.md
# Edit the file — describe your architecture, patterns to enforce, known gotchas
```

Keep it under 3,000 characters. See `example-repo-context.md` for the template.

### Running the tests

```bash
cd sdk/python/examples/pr-review-skill
pytest tests/ -v
```

54 unit tests covering all script tools and skill loading. No server or LLM needed.

---

## Part 2 — Integrating into a CI/CD pipeline

The skill ships with a ready-to-use GitHub Actions workflow at
`.github/workflows/pr-review.yml`. Follow these steps to wire it up for any repo.

### Step 1 — Add repository secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `AGENTSPAN_SERVER_URL` | URL of your running AgentSpan server, e.g. `https://agentspan.mycompany.com` |
| `GH_TOKEN` | GitHub token with `repo` read + `pull-requests: write` permission |
| `AGENTSPAN_LLM_MODEL` | *(optional)* Model override, e.g. `openai/gpt-4o`. Defaults to `anthropic/claude-sonnet-4-6` |

> **Important:** `GH_TOKEN` must also be stored server-side so the AgentSpan worker can
> call the `gh` CLI during execution:
> ```bash
> agentspan credentials set GH_TOKEN <same-token>
> ```

### Step 2 — Copy the workflow file

If you're integrating into a repo other than `agentspan-ai/agentspan`, copy the workflow:

```bash
mkdir -p <your-repo>/.github/workflows
cp .github/workflows/pr-review.yml <your-repo>/.github/workflows/pr-review.yml
```

Then update the `run` step to point to wherever `run_review.py` lives. If you've installed
`agentspan` as a package you can also call it directly — adjust as needed.

The workflow triggers on:
```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
```

This covers new PRs, pushes to an existing PR branch, and reopened PRs.

### Step 3 — Add a repo context file

Commit `.agentspan/pr-review-context.md` to the root of the repo being reviewed. This is
what makes the review repo-aware — without it, the agent applies only generic coding
standards.

```bash
# In your target repo
mkdir -p .agentspan
# Create context file — describe architecture, patterns, gotchas (see template below)
vim .agentspan/pr-review-context.md
git add .agentspan/pr-review-context.md
git commit -m "Add PR review context for AI reviewer"
git push
```

**Template structure** (keep under 3,000 chars):

```markdown
# PR Review Context — <repo name>

## Architecture
<layers and module structure>

## Patterns to enforce
- <pattern 1>
- <pattern 2>

## Known gotchas
- <thing that has caused real bugs before>

## Testing conventions
<where tests live, what coverage is expected>

## Out of scope for AI review
<generated files, frontend, etc.>
```

### Step 4 — Enable posting review comments *(when ready)*

By default the skill outputs the review to CI logs only. To have it post comments directly
on the PR:

1. Move `post_review_comment.py` from `disabled_tools/` back to `scripts/`:
   ```bash
   mv disabled_tools/post_review_comment.py scripts/
   ```

2. Uncomment the `post_review_comment` row in the Tool Reference table in `SKILL.md`.

3. Remove the `<!-- POSTING DISABLED -->` comment blocks in `SKILL.md` so the agent
   knows to call the tool.

### What the pipeline looks like end-to-end

```
Developer opens / updates a PR
        ↓
GitHub Actions triggers (opened, synchronize, reopened)
        ↓
GHA runner checks out the full repo at the PR head commit
        ↓
python run_review.py <pr_number> <repo> .
        ↓
AgentSpan loads the pr-reviewer skill:
  • SKILL.md  →  agent instructions
  • scripts/  →  callable tools (registered as Conductor workers)
  • params injected: repo=owner/repo, repo_path=<checkout path>
        ↓
Agent executes (hard cap: 2 tool calls, 6 turns):
  Call 1 — get_pr_review_bundle repo pr_number repo_path
    • Fetches PR metadata, changed file list, compact diffs
    • If .agentspan/pr-review-context.md exists → injected as "## Repo Context"
  Call 2 (optional) — grep_in_file
    • Only to verify a CRITICAL finding on a MODIFIED file
        ↓
Agent writes structured review:
  Logic / Quality / Security / Scope / Tests / Performance / Errors / Observability
        ↓
[Current]  Review printed to GHA logs
[Enabled]  post_review_comment posts it as a PR comment on GitHub
```

### Supported models

Any model available in your AgentSpan server works. Tested with:

| Model | Notes |
|-------|-------|
| `anthropic/claude-sonnet-4-6` | Default. Best balance of quality and cost. |
| `anthropic/claude-opus-4-5` | Higher quality, ~3× more expensive. |
| `openai/gpt-4o` | Good alternative if Anthropic unavailable. |
| `openai/gpt-4o-mini` | Fast and cheap; suitable for small PRs. |
