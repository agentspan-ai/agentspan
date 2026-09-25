/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

/**
 * Unit tests for {@link ListApiToolsTask}, focused on the SSRF guard and happy-path parsing.
 */
@SuppressWarnings("unchecked")
class ListApiToolsTaskTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final WorkflowModel WORKFLOW = new WorkflowModel();

    // -----------------------------------------------------------------------
    //  SSRF guard — blocked addresses
    // -----------------------------------------------------------------------

    @ParameterizedTest(name = "SSRF guard blocks {0}")
    @ValueSource(strings = {
            "http://127.0.0.1/spec.json",
            "http://localhost/spec.json",
            "http://169.254.169.254/latest/meta-data/",   // AWS metadata
            "http://10.0.0.1/openapi.json",
            "http://192.168.1.1/openapi.json",
            "http://172.16.0.1/swagger.json",
            "http://[::1]/spec.json",                      // IPv6 loopback
            "http://[fd12:3456:789a:1::1]/spec.json",      // IPv6 unique-local (fc00::/7)
    })
    void ssrfGuard_blocksPrivateAndLoopbackAddresses(String url) {
        HttpClient httpClient = mock(HttpClient.class);
        ListApiToolsTask task = new ListApiToolsTask(MAPPER, httpClient);

        TaskModel taskModel = taskWithInput(Map.of("specUrl", url));
        task.start(WORKFLOW, taskModel, null);

        assertThat(taskModel.getStatus()).isEqualTo(TaskModel.Status.FAILED);
        // HTTP client must never be called for blocked hosts
        verifyNoInteractions(httpClient);
    }

    // -----------------------------------------------------------------------
    //  SSRF guard — redirect to private address is blocked
    // -----------------------------------------------------------------------

    @Test
    void ssrfGuard_blocksRedirectToPrivateAddress() throws Exception {
        HttpClient httpClient = mock(HttpClient.class);
        ListApiToolsTask task = new ListApiToolsTask(MAPPER, httpClient);

        // First response: 301 to a private address
        HttpResponse<String> redirect = mockResponse(301, "", Map.of("Location", "http://10.0.0.1/secret.json"));
        doReturn(redirect).when(httpClient).send(any(), any());

        TaskModel taskModel = taskWithInput(Map.of("specUrl", "http://public.example.com/spec.json"));
        task.start(WORKFLOW, taskModel, null);

        assertThat(taskModel.getStatus()).isEqualTo(TaskModel.Status.FAILED);
    }

    // -----------------------------------------------------------------------
    //  Happy path — OpenAPI 3.x spec is parsed correctly
    // -----------------------------------------------------------------------

    @Test
    void happyPath_opensApi3SpecParsed() throws Exception {
        String specJson = """
                {
                  "openapi": "3.0.0",
                  "info": { "title": "Test API", "version": "1.0" },
                  "servers": [{ "url": "https://api.example.com" }],
                  "paths": {
                    "/pets": {
                      "get": {
                        "operationId": "listPets",
                        "summary": "List pets",
                        "parameters": []
                      },
                      "post": {
                        "operationId": "createPet",
                        "summary": "Create a pet"
                      }
                    }
                  }
                }
                """;

        HttpClient httpClient = mock(HttpClient.class);
        HttpResponse<String> ok = mockResponse(200, specJson, Map.of());
        doReturn(ok).when(httpClient).send(any(), any());

        ListApiToolsTask task = new ListApiToolsTask(MAPPER, httpClient);
        // Use a numeric public IP so guardSsrf() passes without DNS resolution
        TaskModel taskModel = taskWithInput(Map.of("specUrl", "https://1.1.1.1/openapi.json"));
        task.start(WORKFLOW, taskModel, null);

        assertThat(taskModel.getStatus()).isEqualTo(TaskModel.Status.COMPLETED);

        Map<String, Object> output = taskModel.getOutputData();
        assertThat(output.get("format")).isEqualTo("openapi3");
        assertThat(output.get("baseUrl")).isEqualTo("https://api.example.com");

        List<Map<String, Object>> tools = (List<Map<String, Object>>) output.get("tools");
        assertThat(tools).hasSize(2);
        assertThat(tools).extracting(t -> t.get("name"))
                .containsExactlyInAnyOrder("listPets", "createPet");
    }

    // -----------------------------------------------------------------------
    //  Missing / blank specUrl
    // -----------------------------------------------------------------------

    @Test
    void missingSpecUrl_taskFails() {
        ListApiToolsTask task = new ListApiToolsTask(MAPPER, mock(HttpClient.class));
        TaskModel taskModel = taskWithInput(Map.of());
        task.start(WORKFLOW, taskModel, null);

        assertThat(taskModel.getStatus()).isEqualTo(TaskModel.Status.FAILED);
        assertThat(taskModel.getReasonForIncompletion()).contains("specUrl");
    }

    // -----------------------------------------------------------------------
    //  Helpers
    // -----------------------------------------------------------------------

    private static TaskModel taskWithInput(Map<String, Object> input) {
        TaskModel task = new TaskModel();
        task.setInputData(input);
        task.setOutputData(new java.util.HashMap<>());
        return task;
    }

    private static HttpResponse<String> mockResponse(int status, String body, Map<String, String> headers) {
        HttpResponse<String> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(status);
        when(response.body()).thenReturn(body);
        HttpHeaders httpHeaders = HttpHeaders.of(
                headers.entrySet().stream().collect(
                        java.util.stream.Collectors.toMap(
                                e -> e.getKey().toLowerCase(),
                                e -> List.of(e.getValue()))),
                (k, v) -> true);
        when(response.headers()).thenReturn(httpHeaders);
        return response;
    }
}
