# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Generic framework support for running foreign agents on the Conductor runtime.

This package contains zero framework-specific code. It provides:
- Auto-detection of agent framework from object type
- Generic deep serialization of any agent object to JSON
- Callable extraction and worker registration
"""

from conductor.ai.agents.frameworks.serializer import (
    WorkerInfo,
    detect_framework,
    serialize_agent,
)

__all__ = ["detect_framework", "serialize_agent", "WorkerInfo"]
