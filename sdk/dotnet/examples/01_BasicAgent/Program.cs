// Basic Agent — simplest possible agent with no tools
using Agentspan;
using AgentspanExamples;

var agent = new Agent(
    name: "greeter",
    model: Settings.LlmModel,
    instructions: "You are a helpful assistant."
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);
var result = runtime.Run(agent, "Say hello and tell me a fun fact about C# programming.");
result.PrintResult();
