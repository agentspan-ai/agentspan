/*
 * Copyright (c) 2025 Agentspan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.core.dal.ExecutionDAOFacade;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

/**
 * Unit tests for {@link AgentspanMintTokenTask} — the in-DAG system task that
 * guarantees an execution token exists in {@code workflow.variables.__agentspan_ctx__}
 * regardless of how the workflow was started.
 */
class AgentspanMintTokenTaskTest {

    private static final String CTX = "__agentspan_ctx__";

    private AgentspanMintTokenTask newTask(ExecutionDAOFacade dao, ExecutionTokenService tokenService) {
        AgentspanMintTokenTask task = new AgentspanMintTokenTask(dao);
        // tokenService is @Autowired(required = false) — inject the mock directly.
        ReflectionTestUtils.setField(task, "tokenService", tokenService);
        return task;
    }

    private WorkflowModel workflow(String id, Map<String, Object> metadata) {
        WorkflowModel wf = new WorkflowModel();
        wf.setWorkflowId(id);
        WorkflowDef def = new WorkflowDef();
        def.setName("agent_wf");
        if (metadata != null) def.setMetadata(metadata);
        wf.setWorkflowDefinition(def);
        return wf;
    }

    @Test
    @SuppressWarnings("unchecked")
    void mintsTokenFromStampedMetadata_writesToVariablesAndPersists() {
        ExecutionDAOFacade dao = mock(ExecutionDAOFacade.class);
        ExecutionTokenService tokenService = mock(ExecutionTokenService.class);
        when(tokenService.mint(anyString(), anyString(), anyList(), anyLong())).thenReturn("minted-tok");

        AgentspanMintTokenTask task = newTask(dao, tokenService);
        WorkflowModel wf =
                workflow(
                        "wf-1",
                        Map.of(
                                "agentspan_credential_user", "deployer-1",
                                "agentspan_declared_credentials",
                                        List.of("OCG_PUBLIC_KEY", "github_pat")));
        TaskModel t = new TaskModel();

        boolean handled = task.execute(wf, t, null);

        assertThat(handled).isTrue();
        verify(tokenService)
                .mint(eq("deployer-1"), eq("wf-1"), eq(List.of("OCG_PUBLIC_KEY", "github_pat")), anyLong());
        Map<String, Object> ctx = (Map<String, Object>) wf.getVariables().get(CTX);
        assertThat(ctx).isNotNull();
        assertThat(ctx.get("execution_token")).isEqualTo("minted-tok");
        // The variable must be persisted (SET_VARIABLE durability pattern).
        verify(dao).updateWorkflow(wf);
        assertThat(t.getStatus()).isEqualTo(TaskModel.Status.COMPLETED);
    }

    @Test
    @SuppressWarnings("unchecked")
    void passesThroughExistingToken_doesNotMint() {
        ExecutionDAOFacade dao = mock(ExecutionDAOFacade.class);
        ExecutionTokenService tokenService = mock(ExecutionTokenService.class);

        AgentspanMintTokenTask task = newTask(dao, tokenService);
        WorkflowModel wf = workflow("wf-sdk", Map.of("agentspan_credential_user", "deployer-1"));
        TaskModel t = new TaskModel();
        // The SDK /agent/start path (or a SUB_WORKFLOW input mapping) supplies a token.
        t.setInputData(Map.of(CTX, Map.of("execution_token", "sdk-tok")));

        boolean handled = task.execute(wf, t, null);

        assertThat(handled).isTrue();
        verify(tokenService, never()).mint(anyString(), anyString(), anyList(), anyLong());
        Map<String, Object> ctx = (Map<String, Object>) wf.getVariables().get(CTX);
        assertThat(ctx.get("execution_token")).isEqualTo("sdk-tok");
        verify(dao).updateWorkflow(wf);
        assertThat(t.getStatus()).isEqualTo(TaskModel.Status.COMPLETED);
    }

    @Test
    void fallsBackToCreatedByWhenNoStampedUser() {
        ExecutionDAOFacade dao = mock(ExecutionDAOFacade.class);
        ExecutionTokenService tokenService = mock(ExecutionTokenService.class);
        when(tokenService.mint(anyString(), anyString(), anyList(), anyLong())).thenReturn("tok");

        AgentspanMintTokenTask task = newTask(dao, tokenService);
        WorkflowModel wf =
                workflow("wf-cb", Map.of("agentspan_declared_credentials", List.of("OCG_PUBLIC_KEY")));
        wf.setCreatedBy("creator-app");
        TaskModel t = new TaskModel();

        boolean handled = task.execute(wf, t, null);

        assertThat(handled).isTrue();
        verify(tokenService).mint(eq("creator-app"), eq("wf-cb"), anyList(), anyLong());
    }

    @Test
    @SuppressWarnings("unchecked")
    void noIdentity_completesWithEmptyCtxAndDoesNotMint() {
        ExecutionDAOFacade dao = mock(ExecutionDAOFacade.class);
        ExecutionTokenService tokenService = mock(ExecutionTokenService.class);

        AgentspanMintTokenTask task = newTask(dao, tokenService);
        // No stamped user and no createdBy → nothing to mint with.
        WorkflowModel wf = workflow("wf-anon", Map.of());
        TaskModel t = new TaskModel();

        boolean handled = task.execute(wf, t, null);

        assertThat(handled).isTrue();
        verify(tokenService, never()).mint(anyString(), anyString(), anyList(), anyLong());
        Map<String, Object> ctx = (Map<String, Object>) wf.getVariables().get(CTX);
        assertThat(ctx).isEmpty();
        assertThat(t.getStatus()).isEqualTo(TaskModel.Status.COMPLETED);
    }

    @Test
    void noTokenServiceBound_completesGracefully() {
        ExecutionDAOFacade dao = mock(ExecutionDAOFacade.class);
        // tokenService stays null (as it would when no ExecutionTokenService bean exists).
        AgentspanMintTokenTask task = new AgentspanMintTokenTask(dao);
        WorkflowModel wf = workflow("wf-none", Map.of("agentspan_credential_user", "deployer-1"));
        TaskModel t = new TaskModel();

        boolean handled = task.execute(wf, t, null);

        assertThat(handled).isTrue();
        assertThat(wf.getVariables().get(CTX)).isEqualTo(Map.of());
        assertThat(t.getStatus()).isEqualTo(TaskModel.Status.COMPLETED);
    }
}
