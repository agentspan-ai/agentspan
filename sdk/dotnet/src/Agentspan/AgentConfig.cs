namespace Agentspan;

public sealed class AgentConfig
{
    public string ServerUrl { get; init; } = "http://localhost:8080/api";
    public string? AuthKey { get; init; }
    public string? AuthSecret { get; init; }
    public int WorkerPollIntervalMs { get; init; } = 100;
    public int WorkerThreadCount { get; init; } = 5;
    public int StatusPollIntervalMs { get; init; } = 1000;

    public static AgentConfig FromEnv() => new()
    {
        ServerUrl = Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL") ?? "http://localhost:8080/api",
        AuthKey = Environment.GetEnvironmentVariable("AGENTSPAN_AUTH_KEY"),
        AuthSecret = Environment.GetEnvironmentVariable("AGENTSPAN_AUTH_SECRET"),
    };
}
