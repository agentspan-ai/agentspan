/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service.skill;

import java.io.IOException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "agentspan.skills.package-store",
        name = "type",
        havingValue = "filesystem",
        matchIfMissing = true)
public class FileSystemSkillPackageStore implements SkillPackageStore {

    private static final String HANDLE_PREFIX = "agentspan-fs://";

    private final Path packageRoot;

    public FileSystemSkillPackageStore(
            @Value(
                            "${agentspan.skills.package-store.filesystem.directory:${agentspan.skills.storage.directory:${java.io.tmpdir}/agentspan/skills}/packages}")
                    String packageDirectory) {
        this.packageRoot = Path.of(packageDirectory).toAbsolutePath().normalize();
    }

    @Override
    public String storageType() {
        return "filesystem";
    }

    @Override
    public StoredSkillPackage store(String name, String version, String checksum, byte[] bytes) {
        Path path = packagePath(name, version, checksum);
        try {
            Files.createDirectories(path.getParent());
            Path tmp = Files.createTempFile(path.getParent(), "skill-", ".zip.tmp");
            Files.write(tmp, bytes);
            Files.move(tmp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            return new StoredSkillPackage(handleFor(name, version, checksum), storageType(), bytes.length);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to store skill package: " + e.getMessage(), e);
        }
    }

    @Override
    public byte[] read(String handle) {
        Path path = pathForHandle(handle);
        try {
            return Files.readAllBytes(path);
        } catch (IOException e) {
            throw new IllegalArgumentException("Skill package not found: " + handle, e);
        }
    }

    @Override
    public boolean exists(String handle) {
        return Files.exists(pathForHandle(handle));
    }

    @Override
    public void delete(String handle) {
        try {
            Files.deleteIfExists(pathForHandle(handle));
        } catch (IOException e) {
            throw new IllegalStateException("Failed to delete skill package: " + e.getMessage(), e);
        }
    }

    private Path packagePath(String name, String version, String checksum) {
        return packageRoot
                .resolve(encoded(name))
                .resolve(encoded(version))
                .resolve(encoded(checksum) + ".zip")
                .normalize();
    }

    private String handleFor(String name, String version, String checksum) {
        return HANDLE_PREFIX + encoded(name) + "/" + encoded(version) + "/" + encoded(checksum);
    }

    private Path pathForHandle(String handle) {
        if (handle == null || !handle.startsWith(HANDLE_PREFIX)) {
            throw new IllegalArgumentException("Unsupported skill package handle: " + handle);
        }
        String raw = handle.substring(HANDLE_PREFIX.length());
        String[] parts = raw.split("/");
        if (parts.length != 3) {
            throw new IllegalArgumentException("Invalid skill package handle: " + handle);
        }
        return packagePath(decoded(parts[0]), decoded(parts[1]), decoded(parts[2]));
    }

    private static String encoded(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static String decoded(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }
}
