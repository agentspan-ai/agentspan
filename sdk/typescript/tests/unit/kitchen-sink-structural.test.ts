/**
 * Kitchen Sink — Structural Assertions
 *
 * Validates the structural properties of the kitchen sink pipeline
 * without requiring a running server.
 */

/* eslint-disable @typescript-eslint/no-unused-vars */
import { describe, it, expect } from "vitest";
import { z } from "zod";

import {
  // Stage 1
  intakeRouter,
  techClassifier,
  businessClassifier,
  creativeClassifier,
  ClassificationResult,

  // Stage 2
  researchTeam,
  researchCoordinator,
  dataAnalyst,
  researcherWorker,
  researchDatabase,
  webSearch,
  mcpFactChecker,
  petstoreApi,
  externalResearchAggregator,
  analyzeTrends,

  // Stage 3
  writingPipeline,
  draftWriter,
  editorAgent,
  semanticMem,
  recallPastArticles,
  callbackLog,

  // Stage 4
  reviewAgent,
  piiGuardrail,
  biasGuardrail,
  factValidator,
  complianceGuardrail,
  sqlInjectionGuard,
  safeSearch,

  // Stage 5
  editorialAgent,
  publishArticle,
  editorialQuestion,
  editorialReviewer,

  // Stage 6
  toneDebate,
  translationSwarm,
  titleBrainstorm,
  manualTranslation,
  spanishTranslator,
  frenchTranslator,
  germanTranslator,

  // Stage 7
  publishingPipeline,
  formatter,
  externalPublisher,

  // Stage 8
  analyticsAgent,
  gptAssistant,
  quickResearcher,
  researchSubtool,
  ArticleReport,

  // Full pipeline
  fullPipeline,
} from "../../examples/kitchen-sink.js";

import { Agent } from "../../src/agent.js";
import { RegexGuardrail, LLMGuardrail } from "../../src/guardrail.js";
import { UserProxyAgent, GPTAssistantAgent } from "../../src/ext.js";
import {
  TextMention,
  MaxMessage,
  TokenUsageCondition,
  OrCondition,
  AndCondition,
} from "../../src/termination.js";
import { OnToolResult, OnTextMention, OnCondition, TextGate } from "../../src/handoff.js";
import { getToolDef } from "../../src/tool.js";
import { AgentConfigSerializer } from "../../src/serializer.js";

// ═══════════════════════════════════════════════════════════════════════
// Pipeline structure
// ═══════════════════════════════════════════════════════════════════════

describe("Kitchen Sink — Pipeline Structure", () => {
  it("full pipeline has correct number of agents (8 stages)", () => {
    expect(fullPipeline.agents).toHaveLength(8);
  });

  it("full pipeline uses sequential strategy", () => {
    expect(fullPipeline.strategy).toBe("sequential");
  });

  it("full pipeline has composable termination", () => {
    expect(fullPipeline.termination).toBeDefined();
    const json = fullPipeline.termination!.toJSON() as Record<string, unknown>;
    expect(json.type).toBe("or");
    const conditions = json.conditions as Array<Record<string, unknown>>;
    expect(conditions).toHaveLength(2);
    expect(conditions[0].type).toBe("text_mention");
    expect(conditions[1].type).toBe("max_message");
  });

  it("all stage agents are Agent instances", () => {
    for (const agent of fullPipeline.agents) {
      expect(agent).toBeInstanceOf(Agent);
    }
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 1: Intake & Classification
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 1: Intake & Classification", () => {
  it("intake router uses router strategy", () => {
    expect(intakeRouter.strategy).toBe("router");
  });

  it("intake router has 3 classifier sub-agents", () => {
    expect(intakeRouter.agents).toHaveLength(3);
    const names = intakeRouter.agents.map((a) => a.name);
    expect(names).toContain("tech_classifier");
    expect(names).toContain("business_classifier");
    expect(names).toContain("creative_classifier");
  });

  it("intake router has a router agent", () => {
    expect(intakeRouter.router).toBeDefined();
    expect(intakeRouter.router).toBeInstanceOf(Agent);
    expect((intakeRouter.router as Agent).name).toBe("category_router");
  });

  it("intake router has structured output (JSON Schema)", () => {
    expect(intakeRouter.outputType).toBeDefined();
    // Verify it's a JSON Schema object
    expect(intakeRouter.outputType).toHaveProperty("type", "object");
    expect(intakeRouter.outputType).toHaveProperty("properties");
  });

  it("intake router uses PromptTemplate for instructions", () => {
    expect(intakeRouter.instructions).toBeDefined();
    const tmpl = intakeRouter.instructions as { name: string; variables?: Record<string, string> };
    expect(tmpl.name).toBe("article-classifier");
    expect(tmpl.variables?.categories).toBe("tech, business, creative");
  });

  it("ClassificationResult is a JSON Schema with correct fields", () => {
    const props = (ClassificationResult as any).properties;
    expect(props.category).toBeDefined();
    expect(props.priority).toBeDefined();
    expect(props.tags).toBeDefined();
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 2: Research Team
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 2: Research Team", () => {
  it("research team uses parallel strategy", () => {
    expect(researchTeam.strategy).toBe("parallel");
  });

  it("research team has 2 sub-agents", () => {
    expect(researchTeam.agents).toHaveLength(2);
    const names = researchTeam.agents.map((a) => a.name);
    expect(names).toContain("research_coordinator");
    expect(names).toContain("data_analyst");
  });

  it("scatter_gather produces coordinator with agent_tool workers", () => {
    // scatterGather now creates a flat coordinator with agent_tool tools
    expect(researchCoordinator.tools.length).toBeGreaterThanOrEqual(1);
    expect(researchCoordinator.tools[0]).toHaveProperty("toolType", "agent_tool");
  });

  it("researcher worker has correct tools", () => {
    expect(researcherWorker.tools).toHaveLength(4);
  });

  it("research_database tool has credentials", () => {
    const def = getToolDef(researchDatabase);
    expect(def.name).toBe("research_database");
    expect(def.credentials).toBeDefined();
    expect(def.credentials!.length).toBeGreaterThan(0);
  });

  it("web_search is an HTTP tool with credential header", () => {
    expect(webSearch.toolType).toBe("http");
    expect(webSearch.config).toBeDefined();
    const config = webSearch.config as Record<string, unknown>;
    const headers = config.headers as Record<string, string>;
    expect(headers.Authorization).toContain("${SEARCH_API_KEY}");
  });

  it("mcp_fact_checker is an MCP tool", () => {
    expect(mcpFactChecker.toolType).toBe("mcp");
  });

  it("petstore_api is an API tool", () => {
    expect(petstoreApi.toolType).toBe("api");
  });

  it("external_research_aggregator has external=true", () => {
    const def = getToolDef(externalResearchAggregator);
    expect(def.external).toBe(true);
    expect(def.func).toBeNull();
  });

  it("analyze_trends has isolated=false", () => {
    const def = getToolDef(analyzeTrends);
    expect(def.isolated).toBe(false);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 3: Writing Pipeline
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 3: Writing Pipeline", () => {
  it("writing pipeline is sequential (via .pipe())", () => {
    expect(writingPipeline.strategy).toBe("sequential");
    expect(writingPipeline.agents).toHaveLength(2);
  });

  it("pipeline agents are draft_writer then editor", () => {
    expect(writingPipeline.agents[0].name).toBe("draft_writer");
    expect(writingPipeline.agents[1].name).toBe("editor");
  });

  it("draft_writer has ConversationMemory with maxMessages=50", () => {
    expect(draftWriter.memory).toBeDefined();
    expect(draftWriter.memory!.maxMessages).toBe(50);
  });

  it("draft_writer has callback handlers", () => {
    expect(draftWriter.callbacks).toHaveLength(1);
  });

  it("editor has stopWhen function", () => {
    expect(editorAgent.stopWhen).toBeDefined();
    expect(typeof editorAgent.stopWhen).toBe("function");
  });

  it("draft_writer has recall_past_articles tool", () => {
    expect(draftWriter.tools).toHaveLength(1);
    const def = getToolDef(draftWriter.tools[0]);
    expect(def.name).toBe("recall_past_articles");
  });

  it("semantic memory has indexed articles", () => {
    const results = semanticMem.search("quantum", 3);
    expect(results.length).toBeGreaterThan(0);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 4: Review & Safety
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 4: Review & Safety", () => {
  it("review agent has 4 guardrails", () => {
    expect(reviewAgent.guardrails).toHaveLength(4);
  });

  it("guardrail types include regex, llm, custom, external", () => {
    const types = reviewAgent.guardrails.map((g) => (g as Record<string, unknown>).guardrailType);
    expect(types).toContain("regex");
    expect(types).toContain("llm");
    expect(types).toContain("custom");
    expect(types).toContain("external");
  });

  it("PII guardrail is regex with on_fail=retry", () => {
    const def = piiGuardrail.toGuardrailDef();
    expect(def.guardrailType).toBe("regex");
    expect(def.onFail).toBe("retry");
    expect(def.patterns!.length).toBe(2);
  });

  it("bias guardrail is LLM with on_fail=fix", () => {
    const def = biasGuardrail.toGuardrailDef();
    expect(def.guardrailType).toBe("llm");
    expect(def.onFail).toBe("fix");
  });

  it("fact validator is custom with on_fail=human", () => {
    expect(factValidator.guardrailType).toBe("custom");
    expect(factValidator.onFail).toBe("human");
  });

  it("compliance guardrail is external with on_fail=raise", () => {
    expect(complianceGuardrail.guardrailType).toBe("external");
    expect(complianceGuardrail.onFail).toBe("raise");
  });

  it("safe_search tool has SQL injection guardrail", () => {
    const def = getToolDef(safeSearch);
    expect(def.guardrails).toBeDefined();
    expect(def.guardrails!.length).toBe(1);
  });

  it("SQL injection guard catches dangerous input", () => {
    const guard = sqlInjectionGuard;
    const result = guard.func!("SELECT * FROM users; DROP TABLE users; --") as { passed: boolean };
    expect(result.passed).toBe(false);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 5: Editorial Approval
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 5: Editorial Approval", () => {
  it("editorial agent uses handoff strategy", () => {
    expect(editorialAgent.strategy).toBe("handoff");
  });

  it("publish_article tool has approvalRequired=true", () => {
    const def = getToolDef(publishArticle);
    expect(def.approvalRequired).toBe(true);
  });

  it("human_tool (ask_editor) has correct type", () => {
    expect(editorialQuestion.toolType).toBe("human");
  });

  it("editorial reviewer is a UserProxyAgent", () => {
    expect(editorialReviewer).toBeInstanceOf(UserProxyAgent);
    expect(editorialReviewer.mode).toBe("TERMINATE");
  });

  it("editorial agent has both tools and sub-agents", () => {
    expect(editorialAgent.tools).toHaveLength(2);
    expect(editorialAgent.agents).toHaveLength(1);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 6: Translation & Discussion
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 6: Translation & Discussion", () => {
  it("tone_debate uses round_robin strategy with max_turns=6", () => {
    expect(toneDebate.strategy).toBe("round_robin");
    expect(toneDebate.maxTurns).toBe(6);
  });

  it("translation_swarm uses swarm strategy", () => {
    expect(translationSwarm.strategy).toBe("swarm");
  });

  it("translation_swarm has 3 OnTextMention handoffs", () => {
    expect(translationSwarm.handoffs).toHaveLength(3);
    for (const handoff of translationSwarm.handoffs) {
      expect(handoff).toBeInstanceOf(OnTextMention);
    }
  });

  it("title_brainstorm uses random strategy", () => {
    expect(titleBrainstorm.strategy).toBe("random");
  });

  it("manual_translation uses manual strategy", () => {
    expect(manualTranslation.strategy).toBe("manual");
  });

  it("allowed_transitions has 3 entries with 2 targets each", () => {
    const transitions = translationSwarm.allowedTransitions!;
    expect(Object.keys(transitions)).toHaveLength(3);
    for (const targets of Object.values(transitions)) {
      expect(targets).toHaveLength(2);
    }
  });

  it("all 3 translators have introductions", () => {
    expect(spanishTranslator.introduction).toBeTruthy();
    expect(frenchTranslator.introduction).toBeTruthy();
    expect(germanTranslator.introduction).toBeTruthy();
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 7: Publishing Pipeline
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 7: Publishing Pipeline", () => {
  it("publishing pipeline uses handoff strategy", () => {
    expect(publishingPipeline.strategy).toBe("handoff");
  });

  it("publishing pipeline has a gate condition", () => {
    expect(publishingPipeline.gate).toBeDefined();
    const gateObj = publishingPipeline.gate as TextGate;
    expect(gateObj.text).toBe("APPROVED");
  });

  it("publishing pipeline has composable termination", () => {
    expect(publishingPipeline.termination).toBeDefined();
    const json = publishingPipeline.termination!.toJSON() as Record<string, unknown>;
    expect(json.type).toBe("or");
    const conditions = json.conditions as Array<Record<string, unknown>>;
    expect(conditions).toHaveLength(2);
    // First: TextMention
    expect(conditions[0].type).toBe("text_mention");
    expect(conditions[0].text).toBe("PUBLISHED");
    // Second: AND(MaxMessage, TokenUsage)
    expect(conditions[1].type).toBe("and");
    const andConditions = conditions[1].conditions as Array<Record<string, unknown>>;
    expect(andConditions).toHaveLength(2);
    expect(andConditions[0].type).toBe("max_message");
    expect(andConditions[1].type).toBe("token_usage");
  });

  it("external publisher has external=true", () => {
    expect(externalPublisher.external).toBe(true);
  });

  it("publishing pipeline has OnToolResult and OnCondition handoffs", () => {
    expect(publishingPipeline.handoffs).toHaveLength(2);
    expect(publishingPipeline.handoffs[0]).toBeInstanceOf(OnToolResult);
    expect(publishingPipeline.handoffs[1]).toBeInstanceOf(OnCondition);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Stage 8: Analytics & Reporting
// ═══════════════════════════════════════════════════════════════════════

describe("Stage 8: Analytics & Reporting", () => {
  it("analytics agent has correct tool count", () => {
    // 4 code executors + 4 media + 2 RAG + 1 agent_tool + 1 CLI tool (auto) = 12
    expect(analyticsAgent.tools).toHaveLength(12);
  });

  it("analytics agent has thinking_budget_tokens=2048", () => {
    expect(analyticsAgent.thinkingBudgetTokens).toBe(2048);
  });

  it("analytics agent has planner=true", () => {
    expect(analyticsAgent.planner).toBe(true);
  });

  it('analytics agent has required_tools=["index_article"]', () => {
    expect(analyticsAgent.requiredTools).toEqual(["index_article"]);
  });

  it('analytics agent has include_contents="default"', () => {
    expect(analyticsAgent.includeContents).toBe("default");
  });

  it("analytics agent has code_execution_config", () => {
    expect(analyticsAgent.codeExecutionConfig).toBeDefined();
    expect(analyticsAgent.codeExecutionConfig!.enabled).toBe(true);
    expect(analyticsAgent.codeExecutionConfig!.allowedLanguages).toContain("python");
  });

  it("analytics agent has cli_config", () => {
    expect(analyticsAgent.cliConfig).toBeDefined();
    expect(analyticsAgent.cliConfig!.enabled).toBe(true);
    expect(analyticsAgent.cliConfig!.allowedCommands).toContain("git");
    expect(analyticsAgent.cliConfig!.allowedCommands).toContain("gh");
  });

  it("analytics agent has metadata", () => {
    expect(analyticsAgent.metadata).toEqual({ stage: "analytics", version: "1.0" });
  });

  it("analytics agent has structured output (JSON Schema)", () => {
    expect(analyticsAgent.outputType).toBeDefined();
    expect(analyticsAgent.outputType).toHaveProperty("type", "object");
    expect(analyticsAgent.outputType).toHaveProperty("properties");
  });

  it("GPTAssistantAgent exists with correct properties", () => {
    expect(gptAssistant).toBeInstanceOf(GPTAssistantAgent);
    expect(gptAssistant.assistantId).toBe("asst_placeholder_id");
    expect(gptAssistant.external).toBe(true);
  });

  it("agent_tool wraps quick_researcher as a tool", () => {
    expect(researchSubtool.toolType).toBe("agent_tool");
    expect(researchSubtool.name).toBe("quick_research");
  });

  it("media tools have correct types", () => {
    const mediaToolDefs = analyticsAgent.tools.filter((t) => {
      const def = getToolDef(t);
      return ["generate_image", "generate_audio", "generate_video", "generate_pdf"].includes(
        def.toolType,
      );
    });
    expect(mediaToolDefs).toHaveLength(4);
  });

  it("RAG tools have correct types", () => {
    const ragToolDefs = analyticsAgent.tools.filter((t) => {
      const def = getToolDef(t);
      return ["rag_search", "rag_index"].includes(def.toolType);
    });
    expect(ragToolDefs).toHaveLength(2);
  });

  it("code executor tools have correct count", () => {
    const codeToolDefs = analyticsAgent.tools.filter((t) => {
      const def = getToolDef(t);
      return (
        def.toolType === "worker" &&
        ["execute_code", "run_sandboxed", "run_notebook", "run_cloud"].includes(def.name)
      );
    });
    expect(codeToolDefs).toHaveLength(4);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Strategy verification
// ═══════════════════════════════════════════════════════════════════════

describe("Strategy Coverage", () => {
  it("all 8 strategies are exercised", () => {
    const strategies = new Set<string>();

    strategies.add(fullPipeline.strategy!); // sequential
    strategies.add(intakeRouter.strategy!); // router
    strategies.add(researchTeam.strategy!); // parallel
    strategies.add(editorialAgent.strategy!); // handoff
    strategies.add(toneDebate.strategy!); // round_robin
    strategies.add(titleBrainstorm.strategy!); // random
    strategies.add(translationSwarm.strategy!); // swarm
    strategies.add(manualTranslation.strategy!); // manual

    expect(strategies.size).toBe(8);
    expect(strategies).toContain("sequential");
    expect(strategies).toContain("router");
    expect(strategies).toContain("parallel");
    expect(strategies).toContain("handoff");
    expect(strategies).toContain("round_robin");
    expect(strategies).toContain("random");
    expect(strategies).toContain("swarm");
    expect(strategies).toContain("manual");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Serialization sanity check
// ═══════════════════════════════════════════════════════════════════════

describe("Serialization", () => {
  it("full pipeline serializes without error", () => {
    const serializer = new AgentConfigSerializer();
    const payload = serializer.serialize(fullPipeline, "Test prompt");
    expect(payload).toBeDefined();
    expect(payload.agentConfig).toBeDefined();
    expect((payload.agentConfig as Record<string, unknown>).name).toBe(
      "content_publishing_platform",
    );
    expect(payload.prompt).toBe("Test prompt");
  });
});
