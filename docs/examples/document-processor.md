---
title: Batch document processor
description: Process thousands of documents with crash recovery and progress tracking
---

# Build a Batch Document Processor

Use this example to review a large set of contracts in parallel. Each contract is processed by its own agent run — extract key terms, identify risks, and save a structured review to disk. If the process crashes mid-run, restart it and it picks up exactly where it left off.

## How it works

For each contract:

1. Agent reads the contract text
2. Extracts parties, dates, payment terms, liability, and IP ownership
3. Identifies specific risks and assigns a risk level
4. Saves a structured JSON review to disk

Contracts run in parallel on the server. Already-completed ones are skipped on restart.

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Environment variables set:
    
    ```bash
    export AGENTSPAN_SERVER_URL=http://localhost:6767/api
    export ANTHROPIC_API_KEY=<YOUR-KEY>
    ```

## Full code

!!! note
    The `CONTRACTS` dict uses hardcoded text for demonstration. Replace it with file reads or database queries for production use.

```python
from agentspan.agents import Agent, tool, start
from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum
import json
import re

# ── Output schema ─────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"

class ContractReview(BaseModel):
    file: str
    contract_type: str
    parties: list[str]
    effective_date: str | None
    expiry_date: str | None
    auto_renewal: bool
    payment_terms: str | None
    liability_cap: str | None
    ip_ownership: str | None
    risks: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    action_required: str | None

# ── Contracts ─────────────────────────────────────────────────────────────────

CONTRACTS = {
    "acme-nda.txt": """
MUTUAL NON-DISCLOSURE AGREEMENT
Parties: Acme Corp and Beta Inc.
Effective Date: 2026-01-15
Term: 3 years. Auto-renews annually unless terminated with 30 days notice.
Liability: Each party's liability is capped at $50,000.
IP: All shared information remains the property of the disclosing party.
Governing Law: State of California.
""",
    "vendor-msa.txt": """
MASTER SERVICE AGREEMENT
Parties: TechCorp Ltd (Vendor) and GlobalCo Inc (Client)
Effective Date: 2026-02-01
Term: 1 year. No auto-renewal.
Payment: Net 60 days. Late fees of 5% per month on overdue balances.
Liability: Vendor liability capped at 1x monthly fees paid.
IP: All work product is owned exclusively by Vendor unless explicitly transferred.
Termination: Either party may terminate with 90 days notice.
""",
    "saas-agreement.txt": """
SOFTWARE AS A SERVICE AGREEMENT
Parties: CloudSoft Inc (Provider) and StartupXYZ (Customer)
Effective Date: 2026-03-01
Expiry: 2027-03-01. Auto-renews for successive 1-year terms.
Payment: $5,000/month, billed annually in advance. No refunds.
Liability: Provider liability capped at $500. No consequential damages.
IP: Provider retains all rights to the software and any improvements.
Data: Provider may use anonymized customer data for product improvement.
Governing Law: Delaware.
""",
}

# ── Tool ──────────────────────────────────────────────────────────────────────

@tool
def read_contract(filename: str) -> str:
    """Read a contract by filename and return its text content."""
    if filename not in CONTRACTS:
        return f"Error: contract '{filename}' not found."
    return CONTRACTS[filename]

# ── Agent ─────────────────────────────────────────────────────────────────────

contract_reviewer = Agent(
    name="contract_reviewer",
    model="anthropic/claude-sonnet-4-6",
    output_type=ContractReview,
    tools=[read_contract],
    instructions="""You are a paralegal specializing in technology contracts.

For each contract:
1. Read the full text using read_contract
2. Extract all required fields into ContractReview
3. List specific risks (unusual clauses, missing protections, unfavorable terms)
4. Assign a risk level: low (standard terms), medium (some concerns), high (legal review needed)

Be precise about dates and monetary amounts.
If a field is not present in the contract, use null — do not guess.""",
)

# ── Output parsing ────────────────────────────────────────────────────────────

def extract_review(raw_output: dict) -> dict | None:
    text = raw_output.get("result", "")
    if isinstance(text, dict):
        return text
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return None

# ── Batch runner ──────────────────────────────────────────────────────────────

def process_contracts(max_concurrent: int = 3):
    filenames = list(CONTRACTS.keys())
    print(f"Found {len(filenames)} contracts to process")

    # Skip already-completed (idempotent restarts)
    reviews_dir = Path("reviews")
    completed = {p.stem for p in reviews_dir.glob("*.json")} if reviews_dir.exists() else set()
    pending = [f for f in filenames if Path(f).stem not in completed]
    print(f"{len(completed)} already done, {len(pending)} remaining\n")

    for i in range(0, len(pending), max_concurrent):
        batch = pending[i:i + max_concurrent]

        handles = {
            filename: start(contract_reviewer, filename)
            for filename in batch
        }

        for filename, handle in handles.items():
            try:
                result = handle.stream().get_result()
                review = extract_review(result.output)

                if review is None:
                    print(f"  ✗ {filename}  could not parse output")
                    continue

                reviews_dir.mkdir(exist_ok=True)
                out = reviews_dir / (Path(filename).stem + ".json")
                out.write_text(json.dumps(review, indent=2))

                print(f"  ✓ {filename}  [risk: {review.get('risk_level', '?')}]")
            except Exception as e:
                print(f"  ✗ {filename}  FAILED: {e}")

if __name__ == "__main__":
    process_contracts()
```

## Run it

Save the file as `batch_processor.py`, and run it:

```bash
python batch_processor.py
```

Output:

```
Found 3 contracts to process
0 already done, 3 remaining

  ✓ acme-nda.txt  [risk: medium]
  ✓ vendor-msa.txt  [risk: high]
  ✓ saas-agreement.txt  [risk: high]
```

Reviews are saved to `reviews/` as JSON files. Run it again — already-completed contracts are skipped:

```
Found 3 contracts to process
3 already done, 0 remaining
```

## What this demonstrates

**Parallel execution**: `start()` launches each contract as a separate workflow. All contracts in a batch run concurrently on the server without blocking each other.

**Idempotent restarts**: Before each run, completed reviews are checked in `reviews/`. If the process crashes or is killed, restart it and it picks up exactly where it left off. Nothing is re-processed.

**Structured output**: `output_type=ContractReview` enforces a typed schema. Every review has the same fields regardless of contract length or format.

**Per-contract history**: Every execution is stored on the server with its full trace. Open `http://localhost:6767` to inspect any run, see exactly what the agent read, and audit the reasoning.

## Example modifications

### Load from real files

Replace the `CONTRACTS` dict and `read_contract` tool to load from disk:

```python
@tool
def read_contract(filename: str) -> str:
    """Read a contract file and return its text content."""
    return Path(filename).read_text(encoding="utf-8")

def process_contracts(contract_dir: str = "./contracts", max_concurrent: int = 10):
    paths = list(Path(contract_dir).glob("**/*.txt")) + \
            list(Path(contract_dir).glob("**/*.pdf"))
    filenames = [str(p) for p in paths]
    ...
```

### Resume a failed contract

Find failed executions via CLI:

```bash
agentspan agent execution --name contract_reviewer --status FAILED --since 1d
```

Or open `http://localhost:6767` to browse executions visually. Re-run any failed contract by passing the same filename to `start()` again — the idempotent skip logic ensures already-completed contracts are never re-processed.

### Stream progress per contract

Use `stream()` instead of `start()` to log each tool call as it happens:

```python
from agentspan.agents import stream

for event in stream(contract_reviewer, filename):
    if event.type == "tool_call":
        print(f"  → {filename}: {event.tool_name}")
    elif event.type == "done":
        print(f"  ✓ {filename}: complete")
```

### Flag high-risk contracts

After saving each review, route high-risk ones to a separate queue:

```python
if review.get("risk_level") == "high":
    flag_for_legal_review(filename, review.get("action_required"))
```

### Increase concurrency

For large batches, increase `max_concurrent` to process more contracts at once:

```python
process_contracts(max_concurrent=20)
```

The server handles the parallelism — each contract runs as an independent workflow.
