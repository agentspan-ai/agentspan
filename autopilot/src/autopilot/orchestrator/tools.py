"""Orchestrator tools — creation, management, deployment, credentials.

All tools are ``@tool``-decorated functions usable by the Claw orchestrator
agent.  Creation tools return prompts/templates for the LLM to fill in;
management tools are fully deterministic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from agentspan.agents import tool

from autopilot.config import AutopilotConfig
from autopilot.orchestrator.state import AgentState, StateManager, VALID_STATUSES
from autopilot.registry import get_default_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config() -> AutopilotConfig:
    """Load the autopilot config from environment / file."""
    return AutopilotConfig.from_env()


def _get_state_manager(config: Optional[AutopilotConfig] = None) -> StateManager:
    """Return a StateManager backed by the default state file."""
    if config is None:
        config = _get_config()
    state_file = config.base_dir / "state.json"
    return StateManager(state_file)


def _agents_dir(config: Optional[AutopilotConfig] = None) -> Path:
    """Return the agents directory path."""
    if config is None:
        config = _get_config()
    return config.agents_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestratorError(Exception):
    """Raised for orchestrator-level errors (missing agents, bad state, etc.)."""


def build_integration_catalog() -> str:
    """Build a human-readable integration catalog with credential info.

    Returns a formatted string listing all available integrations, their tools,
    and required credentials.  Used by the orchestrator instructions so the LLM
    can generate agent specs without calling expand_prompt.
    """
    registry = get_default_registry()
    lines: list[str] = []
    for name in registry.list_integrations():
        tools = registry.get_tools(name)
        creds: list[str] = []
        for t in tools:
            if hasattr(t, "_tool_def") and t._tool_def.credentials:
                creds = list(t._tool_def.credentials)
                break
        tool_names = [t._tool_def.name for t in tools if hasattr(t, "_tool_def")]
        cred_str = f" (credentials: {', '.join(creds)})" if creds else " (no credentials needed)"
        lines.append(f"  - builtin:{name}{cred_str} -- tools: {', '.join(tool_names)}")
    return "\n".join(lines)


def _get_credential_aliases() -> dict:
    """Build credential alias map from the credential registry."""
    from autopilot.credentials.acquisition import CREDENTIAL_REGISTRY
    aliases: dict[str, str] = {}
    for cred_name, info in CREDENTIAL_REGISTRY.items():
        # Create common aliases: lowercase, without _TOKEN/_KEY suffix, etc.
        lower = cred_name.lower()
        aliases[lower] = cred_name
        # Strip common suffixes for additional aliases
        for suffix in ("_token", "_access_token", "_api_key", "_api_token", "_key"):
            if lower.endswith(suffix):
                aliases[lower[: -len(suffix)]] = cred_name
        # Service name alias
        if info.service:
            aliases[info.service.lower().replace(" ", "_")] = cred_name
    return aliases


# ---------------------------------------------------------------------------
# Creation Tools (LLM-driven, guardrailed)
# ---------------------------------------------------------------------------

@tool
def expand_prompt(seed_prompt: str, clarifications: str = "") -> str:
    """Expand a user's lazy prompt into a full agent specification.

    .. deprecated::
        The orchestrator now inlines the integration catalog into its
        instructions and generates YAML specs directly, removing the need
        for a separate ``expand_prompt`` tool call.  This function is kept
        for backward compatibility with existing tests but is no longer
        registered in ``get_orchestrator_tools()``.

    Takes the user's seed prompt and any clarification answers, and produces
    a structured prompt that the orchestrator LLM will use to generate a
    complete agent spec in YAML format including: name, model, instructions,
    tools needed, trigger type, schedule, credentials required, error handling.

    Returns the expansion template as a string for the LLM to fill in.
    """
    config = _get_config()
    registry = get_default_registry()

    # Build integration catalog with credential info
    integration_lines = []
    for name in registry.list_integrations():
        tools = registry.get_tools(name)
        creds = []
        for t in tools:
            if hasattr(t, "_tool_def") and t._tool_def.credentials:
                creds = list(t._tool_def.credentials)
                break
        tool_names = [t._tool_def.name for t in tools if hasattr(t, "_tool_def")]
        cred_str = f" (credentials: {', '.join(creds)})" if creds else " (no credentials needed)"
        integration_lines.append(f"  - builtin:{name}{cred_str} — tools: {', '.join(tool_names)}")

    integrations_catalog = "\n".join(integration_lines)

    template = f"""Based on the user's request and clarifications, create a complete agent specification.

User request: {seed_prompt}
Clarifications: {clarifications or "None provided"}

Generate a YAML agent specification with EXACTLY these fields:

```yaml
name: <snake_case_descriptive_name>
version: 1
model: {config.llm_model}
instructions: |
  <Detailed multi-paragraph instructions for the agent. Be specific about:
  - What data to fetch and from where
  - How to process/analyze the data
  - What output to produce and in what format
  - How to handle edge cases (no data, errors, etc.)
  - Any categorization or prioritization logic>
trigger:
  type: <cron or daemon>
  schedule: "<cron expression>"  # only for type: cron
tools:
  - builtin:<integration_name>  # NO SPACE after colon
credentials:
  - <EXACT_CREDENTIAL_NAME>  # must match the integration's credential names below
error_handling:
  max_retries: 3
  backoff: exponential
  on_failure: pause_and_notify
```

CRITICAL RULES:
1. model MUST be "{config.llm_model}" — do not change it
2. tools entries MUST use format "builtin:name" with NO SPACE after the colon
3. credentials MUST use the EXACT names listed below for each integration
4. instructions MUST be detailed (at least 10 lines) — not a one-liner

Available integrations:
{integrations_catalog}

Return ONLY the YAML specification wrapped in ```yaml ... ``` — no other text."""
    return template


@tool
def generate_agent(spec_yaml: str, agent_name: str) -> str:
    """Generate agent files from an expanded spec.

    Creates the agent directory under the configured agents directory
    with agent.yaml, expanded_prompt.md, and a workers/ directory.

    Returns a summary of what was created.
    """
    config = _get_config()
    agents_base = config.agents_dir

    # Strip markdown code fences if the LLM wrapped the YAML
    cleaned = spec_yaml.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```yaml) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # Parse spec
    try:
        spec = yaml.safe_load(cleaned)
    except yaml.YAMLError as exc:
        return f"Error: Invalid YAML spec — {exc}"

    if not isinstance(spec, dict):
        return "Error: Spec must be a YAML mapping."

    # Normalise name
    name = spec.get("name", agent_name)
    if not name:
        return "Error: Agent name is required."

    agent_dir = agents_base / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    workers_dir = agent_dir / "workers"
    workers_dir.mkdir(exist_ok=True)

    # --- Normalize common LLM mistakes ---

    # Force model to configured value if LLM picked something else
    spec["model"] = config.llm_model

    # Fix tools: normalize various LLM tool reference formats
    if "tools" in spec and isinstance(spec["tools"], list):
        normalized_tools = []
        for t in spec["tools"]:
            if isinstance(t, str):
                # "builtin: gmail" -> "builtin:gmail"
                t = t.replace("builtin: ", "builtin:")
                # "{'name': 'web_search'}" -> "web_search" (LLM writes Python dict as string)
                if t.startswith("{") and "name" in t:
                    import re
                    m = re.search(r"['\"]name['\"]\s*:\s*['\"]([^'\"]+)['\"]", t)
                    if m:
                        t = m.group(1)
                normalized_tools.append(t)
            elif isinstance(t, dict):
                # {"builtin": "gmail"} -> "builtin:gmail"
                if "builtin" in t:
                    normalized_tools.append(f"builtin:{t['builtin']}")
                # {"name": "web_search"} -> "web_search"
                elif "name" in t:
                    normalized_tools.append(str(t["name"]))
                # {"id": "doc_reader.read_document"} -> "doc_reader"
                elif "id" in t:
                    tool_id = str(t["id"])
                    normalized_tools.append(tool_id.split(".")[0] if "." in tool_id else tool_id)
                else:
                    normalized_tools.append(str(t))
            else:
                normalized_tools.append(str(t))
        spec["tools"] = normalized_tools

    # Normalize credential names — map common mistakes to actual names
    _CREDENTIAL_ALIASES = _get_credential_aliases()
    if "credentials" in spec and isinstance(spec["credentials"], list):
        spec["credentials"] = [
            _CREDENTIAL_ALIASES.get(c.lower().strip(), c) for c in spec["credentials"]
        ]

    # Ensure defaults
    spec.setdefault("name", name)
    spec.setdefault("version", 1)
    if "metadata" not in spec:
        spec["metadata"] = {}
    spec["metadata"]["created_at"] = _now_iso()
    spec["metadata"]["created_by"] = "orchestrator"

    # Ensure error_handling exists
    spec.setdefault("error_handling", {
        "max_retries": 3,
        "backoff": "exponential",
        "on_failure": "pause_and_notify",
    })

    yaml_path = agent_dir / "agent.yaml"
    yaml_path.write_text(yaml.dump(spec, default_flow_style=False, sort_keys=False))

    # Write expanded_prompt.md with more detail
    instructions = spec.get("instructions", "")
    trigger = spec.get("trigger", {})
    tools = spec.get("tools", [])
    creds = spec.get("credentials", [])

    prompt_content = f"""# {name}

## Instructions

{instructions}

## Configuration

- **Model:** {spec.get('model', 'default')}
- **Trigger:** {trigger.get('type', 'daemon')}{' — schedule: ' + trigger.get('schedule', '') if trigger.get('schedule') else ''}
- **Tools:** {', '.join(str(t) for t in tools)}
- **Credentials:** {', '.join(str(c) for c in creds)}
- **Error handling:** {spec.get('error_handling', {}).get('max_retries', 3)} retries, {spec.get('error_handling', {}).get('backoff', 'exponential')} backoff
"""
    prompt_path = agent_dir / "expanded_prompt.md"
    prompt_path.write_text(prompt_content)

    # Register in state as DRAFT
    sm = _get_state_manager(config)
    trigger_type = "daemon"
    trigger = spec.get("trigger", {})
    if isinstance(trigger, dict):
        trigger_type = trigger.get("type", "daemon")
    # Validate trigger_type
    if trigger_type not in ("cron", "daemon", "webhook"):
        trigger_type = "daemon"

    sm.set(name, AgentState(
        name=name,
        execution_id="",
        status="DRAFT",
        trigger_type=trigger_type,
        created_at=_now_iso(),
    ))

    # Auto-commit for version tracking
    try:
        commit_agent_change(name, f"created agent v{spec.get('version', 1)}", config)
    except Exception:
        pass  # Git commit is best-effort

    created_files = [
        str(yaml_path),
        str(prompt_path),
        str(workers_dir) + "/",
    ]
    return (
        f"Agent '{name}' created successfully.\n"
        f"Directory: {agent_dir}\n"
        f"Files:\n" + "\n".join(f"  - {f}" for f in created_files) + "\n"
        f"Status: DRAFT — deploy with deploy_agent('{name}')"
    )


@tool
def resolve_integrations(agent_name: str) -> str:
    """Check which integrations an agent needs and whether they are available.

    Reads the agent's config, checks each tool reference against the registry,
    and reports which are available, which need credentials, and which are missing.
    """
    config = _get_config()
    agent_dir = config.agents_dir / agent_name

    yaml_path = agent_dir / "agent.yaml"
    if not yaml_path.exists():
        return f"Error: Agent '{agent_name}' not found at {agent_dir}."

    with open(yaml_path) as f:
        raw = yaml.safe_load(f) or {}

    tool_refs = raw.get("tools", [])
    credentials_needed = raw.get("credentials", [])
    registry = get_default_registry()

    report_lines = [f"Integration check for agent '{agent_name}':", ""]

    # Check tools — Tier 1 (builtin), then Tier 2 (MCP) fallback
    available = []
    missing = []
    mcp_available = []
    for ref in tool_refs:
        if isinstance(ref, str) and ref.startswith("builtin:"):
            integration_name = ref[len("builtin:"):]
            tools = registry.get_tools(integration_name)
            if tools:
                available.append(integration_name)
            else:
                # Tier 2 fallback: check configured MCP servers
                from autopilot.integrations.mcp.tools import get_configured_servers

                mcp_servers = get_configured_servers()
                found_via_mcp = False
                for server_name, server_info in mcp_servers.items():
                    # Check if server's tools overlap with what we need
                    server_tools = server_info.get("tools", [])
                    if not server_tools or integration_name in server_tools:
                        mcp_available.append(f"{integration_name} (via MCP: {server_name})")
                        found_via_mcp = True
                        break
                if not found_via_mcp:
                    missing.append(integration_name)
        elif isinstance(ref, str) and ref.startswith("mcp:"):
            # Explicit MCP reference — e.g. "mcp:http://localhost:3001/mcp"
            server_url = ref[len("mcp:"):]
            mcp_available.append(f"mcp ({server_url})")
        elif isinstance(ref, str):
            # Worker-based tool — check if file exists
            worker_file = agent_dir / "workers" / f"{ref}.py"
            if worker_file.exists():
                available.append(f"{ref} (worker)")
            else:
                missing.append(f"{ref} (worker — file missing)")

    if available:
        report_lines.append("Available integrations:")
        for name in available:
            report_lines.append(f"  [OK] {name}")

    if mcp_available:
        report_lines.append("Available via MCP (Tier 2):")
        for name in mcp_available:
            report_lines.append(f"  [MCP] {name}")

    if missing:
        report_lines.append("Missing integrations:")
        for name in missing:
            report_lines.append(f"  [MISSING] {name}")

    # Check credentials
    if credentials_needed:
        report_lines.append("")
        report_lines.append("Required credentials:")
        for cred in credentials_needed:
            report_lines.append(f"  - {cred}")

    if not available and not missing:
        report_lines.append("No tool references found in agent.yaml.")

    return "\n".join(report_lines)


# ---------------------------------------------------------------------------
# Management Tools (deterministic, no LLM)
# ---------------------------------------------------------------------------

@tool
def deploy_agent(agent_name: str) -> str:
    """Deploy an agent to the Agentspan server.

    Loads the agent from disk using the loader, starts it via AgentRuntime,
    and stores the execution ID in state. Returns the execution ID.
    """
    config = _get_config()
    agent_dir = config.agents_dir / agent_name

    if not (agent_dir / "agent.yaml").exists():
        return f"Error: Agent '{agent_name}' not found at {agent_dir}."

    sm = _get_state_manager(config)

    # Update state to DEPLOYING
    existing = sm.get(agent_name)
    trigger_type = existing.trigger_type if existing else "daemon"
    created_at = existing.created_at if existing else _now_iso()

    sm.set(agent_name, AgentState(
        name=agent_name,
        execution_id="",
        status="DEPLOYING",
        trigger_type=trigger_type,
        created_at=created_at,
    ))

    # Load the agent config for retry policy
    with open(agent_dir / "agent.yaml") as f:
        agent_yaml = yaml.safe_load(f) or {}
    error_handling = agent_yaml.get("error_handling", {})

    from autopilot.orchestrator.retry import RetryPolicy, retry_with_policy

    policy = RetryPolicy.from_agent_config(error_handling)

    # Deploy via the server's HTTP API directly.
    # We cannot use AgentRuntime() here because this tool runs inside a
    # Conductor daemon worker process, and daemon processes cannot spawn
    # child processes (which AgentRuntime needs for tool workers).
    #
    # Instead, we use the compile + start REST endpoints and register
    # the agent for execution. Workers for builtin tools are already
    # running as part of the orchestrator's runtime.
    try:
        from autopilot.loader import load_agent
        from agentspan.agents.runtime.serializer import AgentConfigSerializer
        import httpx

        agent = load_agent(agent_dir)
        serializer = AgentConfigSerializer()
        config_json = serializer.serialize(agent)

        server_url = config.server_url.rstrip("/")
        payload = {
            "agentConfig": config_json,
            "prompt": "Begin agent execution.",
            "sessionId": "",
            "media": [],
        }

        # Call the server's /agent/start endpoint directly
        resp = httpx.post(
            f"{server_url}/agent/start",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        execution_id = data.get("executionId", "")

        if not execution_id:
            raise RuntimeError("Server returned no execution ID")

        # Verify the execution is running
        server_status = "ACTIVE"
        try:
            from autopilot.orchestrator.server import get_execution
            details = get_execution(execution_id, config=config)
            srv_status = details.get("status", "")
            if srv_status in ("RUNNING", "COMPLETED"):
                server_status = "ACTIVE"
        except Exception:
            pass

        sm.set(agent_name, AgentState(
            name=agent_name,
            execution_id=execution_id,
            status=server_status,
            trigger_type=trigger_type,
            created_at=created_at,
            last_deployed=_now_iso(),
        ))

        # Auto-commit for version tracking
        try:
            commit_agent_change(agent_name, f"deployed v{agent_yaml.get('version', 1)}", config)
        except Exception:
            pass

        return (
            f"Agent '{agent_name}' deployed successfully.\n"
            f"Execution ID: {execution_id}\n"
            f"Status: {server_status}\n"
            f"The agent is now running on the server."
        )
    except Exception as exc:
        sm.set(agent_name, AgentState(
            name=agent_name,
            execution_id="",
            status="ERROR",
            trigger_type=trigger_type,
            created_at=created_at,
        ))
        return f"Error deploying agent '{agent_name}': {exc}"


@tool
def list_agents() -> str:
    """List all agents with their status.

    Merges local disk info with live server execution status. If the server
    is reachable, running executions are reflected as RUNNING in the output.
    """
    config = _get_config()
    agents_base = config.agents_dir
    sm = _get_state_manager(config)

    if not agents_base.exists():
        return "No agents directory found. No agents created yet."

    dirs = sorted(
        d.name
        for d in agents_base.iterdir()
        if d.is_dir() and (d / "agent.yaml").exists()
    )

    if not dirs:
        return "No agents found."

    # Fetch live server status for enrichment
    server_running: dict[str, dict] = {}
    try:
        from autopilot.orchestrator.server import get_running_agents
        for ex in get_running_agents(config=config):
            aname = ex.get("agentName", "")
            if aname:
                server_running[aname] = ex
    except Exception:
        pass  # Server unreachable — use local state only

    lines = ["Agents:", ""]
    for name in dirs:
        state = sm.get(name)
        if state:
            # Prefer live server status when available
            if name in server_running:
                status = "RUNNING"
                eid_full = server_running[name].get("executionId", state.execution_id)
            else:
                status = state.status
                eid_full = state.execution_id
            eid = eid_full[:12] + "..." if eid_full else "—"
            lines.append(f"  {name:30s} {status:10s} exec={eid}")
        else:
            # Check if the server knows about this agent even without local state
            if name in server_running:
                eid_full = server_running[name].get("executionId", "")
                eid = eid_full[:12] + "..." if eid_full else "—"
                lines.append(f"  {name:30s} {'RUNNING':10s} exec={eid}")
            else:
                lines.append(f"  {name:30s} {'UNTRACKED':10s}")

    return "\n".join(lines)


@tool
def signal_agent(agent_name: str, message: str) -> str:
    """Send a transient signal to a running agent.

    Resolves agent_name to execution_id from state, then calls
    runtime.signal(execution_id, message).
    """
    config = _get_config()
    sm = _get_state_manager(config)
    state = sm.get(agent_name)

    if state is None:
        raise OrchestratorError(f"Agent '{agent_name}' is not tracked. Use list_agents() to see available agents.")

    if not state.execution_id:
        return f"Error: Agent '{agent_name}' has no active execution (status: {state.status})."

    if state.status not in ("ACTIVE", "WAITING"):
        return f"Error: Agent '{agent_name}' is not running (status: {state.status})."

    try:
        from agentspan.agents import AgentRuntime

        with AgentRuntime() as runtime:
            runtime.signal(state.execution_id, message)

        return f"Signal sent to '{agent_name}': {message}"
    except Exception as exc:
        return f"Error signaling agent '{agent_name}': {exc}"


@tool
def update_agent(agent_name: str, changes: str) -> str:
    """Permanently modify an agent's configuration.

    Updates the agent's expanded_prompt.md and/or agent.yaml based on
    the change description. Increments the version number.

    The changes parameter is a natural language description of what to modify.
    The orchestrator LLM interprets this and makes the appropriate changes.
    This tool returns a prompt for the LLM to generate updated YAML.
    """
    config = _get_config()
    agent_dir = config.agents_dir / agent_name

    yaml_path = agent_dir / "agent.yaml"
    if not yaml_path.exists():
        return f"Error: Agent '{agent_name}' not found at {agent_dir}."

    # Read current config
    with open(yaml_path) as f:
        current_yaml = f.read()

    prompt_path = agent_dir / "expanded_prompt.md"
    current_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    template = f"""The user wants to modify agent '{agent_name}'.

Current agent.yaml:
```yaml
{current_yaml}
```

Current expanded_prompt.md:
```
{current_prompt}
```

Requested changes: {changes}

Generate the updated agent.yaml with the changes applied.
Increment the version number by 1.
Return ONLY the updated YAML, no explanation."""

    return template


@tool
def pause_agent(agent_name: str) -> str:
    """Pause a running agent.

    Resolves name to execution_id and calls runtime.stop().
    Updates state to PAUSED.
    """
    config = _get_config()
    sm = _get_state_manager(config)
    state = sm.get(agent_name)

    if state is None:
        raise OrchestratorError(f"Agent '{agent_name}' is not tracked.")

    if state.status not in ("ACTIVE", "WAITING"):
        return f"Agent '{agent_name}' is not running (status: {state.status}). Cannot pause."

    if not state.execution_id:
        return f"Agent '{agent_name}' has no active execution."

    try:
        from agentspan.agents import AgentRuntime

        with AgentRuntime() as runtime:
            runtime.stop(state.execution_id)

        sm.set(agent_name, AgentState(
            name=agent_name,
            execution_id=state.execution_id,
            status="PAUSED",
            trigger_type=state.trigger_type,
            created_at=state.created_at,
            last_deployed=state.last_deployed,
        ))

        return f"Agent '{agent_name}' paused."
    except Exception as exc:
        return f"Error pausing agent '{agent_name}': {exc}"


@tool
def resume_agent(agent_name: str) -> str:
    """Resume a paused agent.

    Re-deploys the agent from its local directory.
    """
    config = _get_config()
    sm = _get_state_manager(config)
    state = sm.get(agent_name)

    if state is None:
        raise OrchestratorError(f"Agent '{agent_name}' is not tracked.")

    if state.status != "PAUSED":
        return f"Agent '{agent_name}' is not paused (status: {state.status}). Cannot resume."

    # Re-deploy
    return deploy_agent(agent_name)


@tool
def archive_agent(agent_name: str) -> str:
    """Archive an agent — stop execution, keep local files.

    Updates state to ARCHIVED. If the agent is running, stops it first.
    """
    config = _get_config()
    sm = _get_state_manager(config)
    state = sm.get(agent_name)

    if state is None:
        raise OrchestratorError(f"Agent '{agent_name}' is not tracked.")

    if state.status == "ARCHIVED":
        return f"Agent '{agent_name}' is already archived."

    # Stop if running
    if state.execution_id and state.status in ("ACTIVE", "WAITING"):
        try:
            from agentspan.agents import AgentRuntime

            with AgentRuntime() as runtime:
                runtime.stop(state.execution_id)
        except Exception:
            pass  # best-effort stop

    sm.set(agent_name, AgentState(
        name=agent_name,
        execution_id=state.execution_id,
        status="ARCHIVED",
        trigger_type=state.trigger_type,
        created_at=state.created_at,
        last_deployed=state.last_deployed,
    ))

    return f"Agent '{agent_name}' archived. Local files retained at {config.agents_dir / agent_name}."


@tool
def get_agent_status(agent_name: str) -> str:
    """Get detailed status of a specific agent.

    Reads local state and agent.yaml, then enriches with live server execution
    data when available.
    """
    config = _get_config()
    sm = _get_state_manager(config)
    state = sm.get(agent_name)

    if state is None:
        raise OrchestratorError(
            f"Agent '{agent_name}' is not tracked. "
            f"Use list_agents() to see available agents."
        )

    agent_dir = config.agents_dir / agent_name
    yaml_path = agent_dir / "agent.yaml"

    # Try to get live server data for this agent
    server_exec: Optional[dict] = None
    try:
        from autopilot.orchestrator.server import get_execution, query_executions
        if state.execution_id:
            server_exec = get_execution(state.execution_id, config=config)
        else:
            # Try to find by agent name
            execs = query_executions(agent_name=agent_name, config=config)
            if execs:
                server_exec = execs[0]
    except Exception:
        pass  # Server unreachable

    # Determine status: prefer server status when available
    display_status = state.status
    if server_exec:
        server_status = server_exec.get("status", "")
        if server_status:
            display_status = server_status

    lines = [
        f"Agent: {agent_name}",
        f"Status: {display_status}",
        f"Trigger: {state.trigger_type}",
        f"Created: {state.created_at}",
    ]

    if state.last_deployed:
        lines.append(f"Last deployed: {state.last_deployed}")

    if state.execution_id:
        lines.append(f"Execution ID: {state.execution_id}")

    # Add server-provided timing info
    if server_exec:
        if server_exec.get("executionTime") is not None:
            lines.append(f"Execution time: {server_exec['executionTime']}ms")
        if server_exec.get("startTime"):
            lines.append(f"Server start: {server_exec['startTime']}")

    # Read agent.yaml for additional info
    if yaml_path.exists():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        if "version" in raw:
            lines.append(f"Version: {raw['version']}")
        if "model" in raw:
            lines.append(f"Model: {raw['model']}")
        creds = raw.get("credentials", [])
        if creds:
            lines.append(f"Credentials: {', '.join(creds)}")

    return "\n".join(lines)


@tool
def get_notifications(since: str = "") -> str:
    """Get recent outputs/notifications from all agents.

    Checks local state and the server for live execution data. If *since* is
    provided (ISO-8601 timestamp), only shows notifications after that time.
    """
    config = _get_config()
    sm = _get_state_manager(config)
    all_states = sm.list_all()

    if not all_states:
        return "No agents tracked. Nothing to report."

    # Fetch live server status to enrich local data
    server_running_names: set[str] = set()
    try:
        from autopilot.orchestrator.server import get_running_agents
        for ex in get_running_agents(config=config):
            aname = ex.get("agentName", "")
            if aname:
                server_running_names.add(aname)
    except Exception:
        pass  # Server unreachable

    lines = ["Notifications:", ""]

    active_count = 0
    error_count = 0
    waiting_count = 0

    for state in all_states:
        # If the server says it's running, treat as active regardless of local state
        if state.name in server_running_names:
            active_count += 1
            continue

        if state.status == "ERROR":
            error_count += 1
            lines.append(f"  [ERROR] {state.name} — requires attention")
        elif state.status == "WAITING":
            waiting_count += 1
            lines.append(f"  [WAITING] {state.name} — needs user input")
        elif state.status == "ACTIVE":
            active_count += 1

    lines.append("")
    lines.append(f"Summary: {active_count} active, {waiting_count} waiting, {error_count} errors")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Credential Tools (deterministic)
# ---------------------------------------------------------------------------

@tool
def check_credentials(agent_name: str) -> str:
    """Check if all required credentials for an agent are available.

    Reads the agent's agent.yaml and checks each credential requirement.
    """
    config = _get_config()
    agent_dir = config.agents_dir / agent_name

    yaml_path = agent_dir / "agent.yaml"
    if not yaml_path.exists():
        return f"Error: Agent '{agent_name}' not found."

    with open(yaml_path) as f:
        raw = yaml.safe_load(f) or {}

    credentials_needed = raw.get("credentials", [])
    if not credentials_needed:
        return f"Agent '{agent_name}' does not require any credentials."

    lines = [f"Credential check for '{agent_name}':", ""]
    for cred in credentials_needed:
        lines.append(f"  - {cred}: required")

    lines.append("")
    lines.append(
        "Use acquire_credentials('<credential_name>') to seamlessly set up missing "
        "credentials (opens browser for OAuth/API key flows)."
    )

    return "\n".join(lines)


@tool
def prompt_credentials(credential_name: str) -> str:
    """Guide the user through setting up a missing credential.

    Returns instructions for the user to configure the named credential
    via the Agentspan CLI.

    .. deprecated:: Use :func:`acquire_credentials` instead for seamless
       browser-based acquisition.
    """
    return (
        f"To set up the '{credential_name}' credential:\n\n"
        f"1. Run: agentspan credentials set {credential_name} <your-value>\n"
        f"2. Or set it as an environment variable: export {credential_name}=<your-value>\n\n"
        f"The credential will be securely stored on the Agentspan server and "
        f"injected into agent executions automatically."
    )


@tool
def acquire_credentials(credential_name: str) -> str:
    """Acquire a missing credential by guiding the user through the setup process.

    For OAuth services (Gmail, Google Calendar, etc.): opens browser for OAuth flow.
    For API key services (GitHub, Linear, etc.): opens browser to API key page and prompts for the key.
    For AWS: reads from ~/.aws/credentials or guides through IAM console.

    Returns the result of the acquisition attempt.
    """
    from autopilot.credentials.acquisition import (
        CREDENTIAL_REGISTRY,
        acquire_credential,
    )

    info = CREDENTIAL_REGISTRY.get(credential_name)
    if info:
        method = info.acquisition_type.replace("_", " ").title()
        service = info.service
    else:
        method = "Manual"
        service = credential_name

    return acquire_credential(credential_name)


# ---------------------------------------------------------------------------
# Worker generation (Tier 3)
# ---------------------------------------------------------------------------


@tool
def generate_worker(agent_name: str, tool_name: str, description: str, parameters: str = "", api_docs: str = "") -> str:
    """Generate a custom worker Python file for an agent when no pre-built integration exists.

    Creates a worker file at ~/.agentspan/autopilot/agents/<agent_name>/workers/<tool_name>.py
    with a @tool-decorated function skeleton based on the provided description and parameters.

    Args:
        agent_name: Name of the agent to add the worker to.
        tool_name: Name for the tool function (snake_case).
        description: What the tool should do.
        parameters: Comma-separated list of parameters with types, e.g. "query: str, limit: int = 10".
        api_docs: Optional API documentation or reference to help implement the tool.

    Returns:
        The generated worker code as a string, and the file path where it was saved.
    """
    config = _get_config()
    agent_dir = config.agents_dir / agent_name
    if not agent_dir.exists():
        raise RuntimeError(f"Agent '{agent_name}' not found at {agent_dir}")

    if not tool_name.isidentifier():
        raise RuntimeError(f"Invalid tool name '{tool_name}' — must be a valid Python identifier")

    workers_dir = agent_dir / "workers"
    workers_dir.mkdir(parents=True, exist_ok=True)

    # Build parameter string
    params = parameters.strip() if parameters.strip() else "input_data: str"

    # Generate the worker code
    code = f'''"""Worker: {tool_name} — {description}

Auto-generated by Agentspan Claw orchestrator.
"""

from __future__ import annotations

import os

import httpx

from agentspan.agents import tool


@tool
def {tool_name}({params}) -> str:
    """{description}"""
'''

    if api_docs:
        code += f'''    # API Reference:
    # {api_docs[:500]}

'''

    code += f'''    # TODO: Implement the tool logic here.
    # Use httpx for HTTP calls, os.environ.get() for credentials.
    raise NotImplementedError("Tool '{tool_name}' needs implementation. Edit {workers_dir / (tool_name + '.py')}")
'''

    worker_path = workers_dir / f"{tool_name}.py"
    worker_path.write_text(code)

    # Update agent.yaml to include the new tool
    yaml_path = agent_dir / "agent.yaml"
    if yaml_path.exists():
        agent_config = yaml.safe_load(yaml_path.read_text()) or {}
        tools_list = agent_config.get("tools", [])
        if tool_name not in tools_list:
            tools_list.append(tool_name)
            agent_config["tools"] = tools_list
            yaml_path.write_text(yaml.dump(agent_config, default_flow_style=False, sort_keys=False))

    return (
        f"Generated worker at {worker_path}\n\n"
        f"```python\n{code}```\n\n"
        f"The tool '{tool_name}' has been added to {agent_name}'s agent.yaml.\n"
        f"Edit the worker file to implement the actual logic, then deploy with deploy_agent."
    )


# ---------------------------------------------------------------------------
# Git-based versioning for ~/.agentspan/autopilot/
# ---------------------------------------------------------------------------


def init_autopilot_repo(config: Optional[AutopilotConfig] = None) -> None:
    """Initialize the ~/.agentspan/autopilot/ directory as a git repo for version tracking.

    Called on first run. Subsequent calls are no-ops if .git already exists.
    """
    import subprocess

    if config is None:
        config = _get_config()

    base_dir = config.autopilot_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    git_dir = base_dir / ".git"
    if git_dir.exists():
        return  # Already initialized

    subprocess.run(
        ["git", "init"],
        cwd=str(base_dir),
        capture_output=True,
        text=True,
        check=True,
    )

    # Create .gitignore
    gitignore = base_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("state.json\n*.pyc\n__pycache__/\n")

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=str(base_dir), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial Agentspan Claw setup", "--allow-empty"],
        cwd=str(base_dir),
        capture_output=True,
        check=True,
    )


def commit_agent_change(agent_name: str, message: str, config: Optional[AutopilotConfig] = None) -> None:
    """Commit changes to an agent's directory in the autopilot git repo."""
    import subprocess

    if config is None:
        config = _get_config()

    base_dir = config.autopilot_dir
    if not (base_dir / ".git").exists():
        init_autopilot_repo(config)

    agent_dir = config.agents_dir / agent_name
    if not agent_dir.exists():
        return

    rel_path = agent_dir.relative_to(base_dir)
    subprocess.run(
        ["git", "add", str(rel_path)],
        cwd=str(base_dir),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"[{agent_name}] {message}", "--allow-empty"],
        cwd=str(base_dir),
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Tool collection for the orchestrator agent
# ---------------------------------------------------------------------------

def get_orchestrator_tools() -> list:
    """Return all orchestrator tools as a list for agent construction."""
    from autopilot.integrations.mcp.tools import add_mcp_integration
    from autopilot.orchestrator.gates import (
        validate_code,
        validate_deployment,
        validate_integrations,
        validate_spec,
    )

    return [
        generate_agent,
        generate_worker,
        resolve_integrations,
        deploy_agent,
        list_agents,
        signal_agent,
        update_agent,
        pause_agent,
        resume_agent,
        archive_agent,
        get_agent_status,
        get_notifications,
        check_credentials,
        prompt_credentials,
        acquire_credentials,
        # MCP integration
        add_mcp_integration,
        # Validation gates
        validate_spec,
        validate_code,
        validate_integrations,
        validate_deployment,
    ]
