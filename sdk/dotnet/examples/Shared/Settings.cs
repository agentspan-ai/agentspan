namespace AgentspanExamples;

public static class Settings
{
    public static string ServerUrl => Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL") ?? "http://localhost:8080/api";
    public static string LlmModel => Environment.GetEnvironmentVariable("AGENTSPAN_LLM_MODEL") ?? "openai/gpt-4o-mini";
    public static string? AuthKey => Environment.GetEnvironmentVariable("AGENTSPAN_AUTH_KEY");
    public static string? AuthSecret => Environment.GetEnvironmentVariable("AGENTSPAN_AUTH_SECRET");
}
