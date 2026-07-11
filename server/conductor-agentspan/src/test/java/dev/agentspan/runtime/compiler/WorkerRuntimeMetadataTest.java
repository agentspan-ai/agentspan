/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.compiler;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.netflix.conductor.common.metadata.tasks.TaskDef;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import com.netflix.conductor.dao.MetadataDAO;
import com.netflix.conductor.service.MetadataService;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.GuardrailConfig;
import dev.agentspan.runtime.model.TerminationConfig;
import dev.agentspan.runtime.model.ToolConfig;
import dev.agentspan.runtime.service.AgentService;
import dev.agentspan.runtime.util.EmbeddedMode;

/**
 * Target-state worker-secret delivery (conductor-oss PR #1255): in EMBEDDED mode the worker's
 * {@link TaskDef} declares its secret names on {@code runtimeMetadata}; the host resolves them at the
 * SIMPLE task's own poll and injects the values onto the wire-only {@code Task.runtimeMetadata} — the
 * enrich script never stamps {@code __resolved_credentials__} into persisted task input. Standalone
 * leaves {@code runtimeMetadata} empty (the native execution-token pull delivers secrets instead).
 */
class WorkerRuntimeMetadataTest {

    @AfterEach
    void resetEmbedded() {
        new EmbeddedMode().setEmbedded(false);
    }

    private static ToolConfig worker(String name, String... creds) {
        return ToolConfig.builder()
                .name(name)
                .description(name)
                .toolType("worker")
                .config(Map.of("credentials", List.of(creds)))
                .build();
    }

    private static AgentConfig agentWith(ToolConfig tool) {
        return AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .tools(List.of(tool))
                .build();
    }

    // ── The enrich script must NOT stamp __resolved_credentials__ (the retired interim) ──

    @Test
    void enrichScript_neverStampsResolvedCredentials_embedded() {
        new EmbeddedMode().setEmbedded(true);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        Object[] r = new ToolCompiler().buildEnrichTask("agent", "agent_llm", List.of(gh), "");
        String script = (String) ((WorkflowTask) r[0]).getInputParameters().get("expression");
        assertThat(script).doesNotContain("__resolved_credentials__");
    }

    @Test
    void enrichScript_neverStampsResolvedCredentials_standalone() {
        new EmbeddedMode().setEmbedded(false);
        ToolConfig gh = worker("gh", "GITHUB_TOKEN");
        Object[] r = new ToolCompiler().buildEnrichTask("agent", "agent_llm", List.of(gh), "");
        String script = (String) ((WorkflowTask) r[0]).getInputParameters().get("expression");
        assertThat(script).doesNotContain("__resolved_credentials__");
    }

    // ── AgentService declares runtimeMetadata on the worker TaskDef in BOTH modes ──
    // runtimeMetadata is the only credential-delivery path now (the native token pull is
    // gone): embedded, the host resolves the names at poll; standalone, the built-in
    // conductor core resolves them via AgentspanSecretsDAO. So the declaration must not
    // be gated on EmbeddedMode.

    @Test
    void embedded_stampsRuntimeMetadataOnWorkerTaskDef() throws Exception {
        new EmbeddedMode().setEmbedded(true);
        TaskDef registered = registerWorkerTaskDef("gh", List.of("GITHUB_TOKEN"));
        assertThat(registered.getRuntimeMetadata()).containsExactly("GITHUB_TOKEN");
    }

    @Test
    void standalone_alsoStampsRuntimeMetadata() throws Exception {
        new EmbeddedMode().setEmbedded(false);
        TaskDef registered = registerWorkerTaskDef("gh", List.of("GITHUB_TOKEN"));
        assertThat(registered.getRuntimeMetadata()).containsExactly("GITHUB_TOKEN");
    }

    @Test
    void collectToolCredentials_mapsWorkerToItsSecretNames() {
        AgentConfig config = agentWith(worker("gh", "GITHUB_TOKEN", "GH_APP_ID"));
        Map<String, List<String>> creds = AgentCompiler.collectToolCredentials(config);
        assertThat(creds.get("gh")).containsExactlyInAnyOrder("GITHUB_TOKEN", "GH_APP_ID");
    }

    // ── Agent-level creds feed the non-worker user-code task defs (guardrail/callback/etc.) ──

    @Test
    void collectAgentCredentials_returnsDedupedOrdered() {
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .credentials(List.of("A", "B", "A"))
                .build();
        assertThat(AgentCompiler.collectAgentCredentials(config)).containsExactly("A", "B");
    }

    @Test
    void collectAgentCredentials_emptyWhenNoneDeclared() {
        AgentConfig config =
                AgentConfig.builder().name("a").model("openai/gpt-4o").build();
        assertThat(AgentCompiler.collectAgentCredentials(config)).isEmpty();
    }

    /**
     * Wiring test: embedded, {@code collectAndRegisterTasks} must declare the agent-level creds on a
     * custom-guardrail worker's {@link TaskDef} (user code → needs secrets), but leave the declarative
     * {@code _termination} def empty (no user function runs there). Fails until agent-level creds are
     * threaded into the guardrail registration site.
     */
    @Test
    void embedded_declaresAgentCredsOnGuardrailButNotTermination() throws Exception {
        new EmbeddedMode().setEmbedded(true);
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .credentials(List.of("DEMO_SECRET"))
                .guardrails(List.of(GuardrailConfig.builder()
                        .guardrailType("custom")
                        .taskName("a_guard")
                        .build()))
                .termination(TerminationConfig.builder().build())
                .build();

        Map<String, TaskDef> defs = registerAllTaskDefs(config);

        assertThat(defs.get("a_guard").getRuntimeMetadata()).containsExactly("DEMO_SECRET");
        assertThat(defs.get("a_termination").getRuntimeMetadata()).isNullOrEmpty();
    }

    @Test
    void standalone_alsoDeclaresNonWorkerRuntimeMetadata() throws Exception {
        new EmbeddedMode().setEmbedded(false);
        AgentConfig config = AgentConfig.builder()
                .name("a")
                .model("openai/gpt-4o")
                .credentials(List.of("DEMO_SECRET"))
                .guardrails(List.of(GuardrailConfig.builder()
                        .guardrailType("custom")
                        .taskName("a_guard")
                        .build()))
                .build();

        Map<String, TaskDef> defs = registerAllTaskDefs(config);

        assertThat(defs.get("a_guard").getRuntimeMetadata()).containsExactly("DEMO_SECRET");
    }

    /**
     * Drive {@link AgentService}'s private {@code registerTaskDefinitions(AgentConfig)} and return every
     * {@link TaskDef} handed to {@code MetadataService.registerTaskDef}, keyed by task name — so a test
     * can assert per-task-kind {@code runtimeMetadata}.
     */
    private static Map<String, TaskDef> registerAllTaskDefs(AgentConfig config) throws Exception {
        MetadataDAO metadataDAO = mock(MetadataDAO.class);
        MetadataService metadataService = mock(MetadataService.class);

        AgentService service = new AgentService(
                mock(dev.agentspan.runtime.compiler.AgentCompiler.class),
                mock(dev.agentspan.runtime.normalizer.NormalizerRegistry.class),
                mock(com.netflix.conductor.dao.ExecutionDAO.class),
                metadataDAO,
                mock(com.netflix.conductor.core.execution.WorkflowExecutor.class),
                mock(com.netflix.conductor.service.WorkflowService.class),
                mock(dev.agentspan.runtime.service.AgentStreamRegistry.class),
                mock(com.netflix.conductor.service.ExecutionService.class),
                mock(dev.agentspan.runtime.util.ProviderValidator.class));

        Field msField = AgentService.class.getDeclaredField("metadataService");
        msField.setAccessible(true);
        msField.set(service, metadataService);

        Method m = AgentService.class.getDeclaredMethod("registerTaskDefinitions", AgentConfig.class);
        m.setAccessible(true);
        m.invoke(service, config);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<TaskDef>> captor = ArgumentCaptor.forClass(List.class);
        verify(metadataService, atLeastOnce()).registerTaskDef(captor.capture());
        Map<String, TaskDef> byName = new HashMap<>();
        for (List<TaskDef> batch : captor.getAllValues()) {
            for (TaskDef def : batch) {
                byName.put(def.getName(), def);
            }
        }
        return byName;
    }

    /**
     * Drive {@link AgentService}'s private {@code registerTaskDef(String, List)} with the credential
     * names {@link AgentCompiler#collectToolCredentials} yields for {@code toolName}, and capture the
     * {@link TaskDef} handed to {@code MetadataService.registerTaskDef}.
     */
    private static TaskDef registerWorkerTaskDef(String toolName, List<String> creds) throws Exception {
        MetadataDAO metadataDAO = mock(MetadataDAO.class);
        MetadataService metadataService = mock(MetadataService.class);
        when(metadataDAO.getTaskDef(toolName)).thenReturn(null);

        AgentService service = new AgentService(
                mock(dev.agentspan.runtime.compiler.AgentCompiler.class),
                mock(dev.agentspan.runtime.normalizer.NormalizerRegistry.class),
                mock(com.netflix.conductor.dao.ExecutionDAO.class),
                metadataDAO,
                mock(com.netflix.conductor.core.execution.WorkflowExecutor.class),
                mock(com.netflix.conductor.service.WorkflowService.class),
                mock(dev.agentspan.runtime.service.AgentStreamRegistry.class),
                mock(com.netflix.conductor.service.ExecutionService.class),
                mock(dev.agentspan.runtime.util.ProviderValidator.class));

        Field msField = AgentService.class.getDeclaredField("metadataService");
        msField.setAccessible(true);
        msField.set(service, metadataService);

        Method m = AgentService.class.getDeclaredMethod("registerTaskDef", String.class, List.class);
        m.setAccessible(true);
        m.invoke(service, toolName, creds);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<TaskDef>> captor = ArgumentCaptor.forClass(List.class);
        verify(metadataService).registerTaskDef(captor.capture());
        return captor.getValue().get(0);
    }
}
