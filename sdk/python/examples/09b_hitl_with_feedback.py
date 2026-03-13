# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-Loop with Custom Feedback.

Demonstrates the general-purpose `respond()` API.  Instead of a binary
approve/reject, the human can send arbitrary feedback that the LLM
processes on its next iteration.

Use case: a content-publishing agent writes a blog post, and a human
editor can approve, reject, or provide revision notes.  The agent
incorporates the feedback and tries again.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from settings import settings


@tool(approval_required=True)
def publish_article(title: str, body: str) -> dict:
    """Publish an article to the blog. Requires editorial approval."""
    return {"status": "published", "title": title, "url": f"/blog/{title.lower().replace(' ', '-')}"}


agent = Agent(
    name="writer",
    model=settings.llm_model,
    tools=[publish_article],
    instructions=(
        "You are a blog writer. When asked to write about a topic, draft an article "
        "and publish it using the publish_article tool. If you receive editorial "
        "feedback, revise the article and try publishing again."
    ),
)

with AgentRuntime() as runtime:
    result = runtime.stream(
        agent, "Write a short blog post about the benefits of code review"
    )
    print(f"Workflow started: {result.workflow_id}\n")

    for event in result:
        print(f'event type: {event.type} --> {event.content}')
        if event.type == EventType.THINKING:
            print(f"  [thinking] {event.content}")

        elif event.type == EventType.TOOL_CALL:
            print(f"  [tool_call] {event.tool_name}")
            if event.args:
                title = event.args.get("title", "")
                body = event.args.get("body", "")
                if title:
                    print(f"    Title: {title}")
                if body:
                    preview = body[:200] + "..." if len(body) > 200 else body
                    print(f"    Body:  {preview}")

        elif event.type == EventType.GUARDRAIL_FAIL:
            print(f"  [guardrail failed] {event.guardrail_name}")
            if event.args:
                title = event.args.get("title", "")
                body = event.args.get("body", "")
                if title:
                    print(f"    Title: {title}")
                if body:
                    preview = body[:200] + "..." if len(body) > 200 else body
                    print(f"    Body:  {preview}")

        elif event.type == EventType.TOOL_RESULT:
            print(f"  [tool_result] {event.tool_name} -> {event.result}")

        elif event.type == EventType.WAITING:
            print(f"\n--- Editorial Review Required ---")
            print("  [a] Approve and publish")
            print("  [r] Reject entirely")
            print("  [f] Provide feedback for revision")
            print()

            choice = input("  Choice (a/r/f): ").strip().lower()

            if choice == "a":
                result.approve()
                print("  Approved for publication!\n")
            elif choice == "r":
                reason = input("  Rejection reason: ").strip()
                result.reject(reason or "Does not meet editorial standards")
                print("  Rejected.\n")
            else:
                feedback = input("  Feedback: ").strip()
                result.respond({"feedback": feedback})
                print("  Feedback sent, agent will revise...\n")

        elif event.type == EventType.ERROR:
            print(f"  [error] {event.content}")

        elif event.type == EventType.DONE:
            print(f"\n  [done] {event.output}")

    # Access the structured result after streaming
    final = result.get_result()
    print(f"\nTool calls made: {len(final.tool_calls)}")
    print(f"Status: {final.status}")
