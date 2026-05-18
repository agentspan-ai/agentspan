# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Coding Agent with QA Tester — write, review, and fix code.

Demonstrates:
    - Swarm orchestration: agents decide when to hand off
    - Coder writes code, transfers to QA when ready
    - QA tester reviews and runs tests, transfers back if bugs found
    - Natural back-and-forth until QA approves the code
    - Extended thinking for step-by-step reasoning

Flow (swarm — LLM-driven handoffs):
    1. coder writes the solution, executes it, transfers to qa_tester
    2. qa_tester reviews code, writes and runs tests
       - if bugs found → transfers back to coder
       - if all tests pass → done
    3. coder fixes issues, re-runs, transfers to qa_tester
    4. qa_tester verifies fixes → done

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy

# ── QA Tester: reviews code and runs tests ───────────────────────────

qa_tester = Agent(
    name="qa_tester",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a meticulous QA engineer. Review the code written by the "
        "coder for correctness, edge cases, and bugs. Write and execute test "
        "cases that cover: normal inputs, edge cases (empty input, zero, "
        "negative numbers, large values), and boundary conditions.\n\n"
        "If you find bugs, clearly describe them and transfer back to coder "
        "for fixes. If all tests pass, confirm the code is correct and "
        "provide your final QA report. Do NOT transfer back if all tests pass."
    ),
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── Coder: writes code, hands off to QA for review ──────────────────

coder = Agent(
    name="coder",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are an expert Python developer. Write clean, well-structured "
        "Python code to solve the given problem. Always execute your code to "
        "verify it works. Always include ALL necessary code in each execution "
        "— every code block runs in an isolated environment.\n\n"
        "Once your code runs successfully, transfer to qa_tester for review. "
        "If the qa_tester reports bugs, fix them, re-run, and transfer back "
        "to qa_tester for verification."
    ),
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
    # Swarm: coder starts, can hand off to qa_tester and back
    agents=[qa_tester],
    strategy=Strategy.SWARM,
    max_turns=8,
    timeout_seconds=300,
)

# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = (
        "Write a Python function that finds all prime numbers up to N using "
        "the Sieve of Eratosthenes. Then use it to find all primes up to 100 "
        "and calculate their sum."
    )

    print("=" * 60)
    print("  Coding Agent + QA Tester (Swarm)")
    print("  coder ↔ qa_tester (LLM-driven handoffs)")
    print("=" * 60)
    print(f"\nPrompt: {prompt}\n")


    with AgentRuntime() as runtime:
        result = runtime.run(coder, prompt)

        # Swarm output is a dict keyed by agent name
        output = result.output
        if isinstance(output, dict):
            for agent_name, text in output.items():
                print(f"\n{'─' * 60}")
                print(f"  [{agent_name}]")
                print(f"{'─' * 60}")
                print(text)
        else:
            print(output)

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coder)
        # CLI alternative:
        # agentspan deploy --package examples.59_coding_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coder)

