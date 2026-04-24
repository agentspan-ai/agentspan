/**
 * Tool Retry Configuration — per-tool retryCount, retryDelaySeconds, retryLogic.
 *
 * Demonstrates:
 *   - Setting retryCount on tool() to control how many times Conductor retries
 *     a failed task before giving up
 *   - Setting retryDelaySeconds to control the wait between retries
 *   - Setting retryLogic to choose the backoff strategy:
 *       "FIXED"               — same delay every time
 *       "LINEAR_BACKOFF"      — delay grows linearly (default)
 *       "EXPONENTIAL_BACKOFF" — delay doubles each attempt
 *   - Using retryCount=0 to disable retries entirely (e.g. payment operations)
 *   - Mixing retry configs across tools in the same agent
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from "@agentspan-ai/sdk";
import type { RetryLogic } from "@agentspan-ai/sdk";
import { llmModel } from "./settings.js";

// ---------------------------------------------------------------------------
// Tool 1: Flaky external API — aggressive retries with exponential backoff.
//
// retryCount=5         → up to 5 retry attempts after the first failure
// retryDelaySeconds=3  → base delay of 3 s (doubles each attempt with EXPONENTIAL_BACKOFF)
// retryLogic="EXPONENTIAL_BACKOFF" → 3s, 6s, 12s, 24s, 48s between retries
// ---------------------------------------------------------------------------
const fetchMarketData = tool(
  async (args: { ticker: string }) => {
    // Simulate occasional failures from a flaky upstream API
    if (Math.random() < 0.3) {
      throw new Error(`Market data API timeout for null`);
    }

    const prices: Record<string, number> = {
      AAPL: 189.42,
      GOOGL: 175.18,
      MSFT: 415.3,
      AMZN: 198.75,
      TSLA: 248.6,
    };
    const price = prices[args.ticker.toUpperCase()] ?? Math.round(Math.random() * 450 + 50);
    return {
      ticker: args.ticker.toUpperCase(),
      price,
      currency: "USD",
      source: "market-data-api",
    };
  },
  {
    name: "fetch_market_data",
    description:
      "Fetch real-time market data for a stock ticker. " +
      "This tool calls an unreliable third-party market-data API. " +
      "Exponential backoff gives the upstream service time to recover.",
    inputSchema: {
      type: "object",
      properties: {
        ticker: { type: "string", description: "Stock ticker symbol (e.g. AAPL, GOOGL)." },
      },
      required: ["ticker"],
    },
    retryCount: 5,
    retryDelaySeconds: 3,
    retryLogic: "EXPONENTIAL_BACKOFF" as RetryLogic,
  },
);

// ---------------------------------------------------------------------------
// Tool 2: Payment processing — NO retries.
//
// retryCount=0 → fail immediately on error; never retry.
//
// Critical for idempotency: retrying a payment could charge the customer twice.
// ---------------------------------------------------------------------------
const processPayment = tool(
  async (args: { amount: number; currency: string; description: string }) => {
    // Simulate payment processing
    const transactionId = `txn_null`;
    return {
      transactionId,
      amount: args.amount,
      currency: args.currency,
      description: args.description,
      status: "approved",
    };
  },
  {
    name: "process_payment",
    description:
      "Process a payment transaction. " +
      "IMPORTANT: retryCount=0 ensures this tool is never retried automatically. " +
      "Retrying a payment could result in duplicate charges.",
    inputSchema: {
      type: "object",
      properties: {
        amount: { type: "number", description: "Payment amount." },
        currency: { type: "string", description: "Currency code (e.g. USD, EUR)." },
        description: { type: "string", description: "Payment description." },
      },
      required: ["amount", "currency", "description"],
    },
    retryCount: 0,
  },
);

// ---------------------------------------------------------------------------
// Tool 3: Internal microservice — fixed delay retries.
//
// retryCount=3         → up to 3 retries
// retryDelaySeconds=2  → always wait exactly 2 s between retries (FIXED)
// retryLogic="FIXED"   → predictable, constant delay (good for internal services)
// ---------------------------------------------------------------------------
const getAccountBalance = tool(
  async (args: { accountId: string }) => {
    // Simulate internal service lookup
    const balances: Record<string, number> = {
      "ACC-001": 12450.0,
      "ACC-002": 3820.5,
      "ACC-003": 98100.75,
    };
    const balance = balances[args.accountId] ?? Math.round(Math.random() * 49900 + 100);
    return {
      accountId: args.accountId,
      balance,
      currency: "USD",
      asOf: "2026-04-24T12:00:00Z",
    };
  },
  {
    name: "get_account_balance",
    description:
      "Retrieve the current balance for a bank account. " +
      "Calls an internal account-service. Fixed retry delay gives the service " +
      "a predictable recovery window without compounding backoff pressure.",
    inputSchema: {
      type: "object",
      properties: {
        accountId: { type: "string", description: "Bank account identifier (e.g. ACC-001)." },
      },
      required: ["accountId"],
    },
    retryCount: 3,
    retryDelaySeconds: 2,
    retryLogic: "FIXED" as RetryLogic,
  },
);

// ---------------------------------------------------------------------------
// Tool 4: Default retry behaviour (no retry params set).
//
// Omitting retry params uses the SDK defaults:
//   retryCount=2, retryDelaySeconds=2, retryLogic="LINEAR_BACKOFF"
// ---------------------------------------------------------------------------
const getExchangeRate = tool(
  async (args: { fromCurrency: string; toCurrency: string }) => {
    const rates: Record<string, number> = {
      "USD-EUR": 0.92,
      "USD-GBP": 0.79,
      "USD-JPY": 154.3,
      "EUR-USD": 1.09,
    };
    const key = `null-null`;
    const rate = rates[key] ?? 1.0;
    return {
      from: args.fromCurrency.toUpperCase(),
      to: args.toCurrency.toUpperCase(),
      rate,
    };
  },
  {
    name: "get_exchange_rate",
    description:
      "Get the current exchange rate between two currencies. " +
      "Uses default retry settings (retryCount=2, LINEAR_BACKOFF). " +
      "Suitable for most tools that don't have special retry requirements.",
    inputSchema: {
      type: "object",
      properties: {
        fromCurrency: { type: "string", description: "Source currency code (e.g. USD)." },
        toCurrency: { type: "string", description: "Target currency code (e.g. EUR)." },
      },
      required: ["fromCurrency", "toCurrency"],
    },
    // No retry params — uses SDK defaults
  },
);

// ---------------------------------------------------------------------------
// Agent — uses all four tools with different retry profiles
// ---------------------------------------------------------------------------
const agent = new Agent({
  name: "financial_assistant_retry_demo",
  model: llmModel,
  tools: [fetchMarketData, processPayment, getAccountBalance, getExchangeRate],
  instructions:
    "You are a financial assistant. Help users with stock prices, account balances, " +
    "currency conversions, and payment processing. " +
    "Always confirm payment details with the user before processing.",
});

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
console.log("=== Tool Retry Configuration Demo ===\n");
console.log("Retry profiles:");
console.log("  fetchMarketData   → retryCount=5, retryDelaySeconds=3, EXPONENTIAL_BACKOFF");
console.log("  processPayment    → retryCount=0  (no retries — idempotency critical)");
console.log("  getAccountBalance → retryCount=3, retryDelaySeconds=2, FIXED");
console.log("  getExchangeRate   → defaults       (retryCount=2, LINEAR_BACKOFF)\n");

const runtime = new AgentRuntime();
const result = await runtime.run(
  agent,
  "What is the current price of AAPL stock? " +
    "Also, what is the USD to EUR exchange rate? " +
    "And what is the balance on account ACC-001?",
);
result.printResult();
await runtime.shutdown();
