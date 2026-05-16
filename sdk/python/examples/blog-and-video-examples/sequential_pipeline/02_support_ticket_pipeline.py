import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

"""Support Ticket Pipeline — Classifier >> Responder >> Escalation Checker

Takes a customer support ticket and produces a classification,
a draft response, and an escalation recommendation.

Demonstrates:
    - Sequential strategy with the >> operator
    - AgentRuntime for durable execution
    - Three specialist agents chained together

Setup:
    pip install agentspan
    agentspan server start
    python 02_support_ticket_pipeline.py
"""

from agentspan.agents import Agent, AgentRuntime


# ── Agents ────────────────────────────────────────────────────────

classifier = Agent(
    name="classifier",
    model="openai/gpt-4o",
    instructions=(
        "You are a support ticket classifier. Given a customer support "
        "ticket, produce a structured classification:\n"
        "- Customer: name and company (from the ticket)\n"
        "- Priority: P0 (outage), P1 (critical), P2 (degraded), P3 (minor)\n"
        "- Category: performance, bug, feature-request, billing, onboarding\n"
        "- Product area: which part of the product is affected\n"
        "- Customer sentiment: frustrated, neutral, positive\n"
        "- Key facts: bullet list of the specific issues mentioned\n\n"
        "Be concise and structured. Do not guess — only classify based "
        "on what the customer actually wrote."
    ),
)

responder = Agent(
    name="responder",
    model="openai/gpt-4o",
    instructions=(
        "You are a senior support engineer drafting a response to a "
        "customer. Given the original ticket and the classification, "
        "write a professional reply that:\n"
        "- Acknowledges their issue and urgency\n"
        "- Confirms what you understand the problem to be\n"
        "- Asks specific follow-up questions if anything is unclear\n"
        "- Sets expectations for next steps and timeline\n\n"
        "Be empathetic but not generic. Reference the specific details "
        "they mentioned. Keep it under 200 words."
    ),
)

escalation_checker = Agent(
    name="escalation_checker",
    model="openai/gpt-4o",
    instructions=(
        "You are a support team lead reviewing a ticket for escalation. "
        "Given the original ticket, classification, and draft response, "
        "decide:\n"
        "1. Should this be escalated to engineering? (yes/no)\n"
        "2. Why or why not? (one sentence)\n"
        "3. If yes, write an internal note for the engineering team — "
        "include the customer impact, urgency, and what to investigate.\n"
        "4. If no, confirm the support team can handle it and why.\n\n"
        "Be direct. Engineers are busy — give them only what they need."
    ),
)

# ── Pipeline ──────────────────────────────────────────────────────

pipeline = classifier >> responder >> escalation_checker


# ── Sample Input ─────────────────────────────────────────────────

SAMPLE_TICKET = """
Subject: URGENT — API extremely slow, blocking our monthly batch processing

From: David Park <david.park@acmelogistics.com>
Company: Acme Logistics (Enterprise plan)
Environment: Production (US-East)
Submitted: Monday 3:15 PM EST

Hi Support Team,

We're in the middle of our monthly batch processing and we're completely
stuck. This is our most critical operational window of the month.

Here's what's happening:

1. Our batch API calls are going through, but response times have gone
   from ~200ms to 15-30 SECONDS per call. We have 50,000+ items to
   process and at this rate it will take days instead of hours.

2. The web dashboard is nearly unusable — pages take 45+ seconds to
   load, and we keep getting timeout errors when trying to view our
   job status.

3. We tried splitting our batch into smaller chunks thinking it was a
   rate limit issue, but even individual API calls are slow.

4. Nothing changed on our end — same code, same volume as last month
   when everything ran fine in under 2 hours.

We have downstream systems waiting on this data and our SLA with our
own customers is at risk. Three of our team members have been stuck
on this since 1 PM and can't do anything else until it's resolved.

Can someone please look into this ASAP? We need to know:
- Is there a known issue on your end?
- Is there anything we can do to work around it?
- When can we expect normal performance?

Thanks,
David Park
Senior Platform Engineer, Acme Logistics
"""


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("Starting support ticket pipeline...\n")
        result = runtime.run(pipeline, SAMPLE_TICKET)
        result.print_result()
