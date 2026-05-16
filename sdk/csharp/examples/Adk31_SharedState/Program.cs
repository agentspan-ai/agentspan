// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk31 — Shared State.
//
// Tools sharing state across tool calls within the same agent execution.
// The Python source uses ADK's ToolContext.state; we keep the same
// shopping-list semantics via an in-memory instance field.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("shopping_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You help manage a shopping list. Use add_item to add items, " +
        "get_list to view the list, and clear_list to reset it.")
    .Tools(new ShoppingListTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "Add milk, eggs, and bread to my shopping list, then show me the list.");
result.PrintResult();

internal sealed class ShoppingListTools
{
    private readonly List<string> _shoppingList = new();

    [Tool(Name = "add_item", Description = "Add an item to the shared shopping list.")]
    public Dictionary<string, object> AddItem(string item)
    {
        _shoppingList.Add(item);
        return new Dictionary<string, object> { ["added"] = item, ["total_items"] = _shoppingList.Count };
    }

    [Tool(Name = "get_list", Description = "Get the current shopping list from shared state.")]
    public Dictionary<string, object> GetList()
        => new() { ["items"] = new List<string>(_shoppingList), ["total_items"] = _shoppingList.Count };

    [Tool(Name = "clear_list", Description = "Clear the shopping list.")]
    public Dictionary<string, object> ClearList()
    {
        _shoppingList.Clear();
        return new Dictionary<string, object> { ["status"] = "cleared" };
    }
}
