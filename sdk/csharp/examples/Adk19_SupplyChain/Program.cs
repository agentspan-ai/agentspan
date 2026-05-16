// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk19 — Supply Chain.
//
// A coordinator delegating to inventory, logistics, and demand
// forecasting specialists.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var inventoryAgent = GoogleADKAgent.Builder()
    .Name("inventory_manager")
    .Model(Settings.LlmModel)
    .Instruction("Check inventory levels and supplier status. Flag items below reorder points.")
    .Tools(new InventoryTools())
    .Build();

var logisticsAgent = GoogleADKAgent.Builder()
    .Name("logistics_coordinator")
    .Model(Settings.LlmModel)
    .Instruction("Find optimal shipping routes and track pending shipments.")
    .Tools(new LogisticsTools())
    .Build();

var demandAgent = GoogleADKAgent.Builder()
    .Name("demand_planner")
    .Model(Settings.LlmModel)
    .Instruction("Analyze demand forecasts and identify trends.")
    .Tools(new DemandTools())
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("supply_chain_coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a supply chain coordinator. Analyze inventory, logistics, and demand. " +
        "Identify items that need restocking, recommend optimal shipping, and provide " +
        "an action plan. Delegate to the appropriate specialist.")
    .SubAgents(inventoryAgent, logisticsAgent, demandAgent)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "Give me a full supply chain status report. Check both warehouses, " +
    "identify any items below reorder points, and recommend restocking actions.");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class InventoryTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _warehouses = new(StringComparer.OrdinalIgnoreCase)
    {
        ["west"] = new()
        {
            ["warehouse"] = "West Coast",
            ["items"]     = new List<Dictionary<string, object>>
            {
                new() { ["sku"] = "WIDGET-A", ["quantity"] = 5000, ["reorder_point"] = 2000 },
                new() { ["sku"] = "WIDGET-B", ["quantity"] = 1200, ["reorder_point"] = 1500 },
                new() { ["sku"] = "GADGET-X", ["quantity"] = 800,  ["reorder_point"] = 500  },
            },
        },
        ["east"] = new()
        {
            ["warehouse"] = "East Coast",
            ["items"]     = new List<Dictionary<string, object>>
            {
                new() { ["sku"] = "WIDGET-A", ["quantity"] = 3200, ["reorder_point"] = 2000 },
                new() { ["sku"] = "WIDGET-B", ["quantity"] = 4500, ["reorder_point"] = 1500 },
                new() { ["sku"] = "GADGET-X", ["quantity"] = 200,  ["reorder_point"] = 500  },
            },
        },
    };
    private static readonly Dictionary<string, Dictionary<string, object>> _suppliers = new()
    {
        ["WIDGET-A"] = new() { ["supplier"] = "WidgetCorp",  ["lead_time_days"] = 14, ["min_order"] = 1000, ["unit_cost"] = 2.50  },
        ["WIDGET-B"] = new() { ["supplier"] = "WidgetCorp",  ["lead_time_days"] = 21, ["min_order"] = 500,  ["unit_cost"] = 4.75  },
        ["GADGET-X"] = new() { ["supplier"] = "GadgetWorks", ["lead_time_days"] = 30, ["min_order"] = 200,  ["unit_cost"] = 12.00 },
    };

    [Tool(Name = "get_inventory_levels", Description = "Get current inventory levels at a warehouse.")]
    public Dictionary<string, object> GetInventoryLevels(string warehouse)
        => _warehouses.TryGetValue(warehouse, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Warehouse '{warehouse}' not found" };

    [Tool(Name = "check_supplier_status", Description = "Check supplier availability and lead times.")]
    public Dictionary<string, object> CheckSupplierStatus(string sku)
        => _suppliers.TryGetValue(sku.ToUpperInvariant(), out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"No supplier for SKU {sku}" };
}

internal sealed class LogisticsTools
{
    [Tool(Name = "get_shipping_routes", Description = "Get available shipping routes between warehouses.")]
    public Dictionary<string, object> GetShippingRoutes(string origin, string destination)
        => new()
        {
            ["origin"]      = origin,
            ["destination"] = destination,
            ["routes"]      = new List<Dictionary<string, object>>
            {
                new() { ["method"] = "Ground", ["transit_days"] = 5, ["cost_per_unit"] = 0.50 },
                new() { ["method"] = "Rail",   ["transit_days"] = 3, ["cost_per_unit"] = 0.75 },
                new() { ["method"] = "Air",    ["transit_days"] = 1, ["cost_per_unit"] = 2.00 },
            },
        };

    [Tool(Name = "get_pending_shipments", Description = "Get all pending shipments in the system.")]
    public Dictionary<string, object> GetPendingShipments()
        => new()
        {
            ["shipments"] = new List<Dictionary<string, object>>
            {
                new() { ["id"] = "SHP-001", ["sku"] = "WIDGET-A", ["qty"] = 2000, ["status"] = "in_transit", ["eta"] = "2025-04-18" },
                new() { ["id"] = "SHP-002", ["sku"] = "GADGET-X", ["qty"] = 500,  ["status"] = "processing", ["eta"] = "2025-05-01" },
            },
        };
}

internal sealed class DemandTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _forecasts = new()
    {
        ["WIDGET-A"] = new() { ["weekly_demand"] = 800, ["trend"] = "increasing", ["confidence"] = 0.85 },
        ["WIDGET-B"] = new() { ["weekly_demand"] = 300, ["trend"] = "stable",     ["confidence"] = 0.90 },
        ["GADGET-X"] = new() { ["weekly_demand"] = 150, ["trend"] = "decreasing", ["confidence"] = 0.75 },
    };

    [Tool(Name = "get_demand_forecast", Description = "Get demand forecast for a SKU.")]
    public Dictionary<string, object> GetDemandForecast(string sku, int weeks_ahead)
    {
        var data = _forecasts.TryGetValue(sku.ToUpperInvariant(), out var v)
            ? v
            : new Dictionary<string, object> { ["weekly_demand"] = 0, ["trend"] = "unknown" };
        var weekly = Convert.ToInt32(data.GetValueOrDefault("weekly_demand", 0));
        var wa = weeks_ahead <= 0 ? 4 : weeks_ahead;
        var result = new Dictionary<string, object>
        {
            ["sku"]         = sku,
            ["weeks_ahead"] = wa,
        };
        foreach (var (k, val) in data) result[k] = val;
        result["total_forecast"] = weekly * wa;
        return result;
    }
}
