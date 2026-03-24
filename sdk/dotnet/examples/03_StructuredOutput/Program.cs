// Structured Output — typed response via outputType
using Agentspan;
using AgentspanExamples;

var agent = new Agent(
    name: "weather_reporter",
    model: Settings.LlmModel,
    instructions: "You are a weather reporter. Always respond with structured weather data.",
    outputType: typeof(WeatherReport)
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);
var result = runtime.Run(agent, "Give me a weather report for New York City.");
result.PrintResult();

var report = result.GetOutput<WeatherReport>();
if (report != null)
{
    Console.WriteLine($"\nCity: {report.City}");
    Console.WriteLine($"Temperature: {report.TemperatureF}°F");
    Console.WriteLine($"Condition: {report.Condition}");
    Console.WriteLine($"Summary: {report.Summary}");
}

// Type declaration must come after top-level statements
class WeatherReport
{
    public string City { get; set; } = "";
    public int TemperatureF { get; set; }
    public string Condition { get; set; } = "";
    public string Summary { get; set; } = "";
}
