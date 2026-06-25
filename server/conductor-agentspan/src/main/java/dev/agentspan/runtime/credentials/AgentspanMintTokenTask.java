/*
 * Copyright (c) 2025 Agentspan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.credentials;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import com.netflix.conductor.core.dal.ExecutionDAOFacade;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.core.execution.tasks.WorkflowSystemTask;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

/**
 * System task that guarantees an execution token exists for the workflow,
 * regardless of how the workflow was started.
 *
 * <p>The SDK {@code /agent/start} path mints a token and embeds it in the
 * workflow input before {@code startWorkflow}. Other start paths — an inbound
 * webhook, the UI, a schedule — go through Conductor core and do NOT, so their
 * credentialed tools (OCG/GitHub/Slack) would fail to resolve secrets.</p>
 *
 * <p>The compiler injects this as the FIRST task of every agent workflow. It:</p>
 * <ol>
 *   <li>passes through an existing {@code __agentspan_ctx__} (the {@code /agent/start}
 *       path, or a sub-workflow that inherited it from its parent's input); else</li>
 *   <li>mints a fresh token using the identity + declared-name allow-list stamped
 *       onto the WorkflowDef metadata at deploy time
 *       ({@code agentspan_credential_user} / {@code agentspan_declared_credentials}).</li>
 * </ol>
 *
 * <p>The result is written to {@code workflow.variables.__agentspan_ctx__} and
 * persisted via {@link ExecutionDAOFacade#updateWorkflow} — the same mechanism
 * Conductor's own {@code SET_VARIABLE} uses, so it is durable across decide()
 * cycles on every core (unlike a status-listener mutation, which orkes-conductor
 * does not persist). Downstream tasks read {@code ${workflow.variables.__agentspan_ctx__}}.</p>
 */
@Component(AgentspanMintTokenTask.TASK_TYPE)
public class AgentspanMintTokenTask extends WorkflowSystemTask {

    public static final String TASK_TYPE = "AGENTSPAN_MINT_TOKEN";
    public static final String CTX_KEY = "__agentspan_ctx__";
    public static final String META_USER = "agentspan_credential_user";
    public static final String META_DECLARED = "agentspan_declared_credentials";

    private static final Logger log = LoggerFactory.getLogger(AgentspanMintTokenTask.class);

    private final ExecutionDAOFacade executionDAOFacade;

    @Autowired(required = false)
    private ExecutionTokenService tokenService;

    public AgentspanMintTokenTask(ExecutionDAOFacade executionDAOFacade) {
        super(TASK_TYPE);
        this.executionDAOFacade = executionDAOFacade;
    }

    @Override
    public boolean execute(WorkflowModel workflow, TaskModel task, WorkflowExecutor executor) {
        Map<String, Object> ctx = resolveOrMint(workflow, task);
        workflow.getVariables().put(CTX_KEY, ctx);
        task.getOutputData().put(CTX_KEY, ctx);
        task.setStatus(TaskModel.Status.COMPLETED);
        // Persist the variable now so it is visible to every subsequently
        // scheduled task and to later decide() reloads (SET_VARIABLE pattern).
        executionDAOFacade.updateWorkflow(workflow);
        return true;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> resolveOrMint(WorkflowModel workflow, TaskModel task) {
        // 1. Pass through an existing token (SDK /agent/start, or inherited by a sub-workflow).
        Object existing = task.getInputData() != null ? task.getInputData().get(CTX_KEY) : null;
        if (existing instanceof Map && ((Map<?, ?>) existing).get("execution_token") != null) {
            return (Map<String, Object>) existing;
        }

        if (tokenService == null) {
            return Map.of();
        }

        // 2. Mint from the identity + allow-list stamped on the WorkflowDef.
        Map<String, Object> md =
                workflow.getWorkflowDefinition() != null
                        ? workflow.getWorkflowDefinition().getMetadata()
                        : null;
        Object userObj = md != null ? md.get(META_USER) : null;
        String userId = userObj instanceof String ? (String) userObj : workflow.getCreatedBy();
        if (userId == null || userId.isEmpty()) {
            log.debug(
                    "No credential identity for workflow {} — leaving ctx empty",
                    workflow.getWorkflowId());
            return Map.of();
        }

        Object declaredObj = md != null ? md.get(META_DECLARED) : null;
        List<String> declared = declaredObj instanceof List ? (List<String>) declaredObj : List.of();
        long ttlSeconds =
                workflow.getWorkflowDefinition() != null
                                && workflow.getWorkflowDefinition().getTimeoutSeconds() > 0
                        ? workflow.getWorkflowDefinition().getTimeoutSeconds()
                        : 0;

        try {
            String token =
                    tokenService.mint(userId, workflow.getWorkflowId(), declared, ttlSeconds);
            Map<String, Object> ctx = new LinkedHashMap<>();
            ctx.put("execution_token", token);
            log.info(
                    "Minted execution token for workflow {} (user={}, declared={})",
                    workflow.getWorkflowId(),
                    userId,
                    declared.size());
            return ctx;
        } catch (Exception e) {
            log.warn(
                    "Failed to mint execution token for workflow {}: {}",
                    workflow.getWorkflowId(),
                    e.getMessage());
            return Map.of();
        }
    }
}
