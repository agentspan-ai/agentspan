// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Chat REPL — interactive conversation with a long-running agent via WMQ.
//
// Turns a running agent into a conversational REPL. Every message you type
// is sent into the agent's Workflow Message Queue via runtime.SendMessageAsync();
// the agent dequeues it, thinks, and pushes a reply back via reply_to_user.
// The session stays alive across as many turns as you want — the agent is a
// persistent running workflow, not a one-shot call.
//
// Key WMQ concept — bidirectional conversation loop:
//   The agent uses WaitForMessageTool to receive user input and reply_to_user
//   (a [Tool] method backed by an in-process Channel<string>) to send replies
//   back. The main thread blocks on the channel reader, reads the reply,
//   and prompts again.
//
// Resume support:
//   The REPL saves the execution_id to a session file on start. Run again
//   and the session file is detected automatically — you're reconnected to
//   the same workflow. Conversation history lives on the server.
//
// Start the REPL:
//   dotnet run --project 81_ChatRepl
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)

using System.Threading.Channels;
using Agentspan;
using Agentspan.Examples;

const string SessionFile = "/tmp/agentspan_chat_repl_81.session";

// ── In-process IPC ────────────────────────────────────────────────────
// In Python the workers run in separate OS processes so replies are sent via
// the filesystem. In C# the workers are in-process, so a Channel<string>
// is enough — no filesystem round-trip needed.
var replyChannel = Channel.CreateUnbounded<string>();

// ── Agent definition ──────────────────────────────────────────────────

var agent = new Agent("chat_repl_agent_81")
{
    Model     = Settings.LlmModel,
    MaxTurns  = 10000,
    Stateful  = true,
    Tools     =
    [
        WaitForMessageTool.Create(
            name:        "wait_for_message",
            description: "Wait for the next user message. The message has a 'text' field."),
        ToolDefFactory.Create(
            name:        "reply_to_user",
            description: "Send a reply back to the user in the REPL.",
            handler:     (args, _) =>
            {
                var message = args.TryGetValue("message", out var m) ? m.GetString() ?? "" : "";
                replyChannel.Writer.TryWrite(message);
                return Task.FromResult<object?>("reply sent");
            },
            inputSchema: new System.Text.Json.Nodes.JsonObject
            {
                ["type"] = "object",
                ["properties"] = new System.Text.Json.Nodes.JsonObject
                {
                    ["message"] = new System.Text.Json.Nodes.JsonObject
                    {
                        ["type"] = "string",
                        ["description"] = "The reply text to display to the user.",
                    },
                },
                ["required"] = new System.Text.Json.Nodes.JsonArray { "message" },
            }),
    ],
    Instructions =
        "You are a helpful conversational assistant in an interactive REPL. "
      + "Repeat indefinitely:\n\n"
      + "1. Call wait_for_message to receive the next user message.\n"
      + "2. Respond naturally to the 'text' field in the message.\n"
      + "3. Call reply_to_user with your response.\n"
      + "4. Return to step 1 immediately.",
};

// ── Start or resume ───────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
AgentHandle handle;

if (File.Exists(SessionFile))
{
    var savedId = File.ReadAllText(SessionFile).Trim();
    Console.WriteLine($"Resuming session: {savedId}");
    handle = await runtime.ResumeAsync(savedId, agent);
    Console.WriteLine($"Workers re-registered.");
}
else
{
    handle = await runtime.StartAsync(agent, "Begin. Wait for the user's first message.");
    File.WriteAllText(SessionFile, handle.ExecutionId);
    Console.WriteLine($"Agent started: {handle.ExecutionId}");
    Console.WriteLine($"Session saved to {SessionFile}");
}

Console.WriteLine();
Console.WriteLine(new string('=', 60));
Console.WriteLine("Chat REPL — type 'quit' to exit, 'disconnect' to suspend");
Console.WriteLine(new string('=', 60));
Console.WriteLine();

// ── REPL loop ─────────────────────────────────────────────────────────

while (true)
{
    string userInput;
    try
    {
        Console.Write("You: ");
        userInput = (Console.ReadLine() ?? "").Trim();
    }
    catch (Exception)
    {
        Console.WriteLine("\nDisconnected. Resume later by running the program again.");
        break;
    }

    if (string.IsNullOrEmpty(userInput))
        continue;

    if (userInput.Equals("quit", StringComparison.OrdinalIgnoreCase)
     || userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        handle.Stop();
        Console.WriteLine("Agent stopped.");
        if (File.Exists(SessionFile)) File.Delete(SessionFile);
        break;
    }

    if (userInput.Equals("disconnect", StringComparison.OrdinalIgnoreCase))
    {
        Console.WriteLine("Disconnected. Run the program again to resume.");
        break;
    }

    // Send the message to the agent's WMQ.
    await runtime.SendMessageAsync(handle.ExecutionId, new { text = userInput });

    // Block until reply_to_user writes to the channel.
    using var replyCts = new CancellationTokenSource(TimeSpan.FromSeconds(60));
    try
    {
        var reply = await replyChannel.Reader.ReadAsync(replyCts.Token);
        Console.WriteLine($"Agent: {reply}");
        Console.WriteLine();
    }
    catch (OperationCanceledException)
    {
        Console.WriteLine("(Agent did not reply within 60s. It may still be thinking.)");
    }
}

Console.WriteLine("Session ended.");
