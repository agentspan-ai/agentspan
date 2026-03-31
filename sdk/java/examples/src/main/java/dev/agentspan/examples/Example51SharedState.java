// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolContext;
import dev.agentspan.model.ToolDef;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Example 51 — Shared State
 *
 * <p>Tools can read and write to {@link ToolContext#getState()}, a map that
 * persists across all tool calls within the same agent execution. This enables
 * tools to accumulate data or pass information between invocations without
 * relying on the LLM to relay state.
 *
 * <p>The server injects the current state as {@code _agent_state} in each
 * tool's input, and the SDK reads back {@code _state_updates} from the output
 * to persist mutations for the next call.
 */
public class Example51SharedState {

    static class ShoppingListTools {

        @Tool(name = "add_item", description = "Add an item to the shared shopping list")
        public Map<String, Object> addItem(String item, ToolContext context) {
            @SuppressWarnings("unchecked")
            List<String> items = (List<String>) context.getState()
                .getOrDefault("shopping_list", new ArrayList<>());
            items = new ArrayList<>(items); // ensure mutable copy
            items.add(item);
            context.getState().put("shopping_list", items);
            return Map.of("added", item, "total_items", items.size());
        }

        @Tool(name = "get_list", description = "Get the current shopping list")
        public Map<String, Object> getList(ToolContext context) {
            @SuppressWarnings("unchecked")
            List<String> items = (List<String>) context.getState()
                .getOrDefault("shopping_list", new ArrayList<>());
            return Map.of("items", items, "total_items", items.size());
        }

        @Tool(name = "clear_list", description = "Clear the shopping list")
        public Map<String, Object> clearList(ToolContext context) {
            context.getState().put("shopping_list", new ArrayList<>());
            return Map.of("status", "cleared");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new ShoppingListTools());

        Agent agent = Agent.builder()
            .name("shopping_assistant_51")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions(
                "You help manage a shopping list. Use add_item to add items, "
                + "get_list to view the list, and clear_list to reset it. "
                + "IMPORTANT: Always add all items first, then call get_list separately "
                + "in a follow-up step to verify the list contents. Never call get_list "
                + "in the same batch as add_item calls.")
            .build();

        AgentResult result = Agentspan.run(agent,
            "Add milk, eggs, and bread to my shopping list, then show me the list.");
        result.printResult();

        Agentspan.shutdown();
    }
}
