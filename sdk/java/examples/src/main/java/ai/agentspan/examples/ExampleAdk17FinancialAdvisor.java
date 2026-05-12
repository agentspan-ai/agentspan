// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

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
public class ExampleAdk17FinancialAdvisor {

    static class PortfolioTools {

        @Tool(name = "get_portfolio", value = "Get the investment portfolio for a client.")
        public Map<String, Object> getPortfolio(@P("client_id") String clientId) {
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

        @Tool(name = "calculate_returns", value = "Calculate returns for an asset over a period.")
        public Map<String, Object> calculateReturns(
                @P("asset") String asset,
                @P("period_months") int periodMonths) {
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
    }

    static class MarketTools {

        @Tool(name = "get_market_data", value = "Get current market data for a sector.")
        public Map<String, Object> getMarketData(@P("sector") String sector) {
            Map<String, Map<String, Object>> sectors = new LinkedHashMap<>();
            sectors.put("technology", Map.of("trend", "bullish", "pe_ratio", 28.5, "ytd_return", "18.3%"));
            sectors.put("healthcare", Map.of("trend", "neutral", "pe_ratio", 22.1, "ytd_return", "8.7%"));
            sectors.put("energy", Map.of("trend", "bearish", "pe_ratio", 15.3, "ytd_return", "-2.1%"));
            sectors.put("bonds", Map.of("trend", "stable", "yield", "4.5%", "ytd_return", "3.2%"));
            return sectors.getOrDefault(sector.toLowerCase(),
                Map.of("error", "Sector '" + sector + "' not found"));
        }

        @Tool(name = "get_economic_indicators", value = "Get current key economic indicators.")
        public Map<String, Object> getEconomicIndicators() {
            return Map.of(
                "gdp_growth", "2.1%",
                "inflation", "3.2%",
                "unemployment", "3.8%",
                "fed_rate", "5.25%",
                "consumer_confidence", 102.5
            );
        }
    }

    static class TaxTools {
        @Tool(name = "estimate_tax_impact", value = "Estimate tax impact of selling an investment.")
        public Map<String, Object> estimateTaxImpact(
                @P("gains") double gains,
                @P("holding_period_months") int holdingPeriodMonths) {
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
    }

    public static void main(String[] args) {
        Agent portfolioAnalyst = GoogleADKAgent.builder()
            .name("portfolio_analyst")
            .model(Settings.LLM_MODEL)
            .instruction("You are a portfolio analyst. Use tools to retrieve and analyze client portfolios.")
            .tools(new PortfolioTools())
            .build();

        Agent marketResearcher = GoogleADKAgent.builder()
            .name("market_researcher")
            .model(Settings.LLM_MODEL)
            .instruction("You are a market researcher. Provide sector analysis and economic outlook.")
            .tools(new MarketTools())
            .build();

        Agent taxAdvisor = GoogleADKAgent.builder()
            .name("tax_advisor")
            .model(Settings.LLM_MODEL)
            .instruction("You are a tax advisor. Estimate tax impacts of proposed changes.")
            .tools(new TaxTools())
            .build();

        Agent coordinator = GoogleADKAgent.builder()
            .name("financial_advisor")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a senior financial advisor. Help clients with investment advice. "
                + "Use the portfolio analyst to review holdings, market researcher for conditions, "
                + "and tax advisor for tax implications. Provide a comprehensive recommendation.")
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
