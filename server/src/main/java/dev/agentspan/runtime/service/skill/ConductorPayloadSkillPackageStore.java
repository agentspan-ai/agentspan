/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service.skill;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import com.netflix.conductor.common.run.ExternalStorageLocation;
import com.netflix.conductor.common.utils.ExternalPayloadStorage;
import com.netflix.conductor.common.utils.ExternalPayloadStorage.Operation;
import com.netflix.conductor.common.utils.ExternalPayloadStorage.PayloadType;

@Component
@ConditionalOnProperty(prefix = "agentspan.skills.package-store", name = "type", havingValue = "conductor-payload")
public class ConductorPayloadSkillPackageStore implements SkillPackageStore {

    private static final String HANDLE_PREFIX = "conductor-payload://";

    private final ExternalPayloadStorage payloadStorage;

    public ConductorPayloadSkillPackageStore(ExternalPayloadStorage payloadStorage) {
        this.payloadStorage = payloadStorage;
    }

    @Override
    public String storageType() {
        return "conductor-payload";
    }

    @Override
    public StoredSkillPackage store(String name, String version, String checksum, byte[] bytes) {
        String requestedPath = storagePath(name, version, checksum);
        ExternalStorageLocation location =
                payloadStorage.getLocation(Operation.WRITE, PayloadType.WORKFLOW_INPUT, requestedPath, bytes);
        String path = location.getPath() != null && !location.getPath().isBlank() ? location.getPath() : requestedPath;
        payloadStorage.upload(path, new ByteArrayInputStream(bytes), bytes.length);
        return new StoredSkillPackage(HANDLE_PREFIX + encoded(path), storageType(), bytes.length);
    }

    @Override
    public byte[] read(String handle) {
        String path = pathForHandle(handle);
        try (InputStream in = payloadStorage.download(path)) {
            return in.readAllBytes();
        } catch (IOException e) {
            throw new IllegalArgumentException("Skill package not found: " + handle, e);
        }
    }

    @Override
    public boolean exists(String handle) {
        try {
            read(handle);
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    @Override
    public void delete(String handle) {
        // Conductor ExternalPayloadStorage is immutable/write-read only. Registry
        // deletion removes metadata immediately; blob reclamation is left to the
        // backing store's retention/GC policy.
    }

    private String storagePath(String name, String version, String checksum) {
        return "agentspan/skills/" + encoded(name) + "/" + encoded(version) + "/" + encoded(checksum) + ".zip";
    }

    private String pathForHandle(String handle) {
        if (handle == null || !handle.startsWith(HANDLE_PREFIX)) {
            throw new IllegalArgumentException("Unsupported skill package handle: " + handle);
        }
        return decoded(handle.substring(HANDLE_PREFIX.length()));
    }

    private static String encoded(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static String decoded(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }
}
