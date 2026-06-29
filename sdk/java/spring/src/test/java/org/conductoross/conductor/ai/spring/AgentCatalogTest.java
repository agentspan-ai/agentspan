package org.conductoross.conductor.ai.spring;

import static org.junit.jupiter.api.Assertions.*;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.annotations.AgentDef;
import org.conductoross.conductor.ai.annotations.Tool;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import io.orkes.conductor.client.ApiClient;

class AgentCatalogTest {

    private static ApiClient stubApiClient() {
        return AgentRuntime.client("http://localhost:6767");
    }

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(AgentAutoConfiguration.class))
            .withBean(ApiClient.class, AgentCatalogTest::stubApiClient);

    // ── Fixture beans ───────────────────────────────────────────────────

    static class CrewBean {
        @Tool(description = "Look up an order")
        public String lookupOrder(String orderId) {
            return "order " + orderId;
        }

        @AgentDef(model = "openai/gpt-4o", instructions = "Handle billing questions.")
        public void billing() {}

        @AgentDef(model = "openai/gpt-4o")
        public String support() {
            return "Handle support tickets.";
        }
    }

    static class DuplicateNameBean {
        @AgentDef(model = "openai/gpt-4o", instructions = "Clashes with CrewBean.billing.")
        public void billing() {}
    }

    static class PlainBean {}

    // ── Tests ───────────────────────────────────────────────────────────

    @Test
    void collectsAgentsFromBeans() {
        runner.withBean("crew", CrewBean.class)
                .withBean("plain", PlainBean.class)
                .run(ctx -> {
                    AgentCatalog catalog = ctx.getBean(AgentCatalog.class);
                    assertEquals(2, catalog.all().size());
                    assertEquals(java.util.Set.of("billing", "support"), catalog.names());

                    Agent billing = catalog.get("billing");
                    assertEquals("Handle billing questions.", billing.getInstructions());

                    Agent support = catalog.get("support");
                    assertEquals("Handle support tickets.", support.getInstructions());
                    // @Tool methods on the same bean attach automatically
                    assertEquals(1, support.getTools().size());
                    assertEquals("lookupOrder", support.getTools().get(0).getName());
                });
    }

    @Test
    void duplicateAgentNamesAcrossBeansFailFast() {
        runner.withBean("crew", CrewBean.class)
                .withBean("dup", DuplicateNameBean.class)
                .run(ctx -> {
                    AgentCatalog catalog = ctx.getBean(AgentCatalog.class);
                    IllegalStateException e = assertThrows(IllegalStateException.class, catalog::all);
                    assertTrue(e.getMessage().contains("billing"));
                    assertTrue(e.getMessage().contains("crew"));
                    assertTrue(e.getMessage().contains("dup"));
                });
    }

    @Test
    void emptyCatalogWhenNoAgentBeans() {
        runner.withBean("plain", PlainBean.class).run(ctx -> {
            AgentCatalog catalog = ctx.getBean(AgentCatalog.class);
            assertTrue(catalog.all().isEmpty());
            assertTrue(catalog.find("nope").isEmpty());
            IllegalArgumentException e = assertThrows(IllegalArgumentException.class, () -> catalog.get("nope"));
            assertTrue(e.getMessage().contains("nope"));
        });
    }

    @Test
    void userDefinedCatalogWins() {
        runner.withBean(AgentCatalog.class, () -> new AgentCatalog(null) {
                    @Override
                    public java.util.List<Agent> all() {
                        return java.util.List.of();
                    }
                })
                .run(ctx -> {
                    assertTrue(ctx.getBean(AgentCatalog.class).all().isEmpty());
                });
    }
}
