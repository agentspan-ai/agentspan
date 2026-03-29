#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Financial Advisor — Multi-agent with specialized tool-using sub-agents.

Mirrors the financial-advisor ADK sample. A coordinator agent delegates
to specialized sub-agents (portfolio analyst, market researcher, tax advisor)
each with their own tools.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    # ── Portfolio tools ───────────────────────────────────────────

    def get_portfolio(client_id: str) -> dict:
        """Get the investment portfolio for a client."""
        portfolios = {
            "CLT-001": {
                "client": "Sarah Chen",
                "total_value": 250000,
                "holdings": [
                    {"asset": "AAPL", "shares": 100, "value": 17500},
                    {"asset": "GOOGL", "shares": 50, "value": 8750},
                    {"asset": "US Treasury Bonds", "units": 200, "value": 200000},
                    {"asset": "S&P 500 ETF", "shares": 150, "value": 23750},
                ],
                "risk_profile": "moderate",
            },
        }
        return portfolios.get(client_id.upper(), {"error": f"Client {client_id} not found"})

    def calculate_returns(asset: str, period_months: int = 12) -> dict:
        """Calculate returns for an asset over a period."""
        returns = {
            "AAPL": {"return_pct": 15.2, "annualized": 15.2},
            "GOOGL": {"return_pct": 22.1, "annualized": 22.1},
            "US Treasury Bonds": {"return_pct": 4.5, "annualized": 4.5},
            "S&P 500 ETF": {"return_pct": 12.8, "annualized": 12.8},
        }
        data = returns.get(asset, {"return_pct": 0, "annualized": 0})
        return {"asset": asset, "period_months": period_months, **data}

    # ── Market tools ──────────────────────────────────────────────

    def get_market_data(sector: str) -> dict:
        """Get current market data for a sector."""
        sectors = {
            "technology": {"trend": "bullish", "pe_ratio": 28.5, "ytd_return": "18.3%"},
            "healthcare": {"trend": "neutral", "pe_ratio": 22.1, "ytd_return": "8.7%"},
            "energy": {"trend": "bearish", "pe_ratio": 15.3, "ytd_return": "-2.1%"},
            "bonds": {"trend": "stable", "yield": "4.5%", "ytd_return": "3.2%"},
        }
        return sectors.get(sector.lower(), {"error": f"Sector '{sector}' not found"})

    def get_economic_indicators() -> dict:
        """Get current key economic indicators."""
        return {
            "gdp_growth": "2.1%",
            "inflation": "3.2%",
            "unemployment": "3.8%",
            "fed_rate": "5.25%",
            "consumer_confidence": 102.5,
        }

    # ── Tax tools ─────────────────────────────────────────────────

    def estimate_tax_impact(gains: float, holding_period_months: int) -> dict:
        """Estimate tax impact of selling an investment."""
        if holding_period_months >= 12:
            rate = 0.15  # Long-term capital gains
            category = "long-term"
        else:
            rate = 0.32  # Short-term (ordinary income)
            category = "short-term"
        tax = round(gains * rate, 2)
        return {
            "gains": gains,
            "holding_period": f"{holding_period_months} months",
            "category": category,
            "tax_rate": f"{rate*100}%",
            "estimated_tax": tax,
        }

    # ── Sub-agents ────────────────────────────────────────────────

    portfolio_analyst = Agent(
        name="portfolio_analyst",
        model=settings.llm_model,
        description="Analyzes client portfolios and calculates returns.",
        instruction="You are a portfolio analyst. Use tools to retrieve and analyze client portfolios.",
        tools=[get_portfolio, calculate_returns],
    )

    market_researcher = Agent(
        name="market_researcher",
        model=settings.llm_model,
        description="Researches market conditions and economic indicators.",
        instruction="You are a market researcher. Provide sector analysis and economic outlook.",
        tools=[get_market_data, get_economic_indicators],
    )

    tax_advisor = Agent(
        name="tax_advisor",
        model=settings.llm_model,
        description="Advises on tax implications of investment decisions.",
        instruction="You are a tax advisor. Estimate tax impacts of proposed changes.",
        tools=[estimate_tax_impact],
    )

    # ── Coordinator ───────────────────────────────────────────────

    coordinator = Agent(
        name="financial_advisor",
        model=settings.llm_model,
        instruction=(
            "You are a senior financial advisor. Help clients with investment advice. "
            "Use the portfolio analyst to review holdings, market researcher for conditions, "
            "and tax advisor for tax implications. Provide a comprehensive recommendation."
        ),
        sub_agents=[portfolio_analyst, market_researcher, tax_advisor],
    )

    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.17_financial_advisor
        runtime.deploy(coordinator)
        runtime.serve(coordinator)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # coordinator,
        # "I'm client CLT-001. Review my portfolio and tell me if I should rebalance "
        # "given current market conditions. What would the tax impact be if I sold some AAPL?",
        # )
        # print(f"Status: {result.status}")
        # print(f"Output: {result.output}")



if __name__ == "__main__":
    main()
