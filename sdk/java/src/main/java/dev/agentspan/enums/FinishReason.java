// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.enums;

/**
 * Why the agent stopped executing.
 */
public enum FinishReason {
    STOP,
    LENGTH,
    TOOL_CALLS,
    ERROR,
    CANCELLED,
    TIMEOUT,
    GUARDRAIL,
    REJECTED
}
