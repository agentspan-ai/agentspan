/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package org.conductoross.conductor.ai.internal;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Field;
import java.util.List;

import org.conductoross.conductor.ai.AgentConfig;
import org.junit.jupiter.api.Test;

import com.netflix.conductor.client.http.ConductorClient;
import com.netflix.conductor.client.http.MetadataClient;
import com.netflix.conductor.common.metadata.tasks.TaskDef;

/**
 * Worker TaskDefs are registered create-only: the SDK creates the def when absent but never
 * overwrites one that already exists. When embedded, the host server pre-registers the worker
 * TaskDef and declares its secret names on TaskDef.runtimeMetadata (conductor-oss PR #1255);
 * overwriting here with a bare def (the client TaskDef model has no runtimeMetadata field) would
 * clobber that and starve the host resolver. No embedded flag — the existence check decides.
 */
class EmbeddedTaskDefRegistrationTest {

    /** Fake client: reports whether a def "exists" and records any registration, without network. */
    private static final class RecordingMetadataClient extends MetadataClient {
        private final boolean exists;
        boolean registered = false;

        RecordingMetadataClient(boolean exists) {
            this.exists = exists;
        }

        @Override
        public TaskDef getTaskDef(String taskType) {
            return exists ? new TaskDef(taskType) : null;
        }

        @Override
        public void registerTaskDefs(List<TaskDef> taskDefs) {
            this.registered = true;
        }
    }

    private static boolean didRegister(boolean alreadyExists) throws Exception {
        WorkerManager wm = new WorkerManager(new AgentConfig(), new ConductorClient());
        RecordingMetadataClient client = new RecordingMetadataClient(alreadyExists);
        Field f = WorkerManager.class.getDeclaredField("metadataClient");
        f.setAccessible(true);
        f.set(wm, client);
        wm.registerTaskDef("check_secret", 300);
        return client.registered;
    }

    @Test
    void doesNotOverwriteExistingTaskDef() throws Exception {
        // Existing def (e.g. server-registered with runtimeMetadata) must be left untouched.
        assertFalse(didRegister(true), "must not overwrite an existing TaskDef");
    }

    @Test
    void createsTaskDefWhenAbsent() throws Exception {
        assertTrue(didRegister(false), "must create the TaskDef when none exists");
    }
}
