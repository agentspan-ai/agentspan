# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Gate conditions for conditional sequential pipelines."""

from dataclasses import dataclass


@dataclass
class TextGate:
    """Stop the pipeline if the agent's output contains the given text.

    When used on an agent in a sequential pipeline (>>), the pipeline
    stops after this agent if its output contains the sentinel text.
    Otherwise, execution continues to the next stage.

    Compiled entirely server-side (INLINE JavaScript) — no worker
    round-trip needed.

    Args:
        text: The sentinel string to search for in the output.
        case_sensitive: Whether the search is case-sensitive (default True).
    """

    text: str
    case_sensitive: bool = True
