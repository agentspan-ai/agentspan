// Streaming — real-time SSE event streaming with await foreach
using Agentspan;
using AgentspanExamples;

var tools = ToolRegistry.FromInstance(new ResearchTools()).ToList();

var agent = new Agent(
    name: "research_agent",
    model: Settings.LlmModel,
    tools: tools,
    instructions: """
        You are a research assistant. When given a topic:
        1. Search for relevant information using web_search
        2. Get details on the most interesting aspects
        3. Synthesize findings into a comprehensive summary
        Think aloud as you research — show your reasoning process.
        """
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);
var cts = new CancellationTokenSource(TimeSpan.FromMinutes(3));

Console.WriteLine("Streaming agent events in real-time...\n");
Console.WriteLine("=".PadRight(60, '='));

int eventCount = 0;
await foreach (var ev in runtime.StreamAsync(agent, "Research the current state of quantum computing and its practical applications.", ct: cts.Token))
{
    eventCount++;
    var timestamp = DateTime.Now.ToString("HH:mm:ss.fff");

    switch (ev.Type)
    {
        case EventType.Thinking:
            Console.ForegroundColor = ConsoleColor.DarkGray;
            Console.WriteLine($"[{timestamp}] THINKING: {ev.Content?.Substring(0, Math.Min(100, ev.Content?.Length ?? 0))}...");
            Console.ResetColor();
            break;

        case EventType.ToolCall:
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine($"[{timestamp}] TOOL CALL: {ev.ToolName}");
            if (ev.Args != null)
            {
                foreach (var (key, value) in ev.Args)
                    Console.WriteLine($"             {key}: {value}");
            }
            Console.ResetColor();
            break;

        case EventType.ToolResult:
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine($"[{timestamp}] TOOL RESULT: {ev.ToolName} completed");
            Console.ResetColor();
            break;

        case EventType.Handoff:
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine($"[{timestamp}] HANDOFF: {ev.Content}");
            Console.ResetColor();
            break;

        case EventType.Message:
            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine($"[{timestamp}] MESSAGE: {ev.Content}");
            Console.ResetColor();
            break;

        case EventType.Error:
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine($"[{timestamp}] ERROR: {ev.Content}");
            Console.ResetColor();
            break;

        case EventType.Done:
            Console.ForegroundColor = ConsoleColor.Magenta;
            Console.WriteLine($"[{timestamp}] DONE");
            Console.ResetColor();
            break;

        default:
            Console.WriteLine($"[{timestamp}] {ev.Type}: {ev.Content}");
            break;
    }
}

Console.WriteLine("=".PadRight(60, '='));
Console.WriteLine($"\nStream completed. Total events received: {eventCount}");

// Tool class must come after top-level statements
class ResearchTools
{
    [Tool(Description = "Search the web for information about a topic")]
    public Dictionary<string, object> WebSearch(string query, int maxResults = 5)
    {
        Console.WriteLine($"  [TOOL] Searching: {query}");
        return new()
        {
            ["query"] = query,
            ["results"] = new[]
            {
                $"Result 1 for '{query}': Key finding about the topic...",
                $"Result 2 for '{query}': Additional context and data...",
                $"Result 3 for '{query}': Expert opinion and analysis..."
            },
            ["result_count"] = Math.Min(maxResults, 3)
        };
    }

    [Tool(Description = "Get detailed information about a specific subject")]
    public Dictionary<string, object> GetDetails(string subject, string aspect = "overview")
    {
        Console.WriteLine($"  [TOOL] Getting details: {subject} ({aspect})");
        return new()
        {
            ["subject"] = subject,
            ["aspect"] = aspect,
            ["content"] = $"Detailed information about {subject} from the {aspect} perspective...",
            ["confidence"] = 0.92
        };
    }
}
