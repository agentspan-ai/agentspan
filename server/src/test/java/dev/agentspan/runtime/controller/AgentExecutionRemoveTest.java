package dev.agentspan.runtime.controller;

import dev.agentspan.runtime.model.PruneResult;
import dev.agentspan.runtime.service.AgentService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Arrays;
import java.util.List;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(AgentController.class)
class AgentExecutionRemoveTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AgentService agentService;

    @Test
    void testDeleteExecutionById_RemovesRecord() throws Exception {
        doNothing().when(agentService).removeExecution(eq("test-id"), anyBoolean());

        mockMvc.perform(delete("/api/agent/executions/test-id"))
                .andExpect(status().isOk());

        verify(agentService).removeExecution(eq("test-id"), anyBoolean());
    }

    @Test
    void testDeleteExecutionById_NotFound_ReturnsOk() throws Exception {
        doThrow(new RuntimeException("not found")).when(agentService).removeExecution(eq("missing-id"), anyBoolean());

        mockMvc.perform(delete("/api/agent/executions/missing-id"))
                .andExpect(status().isOk());
    }

    @Test
    void testBulkRemoveExecutions_RemovesAll() throws Exception {
        PruneResult result = PruneResult.builder()
                .prunedCount(3)
                .prunedExecutionIds(List.of("id1", "id2", "id3"))
                .build();
        when(agentService.bulkRemoveExecutions(anyList())).thenReturn(result);

        mockMvc.perform(delete("/api/agent/executions/bulk/remove")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[\"id1\",\"id2\",\"id3\"]"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.prunedCount").value(3));
    }

    @Test
    void testBulkRemoveExecutions_EmptyList_ReturnsZero() throws Exception {
        PruneResult result = PruneResult.builder()
                .prunedCount(0)
                .prunedExecutionIds(List.of())
                .build();
        when(agentService.bulkRemoveExecutions(anyList())).thenReturn(result);

        mockMvc.perform(delete("/api/agent/executions/bulk/remove")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[]"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.prunedCount").value(0));
    }

    @Test
    void testPruneExecutions_OlderThan30Days() throws Exception {
        PruneResult result = PruneResult.builder()
                .prunedCount(5)
                .prunedExecutionIds(List.of("e1", "e2", "e3", "e4", "e5"))
                .build();
        when(agentService.pruneExecutions(eq(30), anyInt())).thenReturn(result);

        mockMvc.perform(delete("/api/agent/executions/prune")
                        .param("maxAgeDays", "30"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.prunedCount").value(5));

        verify(agentService).pruneExecutions(eq(30), anyInt());
    }
}
