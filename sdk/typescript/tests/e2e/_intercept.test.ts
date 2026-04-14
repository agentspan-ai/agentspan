import { it } from "vitest";
import { createReactAgent } from "@langchain/langgraph/prebuilt";
import { ChatOpenAI } from "@langchain/openai";
import { DynamicStructuredTool } from "@langchain/core/tools";
import { z } from "zod";
import { serializeLangGraph } from "../../src/frameworks/langgraph-serializer.js";

it("trace what gets sent to server", async () => {
  const calculateTool = new DynamicStructuredTool({
    name: "calculate",
    description: "Evaluate a mathematical expression.",
    schema: z.object({ expression: z.string() }),
    func: async ({ expression }) => String(eval(expression)),
  });

  const llm = new ChatOpenAI({ model: "gpt-4o-mini", temperature: 0 });
  const graph = createReactAgent({ llm, tools: [calculateTool], name: "test" });
  (graph as any)._agentspan = {
    model: "openai/gpt-4o-mini",
    tools: [calculateTool],
    framework: "langgraph",
  };

  // Step 1: What does the serializer produce?
  const [rawConfig, _workers] = serializeLangGraph(graph);
  const tool = (rawConfig.tools as any[])[0];
  console.log("=== SDK serializeLangGraph output ===");
  console.log("parameters:", JSON.stringify(tool.parameters));

  // Step 2: What does JSON.stringify(rawConfig) produce? (this is what fetch sends)
  const payload = { framework: "langgraph", rawConfig, prompt: "test" };
  const jsonStr = JSON.stringify(payload);

  // Extract just the tool parameters from the JSON string
  const parsed = JSON.parse(jsonStr);
  const sentTool = parsed.rawConfig.tools[0];
  console.log("=== After JSON round-trip ===");
  console.log("parameters:", JSON.stringify(sentTool.parameters));
  console.log("parameters.type:", sentTool.parameters?.type);
  console.log("parameters.properties:", JSON.stringify(sentTool.parameters?.properties));

  // Step 3: POST to /agent/start (what runtime.run() uses)
  const resp = await fetch("http://localhost:6767/api/agent/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: jsonStr,
  });
  console.log("=== Server /agent/start response ===");
  console.log("status:", resp.status);
  const result = resp.ok ? ((await resp.json()) as any) : null;
  console.log("response keys:", result ? Object.keys(result) : "FAILED");
  console.log("executionId:", result?.executionId);

  // If we got an executionId, check the workflow
  if (result?.executionId) {
    // Wait for workflow to progress past LLM call
    await new Promise((r) => setTimeout(r, 10000));
    const wfResp = await fetch(`http://localhost:6767/api/workflow/${result.executionId}`);
    if (wfResp.ok) {
      const wf = (await wfResp.json()) as any;
      console.log("=== Workflow tasks ===");
      for (const t of wf.tasks || []) {
        const status = t.status || "?";
        const reason = (t.reasonForIncompletion || "").slice(0, 150);
        console.log(
          `  ${t.referenceTaskName} [${t.taskType}] ${status} ${reason ? "| " + reason : ""}`,
        );
      }
    }
  }
  if (!resp.ok) {
    const text = await resp.text();
    console.log("error:", text.slice(0, 500));
  }
});
