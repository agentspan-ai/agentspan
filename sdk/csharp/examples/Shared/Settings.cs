namespace Agentspan.Examples;

internal static class Settings
{
    public static string LlmModel =>
        Environment.GetEnvironmentVariable("AGENTSPAN_LLM_MODEL") ?? "openai/gpt-4o-mini";

    public static string ServerUrl =>
        Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL") ?? "http://localhost:6767/api";
}
