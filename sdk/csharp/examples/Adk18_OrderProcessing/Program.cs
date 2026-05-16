// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk18 — Order Processing.
//
// A single agent that handles the full order lifecycle:
// search -> check stock -> calculate total -> place order.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("order_processor")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are an order processing assistant for TechMart. " +
        "Help customers search products, check availability, calculate totals, and place orders. " +
        "Always verify stock before confirming an order. Provide clear pricing breakdowns.")
    .Tools(new OrderTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "I need a laptop for work. Show me what's available, check stock for your recommendation, " +
    "and calculate the total with express shipping.");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class OrderTools
{
    private static readonly List<Dictionary<string, object>> _catalog = new()
    {
        new() { ["sku"] = "LAP-001", ["name"] = "ProBook Laptop 15\"",      ["category"] = "laptops",     ["price"] = 1299.99, ["stock"] = 23  },
        new() { ["sku"] = "LAP-002", ["name"] = "UltraSlim Notebook 13\"",  ["category"] = "laptops",     ["price"] = 899.99,  ["stock"] = 45  },
        new() { ["sku"] = "ACC-001", ["name"] = "Wireless Mouse",            ["category"] = "accessories", ["price"] = 29.99,   ["stock"] = 200 },
        new() { ["sku"] = "ACC-002", ["name"] = "USB-C Dock",                ["category"] = "accessories", ["price"] = 79.99,   ["stock"] = 67  },
        new() { ["sku"] = "MON-001", ["name"] = "4K Monitor 27\"",           ["category"] = "monitors",    ["price"] = 449.99,  ["stock"] = 12  },
    };
    private static readonly Dictionary<string, Dictionary<string, object>> _stock = new()
    {
        ["LAP-001"] = new() { ["available"] = true, ["quantity"] = 23,  ["warehouse"] = "West"    },
        ["LAP-002"] = new() { ["available"] = true, ["quantity"] = 45,  ["warehouse"] = "East"    },
        ["ACC-001"] = new() { ["available"] = true, ["quantity"] = 200, ["warehouse"] = "Central" },
        ["ACC-002"] = new() { ["available"] = true, ["quantity"] = 67,  ["warehouse"] = "Central" },
        ["MON-001"] = new() { ["available"] = true, ["quantity"] = 12,  ["warehouse"] = "West"    },
    };
    private static readonly Dictionary<string, double> _prices = new()
    {
        ["LAP-001"] = 1299.99, ["LAP-002"] = 899.99, ["ACC-001"] = 29.99,
        ["ACC-002"] = 79.99,   ["MON-001"] = 449.99,
    };
    private static readonly Dictionary<string, double> _shippingRates = new()
    {
        ["standard"] = 9.99, ["express"] = 24.99, ["overnight"] = 49.99,
    };

    [Tool(Name = "search_catalog", Description = "Search the product catalog.")]
    public Dictionary<string, object> SearchCatalog(string query, string category)
    {
        var cat = string.IsNullOrEmpty(category) ? "all" : category;
        var q = query.ToLowerInvariant();
        var results = new List<Dictionary<string, object>>();
        foreach (var item in _catalog)
        {
            var itemCat = (string)item["category"];
            if (cat != "all" && itemCat != cat) continue;
            var name = ((string)item["name"]).ToLowerInvariant();
            if (name.Contains(q) || itemCat.Contains(q)) results.Add(item);
        }
        if (results.Count == 0)
        {
            foreach (var item in _catalog)
            {
                if (cat == "all" || (string)item["category"] == cat) results.Add(item);
            }
        }
        return new Dictionary<string, object>
        {
            ["results"]     = results.Take(5).ToList(),
            ["total_found"] = results.Count,
        };
    }

    [Tool(Name = "check_stock", Description = "Check real-time stock availability for a SKU.")]
    public Dictionary<string, object> CheckStock(string sku)
        => _stock.TryGetValue(sku.ToUpperInvariant(), out var v)
            ? v
            : new Dictionary<string, object> { ["available"] = false, ["quantity"] = 0 };

    [Tool(Name = "calculate_total", Description = "Calculate order total with tax and shipping. item_skus is a comma-separated list of SKUs.")]
    public Dictionary<string, object> CalculateTotal(string item_skus, string shipping_method)
    {
        var items = item_skus.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()).ToList();
        var subtotal = items.Sum(sku => _prices.GetValueOrDefault(sku, 0.0));
        var tax = Math.Round(subtotal * 0.085, 2);
        var method = string.IsNullOrEmpty(shipping_method) ? "standard" : shipping_method;
        var shipping = _shippingRates.GetValueOrDefault(method, 9.99);
        var total = Math.Round(subtotal + tax + shipping, 2);
        return new Dictionary<string, object>
        {
            ["subtotal"]        = subtotal,
            ["tax"]             = tax,
            ["shipping"]        = shipping,
            ["shipping_method"] = method,
            ["total"]           = total,
        };
    }

    [Tool(Name = "place_order", Description = "Place an order. item_skus is a comma-separated list of SKUs.")]
    public Dictionary<string, object> PlaceOrder(string item_skus, string shipping_method, string payment_method)
    {
        var items = item_skus.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()).ToList();
        var method = string.IsNullOrEmpty(shipping_method) ? "standard" : shipping_method;
        var pay = string.IsNullOrEmpty(payment_method) ? "credit_card" : payment_method;
        return new Dictionary<string, object>
        {
            ["order_id"]           = "ORD-2025-0789",
            ["status"]             = "confirmed",
            ["items"]              = items,
            ["shipping_method"]    = method,
            ["payment_method"]     = pay,
            ["estimated_delivery"] = method == "standard" ? "2025-04-22" : "2025-04-18",
        };
    }
}
