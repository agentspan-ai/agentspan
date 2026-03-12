# Validation Design

## Architecture

Two decoupled scripts separate execution from evaluation.

### Data Flow

```mermaid
flowchart LR
    subgraph Inputs
        EX["examples/*.py<br/>examples/openai/*.py<br/>examples/adk/*.py"]
        ENV_MODEL["AGENT_LLM_MODEL<br/>(set per subprocess)"]
        SERVER["Conductor Server<br/>(handles LLM calls)"]
    end

    subgraph "Process 1: run_examples.py"
        DISC[Discover examples] --> FILTER[Filter by --group]
        FILTER --> RUN["Run each example<br/>× N models in parallel"]
        RUN --> PARSE[Parse stdout/stderr]
        PARSE --> WRITE_CSV[Write execution CSV]
        PARSE --> WRITE_RAW[Write raw outputs]
    end

    subgraph "validation/output/run_*/"
        CSV["results.csv"]
        RAW["outputs/<br/>*_openai.txt<br/>*_anthropic.txt<br/>*_adk.txt"]
        REPORT["report.md"]
    end

    subgraph "Process 2: judge_results.py"
        READ_CSV[Read CSV + raw outputs] --> EXTRACT[Extract prompts<br/>from example source]
        EXTRACT --> JUDGE_IND["Individual judge<br/>(score each completed model 1-5)"]
        JUDGE_IND --> CONFIDENCE[Compute confidence]
        CONFIDENCE --> UPDATE[Update CSV + write report]
    end

    EX --> DISC
    ENV_MODEL --> RUN
    SERVER --> RUN
    WRITE_CSV --> CSV
    WRITE_RAW --> RAW
    CSV --> READ_CSV
    RAW --> READ_CSV
    UPDATE --> CSV
    UPDATE --> REPORT
```

**Why two scripts?**
- Re-run judge without re-running expensive examples
- Try different judge models/prompts without re-executing
- Process 1 needs no API key — server handles LLM calls
- Debug judge independently

## Per-Example Execution

```
for each example:
    ┌──────────────────────────────────────────┐
    │ ThreadPoolExecutor(max_workers=len(MODELS))│
    │                                          │
    │  Thread 1: run with openai/gpt-4o        │
    │  Thread 2: run with anthropic/claude-...  │
    │  Thread 3: run with google_gemini/gemini  │
    │                                          │
    │  All run simultaneously                  │
    └────────────┬─────────────────────────────┘
                 │
                 ▼
    Parse stdout → extract workflow_id, tool_calls, tokens, output
    Detect errors → "workflow FAILED", tracebacks, non-zero exit
    Compute match (PASS/FAIL/PARTIAL) + preliminary confidence
    Write CSV row + raw output files
```

The `AGENT_LLM_MODEL` env var is set per-subprocess, overriding whatever the example's `settings.py` would normally read from `.env`.

## Example Discovery

```mermaid
flowchart TD
    SCAN["Scan examples/<br/>+ examples/openai/<br/>+ examples/adk/"] --> GROUP{"--group flag?"}
    GROUP -->|Yes| FILTER_GROUP["Filter to group stems<br/>(from .env)"]
    GROUP -->|No| ALL["All examples"]

    FILTER_GROUP --> PREFIX{"Matches prefix filter?"}
    ALL --> PREFIX

    PREFIX -->|Yes| DEP{"Subdir dep<br/>available?"}
    PREFIX -->|No filter| DEP
    PREFIX -->|No match| EXCLUDED["Excluded by filter"]

    DEP -->|"Yes / main dir"| RUN["Run"]
    DEP -->|"No (skip silently)"| SKIPPED["Skipped"]

    style EXCLUDED fill:#ffe
    style SKIPPED fill:#ffe
    style RUN fill:#efe
```

### HITL stdin map

| Example | Stdin | Action |
|---------|-------|--------|
| `02_tools` | `y` | Approve send_email |
| `09_human_in_the_loop` | `y` | Approve transfer_funds |
| `09b_hitl_with_feedback` | `a` | Approve article publication |
| `09c_hitl_streaming` | `y` | Approve delete_service_data |

## Output Parsing

Extracts from stdout (produced by `AgentResult.print_result()`):

| Field | Regex / Method |
|-------|---------------|
| Workflow ID | `Workflow ID: (\S+)` |
| Tool calls | `Tool calls: (\d+)` |
| Tokens | `Tokens: (\d+) total \((\d+) prompt, (\d+) completion\)` |
| Agent output | Text between `╘═+╛` banner and next metadata line |
| Errors | `workflow FAILED` in stdout/stderr, tracebacks, non-zero exit |

### Status determination

| Condition | Status |
|-----------|--------|
| `workflow FAILED` in output | FAILED |
| exit_code == 0 and no errors | COMPLETED |
| Subprocess timed out | TIMEOUT |
| Non-zero exit code | FAILED |
| Other error detected | ERROR |

## LLM Judge

One judge call per completed model — scores each output against the original prompt on a 1-5 scale:

| Score | Meaning |
|-------|---------|
| 1 | Completely wrong, irrelevant, or empty |
| 2 | Partially relevant but mostly incorrect |
| 3 | Relevant but missing key elements |
| 4 | Good, addresses the task well |
| 5 | Excellent, fully addresses the task |

Models that did not complete (FAILED, TIMEOUT, ERROR) are skipped by the judge.

### Prompt extraction

Parses each example's source to find the prompt:
```python
# Regex: (?:run|stream)\s*\(\s*\w+\s*,\s*"([^"]+)"
runtime.run(agent, "Say hello and tell me a fun fact")  →  extracted
```

### Cost

~$0.001/model/example (1 call to `gpt-4o-mini` per completed model).

## Confidence Levels

Confidence measures **execution reliability**, not output quality:

| Level | Criteria |
|-------|----------|
| **HIGH** | All COMPLETED, all judge scores >= 4 |
| **MEDIUM** | All COMPLETED, but a score is 3 or tool_calls differ |
| **LOW** | Some failed/timed out, or any score <= 2 |
| **N/A** | All failed or skipped |

### Confidence Decision Matrix

```mermaid
flowchart TD
    START["All models ran"] --> ALL_COMPLETE{"All COMPLETED?"}

    ALL_COMPLETE -->|"None completed"| NA["N/A"]
    ALL_COMPLETE -->|"Some failed/timed out"| LOW1["LOW"]
    ALL_COMPLETE -->|"All completed"| JUDGE["Run judge scoring"]

    JUDGE --> SCORE_CHECK{"Any judge<br/>score <= 2?"}
    SCORE_CHECK -->|Yes| LOW2["LOW<br/>(poor output quality)"]
    SCORE_CHECK -->|No| HIGH_CHECK{"All scores >= 4?"}

    HIGH_CHECK -->|No| MEDIUM1["MEDIUM<br/>(a score is 3)"]
    HIGH_CHECK -->|Yes| TOOLS{"tool_calls match<br/>across providers?"}

    TOOLS -->|No| MEDIUM2["MEDIUM<br/>(different tool usage)"]
    TOOLS -->|Yes| HIGH["HIGH"]

    style NA fill:#eee
    style LOW1 fill:#fee
    style LOW2 fill:#fee
    style MEDIUM1 fill:#ffe
    style MEDIUM2 fill:#ffe
    style HIGH fill:#efe
```

## Output Files

All output goes to `validation/output/` (gitignored). Each run gets its own directory:

```
validation/output/
├── run_2026-03-12_12-29-35_d766/
│   ├── results.csv
│   ├── report.md          ← added by judge_results.py
│   ├── meta.json           ← timing metadata
│   └── outputs/
│       ├── 01_basic_agent_openai.txt
│       ├── 01_basic_agent_anthropic.txt
│       ├── 01_basic_agent_adk.txt
│       ├── openai_01_basic_agent_openai.txt
│       └── ...
└── ...
```

Directory format: `run_{YYYY-MM-DD}_{HH-MM-SS}_{run_id}/` where run_id = first 4 chars of UUID4.
