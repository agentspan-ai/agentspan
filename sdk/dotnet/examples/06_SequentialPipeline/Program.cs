// Sequential Pipeline — researcher >> writer >> editor using the >> operator
// Each agent processes and passes output to the next in the chain.
using Agentspan;
using AgentspanExamples;

var researcher = new Agent(
    name: "researcher",
    model: Settings.LlmModel,
    instructions: """
        You are a research specialist. Given a topic, produce a structured research summary with:
        - Key facts and statistics
        - Main concepts to cover
        - Interesting angles or perspectives
        Keep it concise but comprehensive (3-5 bullet points per section).
        """
);

var writer = new Agent(
    name: "writer",
    model: Settings.LlmModel,
    instructions: """
        You are a professional content writer. Given research material, write a well-structured,
        engaging article with:
        - A compelling introduction
        - 2-3 body paragraphs with clear transitions
        - A strong conclusion
        Write in a clear, accessible style for a general audience.
        """
);

var editor = new Agent(
    name: "editor",
    model: Settings.LlmModel,
    instructions: """
        You are an expert editor. Review and polish the article for:
        - Clarity and readability
        - Grammar and style consistency
        - Flow and transitions
        - Compelling headline
        Return the final polished version with a title.
        """
);

// Compose agents into a sequential pipeline using >> operator
var pipeline = researcher >> writer >> editor;

Console.WriteLine($"Pipeline: {pipeline.Name}");
Console.WriteLine($"Strategy: {pipeline.Strategy}");
Console.WriteLine($"Stages: {string.Join(" >> ", pipeline.SubAgents.Select(a => a.Name))}");
Console.WriteLine();

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);
var result = runtime.Run(pipeline, "Write an article about the benefits of functional programming in modern software development.");
result.PrintResult();
