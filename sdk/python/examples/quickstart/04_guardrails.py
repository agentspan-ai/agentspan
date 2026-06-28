#!/usr/bin/env python3
"""Guardrails — block responses containing email addresses."""

from conductor.ai.agents import Agent, AgentRuntime, RegexGuardrail

agent = Agent(
    name="safe_bot",
    model="anthropic/claude-sonnet-4-6",
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

prompt = "How do I contact support?"

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(agent, prompt)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.quickstart.04_guardrails
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(agent)
