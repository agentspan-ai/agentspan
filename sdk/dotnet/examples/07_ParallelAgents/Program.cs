// Parallel Agents — run multiple agents concurrently with Strategy.Parallel
// All sub-agents receive the same input and their outputs are aggregated.
using Agentspan;
using AgentspanExamples;

// Each agent analyzes the same topic from a different perspective
var technicalAnalyst = new Agent(
    name: "technical_analyst",
    model: Settings.LlmModel,
    instructions: "You are a technical analyst. Evaluate the technical feasibility, implementation challenges, and engineering considerations. Be specific and precise."
);

var businessAnalyst = new Agent(
    name: "business_analyst",
    model: Settings.LlmModel,
    instructions: "You are a business analyst. Assess market opportunity, ROI, competitive landscape, and business viability. Focus on numbers and market data."
);

var riskAnalyst = new Agent(
    name: "risk_analyst",
    model: Settings.LlmModel,
    instructions: "You are a risk analyst. Identify potential risks, failure modes, regulatory concerns, and mitigation strategies. Be thorough and conservative."
);

// Aggregator combines all parallel analyses
var aggregator = new Agent(
    name: "report_aggregator",
    model: Settings.LlmModel,
    instructions: """
        You receive analysis from multiple specialists running in parallel.
        Synthesize their findings into a comprehensive executive summary that:
        - Highlights key insights from each perspective
        - Identifies areas of consensus and divergence
        - Provides an overall recommendation
        """,
    subAgents: [technicalAnalyst, businessAnalyst, riskAnalyst],
    strategy: Strategy.Parallel
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);
Console.WriteLine("Running parallel analysis (all agents work simultaneously)...\n");
var result = runtime.Run(
    aggregator,
    "Analyze the opportunity to build a SaaS platform for AI-powered code review."
);
result.PrintResult();
