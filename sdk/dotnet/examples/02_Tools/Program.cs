// Tools — [Tool] attribute + ToolRegistry.FromInstance()
using Agentspan;
using AgentspanExamples;

var tools = ToolRegistry.FromInstance(new WeatherTools()).ToList();
var agent = new Agent(
    name: "tool_demo",
    model: Settings.LlmModel,
    tools: tools,
    instructions: "You are a helpful assistant with weather, calculator, and email tools."
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);
var result = runtime.Run(agent, "What's the weather in San Francisco? Then calculate 15 * 7.");
result.PrintResult();

// Tool class must come after top-level statements
class WeatherTools
{
    [Tool(Description = "Get current weather for a city")]
    public Dictionary<string, object> GetWeather(string city)
    {
        var data = city.ToLower() switch
        {
            "new york" => (72, "Partly Cloudy"),
            "san francisco" => (58, "Foggy"),
            "miami" => (85, "Sunny"),
            _ => (70, "Clear")
        };
        return new() { ["city"] = city, ["temperature_f"] = data.Item1, ["condition"] = data.Item2 };
    }

    [Tool(Description = "Evaluate a math expression")]
    public Dictionary<string, object> Calculate(string expression)
    {
        try
        {
            var result = new System.Data.DataTable().Compute(expression, null);
            return new() { ["expression"] = expression, ["result"] = result };
        }
        catch (Exception e)
        {
            return new() { ["expression"] = expression, ["error"] = e.Message };
        }
    }

    [Tool(ApprovalRequired = true, TimeoutSeconds = 60, Description = "Send an email to a recipient")]
    public Dictionary<string, object> SendEmail(string to, string subject, string body)
        => new() { ["status"] = "sent", ["to"] = to, ["subject"] = subject };
}
