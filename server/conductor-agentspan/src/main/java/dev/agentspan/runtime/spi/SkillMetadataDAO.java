/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.spi;

import java.util.List;
import java.util.Optional;

import dev.agentspan.runtime.model.skill.SkillDetail;

/**
 * Persistence SPI for skill <b>metadata</b> (manifest, versions, and the per-skill "latest"
 * pointer). Skill package <b>bytes</b> are stored separately via {@link SkillPackageStore}.
 *
 * <p>The standalone server ships a filesystem-backed implementation (zero-config, single node);
 * an embedding host (e.g. orkes-conductor) supplies a durable/HA implementation (e.g. Postgres)
 * so skill listings are consistent across nodes.</p>
 *
 * <p>All operations are scoped by {@code ownerId}. Authorization (whether the caller may read a
 * given skill) is the caller's concern, not this DAO's.</p>
 */
public interface SkillMetadataDAO {

    /**
     * Persist a skill version's metadata (create or overwrite).
     *
     * @param detail     metadata to store, keyed by {@code ownerId + name + version}
     * @param makeLatest when {@code true}, mark this version as the skill's latest
     */
    void save(SkillDetail detail, boolean makeLatest);

    /** Exact-version lookup. */
    Optional<SkillDetail> find(String ownerId, String name, String version);

    /** The recorded latest version string for a skill, if any. */
    Optional<String> latestVersion(String ownerId, String name);

    /** All recorded versions of a single skill (unordered). */
    List<SkillDetail> listVersions(String ownerId, String name);

    /**
     * All skills for an owner. When {@code allVersions} is {@code false}, returns only each
     * skill's latest version; when {@code true}, returns every version of every skill.
     */
    List<SkillDetail> list(String ownerId, boolean allVersions);

    /** Remove a single version and recompute the skill's latest pointer if needed. */
    void delete(String ownerId, String name, String version);
}
