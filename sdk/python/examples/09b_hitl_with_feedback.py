# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-Loop with Custom Feedback.

Demonstrates the general-purpose `respond()` API.  Instead of a binary
approve/reject, the human can send arbitrary feedback that the LLM
processes on its next iteration.  Uses interactive streaming with
schema-driven console prompts.

Use case: a content-publishing agent writes a blog post, and a human
editor can approve, reject, or provide revision notes.  The agent
incorporates the feedback and tries again.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
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


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        handle = runtime.start(agent, "Write a short blog post about the benefits of code review")
        print(f"Started: {handle.execution_id}\n")

        for event in handle.stream():
            if event.type == EventType.THINKING:
                print(f"  [thinking] {event.content}")

            elif event.type == EventType.TOOL_CALL:
                print(f"  [tool_call] {event.tool_name}({event.args})")

            elif event.type == EventType.TOOL_RESULT:
                print(f"  [tool_result] {event.tool_name} -> {str(event.result)[:100]}")

            elif event.type == EventType.WAITING:
                status = handle.get_status()
                pt = status.pending_tool or {}
                schema = pt.get("response_schema", {})
                props = schema.get("properties", {})
                print("\n--- Human input required ---")
                response = {}
                for field, fs in props.items():
                    desc = fs.get("description") or fs.get("title", field)
                    if fs.get("type") == "boolean":
                        val = input(f"  {desc} (y/n): ").strip().lower()
                        response[field] = val in ("y", "yes")
                    else:
                        response[field] = input(f"  {desc}: ").strip()
                handle.respond(response)
                print()

            elif event.type == EventType.DONE:
                print(f"\nDone: {event.output}")

        # Non-interactive alternative (no HITL, will block on human tasks):
        # result = runtime.run(agent, "Write a short blog post outline about the benefits of code review. Do not publish it.")
        # result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

