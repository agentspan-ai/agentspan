// server/src/test/java/dev/agentspan/runtime/controller/AgentControllerSignalTest.java
package dev.agentspan.runtime.controller;

import dev.agentspan.runtime.model.SignalRequest;
import dev.agentspan.runtime.model.SignalReceipt;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.*;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AgentControllerSignalTest {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;

    @Test
    void signalToNonExistentWorkflow_returns404() {
        SignalRequest req = new SignalRequest();
        req.setMessage("hello");
        req.setPriority("normal");

        ResponseEntity<String> resp = rest.postForEntity(
            "http://localhost:" + port + "/api/agent/nonexistent-id/signal",
            req, String.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void getSignalStatus_nonExistent_returns404() {
        ResponseEntity<String> resp = rest.getForEntity(
            "http://localhost:" + port + "/api/agent/signal/nonexistent-uuid/status",
            String.class);
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }
}
