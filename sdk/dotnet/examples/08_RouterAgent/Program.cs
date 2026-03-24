// Router Agent — explicit router agent with Strategy.Router
// A dedicated router agent decides which sub-agent handles each request.
using Agentspan;
using AgentspanExamples;

// Specialized domain agents
var customerSupportAgent = new Agent(
    name: "customer_support",
    model: Settings.LlmModel,
    instructions: "You are a customer support specialist. Handle billing issues, account problems, refunds, and service complaints with empathy and efficiency."
);

var technicalSupportAgent = new Agent(
    name: "technical_support",
    model: Settings.LlmModel,
    instructions: "You are a technical support engineer. Troubleshoot software bugs, integration issues, API problems, and technical configuration questions."
);

var salesAgent = new Agent(
    name: "sales",
    model: Settings.LlmModel,
    instructions: "You are a sales specialist. Handle pricing inquiries, product comparisons, upgrade paths, and enterprise deals. Be persuasive but honest."
);

// The router agent — decides which specialist to invoke
var router = new Agent(
    name: "intent_router",
    model: Settings.LlmModel,
    instructions: """
        You are a routing agent. Analyze the incoming request and route it to the correct specialist:
        - customer_support: billing, account issues, refunds, complaints
        - technical_support: bugs, APIs, integrations, technical problems
        - sales: pricing, features, upgrades, enterprise inquiries
        Return only the agent name to route to.
        """
);

// Main agent with Router strategy
var helpDesk = new Agent(
    name: "help_desk",
    model: Settings.LlmModel,
    instructions: "You are a help desk system. Use the router to direct requests to the right specialist.",
    subAgents: [customerSupportAgent, technicalSupportAgent, salesAgent],
    strategy: Strategy.Router,
    router: router
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);

Console.WriteLine("=== Request 1: Technical Issue ===");
var result1 = runtime.Run(helpDesk, "I'm getting a 401 Unauthorized error when calling your API with my valid token.");
result1.PrintResult();

Console.WriteLine("\n=== Request 2: Billing Issue ===");
var result2 = runtime.Run(helpDesk, "I was charged twice for my subscription this month and need a refund.");
result2.PrintResult();
