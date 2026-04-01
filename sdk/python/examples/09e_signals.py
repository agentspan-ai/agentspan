# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Signals — Send context to a running agent mid-execution.

Demonstrates:
- Starting a long-running agent
- Sending a normal signal to redirect it
- Sending an urgent signal for faster pickup
- Polling for signal disposition

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
    - OPENAI_API_KEY set
"""

import time
from agentspan.agents import Agent, AgentRuntime
from settings import settings

agent = Agent(
    name="researcher",
    model=settings.llm_model,
    instructions="You are a research assistant. Research topics thoroughly before answering.",
    signal_mode="evaluate",  # LLM will accept or reject signals
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.09e_signals
        runtime.deploy(agent)

        # Start a long-running research task
        handle = runtime.start(agent, "Research the history of quantum computing in detail.")
        print(f"Started: {handle.execution_id}")

        # Wait a moment for the agent to start working
        time.sleep(3)

        # Send a normal signal to redirect focus
        receipt = handle.signal(
            message="Focus only on developments after 2015. Skip early history.",
            priority="normal",
            sender="user",
        )
        print(f"Signal queued: {receipt.signal_id}")

        # Send an urgent signal (picked up sooner — after current task, not full loop)
        urgent_receipt = handle.signal(
            message="Budget constraint: wrap up in the next 2 paragraphs.",
            priority="urgent",
            sender="manager",
        )
        print(f"Urgent signal queued: {urgent_receipt.signal_id}")

        # Stream events to see signals being accepted/rejected
        for event in handle.stream():
            print(f"  [{event.type}] {event.data}")
            if event.type in ("signal_accepted", "signal_rejected"):
                print(f"    → Signal {(event.data or {}).get('signalId')} was {event.type}")

        result = runtime.get_result(handle.execution_id)
        result.print_result()

        # Check final signal disposition
        status = runtime.get_signal_status(receipt.signal_id)
        print(f"Signal disposition: {status.disposition}")
