#!/usr/bin/env python3
"""Guardrails — block responses containing email addresses."""

from agentspan.agents import Agent, AgentRuntime, RegexGuardrail

agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o-mini",
    instructions="Answer questions. Never include email addresses in your response.",
    guardrails=[
        RegexGuardrail(
            name="no_emails",
            patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
            message="Remove email addresses from your response.",
            on_fail="retry",
        ),
    ],
)

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(agent, "How do I contact support?")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.04_guardrails
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(agent)
