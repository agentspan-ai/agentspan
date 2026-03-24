// Handoffs — multi-agent orchestration with Strategy.Handoff
// The orchestrator routes tasks to specialized sub-agents based on context.
using Agentspan;
using AgentspanExamples;

// Specialized sub-agents
var codeAgent = new Agent(
    name: "code_expert",
    model: Settings.LlmModel,
    instructions: "You are a C# and .NET expert. Answer programming questions with precise, working code examples."
);

var mathAgent = new Agent(
    name: "math_expert",
    model: Settings.LlmModel,
    instructions: "You are a mathematics expert. Solve problems step by step, showing your work clearly."
);

var writingAgent = new Agent(
    name: "writing_expert",
    model: Settings.LlmModel,
    instructions: "You are a writing and communication expert. Help craft clear, concise, professional content."
);

// Orchestrator with handoff strategy
var orchestrator = new Agent(
    name: "orchestrator",
    model: Settings.LlmModel,
    instructions: """
        You are an orchestrator that routes tasks to specialists:
        - code_expert: for programming, coding, and software questions
        - math_expert: for mathematics, calculations, and formulas
        - writing_expert: for writing, editing, and communication tasks
        Route the user's request to the most appropriate specialist.
        """,
    subAgents: [codeAgent, mathAgent, writingAgent],
    strategy: Strategy.Handoff
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);

Console.WriteLine("=== Example 1: Code Question ===");
var result1 = runtime.Run(orchestrator, "How do I implement a binary search tree in C#?");
result1.PrintResult();

Console.WriteLine("\n=== Example 2: Math Question ===");
var result2 = runtime.Run(orchestrator, "What is the derivative of x^3 + 2x^2 - 5x + 3?");
result2.PrintResult();
