# Java Examples — Verification Report

End-to-end verification of every example in this module, run against a
live Agentspan server and inspected at the Conductor workflow level to
confirm LLM calls, tool calls, sub-agent orchestration, and guardrails
all execute **server-side**.

- **Last full run:** 2026-05-21 against a local server at `localhost:6767`
- **Model:** `openai/gpt-4o-mini` for every example (configurable via
  `AGENTSPAN_LLM_MODEL`)
- **Examples covered:** 88 (39 ADK + 28 LangChain + 11 LangGraph + 10 OpenAI)
- **Workflow-level pass rate:** 88 / 88 COMPLETED
- **Sub-task error rate:** 1 example with errored sub-tasks
  (`adk.Example36BuiltInTools`, see Known Issues)

> **Note on OpenAI Agents:** Unlike ADK / LangChain4j / LangGraph4j, there
> is **no native OpenAI Agents Java SDK** at the time of this writing —
> only the raw `com.openai:openai-java` HTTP client, which has zero agent
> abstractions. The OpenAI examples therefore use Agentspan's own
> `OpenAIAgent.builder()` (in `ai.agentspan.frameworks`) — that builder
> IS the Java equivalent of the Python `openai-agents` library, not a
> bridge over something native. The same bug-bounty fixes applied to
> `AdkBridge` and `LangChain4jAgent` (rich coercion via
> `ToolRegistry.coerceArgument`, `arg0` paramName warning, unwrapped
> `InvocationTargetException`) have been applied to `OpenAIAgent`.

## What "server-side execution" means here

For each example we ran the user code unchanged, captured the
execution ID returned by `Agentspan.run(...)`, then queried
`GET /api/workflow/{executionId}?includeTasks=true` to count and
classify the tasks the server actually scheduled. The shapes that
should appear in those task lists, per pattern:

| Pattern | Expected server tasks |
|---|---|
| Plain LLM call | 1 × `LLM_CHAT_COMPLETE` |
| Function tool | `LLM_CHAT_COMPLETE` → `SWITCH` → `FORK` → `<tool_name>` SIMPLE → `JOIN` → next iteration, wrapped in `DO_WHILE` |
| Sub-agents | One `SUB_WORKFLOW` per child agent; child workflow has its own LLM + tools |
| Composite agents (Sequential / Parallel / Loop) | `SUB_WORKFLOW` per step inside the outer orchestration |
| Output guardrail | `LLM` → `<agent>_output_guardrail` worker → `INLINE` normalize → `SWITCH` route → `INLINE` fix → `SET_VARIABLE` |
| Built-in HTTP tool (Google Search) | `HTTP` task per call — **see Known Issues** |
| Built-in code execution | `INLINE` code-exec task |

If any of those expected tasks are missing from the workflow, the
"feature" was silently dropped client-side. The table below shows
each verified row landed with the expected shape.

## How to reproduce

```bash
# 1. Start the Agentspan server (separate terminal)
cd server && ./gradlew bootJar
java -jar build/libs/agentspan-runtime.jar

# 2. Run a single example
cd sdk/java
AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini \
  ./gradlew :examples:run -PmainClass=ai.agentspan.examples.adk.Example02FunctionTools

# 3. Inspect the workflow
EXEC=<execution-id from the example's stdout>
curl -s "http://localhost:6767/api/workflow/$EXEC?includeTasks=true" | jq
```

## Roll-up

- **39 / 39** ADK examples completed
- **28 / 28** LangChain examples completed
- **11 / 11** LangGraph examples completed
- **10 / 10** OpenAI examples completed
- **Largest workflows** (>200 tasks each): `langchain.Example25AdvancedOrchestration` (240), `langchain.Example10WebSearchAgent` (228), `adk.Example17FinancialAdvisor` (204), `adk.Example19SupplyChain` (204) — all completed cleanly
- **Smallest workflows** (1 task): pure no-tool LLM calls, and `adk.Example23Callbacks` (callbacks-only — server does not yet compile callback hooks; see Known Issues)

## Known issues

### 1. `adk.Example36BuiltInTools` — `GoogleSearchTool` HTTP backend missing

`GoogleSearchTool.INSTANCE` (or `new GoogleSearchTool()`) emits the
correct wire shape `{_type: GoogleSearchTool}` from the SDK; the
server-side `GoogleADKNormalizer` translates it to an HTTP tool with
config `{builtin: google_search}`. **The downstream HTTP compiler has
no real handler for that builtin** — every call ships with `uri: ""`
and dies with `Target host is not specified`. The LLM then hallucinates
a "I can't access external sources" answer. The example workflow
shows `COMPLETED` with 12 `COMPLETED_WITH_ERRORS` HTTP sub-tasks.

**Fix vector:** server-side. Either route to Gemini's native grounding
when the LLM provider is Gemini, ship a real Google Search adapter
with API-key configuration, or reject `GoogleSearchTool` when no
backend is configured. Tracked separately.

### 2. ADK callbacks compile to a no-op for the simple-LLM agent shape

`adk.Example23Callbacks` registers `beforeModelCallback` and
`afterModelCallback`. The SDK forwards `_worker_ref` placeholders in
the wire payload (verifiable in the workflow metadata's `agentDef`
field), and `GoogleADKNormalizer` builds `CallbackConfig` objects from
them. **The downstream workflow compiler does not yet emit Conductor
hook tasks** for these on the simple-LLM path, so the registered
worker is never polled (workflow has 1 task: just the LLM call).

Python ADK has the same gap — see
`sdk/python/examples/adk/14_callbacks.py` comment. Fix is server-side,
not bridge-side. Tracked separately.

## Per-example table

| # | Example | Execution ID | Agent Name | Status | Tasks | Errors |
|---|---|---|---|---|---|---|
| 1 | adk.Example00HelloWorld | `8842a380-0fd7-4827-9d97-27c0d80d9511` | greeter | COMPLETED | 1 | 0 |
| 2 | adk.Example01BasicAgent | `a4611ebd-3415-4094-bb4b-836bf0c355fb` | greeter | COMPLETED | 1 | 0 |
| 3 | adk.Example02FunctionTools | `6f58c04e-7973-4aa1-8a56-9cff9c63c14a` | travel_assistant | COMPLETED | 24 | 0 |
| 4 | adk.Example03StructuredOutput | `b1288601-a4e6-474a-97b4-6b71b1480922` | recipe_generator | COMPLETED | 1 | 0 |
| 5 | adk.Example04SubAgents | `d87f2e78-b61d-4884-a9c4-ee5b203b9e83` | travel_coordinator | COMPLETED | 33 | 0 |
| 6 | adk.Example05GenerationConfig | `780320c0-7fb1-4093-9571-821da359e108` | fact_checker | COMPLETED | 1 | 0 |
| 7 | adk.Example06Streaming | `0077193d-e0eb-453a-aeee-d4e76021a7b2` | docs_assistant | COMPLETED | 24 | 0 |
| 8 | adk.Example07OutputKeyState | `e28d1079-a204-4190-a67d-692915b56e95` | report_coordinator | COMPLETED | 17 | 0 |
| 9 | adk.Example08InstructionTemplating | `031decfe-b4b6-48f5-9f3b-911ef616031f` | adaptive_tutor | COMPLETED | 15 | 0 |
| 10 | adk.Example09MultiToolAgent | `73ec468f-e6f4-4d9f-bc79-19b694b2c704` | shopping_assistant | COMPLETED | 35 | 0 |
| 11 | adk.Example10HierarchicalAgents | `3602ff91-be17-4356-a4cc-12c82dfa8233` | platform_coordinator | COMPLETED | 25 | 0 |
| 12 | adk.Example11SequentialAgent | `63361c7a-489d-4337-90a8-cdc524848b51` | content_pipeline | COMPLETED | 13 | 0 |
| 13 | adk.Example12ParallelAgent | `86dd1ab4-7d80-451e-830b-33a28e980dce` | parallel_analysis | COMPLETED | 10 | 0 |
| 14 | adk.Example13LoopAgent | `5018ddb7-2cb3-4d42-bdca-6f43142a8033` | refinement_loop | COMPLETED | 9 | 0 |
| 15 | adk.Example14Callbacks | `7f6787b8-2848-404f-b37a-245013114e49` | customer_service_agent | COMPLETED | 25 | 0 |
| 16 | adk.Example15GlobalInstruction | `d2011790-0162-4940-993e-099dd8f50d10` | store_assistant | COMPLETED | 16 | 0 |
| 17 | adk.Example16CustomerService | `4ac3810e-c280-4019-8600-d1a039f60ff1` | customer_service_rep | COMPLETED | 16 | 0 |
| 18 | adk.Example17FinancialAdvisor | `08eadf97-4333-4475-92fe-cd1b1ed77cdb` | financial_advisor | COMPLETED | **204** | 0 |
| 19 | adk.Example18OrderProcessing | `fbfab64f-cfe2-4b96-974a-d524197c8376` | order_processor | COMPLETED | 15 | 0 |
| 20 | adk.Example19SupplyChain | `b6a6f6d2-c836-49f6-b634-24a55fadc68f` | supply_chain_coordinator | COMPLETED | **204** | 0 |
| 21 | adk.Example20BlogWriter | `997e831d-28ca-43b2-8c77-7428ff142e10` | content_coordinator | COMPLETED | 33 | 0 |
| 22 | adk.Example21AgentTool | `e6cc8cf1-09e7-460e-8c55-ff292a2e8c0d` | manager | COMPLETED | 25 | 0 |
| 23 | adk.Example22TransferControl | `66d972b9-0c67-4483-bbfe-cf896ba345a6` | research_coordinator | COMPLETED | 33 | 0 |
| 24 | adk.Example23Callbacks | `b86c58cd-0669-4f14-8a9c-cef2acc89028` | monitored_assistant | COMPLETED | **1** ⚠️ | 0 |
| 25 | adk.Example24Planner | `fc16c606-ad27-408c-9d0c-03fd157c30fb` | research_writer | COMPLETED | 71 | 0 |
| 26 | adk.Example25CamelSecurity | `e6de5e54-aed5-4acd-8a76-2c2cff69dcd0` | secure_data_pipeline | COMPLETED | 33 | 0 |
| 27 | adk.Example26SafetyGuardrails | `8587797c-dd0e-4ce0-883f-ef632986be0e` | safe_assistant | COMPLETED | 25 | 0 |
| 28 | adk.Example27SecurityAgent | `bed4d40e-f414-4ee5-a2ca-621c40deecf5` | security_test_pipeline | COMPLETED | 33 | 0 |
| 29 | adk.Example28MoviePipeline | `e08adcd9-2f1d-4fdb-8617-40d8ecdbdae8` | short_movie_pipeline | COMPLETED | 49 | 0 |
| 30 | adk.Example29IncludeContents | `a3ee8f3c-263f-427e-b91f-275920726db5` | coordinator | COMPLETED | 17 | 0 |
| 31 | adk.Example30ThinkingConfig | `148d54f4-f6ab-4af8-83ba-e90245efc5cf` | deep_thinker | COMPLETED | 15 | 0 |
| 32 | adk.Example31SharedState | `c5655d62-073d-467a-813e-6aa83e6d33e2` | shopping_assistant | COMPLETED | 26 | 0 |
| 33 | adk.Example32NestedStrategies | `1da8bead-599f-4b7f-9452-ac07efd708a2` | analysis_pipeline | COMPLETED | 25 | 0 |
| 34 | adk.Example33SoftwareBugAssistant | `4f28868d-26a6-45d5-93c0-8f4e169d242c` | software_assistant | COMPLETED | 17 | 0 |
| 35 | adk.Example34MlEngineering | `2d56442d-afc9-4536-b76d-7cba8461df30` | ml_pipeline | COMPLETED | 57 | 0 |
| 36 | adk.Example35RagAgent | `b6fae52b-dec8-4996-bc80-9b526ec0892a` | rag_assistant | COMPLETED | 22 | 0 |
| 37 | adk.Example36BuiltInTools | `8208d703-5ad2-4508-ae12-1f7faffec862` | research_assistant | COMPLETED | 60 | **12** ⚠️ |
| 38 | adk.Example37DeployAndServe | `554e7495-8042-437f-9132-36d2c081f809` | deploy_demo_agent | COMPLETED | 15 | 0 |
| 39 | adk.Example38AgentspanGuardrails | `8d6b96ea-00bb-4bf1-8b99-d3d05aa3b432` | contact_directory | COMPLETED | 8 | 0 |
| 40 | langchain.Example01HelloWorld | `e3bc9290-4c66-4418-ab53-0b9d930e03a4` | langchain_agent | COMPLETED | 1 | 0 |
| 41 | langchain.Example02ReactWithTools | `ffad44aa-b457-4194-9930-fe5343df4d00` | langchain_agent | COMPLETED | 17 | 0 |
| 42 | langchain.Example03CustomTools | `3e65dca9-8b8a-4b24-9298-c2869da45673` | langchain_agent | COMPLETED | 17 | 0 |
| 43 | langchain.Example04StructuredOutput | `37ff52e8-349e-47b6-996f-a6d718f44931` | langchain_agent | COMPLETED | 16 | 0 |
| 44 | langchain.Example05PromptTemplates | `ba7547f8-5f4e-4d18-b955-2e830748392e` | langchain_agent | COMPLETED | 16 | 0 |
| 45 | langchain.Example06ChatHistory | `0adb5052-106e-48b2-abfd-d2a987412ff3` | langchain_agent | COMPLETED | 15 | 0 |
| 46 | langchain.Example07MemoryAgent | `25016593-d25f-4044-9968-fdd5723311fb` | langchain_agent | COMPLETED | 15 | 0 |
| 47 | langchain.Example08MultiToolAgent | `3379a4ad-7637-4e19-86f5-0a449f92923d` | langchain_agent | COMPLETED | 17 | 0 |
| 48 | langchain.Example09MathCalculator | `6003756a-3433-4136-9d06-64c4583f04c8` | langchain_agent | COMPLETED | 17 | 0 |
| 49 | langchain.Example10WebSearchAgent | `7714559b-430f-421b-83ad-ffe3089bd5ed` | langchain_agent | COMPLETED | **228** | 0 |
| 50 | langchain.Example11CodeReviewAgent | `ff82b5b5-e978-475d-93f6-14f3d8a6b578` | langchain_agent | COMPLETED | 17 | 0 |
| 51 | langchain.Example12DocumentSummarizer | `1f005b3b-ff4c-442e-a5dd-a9937cc2a0f3` | langchain_agent | COMPLETED | 17 | 0 |
| 52 | langchain.Example13CustomerServiceAgent | `6eb1e0f2-e8e1-40b2-b22f-7467a005fdc1` | langchain_agent | COMPLETED | 15 | 0 |
| 53 | langchain.Example14ResearchAssistant | `6a1781e9-11b7-4ce2-9f08-ecb1323356a8` | langchain_agent | COMPLETED | 17 | 0 |
| 54 | langchain.Example15DataAnalyst | `de83ba83-cd26-463f-8dcd-644909cd02fb` | langchain_agent | COMPLETED | 17 | 0 |
| 55 | langchain.Example16ContentWriter | `8dba8001-1fb3-4a63-b828-47f3474fe406` | langchain_agent | COMPLETED | 17 | 0 |
| 56 | langchain.Example17SqlAgent | `ec0a450d-035e-4dcb-b5d2-954c6b093ae4` | langchain_agent | COMPLETED | 25 | 0 |
| 57 | langchain.Example18EmailDrafter | `5e49db29-0381-4b6a-9e30-1debc7ca28d1` | langchain_agent | COMPLETED | 25 | 0 |
| 58 | langchain.Example19FactChecker | `3d01c40f-d397-45da-91ec-b5c849a8f11f` | langchain_agent | COMPLETED | 17 | 0 |
| 59 | langchain.Example20TranslationAgent | `b0676b02-be95-4480-bbbd-32d150ce795d` | langchain_agent | COMPLETED | 16 | 0 |
| 60 | langchain.Example21SentimentAnalysis | `95df4861-043c-4fc6-9592-357ce4484a96` | langchain_agent | COMPLETED | 16 | 0 |
| 61 | langchain.Example22ClassificationAgent | `2e6b312c-5b09-43b9-a912-b41489a0568e` | langchain_agent | COMPLETED | 16 | 0 |
| 62 | langchain.Example23RecommendationAgent | `f976873e-a9c5-4934-b4cb-ea1a140413a5` | langchain_agent | COMPLETED | 25 | 0 |
| 63 | langchain.Example24OutputParsers | `4a2785b1-30d1-4642-a948-dfece8c99185` | langchain_agent | COMPLETED | 25 | 0 |
| 64 | langchain.Example25AdvancedOrchestration | `6f783be7-2540-477a-ab1b-1c69c48d61c7` | langchain_agent | COMPLETED | **240** | 0 |
| 65 | langchain.Example26AgentspanGuardrails | `43a161fd-42f9-4ce1-9124-a614a720cc09` | contact_directory_lc | COMPLETED | 8 | 0 |
| 66 | langchain.ExampleCredentials | `e8faaffa-69f1-409c-9c25-796d444cc1c5` | lc4j_weather_agent | COMPLETED | 16 | 0 |
| 67 | langchain.ExamplePipeline | `dca4108c-d748-4127-87e6-93829fe92e5d` | data_gatherer_report_writer | COMPLETED | 9 | 0 |
| 68 | langgraph.Example01HelloWorld | `bb744b58-00dc-4f7c-a469-483e9f4dd345` | langgraph_agent | COMPLETED | 1 | 0 |
| 69 | langgraph.Example02ReactWithTools | `1868285d-c078-4cc6-ab95-ae7fd56b4e54` | langgraph_agent | COMPLETED | 17 | 0 |
| 70 | langgraph.Example03Memory | `32aa500c-b8f6-48c8-ad65-6ce5fe9269b7` | langgraph_agent | COMPLETED | 1 | 0 |
| 71 | langgraph.Example04SimpleStateGraph | `c82d9e20-d9c9-4689-ac2c-585ec39c13b7` | langgraph_agent | COMPLETED | 33 | 0 |
| 72 | langgraph.Example05ToolNode | `967799ca-661f-450b-922d-3df4bb0f302e` | langgraph_agent | COMPLETED | 18 | 0 |
| 73 | langgraph.Example06ConditionalRouting | `6259a36f-37f5-41f6-b8a4-3d8d3531bd30` | langgraph_agent | COMPLETED | 24 | 0 |
| 74 | langgraph.Example07SystemPrompt | `7662f6df-3ea2-4192-8d5a-e1a5b1e0e466` | langgraph_agent | COMPLETED | 1 | 0 |
| 75 | langgraph.Example08StructuredOutput | `91fa995a-70bb-4f0c-84f8-197c72bca34a` | langgraph_agent | COMPLETED | 15 | 0 |
| 76 | langgraph.Example09MathAgent | `1e5eec8a-3937-4682-b45b-ea28a803eec8` | langgraph_agent | COMPLETED | 27 | 0 |
| 77 | langgraph.Example10ResearchAgent | `ece7bcaa-81a8-45a9-a309-125ef5d899bc` | langgraph_agent | COMPLETED | 25 | 0 |
| 78 | langgraph.Example11CustomerSupport | `71b40b3a-533e-4ea8-8eec-a4b803e97100` | langgraph_agent | COMPLETED | 25 | 0 |
| 79 | openai.Example01BasicAgent | `6329c9fe-0bd4-4dfd-92d8-ab1b3a5c0bf3` | greeter | COMPLETED | 1 | 0 |
| 80 | openai.Example02FunctionTools | `ddd14d63-b016-4f90-b148-7e5ee39dc7f0` | multi_tool_agent | COMPLETED | 25 | 0 |
| 81 | openai.Example03StructuredOutput | `02515522-3d75-4f56-9baa-fc03ffe44f45` | movie_recommender | COMPLETED | 1 | 0 |
| 82 | openai.Example04Handoffs | `2ecca482-ff80-42dd-9393-27871d19901c` | customer_service_triage | COMPLETED | 17 | 0 |
| 83 | openai.Example05Guardrails | `441c1666-7329-42fd-a5df-391684a500bf` | banking_assistant | COMPLETED | 15 | 0 |
| 84 | openai.Example06ModelSettings | `dba7da6a-69ee-40a7-8cf9-31abc19ec5ff` | creative_writer | COMPLETED | 1 | 0 |
| 85 | openai.Example07Streaming | `3eed1c84-13e8-46fe-a461-7d8ad23b580e` | support_agent | COMPLETED | 15 | 0 |
| 86 | openai.Example08AgentAsTool | `d8329145-2951-4f32-87b8-67b4f90eb0d6` | text_analysis_manager | COMPLETED | 33 | 0 |
| 87 | openai.Example09DynamicInstructions | `304cd678-4e5d-4ed9-ab8e-e2511aa7e324` | personal_assistant | COMPLETED | 16 | 0 |
| 88 | openai.Example10MultiModel | `2c596a5c-e90d-4143-8386-bbab5cae37dc` | triage | COMPLETED | 17 | 0 |

Execution IDs are stable for as long as the local server's database
isn't reset. To re-verify any row, paste its ID into:

```bash
curl -s "http://localhost:6767/api/workflow/<EXECUTION_ID>?includeTasks=true" | jq
```

To regenerate this table from scratch, run all examples and query each
workflow — the script that produced this batch is available on request
or can be reconstructed from the example list at the top of the
`Per-example table` section.
