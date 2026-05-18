package ai.agentspan.spring;

import ai.agentspan.AgentConfig;
import ai.agentspan.AgentRuntime;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.*;

class AgentspanAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(AgentspanAutoConfiguration.class));

    @Test
    void registersAgentConfigAndRuntimeBeansWithDefaults() {
        runner.run(ctx -> {
            assertTrue(ctx.containsBean("agentspanConfig"));
            assertTrue(ctx.containsBean("agentRuntime"));

            AgentConfig config = ctx.getBean(AgentConfig.class);
            assertEquals("http://localhost:6767", config.getServerUrl());
            assertEquals(100, config.getWorkerPollIntervalMs());
            assertEquals(1, config.getWorkerThreadCount());
            assertNull(config.getAuthKey());
            assertNull(config.getAuthSecret());
        });
    }

    @Test
    void respectsCustomProperties() {
        runner
            .withPropertyValues(
                "agentspan.server-url=http://myserver:9090",
                "agentspan.auth-key=mykey",
                "agentspan.auth-secret=mysecret",
                "agentspan.worker-thread-count=4",
                "agentspan.worker-poll-interval-ms=250"
            )
            .run(ctx -> {
                AgentConfig config = ctx.getBean(AgentConfig.class);
                assertEquals("http://myserver:9090", config.getServerUrl());
                assertEquals("mykey", config.getAuthKey());
                assertEquals("mysecret", config.getAuthSecret());
                assertEquals(4, config.getWorkerThreadCount());
                assertEquals(250, config.getWorkerPollIntervalMs());
            });
    }

    @Test
    void doesNotOverrideUserDefinedAgentConfigBean() {
        AgentConfig custom = new AgentConfig("http://custom:1234", null, null, 50, 2);
        runner
            .withBean(AgentConfig.class, () -> custom)
            .run(ctx -> {
                AgentConfig config = ctx.getBean(AgentConfig.class);
                assertSame(custom, config);
                assertEquals("http://custom:1234", config.getServerUrl());
            });
    }

    @Test
    void doesNotOverrideUserDefinedAgentRuntimeBean() {
        AgentConfig config = new AgentConfig("http://localhost:6767", null, null, 100, 1);
        AgentRuntime customRuntime = new AgentRuntime(config);
        runner
            .withBean(AgentRuntime.class, () -> customRuntime)
            .run(ctx -> {
                AgentRuntime runtime = ctx.getBean(AgentRuntime.class);
                assertSame(customRuntime, runtime);
                customRuntime.shutdown();
            });
    }
}
