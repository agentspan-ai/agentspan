import { describe, it, expect } from "vitest";
import type { DeploymentInfo } from "../../src/types.js";

describe("deploy bin script", () => {
  it("should filter agents by name", async () => {
    const { filterAgents } = await import("../../cli-bin/deploy.js");
    const agents = [{ name: "researcher" }, { name: "summarizer" }] as any;
    const filtered = filterAgents(agents, "researcher");
    expect(filtered).toHaveLength(1);
    expect(filtered[0].name).toBe("researcher");
  });

  it("should return all agents when no filter", async () => {
    const { filterAgents } = await import("../../cli-bin/deploy.js");
    const agents = [{ name: "a" }, { name: "b" }] as any;
    expect(filterAgents(agents, undefined)).toHaveLength(2);
  });

  it("should format successful result", async () => {
    const { formatDeployResult } = await import("../../cli-bin/deploy.js");
    const info: DeploymentInfo = { workflowName: "wf_a", agentName: "a" };
    expect(formatDeployResult("a", info, null)).toEqual({
      agent_name: "a",
      workflow_name: "wf_a",
      success: true,
      error: null,
    });
  });

  it("should format failed result", async () => {
    const { formatDeployResult } = await import("../../cli-bin/deploy.js");
    expect(formatDeployResult("b", null, "failed")).toEqual({
      agent_name: "b",
      workflow_name: null,
      success: false,
      error: "failed",
    });
  });
});
