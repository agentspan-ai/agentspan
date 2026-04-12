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


# ---------------------------------------------------------------------------
# Creation Tools (LLM-driven, guardrailed)
# ---------------------------------------------------------------------------

@tool
def expand_prompt(seed_prompt: str, clarifications: str = "") -> str:
    """Expand a user's lazy prompt into a full agent specification.

    Takes the user's seed prompt and any clarification answers, and produces
    a structured prompt that the orchestrator LLM will use to generate a
    complete agent spec in YAML format including: name, model, instructions,
    tools needed, trigger type, schedule, credentials required, error handling.

    Returns the expansion template as a string for the LLM to fill in.
    """
    registry = get_default_registry()
    available_integrations = ", ".join(registry.list_integrations())

    template = f"""Based on the user's request and clarifications, create a complete agent specification.

User request: {seed_prompt}
Clarifications: {clarifications or "None provided"}

Generate a YAML agent specification with these fields:
- name: (snake_case, descriptive)
- version: 1
- model: (default to the current model)
- instructions: (detailed instructions for the agent)
- trigger: (type: cron/daemon, schedule if cron)
- tools: (list of builtin: integrations or custom tool names needed)
- credentials: (list of credential names needed)
- error_handling: (max_retries: 3, backoff: exponential, on_failure: pause_and_notify)

Available builtin integrations: {available_integrations}

Return ONLY the YAML specification, no explanation."""
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

    # Parse spec
    try:
        spec = yaml.safe_load(spec_yaml)
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

    # Write agent.yaml
    spec.setdefault("name", name)
    spec.setdefault("version", 1)
    spec.setdefault("model", config.llm_model)
    if "metadata" not in spec:
        spec["metadata"] = {}
    spec["metadata"]["created_at"] = _now_iso()
    spec["metadata"]["created_by"] = "orchestrator"

    yaml_path = agent_dir / "agent.yaml"
    yaml_path.write_text(yaml.dump(spec, default_flow_style=False, sort_keys=False))

    # Write expanded_prompt.md
    instructions = spec.get("instructions", "")
    prompt_path = agent_dir / "expanded_prompt.md"
    prompt_path.write_text(f"# {name}\n\n{instructions}\n")

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

    # Check tools
    available = []
    missing = []
    for ref in tool_refs:
        if isinstance(ref, str) and ref.startswith("builtin:"):
            integration_name = ref[len("builtin:"):]
            tools = registry.get_tools(integration_name)
            if tools:
                available.append(integration_name)
            else:
                missing.append(integration_name)
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

    # Load and start the agent
    try:
        from autopilot.loader import load_agent
        from agentspan.agents import AgentRuntime

        agent = load_agent(agent_dir)

        with AgentRuntime() as runtime:
            handle = runtime.start(agent, "Begin agent execution.")
            execution_id = handle.execution_id

        sm.set(agent_name, AgentState(
            name=agent_name,
            execution_id=execution_id,
            status="ACTIVE",
            trigger_type=trigger_type,
            created_at=created_at,
            last_deployed=_now_iso(),
        ))

        return (
            f"Agent '{agent_name}' deployed successfully.\n"
            f"Execution ID: {execution_id}\n"
            f"Status: ACTIVE"
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

    Reads agent directories from disk and checks state for live execution status.
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

    lines = ["Agents:", ""]
    for name in dirs:
        state = sm.get(name)
        if state:
            status = state.status
            eid = state.execution_id[:12] + "..." if state.execution_id else "—"
            lines.append(f"  {name:30s} {status:10s} exec={eid}")
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

    Reads state and agent.yaml to provide a comprehensive status report.
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

    lines = [
        f"Agent: {agent_name}",
        f"Status: {state.status}",
        f"Trigger: {state.trigger_type}",
        f"Created: {state.created_at}",
    ]

    if state.last_deployed:
        lines.append(f"Last deployed: {state.last_deployed}")

    if state.execution_id:
        lines.append(f"Execution ID: {state.execution_id}")

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

    Checks state for all agents with recent activity. If *since* is provided
    (ISO-8601 timestamp), only shows notifications after that time.
    """
    config = _get_config()
    sm = _get_state_manager(config)
    all_states = sm.list_all()

    if not all_states:
        return "No agents tracked. Nothing to report."

    lines = ["Notifications:", ""]

    active_count = 0
    error_count = 0
    waiting_count = 0

    for state in all_states:
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
        "Use prompt_credentials('<credential_name>') to set up missing credentials, "
        "or run: agentspan credentials set <name> <value>"
    )

    return "\n".join(lines)


@tool
def prompt_credentials(credential_name: str) -> str:
    """Guide the user through setting up a missing credential.

    Returns instructions for the user to configure the named credential
    via the Agentspan CLI.
    """
    return (
        f"To set up the '{credential_name}' credential:\n\n"
        f"1. Run: agentspan credentials set {credential_name} <your-value>\n"
        f"2. Or set it as an environment variable: export {credential_name}=<your-value>\n\n"
        f"The credential will be securely stored on the Agentspan server and "
        f"injected into agent executions automatically."
    )


# ---------------------------------------------------------------------------
# Tool collection for the orchestrator agent
# ---------------------------------------------------------------------------

def get_orchestrator_tools() -> list:
    """Return all orchestrator tools as a list for agent construction."""
    return [
        expand_prompt,
        generate_agent,
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
    ]
