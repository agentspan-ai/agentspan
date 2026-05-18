# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-Loop with Streaming — Console Interactive.

Streams agent events in real time via SSE.  When the agent pauses for
human approval, the user is prompted in the console with schema-driven
prompts and responds through the handle.

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
        handle = runtime.start(agent, "The payments service is down. Check it, restart it, and clear its stale cache data.")
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
        # result = runtime.run(agent, "The payments service is down. Check it and restart it.")
        # result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

