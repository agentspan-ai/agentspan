/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service.skill;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.model.skill.SkillDetail;
import dev.agentspan.runtime.spi.SkillMetadataDAO;

/**
 * Default {@link SkillMetadataDAO} — stores skill metadata as {@code metadata.json} files on the
 * local filesystem under {@code <storage>/<name>/<version>/}, with a per-skill {@code latest}
 * pointer file. This is the standalone-server default; skills are global (no per-caller
 * scoping). Embedding hosts (e.g. orkes-conductor) supply a durable/HA implementation instead
 * (this class ships only in {@code conductor-agentspan-server}, so it is never on an embedding
 * host's classpath).
 */
@Component
public class FileSystemSkillMetadataDAO implements SkillMetadataDAO {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Path storageRoot;

    public FileSystemSkillMetadataDAO(
            @Value("${agentspan.skills.storage.directory:${java.io.tmpdir}/agentspan/skills}") String storageDir) {
        this.storageRoot = Path.of(storageDir).toAbsolutePath().normalize();
    }

    @Override
    public void save(SkillDetail detail, boolean makeLatest) {
        Path metadataPath = metadataPath(detail.getName(), detail.getVersion());
        try {
            Files.createDirectories(metadataPath.getParent());
            writeDetail(metadataPath, detail);
            if (makeLatest) {
                Files.writeString(latestPath(detail.getName()), detail.getVersion(), StandardCharsets.UTF_8);
            }
        } catch (IOException e) {
            throw new IllegalStateException("Failed to write skill metadata: " + e.getMessage(), e);
        }
    }

    @Override
    public Optional<SkillDetail> find(String name, String version) {
        Path metadataPath = metadataPath(name, version);
        if (!Files.exists(metadataPath)) {
            return Optional.empty();
        }
        return Optional.of(readDetail(metadataPath));
    }

    @Override
    public Optional<String> latestVersion(String name) {
        Path latest = latestPath(name);
        if (!Files.exists(latest)) {
            return Optional.empty();
        }
        try {
            return Optional.of(Files.readString(latest, StandardCharsets.UTF_8).trim());
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read latest skill version: " + e.getMessage(), e);
        }
    }

    @Override
    public List<SkillDetail> listVersions(String name) {
        Path skillRoot = skillRoot(name);
        List<SkillDetail> details = new ArrayList<>();
        if (!Files.isDirectory(skillRoot)) {
            return details;
        }
        try (var versions = Files.list(skillRoot)) {
            for (Path versionPath : versions.filter(Files::isDirectory).toList()) {
                Path metadata = versionPath.resolve("metadata.json");
                if (Files.exists(metadata)) {
                    details.add(readDetail(metadata));
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("Failed to list skill versions: " + e.getMessage(), e);
        }
        return details;
    }

    @Override
    public List<SkillDetail> list(boolean allVersions) {
        List<SkillDetail> details = new ArrayList<>();
        if (!Files.isDirectory(storageRoot)) {
            return details;
        }
        try (var skillDirs = Files.list(storageRoot)) {
            for (Path skillDir : skillDirs.filter(Files::isDirectory).toList()) {
                if (allVersions) {
                    try (var versions = Files.list(skillDir)) {
                        for (Path versionPath :
                                versions.filter(Files::isDirectory).toList()) {
                            Path metadata = versionPath.resolve("metadata.json");
                            if (Files.exists(metadata)) {
                                details.add(readDetail(metadata));
                            }
                        }
                    }
                } else {
                    Path latest = skillDir.resolve("latest");
                    if (Files.exists(latest)) {
                        String version =
                                Files.readString(latest, StandardCharsets.UTF_8).trim();
                        Path metadata = skillDir.resolve(encoded(version)).resolve("metadata.json");
                        if (Files.exists(metadata)) {
                            details.add(readDetail(metadata));
                        }
                    }
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("Failed to list skills: " + e.getMessage(), e);
        }
        return details;
    }

    @Override
    public void delete(String name, String version) {
        Path dir = versionDir(name, version);
        if (!Files.exists(dir)) {
            return;
        }
        try (var paths = Files.walk(dir)) {
            for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
            Path latest = latestPath(name);
            if (Files.exists(latest)
                    && version.equals(
                            Files.readString(latest, StandardCharsets.UTF_8).trim())) {
                updateLatestAfterDelete(name);
            }
        } catch (IOException e) {
            throw new IllegalStateException("Failed to delete skill metadata: " + e.getMessage(), e);
        }
    }

    private void updateLatestAfterDelete(String name) throws IOException {
        Path skillRoot = skillRoot(name);
        if (!Files.isDirectory(skillRoot)) {
            Files.deleteIfExists(latestPath(name));
            return;
        }
        List<SkillDetail> remaining = listVersions(name);
        if (remaining.isEmpty()) {
            Files.deleteIfExists(latestPath(name));
            try (var children = Files.list(skillRoot)) {
                if (children.findAny().isEmpty()) {
                    Files.deleteIfExists(skillRoot);
                }
            }
            return;
        }
        remaining.sort(Comparator.comparing(SkillDetail::getCreatedAt, Comparator.nullsFirst(Long::compareTo))
                .thenComparing(SkillDetail::getVersion));
        Files.writeString(latestPath(name), remaining.get(remaining.size() - 1).getVersion(), StandardCharsets.UTF_8);
    }

    private SkillDetail readDetail(Path metadataPath) {
        try {
            return MAPPER.readValue(metadataPath.toFile(), SkillDetail.class);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read skill metadata: " + e.getMessage(), e);
        }
    }

    private void writeDetail(Path metadataPath, SkillDetail detail) {
        try {
            MAPPER.writerWithDefaultPrettyPrinter().writeValue(metadataPath.toFile(), detail);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to write skill metadata: " + e.getMessage(), e);
        }
    }

    private Path skillRoot(String name) {
        return storageRoot.resolve(encoded(name));
    }

    private Path versionDir(String name, String version) {
        return skillRoot(name).resolve(encoded(version));
    }

    private Path metadataPath(String name, String version) {
        return versionDir(name, version).resolve("metadata.json");
    }

    private Path latestPath(String name) {
        return skillRoot(name).resolve("latest");
    }

    private String encoded(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
