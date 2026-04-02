# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-Loop with Streaming — Console Interactive.

Streams agent events in real time via SSE.  When the agent pauses for
human approval, the user is prompted in the console to approve, reject,
or provide feedback — all through the AgentStream object.

Use case: an ops agent that can restart services (safe) and delete data
(dangerous, requires approval).  The operator watches the agent think
in real time and intervenes only for destructive actions.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from settings import settings


@tool
def check_service(service_name: str) -> dict:
    """Check the health of a service."""
    return {"service": service_name, "status": "unhealthy", "uptime": "0m"}


@tool
def restart_service(service_name: str) -> dict:
    """Restart a service. Safe operation, no approval needed."""
    return {"service": service_name, "status": "restarted", "new_uptime": "0m"}


@tool(approval_required=True)
def delete_service_data(service_name: str, data_type: str) -> dict:
    """Delete service data. Destructive — requires human approval."""
    return {"service": service_name, "data_type": data_type, "status": "deleted"}


agent = Agent(
    name="ops_agent",
    model=settings.llm_model,
    tools=[check_service, restart_service, delete_service_data],
    instructions=(
        "You are an operations assistant. You can check, restart, and manage services. "
        "If a service is unhealthy, check it first, then restart it. Only suggest "
        "deleting data if explicitly asked."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "The payments service is down. Check it and restart it.")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.09c_hitl_streaming
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

        # Interactive streaming alternative:
        # # stream() starts the workflow and returns an AgentStream —
        # # iterable for events, with HITL controls built in.
        # result = runtime.stream(
        #     agent,
        #     "The payments service is down. Check it, restart it, and clear its stale cache data.",
        # )
        # print(f"Workflow started: {result.execution_id}\n")

        # for event in result:
        #     if event.type == EventType.THINKING:
        #         print(f"  [thinking] {event.content}")

        #     elif event.type == EventType.TOOL_CALL:
        #         print(f"  [tool_call] {event.tool_name}({event.args})")

        #     elif event.type == EventType.TOOL_RESULT:
        #         print(f"  [tool_result] {event.tool_name} -> {event.result}")

        #     elif event.type == EventType.WAITING:
        #         print(f"\n--- Approval required ---")
        #         choice = input("  Approve? (y/n/message): ").strip().lower()
        #         if choice == "y":
        #             result.approve()
        #             print("  Approved!\n")
        #         elif choice == "n":
        #             reason = input("  Rejection reason: ").strip()
        #             result.reject(reason or "Rejected by operator")
        #             print("  Rejected.\n")
        #         else:
        #             # Anything else is treated as feedback
        #             result.send(choice)
        #             print("  Feedback sent.\n")

        #     elif event.type == EventType.GUARDRAIL_PASS:
        #         print(f"  [guardrail] {event.guardrail_name} passed")

        #     elif event.type == EventType.GUARDRAIL_FAIL:
        #         print(f"  [guardrail] {event.guardrail_name} FAILED: {event.content}")

        #     elif event.type == EventType.ERROR:
        #         print(f"  [error] {event.content}")

        #     elif event.type == EventType.DONE:
        #         print(f"\n  [done] {event.output}")

        # # After iteration, the full result is available
        # final = result.get_result()
        # print(f"\nTool calls made: {len(final.tool_calls)}")
        # print(f"Status: {final.status}")

