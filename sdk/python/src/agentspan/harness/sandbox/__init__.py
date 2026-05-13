# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Sandbox — separation of policy (permissions) from enforcement (sandbox)."""

from .checks import ChecksOnlySandbox
from .interface import Sandbox, SandboxResult

__all__ = ["ChecksOnlySandbox", "Sandbox", "SandboxResult"]
