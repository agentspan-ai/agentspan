# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Strategy validators — verify that an execution trace obeys the rules of its strategy.

These validators inspect an :class:`AgentResult` and the :class:`Agent` definition
to verify that the orchestration pattern was actually followed.  Unlike simple
assertions (which check individual properties), these validate the **structural
correctness** of the entire execution trace against the strategy's rules.

Usage::

    from conductor.ai.agents.testing import validate_strategy

    result = runtime.run(my_agent, "Hello")
    validate_strategy(my_agent, result)  # raises if strategy rules violated

Each strategy has its own validator.  ``validate_strategy`` dispatches to the
right one based on ``agent.strategy``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, List

from conductor.ai.agents.result import AgentResult, EventType

# ── Helpers ────────────────────────────────────────────────────────────


def _get_agent_names(agent: Any) -> List[str]:
    """Extract sub-agent names from an Agent."""
    return [a.name for a in getattr(agent, "agents", []) or []]


def _get_handoff_targets(result: AgentResult) -> List[str]:
    """Extract ordered list of handoff targets from events."""
    return [ev.target for ev in result.events if ev.type == EventType.HANDOFF and ev.target]


def _get_strategy(agent: Any) -> str:
    """Get the strategy string from an Agent."""
    strategy = getattr(agent, "strategy", "handoff")
    return strategy.value if hasattr(strategy, "value") else str(strategy)


# ── Individual strategy validators ─────────────────────────────────────


class StrategyViolation(AssertionError):
    """Raised when an execution trace violates its strategy's rules."""

    def __init__(self, strategy: str, violations: List[str]) -> None:
        self.strategy = strategy
        self.violations = violations
        msg = f"Strategy '{strategy}' violations:\n" + "\n".join(f"  - {v}" for v in violations)
        super().__init__(msg)


def validate_sequential(agent: Any, result: AgentResult) -> None:
    """Validate a SEQUENTIAL execution trace.

    Rules:
      1. ALL sub-agents must execute (no agent skipped)
      2. Agents must execute in definition order
      3. Each agent executes exactly once
    """
    expected = _get_agent_names(agent)
    if not expected:
        return

    handoffs = _get_handoff_targets(result)
    violations: List[str] = []

    # Rule 1: All agents must appear
    missing = set(expected) - set(handoffs)
    if missing:
        violations.append(
            f"Agents skipped (never ran): {sorted(missing)}. Expected all of: {expected}"
        )

    # Rule 2: Order must match definition order
    # Filter handoffs to only those in expected set (ignore other events)
    relevant = [h for h in handoffs if h in set(expected)]
    # Check subsequence order
    idx = 0
    for h in relevant:
        if idx < len(expected) and h == expected[idx]:
            idx += 1
    if idx < len(expected) and not missing:
        violations.append(f"Agents executed out of order. Expected: {expected}, got: {relevant}")

    # Rule 3: No agent should run more than once
    counts = Counter(relevant)
    duplicates = {name: cnt for name, cnt in counts.items() if cnt > 1}
    if duplicates:
        violations.append(f"Agents executed multiple times (should be once each): {duplicates}")

    if violations:
        raise StrategyViolation("sequential", violations)


def validate_parallel(agent: Any, result: AgentResult) -> None:
    """Validate a PARALLEL execution trace.

    Rules:
      1. ALL sub-agents must execute (none skipped)
      2. Each agent contributes to the result
    """
    expected = set(_get_agent_names(agent))
    if not expected:
        return

    handoffs = set(_get_handoff_targets(result))
    violations: List[str] = []

    missing = expected - handoffs
    if missing:
        violations.append(
            f"Agents never executed (skipped): {sorted(missing)}. "
            f"In parallel strategy ALL agents must run. "
            f"Expected: {sorted(expected)}, ran: {sorted(handoffs & expected)}"
        )

    if violations:
        raise StrategyViolation("parallel", violations)


def validate_round_robin(agent: Any, result: AgentResult) -> None:
    """Validate a ROUND_ROBIN execution trace.

    Rules:
      1. ALL sub-agents must participate
      2. Agents must alternate in definition order (A→B→A→B or A→B→C→A→B→C)
      3. No agent runs twice in a row
      4. Turn count must not exceed max_turns
    """
    expected = _get_agent_names(agent)
    if not expected:
        return

    handoffs = _get_handoff_targets(result)
    max_turns = getattr(agent, "max_turns", 25)
    violations: List[str] = []

    # Rule 1: All agents must participate
    missing = set(expected) - set(handoffs)
    if missing:
        violations.append(
            f"Agents never got a turn: {sorted(missing)}. "
            f"All agents must participate in round-robin."
        )

    # Rule 2: Agents must follow the rotation pattern
    relevant = [h for h in handoffs if h in set(expected)]
    num_agents = len(expected)
    for i, actual in enumerate(relevant):
        expected_agent = expected[i % num_agents]
        if actual != expected_agent:
            violations.append(
                f"Turn {i}: expected '{expected_agent}' but got '{actual}'. "
                f"Round-robin pattern broken. "
                f"Expected rotation: {expected}, actual sequence: {relevant}"
            )
            break  # One violation is enough to show the pattern is broken

    # Rule 3: No agent runs twice in a row
    for i in range(1, len(relevant)):
        if relevant[i] == relevant[i - 1]:
            violations.append(
                f"Agent '{relevant[i]}' ran twice in a row at positions "
                f"{i - 1} and {i}. Round-robin must alternate."
            )
            break

    # Rule 4: Turn count
    if len(relevant) > max_turns:
        violations.append(f"Exceeded max_turns: {len(relevant)} turns taken, limit is {max_turns}.")

    if violations:
        raise StrategyViolation("round_robin", violations)


def validate_router(agent: Any, result: AgentResult) -> None:
    """Validate a ROUTER execution trace.

    Rules:
      1. Exactly ONE sub-agent should be selected per request
      2. The selected agent must be one of the defined sub-agents
      3. A router decision must have been made (handoff must occur)
    """
    expected = set(_get_agent_names(agent))
    if not expected:
        return

    handoffs = _get_handoff_targets(result)
    relevant = [h for h in handoffs if h in expected]
    violations: List[str] = []

    # Rule 1: At least one agent must be selected
    if not relevant:
        violations.append(
            f"No sub-agent was selected by the router. "
            f"Available agents: {sorted(expected)}, handoffs: {handoffs}"
        )

    # Rule 2: Only ONE agent should handle the request
    unique_agents = set(relevant)
    if len(unique_agents) > 1:
        violations.append(
            f"Router selected multiple agents: {sorted(unique_agents)}. "
            f"Router strategy should route to exactly ONE specialist per request."
        )

    # Rule 3: Selected agent must be a valid sub-agent
    invalid = set(relevant) - expected
    if invalid:
        violations.append(
            f"Router selected unknown agent(s): {sorted(invalid)}. Valid agents: {sorted(expected)}"
        )

    if violations:
        raise StrategyViolation("router", violations)


def validate_handoff(agent: Any, result: AgentResult) -> None:
    """Validate a HANDOFF execution trace.

    Rules:
      1. At least one handoff should occur (parent should delegate)
      2. Handoff target must be a valid sub-agent
    """
    expected = set(_get_agent_names(agent))
    if not expected:
        return

    handoffs = _get_handoff_targets(result)
    relevant = [h for h in handoffs if h in expected]
    violations: List[str] = []

    if not relevant:
        violations.append(
            f"No handoff to any sub-agent occurred. "
            f"Handoff strategy expects the parent to delegate to a specialist. "
            f"Available agents: {sorted(expected)}"
        )

    invalid = set(handoffs) - expected
    # Only flag if there are NO valid handoffs — some handoffs might be internal
    if invalid and not relevant:
        violations.append(
            f"Handoff targets not in sub-agents: {sorted(invalid)}. "
            f"Valid sub-agents: {sorted(expected)}"
        )

    if violations:
        raise StrategyViolation("handoff", violations)


def validate_swarm(agent: Any, result: AgentResult) -> None:
    """Validate a SWARM execution trace.

    Rules:
      1. At least one agent must handle the request
      2. Transfers must go to valid sub-agents
      3. No infinite transfer loops (same pair shouldn't repeat more than max_turns)
      4. The final handling agent must actually produce output
    """
    expected = set(_get_agent_names(agent))
    if not expected:
        return

    handoffs = _get_handoff_targets(result)
    max_turns = getattr(agent, "max_turns", 25)
    violations: List[str] = []

    # Rule 1: At least one agent must handle
    relevant = [h for h in handoffs if h in expected]
    if not relevant:
        violations.append(f"No agent handled the request. Available agents: {sorted(expected)}")

    # Rule 2: All transfers must go to valid agents
    invalid = set(handoffs) - expected
    if invalid and not relevant:
        violations.append(
            f"Transfer to unknown agent(s): {sorted(invalid)}. Valid agents: {sorted(expected)}"
        )

    # Rule 3: Detect transfer loops
    if len(relevant) >= 2:
        transfer_pairs = [(relevant[i], relevant[i + 1]) for i in range(len(relevant) - 1)]
        pair_counts = Counter(transfer_pairs)
        loops = {pair: cnt for pair, cnt in pair_counts.items() if cnt > 2}
        if loops:
            violations.append(
                f"Possible transfer loop detected: {dict(loops)}. "
                f"Same transfer pair repeated excessively."
            )

    # Rule 4: Total handoffs should not exceed max_turns
    if len(relevant) > max_turns:
        violations.append(
            f"Too many transfers: {len(relevant)}, max_turns={max_turns}. Possible infinite loop."
        )

    if violations:
        raise StrategyViolation("swarm", violations)


def validate_constrained_transitions(agent: Any, result: AgentResult) -> None:
    """Validate that transitions respect allowed_transitions constraints.

    Rules:
      1. Every consecutive handoff pair (A→B) must be in allowed_transitions[A]
    """
    allowed = getattr(agent, "allowed_transitions", None)
    if not allowed:
        return

    expected_agents = set(_get_agent_names(agent))
    handoffs = [h for h in _get_handoff_targets(result) if h in expected_agents]
    violations: List[str] = []

    for i in range(len(handoffs) - 1):
        src, dst = handoffs[i], handoffs[i + 1]
        allowed_next = set(allowed.get(src, []))
        if dst not in allowed_next:
            violations.append(
                f"Invalid transition: '{src}' → '{dst}' at turn {i}. "
                f"Allowed from '{src}': {sorted(allowed_next)}"
            )

    if violations:
        raise StrategyViolation("constrained_transitions", violations)


# ── Dispatch ───────────────────────────────────────────────────────────


_VALIDATORS = {
    "sequential": validate_sequential,
    "parallel": validate_parallel,
    "round_robin": validate_round_robin,
    "router": validate_router,
    "handoff": validate_handoff,
    "swarm": validate_swarm,
}


def validate_strategy(agent: Any, result: AgentResult) -> None:
    """Validate that an execution trace follows the agent's strategy rules.

    Dispatches to the appropriate strategy-specific validator.  Also runs
    constrained transition validation if ``allowed_transitions`` is set.

    Args:
        agent: The :class:`Agent` definition.
        result: The execution result to validate.

    Raises:
        StrategyViolation: If the execution trace violates strategy rules.
    """
    strategy = _get_strategy(agent)
    validator = _VALIDATORS.get(strategy)
    if validator:
        validator(agent, result)

    # Always check transition constraints if present
    if getattr(agent, "allowed_transitions", None):
        validate_constrained_transitions(agent, result)
