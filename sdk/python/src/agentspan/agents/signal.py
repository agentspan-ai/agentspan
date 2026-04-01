# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class SignalReceipt:
    """Returned immediately when a signal is sent — confirms it was queued."""
    signal_id: str
    execution_id: str
    status: str  # Always "queued" at send time


@dataclass
class SignalStatus:
    """Current disposition of a signal — returned by get_signal_status()."""
    signal_id: str
    execution_id: str
    delivered: bool
    disposition: str  # "pending" | "accepted" | "rejected" | "accepted_implicit"
    rejection_reason: Optional[str] = None
