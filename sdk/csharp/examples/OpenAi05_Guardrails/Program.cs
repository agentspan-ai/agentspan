// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi05 — Guardrails.
//
// A banking assistant that uses function tools to look up balances
// and transfer funds. The Python original wraps the agent with PII
// regex input guardrails and forbidden-phrase output guardrails.
//
// Note: simplified from Java original — input_guardrails / output_guardrails
// are not yet surfaced on the OpenAIAgent builder. The tool surface
// and agent shape are ported faithfully; the intended guardrail policy
// is documented below.
//
// Intended guardrails:
//   Input  — block SSN regex (\b\d{3}-\d{2}-\d{4}\b) and credit-card regex
//            (\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b).
//   Output — block "internal system", "database password", "api key",
//            "secret token".
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var agent = OpenAIAgent.Builder()
    .Name("banking_assistant")
    .Instructions(
        "You are a secure banking assistant. Help users check account balances " +
        "and transfer funds. Never reveal internal system details.")
    .Model(Settings.LlmModel)
    .Tools(new BankingTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent, "What's the balance on account ACC-100?");
result.PrintResult();

internal sealed class BankingTools
{
    [Tool(Name = "get_account_balance", Description = "Look up the balance of a bank account.")]
    public string GetAccountBalance(string account_id) => account_id switch
    {
        "ACC-100" => "$5,230.00",
        "ACC-200" => "$12,750.50",
        "ACC-300" => "$890.25",
        _         => $"Account {account_id} not found",
    };

    [Tool(Name = "transfer_funds", Description = "Transfer funds between accounts.")]
    public string TransferFunds(string from_account, string to_account, double amount)
        => $"Transferred ${amount:F2} from {from_account} to {to_account}.";
}
