import { expect, Page, test } from "@playwright/test";

const now = Date.now();

const EXECUTION_FIXTURE = {
  workflowId: "exec-align-123",
  workflowName: "todo_agent",
  workflowType: "todo_agent",
  workflowVersion: 1,
  version: 1,
  status: "COMPLETED",
  startTime: now - 12_000,
  endTime: now,
  updateTime: now,
  executionTime: 12_000,
  correlationId: "corr-align-123",
  createdBy: "playwright",
  failedReferenceTaskNames: "",
  priority: 0,
  reasonForIncompletion: "",
  inputSize: 0,
  outputSize: 0,
  input: {
    prompt: "Add a todo and show me the latest todo list.",
  },
  output: {
    result: "Your todo list was: Review PR #42, Write demo notes.",
  },
  workflowDefinition: {
    name: "todo_agent",
    version: 1,
    tasks: [],
    metadata: {
      agent_sdk: "conductor",
      agentDef: {},
    },
  },
  tasks: [
    {
      taskId: "llm-1",
      referenceTaskName: "todo_agent_llm__1",
      taskType: "LLM_CHAT_COMPLETE",
      workflowTask: {
        name: "todo_agent_llm",
        taskReferenceName: "todo_agent_llm__1",
        type: "LLM_CHAT_COMPLETE",
      },
      inputData: {
        model: "gpt-5.4",
        messages: [
          { role: "system", message: "You are a helpful todo assistant." },
          { role: "user", message: "Add a todo and show me the latest todo list." },
        ],
        tools: [{ name: "add_todo" }, { name: "get_todo_list" }],
      },
      outputData: {
        finishReason: "tool_calls",
        promptTokens: 420,
        completionTokens: 41,
      },
      status: "COMPLETED",
      executed: true,
      workflowType: "todo_agent",
      loopOverTask: false,
      startTime: now - 11_500,
      endTime: now - 11_000,
      updateTime: now - 11_000,
      seq: "1",
    },
    {
      taskId: "tool-1",
      referenceTaskName: "call_add_todo__1",
      taskType: "add_todo",
      workflowTask: {
        name: "add_todo",
        taskReferenceName: "call_add_todo__1",
        type: "SIMPLE",
      },
      inputData: {
        task: "Prepare demo",
      },
      outputData: {
        result: "Added: 'Prepare demo notes'",
      },
      status: "COMPLETED",
      executed: true,
      workflowType: "todo_agent",
      loopOverTask: false,
      startTime: now - 10_700,
      endTime: now - 10_200,
      updateTime: now - 10_200,
      seq: "2",
    },
    {
      taskId: "tool-2",
      referenceTaskName: "call_get_todo_list__1",
      taskType: "get_todo_list",
      workflowTask: {
        name: "get_todo_list",
        taskReferenceName: "call_get_todo_list__1",
        type: "SIMPLE",
      },
      inputData: {},
      outputData: {
        result: "Review PR #42\\nWrite demo notes",
      },
      status: "COMPLETED",
      executed: true,
      workflowType: "todo_agent",
      loopOverTask: false,
      startTime: now - 10_650,
      endTime: now - 10_100,
      updateTime: now - 10_100,
      seq: "3",
    },
    {
      taskId: "llm-2",
      referenceTaskName: "todo_agent_llm__2",
      taskType: "LLM_CHAT_COMPLETE",
      workflowTask: {
        name: "todo_agent_llm",
        taskReferenceName: "todo_agent_llm__2",
        type: "LLM_CHAT_COMPLETE",
      },
      inputData: {
        model: "gpt-5.4",
        messages: [
          { role: "system", message: "You are a helpful todo assistant." },
          { role: "user", message: "Summarize the resulting todo list." },
        ],
      },
      outputData: {
        finishReason: "stop",
        result: "Your todo list was: Review PR #42 and Write demo notes.",
        promptTokens: 380,
        completionTokens: 58,
      },
      status: "COMPLETED",
      executed: true,
      workflowType: "todo_agent",
      loopOverTask: false,
      startTime: now - 9_400,
      endTime: now - 8_900,
      updateTime: now - 8_900,
      seq: "4",
    },
  ],
};

async function mockApis(page: Page) {
  await page.route("**/api/agent/executions/exec-align-123/full", async (route) => {
    return route.fulfill({ json: EXECUTION_FIXTURE });
  });

  await page.route("**/api/credentials", async (route) => {
    return route.fulfill({ json: [] });
  });

  await page.route("**/api/credentials/bindings", async (route) => {
    return route.fulfill({ json: [] });
  });

  await page.route("**/api/metadata/taskdefs*", async (route) => {
    return route.fulfill({ json: [] });
  });

  await page.route("**/api/event*", async (route) => {
    return route.fulfill({ json: [] });
  });

  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (
      url.includes("/api/agent/executions/exec-align-123/full") ||
      url.includes("/api/credentials") ||
      url.includes("/api/metadata/taskdefs") ||
      url.includes("/api/event")
    ) {
      return route.fallback();
    }
    return route.fulfill({ json: {} });
  });
}

test("agent execution diagram keeps LLM cards aligned through fork/join", async ({ page }) => {
  await mockApis(page);

  await page.goto("/execution/exec-align-123");

  const llmModelLabels = page.getByText("gpt-5.4", { exact: true });
  await expect(llmModelLabels.first()).toBeVisible({ timeout: 15000 });
  await expect(llmModelLabels.nth(1)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("add_todo", { exact: true })).toBeVisible();
  await expect(page.getByText("get_todo_list", { exact: true })).toBeVisible();

  await page.screenshot({
    path: "e2e-results/agent-execution-diagram-alignment.png",
    fullPage: true,
  });

  const topBox = await llmModelLabels.first().boundingBox();
  const bottomBox = await llmModelLabels.nth(1).boundingBox();
  const leftToolBox = await page.getByText("add_todo", { exact: true }).boundingBox();
  const rightToolBox = await page.getByText("get_todo_list", { exact: true }).boundingBox();

  expect(topBox).not.toBeNull();
  expect(bottomBox).not.toBeNull();
  expect(leftToolBox).not.toBeNull();
  expect(rightToolBox).not.toBeNull();

  const topCenterX = topBox!.x + topBox!.width / 2;
  const bottomCenterX = bottomBox!.x + bottomBox!.width / 2;
  const centerDelta = Math.abs(topCenterX - bottomCenterX);
  const leftToolCenterX = leftToolBox!.x + leftToolBox!.width / 2;
  const rightToolCenterX = rightToolBox!.x + rightToolBox!.width / 2;
  const forkMidpointX = (leftToolCenterX + rightToolCenterX) / 2;
  const forkCenterDelta = Math.abs(topCenterX - forkMidpointX);

  console.log({
    topCenterX,
    bottomCenterX,
    centerDelta,
    leftToolCenterX,
    rightToolCenterX,
    forkMidpointX,
    forkCenterDelta,
  });

  expect(centerDelta).toBeLessThanOrEqual(8);
  expect(forkCenterDelta).toBeLessThanOrEqual(8);
});
