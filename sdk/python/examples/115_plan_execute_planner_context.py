# Copyright (c) 2025 Agentspan
# Licensed under the MIT License.

"""115 — Plan-Execute with ``planner_context``: customer onboarding plan.

The PAE planner's static ``instructions`` string is fine for *how* to
emit a plan, but it's a poor fit for the domain-specific rules a
real plan depends on — tier thresholds, KYC step ordering, region
exceptions, escalation rules. Those live in docs that change weekly,
not in code.

``planner_context`` solves this: a list of text snippets and/or URLs
appended to the planner's user prompt as a ``## Reference Context``
block on every planner invocation. URLs are fetched dynamically — no
compile-time fetch, no cache — so a Confluence edit lands on the next
plan run with zero redeploy.

Example shape::

    Agent(
        strategy=Strategy.PLAN_EXECUTE,
        tools=[...],
        planner=...,
        planner_context=[
            # 1) Inline rules — short, stable, never changes mid-quarter
            "Onboarding has 3 phases: KYC, account_setup, welcome_email.",
            "Tier 'enterprise' customers also require a kickoff_call step.",

            # 2) Live doc — fetched per planner invocation, edits go live
            Context(
                url="https://confluence.example.com/onboarding/rules",
                headers={
                    # Same ${CRED} placeholder shape as ToolConfig.headers —
                    # one credential pipeline, server escapes ${} → #{} and
                    # the runtime resolver fills the value at request time.
                    "Authorization": "Bearer ${CONFLUENCE_TOKEN}",
                },
                required=True,
                max_bytes=8192,
            ),
        ],
    )

This example runs WITHOUT a real Confluence backend — the
``planner_context`` is text-only by default so you can run it against
a stock server without setting up credentials. The Context(url=…)
example above is commented in the code below as a reference for how
real installations wire credentialed docs.

What to look for in the run:
  * Workflow status reaches a terminal state.
  * The compiled inner plan_exec contains one task per declared
    onboarding tool — ``validate_kyc``, ``create_account``,
    ``send_welcome_email``.
  * The planner's prompt contains the ``## Reference Context``
    block. The compiled workflow's ``_ctx_build`` INLINE produces
    the markdown that gets templated into the planner's user message.

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
"""

from __future__ import annotations

import os

from conductor.ai.agents import Agent, AgentRuntime, Context, Strategy, tool

# ── Onboarding tools (deterministic, no external calls) ────────────────


@tool
def validate_kyc(customer_id: str, doc_type: str) -> dict:
    """Validate a single KYC document. Phase 1 of onboarding."""
    return {
        "customer_id": customer_id,
        "doc_type": doc_type,
        "status": "verified",
    }


@tool
def create_account(customer_id: str, tier: str) -> dict:
    """Provision the customer's account record. Phase 2 of onboarding."""
    return {
        "customer_id": customer_id,
        "tier": tier,
        "account_id": f"acct_{customer_id}_{tier}",
        "status": "active",
    }


@tool
def send_welcome_email(customer_id: str, account_id: str) -> dict:
    """Send the tier-appropriate welcome email. Phase 3 of onboarding."""
    return {
        "customer_id": customer_id,
        "account_id": account_id,
        "message_id": f"msg_{customer_id}",
        "status": "sent",
    }


@tool
def schedule_kickoff_call(customer_id: str, account_id: str) -> dict:
    """Schedule the enterprise-tier kickoff call. Conditional on tier."""
    return {
        "customer_id": customer_id,
        "account_id": account_id,
        "calendar_invite_id": f"cal_{customer_id}",
        "status": "scheduled",
    }


def main() -> None:
    model = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6")

    planner = Agent(
        name="onboarding_planner",
        model=model,
        max_turns=3,
        instructions=(
            "You are an onboarding plan generator. Output a JSON plan that "
            "validates KYC, creates the account, and notifies the customer. "
            "Follow the rules in the Reference Context block exactly."
        ),
    )

    fallback = Agent(
        name="onboarding_fallback",
        model=model,
        max_turns=3,
        instructions=(
            "If you receive this, the plan compile failed. Run the four "
            "onboarding tools in their natural order: validate_kyc, "
            "create_account, send_welcome_email, and schedule_kickoff_call "
            "if the customer tier is 'enterprise'."
        ),
        tools=[validate_kyc, create_account, send_welcome_email, schedule_kickoff_call],
    )

    harness = Agent(
        name="onboarding_harness",
        model=model,
        tools=[
            validate_kyc,
            create_account,
            send_welcome_email,
            schedule_kickoff_call,
        ],
        planner=planner,
        fallback=fallback,
        strategy=Strategy.PLAN_EXECUTE,
        fallback_max_turns=3,
        planner_context=[
            # ── Inline rules: short, stable, hand-edited in code ──
            # Bare strings auto-wrap to Context(text=...). Explicit
            # Context(text=...) is shown on the third entry to make
            # both shapes visible in one example.
            "Onboarding has 3 mandatory phases in this exact order: "
            "(1) validate_kyc with doc_type='id', "
            "(2) create_account, "
            "(3) send_welcome_email.",
            "Tier 'enterprise' customers ADDITIONALLY require step "
            "(4) schedule_kickoff_call AFTER send_welcome_email. "
            "Tiers 'starter' and 'pro' must NOT include this step.",
            Context(
                text=(
                    "send_welcome_email depends on create_account's output: "
                    "use the account_id field as the account_id arg."
                ),
            ),
            # ── Live doc (commented out — uncomment if you have a real
            #     compliance/Confluence URL + token, demonstrates the
            #     URL+auth path the same way ToolConfig.headers does):
            # Context(
            #     url="https://docs.example.com/onboarding-compliance.md",
            #     headers={"Authorization": "Bearer ${CONFLUENCE_TOKEN}"},
            #     required=True,  # workflow fails if the doc can't be fetched
            #     max_bytes=8192,  # truncate giant wikis at 8KB
            # ),
        ],
    )

    prompt = (
        "Onboard customer cust-001 at tier 'enterprise'. "
        "Use customer_id='cust-001' and tier='enterprise' for the tools."
    )

    with AgentRuntime() as runtime:
        result = runtime.run(harness, prompt, timeout=180)
        result.print_result()

        # Surface the executed plan steps so this example doubles as a
        # proof that the planner actually used the context (4 steps when
        # tier=enterprise, 3 when tier=starter/pro).
        _show_executed_steps(result.execution_id)


def _show_executed_steps(execution_id: str) -> None:
    """Walk into the plan_exec sub-workflow and print the tool tasks."""
    import requests

    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")

    parent = requests.get(
        f"{base_url}/api/workflow/{execution_id}?includeTasks=true",
        timeout=10,
    ).json()

    print("\n=== Executed onboarding plan ===")
    sub_id = None
    for t in parent.get("tasks", []):
        if t.get("referenceTaskName", "").endswith("_plan_exec"):
            sub_id = (t.get("outputData") or {}).get("subWorkflowId")
            break

    if not sub_id:
        print("  (no plan_exec sub-workflow — planner output was rejected)")
        return

    sub = requests.get(
        f"{base_url}/api/workflow/{sub_id}?includeTasks=true",
        timeout=10,
    ).json()

    tool_tasks = []
    for t in sub.get("tasks") or []:
        name = t.get("taskDefName") or ""
        if name in {
            "validate_kyc",
            "create_account",
            "send_welcome_email",
            "schedule_kickoff_call",
        }:
            status = t.get("status")
            tool_tasks.append((name, status))

    if not tool_tasks:
        print("  (no tool tasks executed)")
        return

    print(f"  {len(tool_tasks)} step(s) executed:")
    for name, status in tool_tasks:
        print(f"    {status:<10} {name}")

    if "schedule_kickoff_call" in {n for n, _ in tool_tasks}:
        print("  ✓ planner picked up the 'enterprise tier needs kickoff' rule")


if __name__ == "__main__":
    main()
