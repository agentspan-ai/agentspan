package org.conductoross.conductor.ai.spring;

import static org.junit.jupiter.api.Assertions.*;

import org.conductoross.conductor.ai.AgentConfig;
import org.conductoross.conductor.ai.AgentRuntime;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import io.orkes.conductor.client.ApiClient;

class AgentAutoConfigurationTest {

    /**
     * Provide a minimal ApiClient so tests don't need a live conductor-client-spring
     * auto-configuration (which would require a real server URL to be set).
     * In production, OrkesConductorClientAutoConfiguration wires this from
     * conductor.* properties.
     */
    private static ApiClient stubApiClient() {
        return AgentRuntime.client("http://localhost:6767");
    }

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(AgentAutoConfiguration.class))
            .withBean(ApiClient.class, AgentAutoConfigurationTest::stubApiClient);

    @Test
    void wiresConfigAndRuntimeWithDefaults() {
        runner.run(ctx -> {
            assertTrue(ctx.containsBean("agentspanConfig"), "AgentConfig bean must be present");
            assertTrue(ctx.containsBean("agentRuntime"), "AgentRuntime bean must be present");

            // No agentspanConductorClient bean — ApiClient comes from conductor-client-spring.
            assertFalse(
                    ctx.containsBean("agentspanConductorClient"),
                    "auto-config must NOT create its own ApiClient — "
                            + "that is OrkesConductorClientAutoConfiguration's job");

            AgentConfig config = ctx.getBean(AgentConfig.class);
            assertEquals(100, config.getWorkerPollIntervalMs(), "default poll interval");
            assertEquals(1, config.getWorkerThreadCount(), "default thread count");
        });
    }

    @Test
    void respectsWorkerTuningProperties() {
        runner.withPropertyValues("agentspan.worker-thread-count=4", "agentspan.worker-poll-interval-ms=250")
                .run(ctx -> {
                    AgentConfig config = ctx.getBean(AgentConfig.class);
                    assertEquals(4, config.getWorkerThreadCount());
                    assertEquals(250, config.getWorkerPollIntervalMs());
                });
    }

    @Test
    void serverUrlPropertiesAreNotAccepted() {
        // agentspan.server-url no longer exists — setting it must not cause an error
        // (Spring ignores unknown properties by default) and must not affect the client.
        runner.withPropertyValues("agentspan.server-url=http://ignored:9090")
                .run(ctx -> assertFalse(
                        ctx.getStartupFailure() != null, "unknown property must not break context startup"));
    }

    @Test
    void doesNotOverrideUserDefinedAgentConfigBean() {
        AgentConfig custom = new AgentConfig(50, 2);
        runner.withBean(AgentConfig.class, () -> custom).run(ctx -> {
            AgentConfig config = ctx.getBean(AgentConfig.class);
            assertSame(custom, config, "@ConditionalOnMissingBean must yield to user-provided AgentConfig");
            assertEquals(50, config.getWorkerPollIntervalMs());
        });
    }

    @Test
    void doesNotOverrideUserDefinedAgentRuntimeBean() {
        AgentRuntime customRuntime = new AgentRuntime(stubApiClient(), new AgentConfig());
        runner.withBean(AgentRuntime.class, () -> customRuntime).run(ctx -> {
            AgentRuntime runtime = ctx.getBean(AgentRuntime.class);
            assertSame(customRuntime, runtime, "@ConditionalOnMissingBean must yield to user-provided AgentRuntime");
            customRuntime.shutdown();
        });
    }
}
