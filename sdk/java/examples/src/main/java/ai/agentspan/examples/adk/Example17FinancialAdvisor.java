// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 17 — Financial Advisor
 *
 * <p>Java port of <code>sdk/python/examples/adk/17_financial_advisor.py</code>.
 *
 * <p>Demonstrates: a coordinator delegating to specialized tool-using
 * sub-agents (portfolio analyst, market researcher, tax advisor).
 */
public class Example17FinancialAdvisor {

    @Schema(description = "Get the investment portfolio for a client.")
    public static Map<String, Object> getPortfolio(
            @Schema(name = "client_id", description = "Client ID") String clientId) {
        Map<String, Map<String, Object>> portfolios = new LinkedHashMap<>();
        portfolios.put("CLT-001", Map.of(
            "client", "Sarah Chen",
            "total_value", 250000,
            "holdings", List.of(
                Map.of("asset", "AAPL", "shares", 100, "value", 17500),
                Map.of("asset", "GOOGL", "shares", 50, "value", 8750),
                Map.of("asset", "US Treasury Bonds", "units", 200, "value", 200000),
                Map.of("asset", "S&P 500 ETF", "shares", 150, "value", 23750)
            ),
            "risk_profile", "moderate"
        ));
        return portfolios.getOrDefault(clientId.toUpperCase(),
            Map.of("error", "Client " + clientId + " not found"));
    }

    @Schema(description = "Calculate returns for an asset over a period.")
    public static Map<String, Object> calculateReturns(
            @Schema(name = "asset", description = "Asset symbol") String asset,
            @Schema(name = "period_months", description = "Period in months") int periodMonths) {
        Map<String, Map<String, Object>> returns = new LinkedHashMap<>();
        returns.put("AAPL", Map.of("return_pct", 15.2, "annualized", 15.2));
        returns.put("GOOGL", Map.of("return_pct", 22.1, "annualized", 22.1));
        returns.put("US Treasury Bonds", Map.of("return_pct", 4.5, "annualized", 4.5));
        returns.put("S&P 500 ETF", Map.of("return_pct", 12.8, "annualized", 12.8));
        Map<String, Object> data = returns.getOrDefault(asset,
            Map.of("return_pct", 0, "annualized", 0));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("asset", asset);
        result.put("period_months", periodMonths);
        result.putAll(data);
        return result;
    }

    @Schema(description = "Get current market data for a sector.")
    public static Map<String, Object> getMarketData(
            @Schema(name = "sector", description = "Sector name") String sector) {
        Map<String, Map<String, Object>> sectors = new LinkedHashMap<>();
        sectors.put("technology", Map.of("trend", "bullish", "pe_ratio", 28.5, "ytd_return", "18.3%"));
        sectors.put("healthcare", Map.of("trend", "neutral", "pe_ratio", 22.1, "ytd_return", "8.7%"));
        sectors.put("energy", Map.of("trend", "bearish", "pe_ratio", 15.3, "ytd_return", "-2.1%"));
        sectors.put("bonds", Map.of("trend", "stable", "yield", "4.5%", "ytd_return", "3.2%"));
        return sectors.getOrDefault(sector.toLowerCase(),
            Map.of("error", "Sector '" + sector + "' not found"));
    }

    @Schema(description = "Get current key economic indicators.")
    public static Map<String, Object> getEconomicIndicators() {
        return Map.of(
            "gdp_growth", "2.1%",
            "inflation", "3.2%",
            "unemployment", "3.8%",
            "fed_rate", "5.25%",
            "consumer_confidence", 102.5
        );
    }

    @Schema(description = "Estimate tax impact of selling an investment.")
    public static Map<String, Object> estimateTaxImpact(
            @Schema(name = "gains", description = "Realized gains") double gains,
            @Schema(name = "holding_period_months", description = "Holding period in months") int holdingPeriodMonths) {
        double rate;
        String category;
        if (holdingPeriodMonths >= 12) {
            rate = 0.15;
            category = "long-term";
        } else {
            rate = 0.32;
            category = "short-term";
        }
        double tax = Math.round(gains * rate * 100.0) / 100.0;
        return Map.of(
            "gains", gains,
            "holding_period", holdingPeriodMonths + " months",
            "category", category,
            "tax_rate", (rate * 100) + "%",
            "estimated_tax", tax
        );
    }

    public static void main(String[] args) {
        LlmAgent portfolioAnalyst = LlmAgent.builder()
            .name("portfolio_analyst")
            .description("Retrieves client portfolios and computes returns on their holdings.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a portfolio analyst. Use tools to retrieve and analyze client portfolios.")
            .tools(
                FunctionTool.create(Example17FinancialAdvisor.class, "getPortfolio"),
                FunctionTool.create(Example17FinancialAdvisor.class, "calculateReturns"))
            .build();

        LlmAgent marketResearcher = LlmAgent.builder()
            .name("market_researcher")
            .description("Provides sector analysis and economic outlook using market data tools.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a market researcher. Provide sector analysis and economic outlook.")
            .tools(
                FunctionTool.create(Example17FinancialAdvisor.class, "getMarketData"),
                FunctionTool.create(Example17FinancialAdvisor.class, "getEconomicIndicators"))
            .build();

        LlmAgent taxAdvisor = LlmAgent.builder()
            .name("tax_advisor")
            .description("Estimates the tax impact of proposed investment changes.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a tax advisor. Estimate tax impacts of proposed changes.")
            .tools(FunctionTool.create(Example17FinancialAdvisor.class, "estimateTaxImpact"))
            .build();

        LlmAgent coordinator = LlmAgent.builder()
            .name("financial_advisor")
            .description("Senior financial advisor coordinating portfolio, market, and tax specialists.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a senior financial advisor. Help clients with investment advice.
                Use the portfolio analyst to review holdings, market researcher for conditions,
                and tax advisor for tax implications. Provide a comprehensive recommendation.
                """)
            .subAgents(portfolioAnalyst, marketResearcher, taxAdvisor)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "I'm client CLT-001. Review my portfolio and tell me if I should rebalance "
            + "given current market conditions. What would the tax impact be if I sold some AAPL?");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
