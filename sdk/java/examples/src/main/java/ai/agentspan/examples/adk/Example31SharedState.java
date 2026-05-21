// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

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
 * the Java port keeps the same shopping-list semantics via a static collection
 * since {@link FunctionTool#create(Class, String)} requires static methods.
 */
public class Example31SharedState {

    private static final List<String> SHOPPING_LIST = new ArrayList<>();

    @Schema(description = "Add an item to the shared shopping list.")
    public static Map<String, Object> addItem(
            @Schema(name = "item", description = "Item to add") String item) {
        SHOPPING_LIST.add(item);
        return Map.of("added", item, "total_items", SHOPPING_LIST.size());
    }

    @Schema(description = "Get the current shopping list from shared state.")
    public static Map<String, Object> getList() {
        return Map.of("items", List.copyOf(SHOPPING_LIST), "total_items", SHOPPING_LIST.size());
    }

    @Schema(description = "Clear the shopping list.")
    public static Map<String, Object> clearList() {
        SHOPPING_LIST.clear();
        return Map.of("status", "cleared");
    }

    public static void main(String[] args) {
        LlmAgent stateAgent = LlmAgent.builder()
            .name("shopping_assistant")
            .description("Manages a shopping list shared across tool calls via add/get/clear tools.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You help manage a shopping list. Use add_item to add items, "
                + "get_list to view the list, and clear_list to reset it.")
            .tools(
                FunctionTool.create(Example31SharedState.class, "addItem"),
                FunctionTool.create(Example31SharedState.class, "getList"),
                FunctionTool.create(Example31SharedState.class, "clearList"))
            .build();

        AgentResult result = Agentspan.run(stateAgent,
            "Add milk, eggs, and bread to my shopping list, then show me the list.");
        result.printResult();

        Agentspan.shutdown();
    }
}
