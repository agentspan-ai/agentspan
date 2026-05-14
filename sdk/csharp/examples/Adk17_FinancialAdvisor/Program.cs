// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk17 — Financial Advisor.
//
// A coordinator delegating to specialized tool-using sub-agents
// (portfolio analyst, market researcher, tax advisor).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var portfolioAnalyst = GoogleADKAgent.Builder()
    .Name("portfolio_analyst")
    .Model(Settings.LlmModel)
    .Instruction("You are a portfolio analyst. Use tools to retrieve and analyze client portfolios.")
    .Tools(new PortfolioTools())
    .Build();

var marketResearcher = GoogleADKAgent.Builder()
    .Name("market_researcher")
    .Model(Settings.LlmModel)
    .Instruction("You are a market researcher. Provide sector analysis and economic outlook.")
    .Tools(new MarketTools())
    .Build();

var taxAdvisor = GoogleADKAgent.Builder()
    .Name("tax_advisor")
    .Model(Settings.LlmModel)
    .Instruction("You are a tax advisor. Estimate tax impacts of proposed changes.")
    .Tools(new TaxTools())
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("financial_advisor")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a senior financial advisor. Help clients with investment advice. " +
        "Use the portfolio analyst to review holdings, market researcher for conditions, " +
        "and tax advisor for tax implications. Provide a comprehensive recommendation.")
    .SubAgents(portfolioAnalyst, marketResearcher, taxAdvisor)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "I'm client CLT-001. Review my portfolio and tell me if I should rebalance " +
    "given current market conditions. What would the tax impact be if I sold some AAPL?");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class PortfolioTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _portfolios = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CLT-001"] = new()
        {
            ["client"]      = "Sarah Chen",
            ["total_value"] = 250000,
            ["holdings"]    = new List<Dictionary<string, object>>
            {
                new() { ["asset"] = "AAPL",              ["shares"] = 100, ["value"] = 17500  },
                new() { ["asset"] = "GOOGL",             ["shares"] = 50,  ["value"] = 8750   },
                new() { ["asset"] = "US Treasury Bonds", ["units"]  = 200, ["value"] = 200000 },
                new() { ["asset"] = "S&P 500 ETF",       ["shares"] = 150, ["value"] = 23750  },
            },
            ["risk_profile"] = "moderate",
        },
    };
    private static readonly Dictionary<string, Dictionary<string, object>> _returns = new()
    {
        ["AAPL"]              = new() { ["return_pct"] = 15.2, ["annualized"] = 15.2 },
        ["GOOGL"]             = new() { ["return_pct"] = 22.1, ["annualized"] = 22.1 },
        ["US Treasury Bonds"] = new() { ["return_pct"] = 4.5,  ["annualized"] = 4.5  },
        ["S&P 500 ETF"]       = new() { ["return_pct"] = 12.8, ["annualized"] = 12.8 },
    };

    [Tool(Name = "get_portfolio", Description = "Get the investment portfolio for a client.")]
    public Dictionary<string, object> GetPortfolio(string client_id)
        => _portfolios.TryGetValue(client_id, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Client {client_id} not found" };

    [Tool(Name = "calculate_returns", Description = "Calculate returns for an asset over a period.")]
    public Dictionary<string, object> CalculateReturns(string asset, int period_months)
    {
        var data = _returns.TryGetValue(asset, out var v)
            ? v
            : new Dictionary<string, object> { ["return_pct"] = 0, ["annualized"] = 0 };
        var result = new Dictionary<string, object>
        {
            ["asset"]         = asset,
            ["period_months"] = period_months,
        };
        foreach (var (k, val) in data) result[k] = val;
        return result;
    }
}

internal sealed class MarketTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _sectors = new(StringComparer.OrdinalIgnoreCase)
    {
        ["technology"] = new() { ["trend"] = "bullish", ["pe_ratio"] = 28.5,    ["ytd_return"] = "18.3%" },
        ["healthcare"] = new() { ["trend"] = "neutral", ["pe_ratio"] = 22.1,    ["ytd_return"] = "8.7%"  },
        ["energy"]     = new() { ["trend"] = "bearish", ["pe_ratio"] = 15.3,    ["ytd_return"] = "-2.1%" },
        ["bonds"]      = new() { ["trend"] = "stable",  ["yield"]    = "4.5%",  ["ytd_return"] = "3.2%"  },
    };

    [Tool(Name = "get_market_data", Description = "Get current market data for a sector.")]
    public Dictionary<string, object> GetMarketData(string sector)
        => _sectors.TryGetValue(sector, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Sector '{sector}' not found" };

    [Tool(Name = "get_economic_indicators", Description = "Get current key economic indicators.")]
    public Dictionary<string, object> GetEconomicIndicators()
        => new()
        {
            ["gdp_growth"]          = "2.1%",
            ["inflation"]           = "3.2%",
            ["unemployment"]        = "3.8%",
            ["fed_rate"]            = "5.25%",
            ["consumer_confidence"] = 102.5,
        };
}

internal sealed class TaxTools
{
    [Tool(Name = "estimate_tax_impact", Description = "Estimate tax impact of selling an investment.")]
    public Dictionary<string, object> EstimateTaxImpact(double gains, int holding_period_months)
    {
        double rate;
        string category;
        if (holding_period_months >= 12) { rate = 0.15; category = "long-term"; }
        else                              { rate = 0.32; category = "short-term"; }
        var tax = Math.Round(gains * rate, 2);
        return new Dictionary<string, object>
        {
            ["gains"]          = gains,
            ["holding_period"] = $"{holding_period_months} months",
            ["category"]       = category,
            ["tax_rate"]       = $"{rate * 100}%",
            ["estimated_tax"]  = tax,
        };
    }
}
