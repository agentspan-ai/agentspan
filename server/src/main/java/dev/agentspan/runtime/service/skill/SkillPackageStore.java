/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service.skill;

public interface SkillPackageStore {

    String storageType();

    StoredSkillPackage store(String name, String version, String checksum, byte[] bytes);

    byte[] read(String handle);

    boolean exists(String handle);

    void delete(String handle);
}
