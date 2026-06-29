package org.conductoross.conductor.ai.spring;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Agentspan-specific tuning knobs for the Spring Boot auto-configuration.
 *
 * <p>Server connectivity (URL, auth key/secret) is handled by the Conductor
 * Java SDK's own Spring starter via {@code conductor.*} properties — see
 * {@link io.orkes.conductor.client.spring.OrkesConductorClientAutoConfiguration}.
 * Only the Agentspan worker-runner settings live here.
 *
 * <pre>{@code
 * # application.properties
 *
 * # Conductor client (from conductor-client-spring):
 * conductor.root-uri=http://localhost:6767/api
 * conductor.security.client.key-id=my-key       # optional
 * conductor.security.client.secret=my-secret    # optional
 *
 * # Agentspan worker tuning (this class):
 * agentspan.worker-poll-interval-ms=100
 * agentspan.worker-thread-count=1
 * }</pre>
 */
@ConfigurationProperties(prefix = "agentspan")
public class AgentProperties {

    private int workerPollIntervalMs = 100;
    private int workerThreadCount = 1;

    public int getWorkerPollIntervalMs() {
        return workerPollIntervalMs;
    }

    public void setWorkerPollIntervalMs(int workerPollIntervalMs) {
        this.workerPollIntervalMs = workerPollIntervalMs;
    }

    public int getWorkerThreadCount() {
        return workerThreadCount;
    }

    public void setWorkerThreadCount(int workerThreadCount) {
        this.workerThreadCount = workerThreadCount;
    }
}
