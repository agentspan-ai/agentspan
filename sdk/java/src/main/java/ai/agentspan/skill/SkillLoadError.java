// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.skill;

/**
 * Thrown when a skill directory cannot be loaded.
 */
public class SkillLoadError extends RuntimeException {

    public SkillLoadError(String message) {
        super(message);
    }

    public SkillLoadError(String message, Throwable cause) {
        super(message, cause);
    }
}
