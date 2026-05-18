// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk09 — Multi-Tool Agent.
//
// Complex tool orchestration with multiple specialized tools working
// together for an e-commerce shopping flow.
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
        "You are a helpful shopping assistant. Help users find products, " +
        "check availability, calculate shipping, and apply coupons. " +
        "Always check inventory before recommending products. " +
        "Present information in a clear, organized format.")
    .Tools(new ShopTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "I'm looking for electronics. Show me what you have, check if they're " +
    "in stock, and calculate shipping to San Francisco. I have coupon code SAVE10.");
result.PrintResult();

internal sealed class ShopTools
{
    private static readonly List<Dictionary<string, object>> _products = new()
    {
        new() { ["id"] = "P001", ["name"] = "Wireless Mouse",     ["category"] = "electronics", ["price"] = 29.99, ["rating"] = 4.5 },
        new() { ["id"] = "P002", ["name"] = "Python Cookbook",    ["category"] = "books",       ["price"] = 45.00, ["rating"] = 4.8 },
        new() { ["id"] = "P003", ["name"] = "USB-C Hub",          ["category"] = "electronics", ["price"] = 39.99, ["rating"] = 4.2 },
        new() { ["id"] = "P004", ["name"] = "Ergonomic Keyboard", ["category"] = "electronics", ["price"] = 89.99, ["rating"] = 4.7 },
        new() { ["id"] = "P005", ["name"] = "Clean Code",         ["category"] = "books",       ["price"] = 35.00, ["rating"] = 4.9 },
    };

    private static readonly Dictionary<string, Dictionary<string, object>> _inventory = new()
    {
        ["P001"] = new() { ["in_stock"] = true,  ["quantity"] = 150, ["warehouse"]    = "West" },
        ["P002"] = new() { ["in_stock"] = true,  ["quantity"] = 45,  ["warehouse"]    = "East" },
        ["P003"] = new() { ["in_stock"] = false, ["quantity"] = 0,   ["restock_date"] = "2025-04-01" },
        ["P004"] = new() { ["in_stock"] = true,  ["quantity"] = 8,   ["warehouse"]    = "West" },
        ["P005"] = new() { ["in_stock"] = true,  ["quantity"] = 200, ["warehouse"]    = "East" },
    };

    [Tool(Name = "search_products", Description = "Search the product catalog.")]
    public Dictionary<string, object> SearchProducts(string query, string category, int max_results)
    {
        var cat = string.IsNullOrEmpty(category) ? "all" : category;
        var max = max_results <= 0 ? 5 : max_results;
        var q = query.ToLowerInvariant();
        var results = new List<Dictionary<string, object>>();
        foreach (var p in _products)
        {
            var name = ((string)p["name"]).ToLowerInvariant();
            var pcat = (string)p["category"];
            if (name.Contains(q) || (cat != "all" && pcat == cat))
                results.Add(p);
        }
        return new Dictionary<string, object>
        {
            ["status"]  = "success",
            ["results"] = results.Take(max).ToList(),
            ["total"]   = results.Count,
        };
    }

    [Tool(Name = "check_inventory", Description = "Check inventory availability for a product.")]
    public Dictionary<string, object> CheckInventory(string product_id)
    {
        if (!_inventory.TryGetValue(product_id, out var item))
            return new Dictionary<string, object> { ["status"] = "error", ["message"] = $"Product {product_id} not found" };
        var result = new Dictionary<string, object> { ["status"] = "success", ["product_id"] = product_id };
        foreach (var (k, v) in item) result[k] = v;
        return result;
    }

    [Tool(Name = "calculate_shipping", Description = "Calculate shipping cost for a list of products.")]
    public Dictionary<string, object> CalculateShipping(List<string> product_ids, string destination)
    {
        var baseCost = product_ids.Count * 5.99;
        return new Dictionary<string, object>
        {
            ["status"]      = "success",
            ["destination"] = destination,
            ["items"]       = product_ids.Count,
            ["options"]     = new List<Dictionary<string, object>>
            {
                new() { ["method"] = "Standard (5-7 days)", ["cost"] = $"${baseCost:F2}" },
                new() { ["method"] = "Express (2-3 days)",  ["cost"] = $"${baseCost * 1.8:F2}" },
                new() { ["method"] = "Overnight",           ["cost"] = $"${baseCost * 3:F2}" },
            },
        };
    }

    [Tool(Name = "apply_coupon", Description = "Apply a coupon code to calculate the discount.")]
    public Dictionary<string, object> ApplyCoupon(double subtotal, string coupon_code)
    {
        var coupons = new Dictionary<string, (string Type, double Value)>
        {
            ["SAVE10"]   = ("percentage", 10),
            ["FLAT20"]   = ("fixed", 20),
            ["FREESHIP"] = ("shipping", 0),
        };
        if (!coupons.TryGetValue(coupon_code.ToUpperInvariant(), out var c))
            return new Dictionary<string, object> { ["status"] = "error", ["message"] = $"Invalid coupon: {coupon_code}" };
        double discount = c.Type switch
        {
            "percentage" => subtotal * c.Value / 100.0,
            "fixed"      => Math.Min(c.Value, subtotal),
            _            => 0,
        };
        return new Dictionary<string, object>
        {
            ["status"]      = "success",
            ["coupon"]      = coupon_code,
            ["discount"]    = $"${discount:F2}",
            ["final_price"] = $"${subtotal - discount:F2}",
        };
    }
}
