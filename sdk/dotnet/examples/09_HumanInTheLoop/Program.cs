// Human-in-the-Loop — approval workflow for sensitive tool actions
using Agentspan;
using AgentspanExamples;

var tools = ToolRegistry.FromInstance(new DatabaseTools()).ToList();

var agent = new Agent(
    name: "ops_agent",
    model: Settings.LlmModel,
    tools: tools,
    instructions: """
        You are a DevOps automation agent. You can execute database queries and deployments.
        These are sensitive operations that require human approval before execution.
        Always explain what you're about to do before invoking sensitive tools.
        """
);

var config = new AgentConfig
{
    ServerUrl = Settings.ServerUrl,
    AuthKey = Settings.AuthKey,
    AuthSecret = Settings.AuthSecret
};

using var runtime = new AgentRuntime(config);

Console.WriteLine("Starting agent with human-in-the-loop tools...");
Console.WriteLine("The agent will pause and wait for approval on sensitive operations.\n");

var handle = runtime.Start(agent, "Run the database migration to add the user_preferences table, then deploy version 2.1.0 to staging.");

Console.WriteLine($"Agent started with workflow ID: {handle.WorkflowId}");
Console.WriteLine("\nWaiting for agent to reach an approval checkpoint...");

var cts = new CancellationTokenSource(TimeSpan.FromMinutes(5));
bool approved = false;

while (!cts.Token.IsCancellationRequested)
{
    await Task.Delay(2000, cts.Token);

    if (!approved)
    {
        Console.WriteLine("\nAgent is waiting for approval on a sensitive tool call.");
        Console.Write("Approve this action? (y/n): ");
        var input = Console.ReadLine()?.Trim().ToLower() ?? "n";

        if (input == "y")
        {
            Console.WriteLine("Approving...");
            await handle.ApproveAsync(cts.Token);
            approved = true;
            Console.WriteLine("Approved! Agent continuing...\n");
        }
        else
        {
            Console.WriteLine("Rejecting...");
            await handle.RejectAsync("Rejected by operator - not authorized at this time", cts.Token);
            Console.WriteLine("Rejected. Agent will handle the rejection.\n");
            break;
        }
    }
    else
    {
        break;
    }
}

var result = await handle.WaitAsync(cts.Token);
result.PrintResult();

// Tool class must come after top-level statements
class DatabaseTools
{
    [Tool(
        Description = "Execute a SQL query against the production database",
        ApprovalRequired = true,
        TimeoutSeconds = 300)]
    public Dictionary<string, object> ExecuteSql(string query, string database = "production")
    {
        Console.WriteLine($"  [TOOL] Executing SQL on {database}: {query}");
        return new()
        {
            ["rows_affected"] = 42,
            ["status"] = "success",
            ["database"] = database,
            ["query"] = query
        };
    }

    [Tool(
        Description = "Deploy a new version of the application",
        ApprovalRequired = true,
        TimeoutSeconds = 600)]
    public Dictionary<string, object> Deploy(string service, string version, string environment = "staging")
    {
        Console.WriteLine($"  [TOOL] Deploying {service} v{version} to {environment}");
        return new()
        {
            ["status"] = "deployed",
            ["service"] = service,
            ["version"] = version,
            ["environment"] = environment,
            ["deployment_id"] = $"dep_{Guid.NewGuid():N}"[..12]
        };
    }
}
