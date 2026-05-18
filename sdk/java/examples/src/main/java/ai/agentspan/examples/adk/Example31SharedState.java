// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 31 — Shared State
 *
 * <p>Java port of <code>sdk/python/examples/adk/31_shared_state.py</code>.
 *
 * <p>Demonstrates: tools sharing state across tool calls within the same
 * agent execution. The Python source uses ADK's {@code ToolContext.state};
 * the Java port keeps the same shopping-list semantics via an in-memory
 * instance field on the tool class.
 */
public class Example31SharedState {

    static class ShoppingListTools {

        private final List<String> shoppingList = new ArrayList<>();

        @Tool(name = "add_item", value = "Add an item to the shared shopping list.")
        public Map<String, Object> addItem(@P("item") String item) {
            shoppingList.add(item);
            return Map.of("added", item, "total_items", shoppingList.size());
        }

        @Tool(name = "get_list", value = "Get the current shopping list from shared state.")
        public Map<String, Object> getList() {
            return Map.of("items", List.copyOf(shoppingList), "total_items", shoppingList.size());
        }

        @Tool(name = "clear_list", value = "Clear the shopping list.")
        public Map<String, Object> clearList() {
            shoppingList.clear();
            return Map.of("status", "cleared");
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("shopping_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You help manage a shopping list. Use add_item to add items, "
                + "get_list to view the list, and clear_list to reset it.")
            .tools(new ShoppingListTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "Add milk, eggs, and bread to my shopping list, then show me the list.");
        result.printResult();

        Agentspan.shutdown();
    }
}
