# Google ADK Samples — Implementation Status

Tracking coverage of [google/adk-samples/python/agents](https://github.com/google/adk-samples/tree/main/python/agents) (45 samples) in our ADK compatibility layer.

## Our Examples (35)

| # | Example | ADK Feature | Status |
|---|---------|-------------|--------|
| 01 | [01_basic_agent.py](01_basic_agent.py) | Basic Agent (no tools) | ✅ Passing |
| 02 | [02_function_tools.py](02_function_tools.py) | FunctionTool | ✅ Passing |
| 03 | [03_structured_output.py](03_structured_output.py) | `output_schema` (Pydantic) | ✅ Passing |
| 04 | [04_sub_agents.py](04_sub_agents.py) | `sub_agents` handoff delegation | ✅ Passing |
| 05 | [05_generation_config.py](05_generation_config.py) | `generate_content_config` | ✅ Passing |
| 06 | [06_streaming.py](06_streaming.py) | `runtime.stream()` SSE events | ✅ Passing |
| 07 | [07_output_key_state.py](07_output_key_state.py) | `output_key` state management | ✅ Passing |
| 08 | [08_instruction_templating.py](08_instruction_templating.py) | `{variable}` in instruction | ✅ Passing |
| 09 | [09_multi_tool_agent.py](09_multi_tool_agent.py) | Multiple tools on single agent | ✅ Passing |
| 10 | [10_hierarchical_agents.py](10_hierarchical_agents.py) | Nested sub_agents (3 levels) | ✅ Passing |
| 11 | [11_sequential_agent.py](11_sequential_agent.py) | `SequentialAgent` pipeline | ✅ Passing |
| 12 | [12_parallel_agent.py](12_parallel_agent.py) | `ParallelAgent` concurrent execution | ✅ Passing |
| 13 | [13_loop_agent.py](13_loop_agent.py) | `LoopAgent` with `max_iterations` | ✅ Passing |
| 14 | [14_callbacks.py](14_callbacks.py) | Multi-tool chaining with validation | ✅ Passing |
| 15 | [15_global_instruction.py](15_global_instruction.py) | `global_instruction` field | ✅ Passing |
| 16 | [16_customer_service.py](16_customer_service.py) | Real-world customer service pattern | ✅ Passing |
| 17 | [17_financial_advisor.py](17_financial_advisor.py) | Multi-agent specialized sub-agents | ✅ Passing |
| 18 | [18_order_processing.py](18_order_processing.py) | End-to-end order management | ✅ Passing |
| 19 | [19_supply_chain.py](19_supply_chain.py) | Supply chain multi-agent coordination | ✅ Passing |
| 20 | [20_blog_writer.py](20_blog_writer.py) | Content pipeline with `output_key` | ✅ Passing |
| 21 | [21_agent_tool.py](21_agent_tool.py) | `AgentTool` (agent-as-tool) | ✅ Passing |
| 22 | [22_transfer_control.py](22_transfer_control.py) | `disallow_transfer_to_parent/peers` | ✅ Passing |
| 23 | [23_callbacks.py](23_callbacks.py) | `before_model_callback`, `after_model_callback` | ✅ Passing |
| 24 | [24_planner.py](24_planner.py) | `BuiltInPlanner` | ✅ Passing |
| 25 | [25_camel_security.py](25_camel_security.py) | CaMeL security policy (SequentialAgent) | ✅ Passing |
| 26 | [26_safety_guardrails.py](26_safety_guardrails.py) | Safety guardrails with PII detection | ✅ Passing |
| 27 | [27_security_agent.py](27_security_agent.py) | Red-team security testing pipeline | ✅ Passing |
| 28 | [28_movie_pipeline.py](28_movie_pipeline.py) | Sequential content production pipeline | ✅ Passing |
| 29 | [29_include_contents.py](29_include_contents.py) | `include_contents="none"` | ✅ Passing |
| 30 | [30_thinking_config.py](30_thinking_config.py) | `ThinkingConfig` extended reasoning | ✅ Passing |
| 31 | [31_shared_state.py](31_shared_state.py) | `ToolContext.state` shared state | ✅ Passing |
| 32 | [32_nested_strategies.py](32_nested_strategies.py) | `ParallelAgent` inside `SequentialAgent` | ✅ Passing |
| 33 | [33_software_bug_assistant.py](33_software_bug_assistant.py) | `agent_tool` + `mcp_tool` + ticket CRUD | ✅ Passing |
| 34 | [34_ml_engineering.py](34_ml_engineering.py) | ML pipeline: Sequential + Parallel + Loop | ✅ Passing |
| 35 | [35_rag_agent.py](35_rag_agent.py) | RAG: search_tool + index_tool | ✅ Passing |

---

## Google ADK Samples Coverage (45 total)

### ✅ Covered — Pattern replicated in our examples (31 samples)

| ADK Sample | Our Example(s) |
|-----------|----------------|
| [story_teller](https://github.com/google/adk-samples/tree/main/python/agents/story_teller) | [11](11_sequential_agent.py), [12](12_parallel_agent.py), [13](13_loop_agent.py), [32](32_nested_strategies.py) |
| [customer-service](https://github.com/google/adk-samples/tree/main/python/agents/customer-service) | [14](14_callbacks.py), [16](16_customer_service.py) |
| [financial-advisor](https://github.com/google/adk-samples/tree/main/python/agents/financial-advisor) | [17](17_financial_advisor.py) |
| [order-processing](https://github.com/google/adk-samples/tree/main/python/agents/order-processing) | [18](18_order_processing.py) |
| [supply-chain](https://github.com/google/adk-samples/tree/main/python/agents/supply-chain) | [19](19_supply_chain.py) |
| [blog-writer](https://github.com/google/adk-samples/tree/main/python/agents/blog-writer) | [20](20_blog_writer.py) |
| [llm-auditor](https://github.com/google/adk-samples/tree/main/python/agents/llm-auditor) | [11](11_sequential_agent.py) |
| [parallel_task_decomposition_execution](https://github.com/google/adk-samples/tree/main/python/agents/parallel_task_decomposition_execution) | [12](12_parallel_agent.py) |
| [image-scoring](https://github.com/google/adk-samples/tree/main/python/agents/image-scoring) | [13](13_loop_agent.py) |
| [podcast_transcript_agent](https://github.com/google/adk-samples/tree/main/python/agents/podcast_transcript_agent) | [11](11_sequential_agent.py) |
| [personalized-shopping](https://github.com/google/adk-samples/tree/main/python/agents/personalized-shopping) | [09](09_multi_tool_agent.py), [18](18_order_processing.py) |
| [camel](https://github.com/google/adk-samples/tree/main/python/agents/camel) | [25](25_camel_security.py) |
| [safety-plugins](https://github.com/google/adk-samples/tree/main/python/agents/safety-plugins) | [26](26_safety_guardrails.py) |
| [ai-security-agent](https://github.com/google/adk-samples/tree/main/python/agents/ai-security-agent) | [27](27_security_agent.py) |
| [short-movie-agents](https://github.com/google/adk-samples/tree/main/python/agents/short-movie-agents) | [28](28_movie_pipeline.py) |
| [academic-research](https://github.com/google/adk-samples/tree/main/python/agents/academic-research) | [21](21_agent_tool.py) |
| [brand-aligner](https://github.com/google/adk-samples/tree/main/python/agents/brand-aligner) | [21](21_agent_tool.py), [23](23_callbacks.py) |
| [data-science](https://github.com/google/adk-samples/tree/main/python/agents/data-science) | [21](21_agent_tool.py), [23](23_callbacks.py) |
| [google-trends-agent](https://github.com/google/adk-samples/tree/main/python/agents/google-trends-agent) | [21](21_agent_tool.py) |
| [hierarchical-workflow-automation](https://github.com/google/adk-samples/tree/main/python/agents/hierarchical-workflow-automation) | [21](21_agent_tool.py) |
| [marketing-agency](https://github.com/google/adk-samples/tree/main/python/agents/marketing-agency) | [21](21_agent_tool.py) |
| [retail-ai-location-strategy](https://github.com/google/adk-samples/tree/main/python/agents/retail-ai-location-strategy) | [21](21_agent_tool.py), [23](23_callbacks.py) |
| [travel-concierge](https://github.com/google/adk-samples/tree/main/python/agents/travel-concierge) | [21](21_agent_tool.py), [22](22_transfer_control.py) |
| [youtube-analyst](https://github.com/google/adk-samples/tree/main/python/agents/youtube-analyst) | [21](21_agent_tool.py) |
| [deep-search](https://github.com/google/adk-samples/tree/main/python/agents/deep-search) | [24](24_planner.py), [23](23_callbacks.py) |
| [fomc-research](https://github.com/google/adk-samples/tree/main/python/agents/fomc-research) | [23](23_callbacks.py) |
| [swe-benchmark-agent](https://github.com/google/adk-samples/tree/main/python/agents/swe-benchmark-agent) | [24](24_planner.py) |
| [tau2-benchmark-agent](https://github.com/google/adk-samples/tree/main/python/agents/tau2-benchmark-agent) | [24](24_planner.py) |
| [software-bug-assistant](https://github.com/google/adk-samples/tree/main/python/agents/software-bug-assistant) | [33](33_software_bug_assistant.py) |
| [machine-learning-engineering](https://github.com/google/adk-samples/tree/main/python/agents/machine-learning-engineering) | [34](34_ml_engineering.py) |
| [RAG](https://github.com/google/adk-samples/tree/main/python/agents/RAG) | [35](35_rag_agent.py) |

### ⛔ Not Applicable — Requires Google-specific external services (14 samples)

| ADK Sample | External Dependency |
|-----------|-------------------|
| [antom-payment](https://github.com/google/adk-samples/tree/main/python/agents/antom-payment) | Antom/Alipay payment APIs |
| [auto-insurance-agent](https://github.com/google/adk-samples/tree/main/python/agents/auto-insurance-agent) | Apigee API Hub + Vertex AI Agent Engine |
| [bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo) | Gemini Live API (streaming mode) |
| [bigquery-data-agent](https://github.com/google/adk-samples/tree/main/python/agents/bigquery-data-agent) | BigQuery + GCP |
| [brand-search-optimization](https://github.com/google/adk-samples/tree/main/python/agents/brand-search-optimization) | BigQuery + Google Shopping + Selenium |
| [currency-agent](https://github.com/google/adk-samples/tree/main/python/agents/currency-agent) | MCPToolset (external server) + A2A protocol |
| [data-engineering](https://github.com/google/adk-samples/tree/main/python/agents/data-engineering) | BigQuery + Dataform + GCP |
| [gemini-fullstack](https://github.com/google/adk-samples/tree/main/python/agents/gemini-fullstack) | _(Deprecated — redirects to deep-search)_ |
| [incident-management](https://github.com/google/adk-samples/tree/main/python/agents/incident-management) | ServiceNow + Application Integration |
| [medical-pre-authorization](https://github.com/google/adk-samples/tree/main/python/agents/medical-pre-authorization) | Vertex AI Agent Builder + Cloud Run + GCS |
| [plumber-data-engineering-assistant](https://github.com/google/adk-samples/tree/main/python/agents/plumber-data-engineering-assistant) | Dataflow + Dataproc + GKE + GCP |
| [policy-as-code](https://github.com/google/adk-samples/tree/main/python/agents/policy-as-code) | Dataplex + BigQuery + Firestore + GCS |
| [product-catalog-ad-generation](https://github.com/google/adk-samples/tree/main/python/agents/product-catalog-ad-generation) | BigQuery + GCS + Veo-3.1 + Imagen + Lyria |
| [realtime-conversational-agent](https://github.com/google/adk-samples/tree/main/python/agents/realtime-conversational-agent) | Google AI Studio / Vertex AI (live audio/video) |

---

## Server-Side Feature Status

| Feature | Java Files Modified | Status |
|---------|-------------------|--------|
| **AgentTool** | GoogleADKNormalizer, ToolCompiler, JavaScriptBuilder, AgentService | ✅ Deployed + tested |
| **Transfer Control** | GoogleADKNormalizer, MultiAgentCompiler | ✅ Deployed + tested |
| **Callbacks** | CallbackConfig (new), AgentConfig, GoogleADKNormalizer, AgentCompiler | ✅ Deployed + tested |
| **BuiltInPlanner** | GoogleADKNormalizer, AgentCompiler (prompt enhancement) | ✅ Deployed + tested |
| **Sequential null coercion** | AgentCompiler, MultiAgentCompiler, JavaScriptBuilder | ✅ Deployed + tested |
| **include_contents** | AgentConfig, GoogleADKNormalizer, AgentCompiler | ✅ Deployed + tested |
| **ThinkingConfig** | ThinkingConfig (new), AgentConfig, GoogleADKNormalizer, AgentCompiler | ✅ Deployed + tested |
| **ToolContext.state** | — | ✅ Deployed + tested |
| **RAG Tools** | ToolCompiler, JavaScriptBuilder, ToolConfig | ✅ Deployed + tested |

---

## Coverage Summary

| Category | Count |
|----------|-------|
| ✅ Covered + passing | 31 |
| ⛔ Not applicable (Google-specific services) | 14 |
| **Total ADK samples** | **45** |
| **Feasible coverage** | **31/31 (100%)** |

---

## Native SDK Examples (paired with ADK)

| ADK | Native SDK | Feature |
|-----|-----------|---------|
| 21 | [45_agent_tool.py](../45_agent_tool.py) | AgentTool |
| 22 | [46_transfer_control.py](../46_transfer_control.py) | Transfer control |
| 23 | [47_callbacks.py](../47_callbacks.py) | Callbacks |
| 24 | [48_planner.py](../48_planner.py) | Planner |
| 29 | [49_include_contents.py](../49_include_contents.py) | include_contents |
| 30 | [50_thinking_config.py](../50_thinking_config.py) | ThinkingConfig |
| 31 | [51_shared_state.py](../51_shared_state.py) | Shared state |
| 32 | [52_nested_strategies.py](../52_nested_strategies.py) | Nested strategies |
| 33 | [54_software_bug_assistant.py](../54_software_bug_assistant.py) | Software bug assistant |
| 34 | [55_ml_engineering.py](../55_ml_engineering.py) | ML engineering pipeline |
| 35 | [56_rag_agent.py](../56_rag_agent.py) | RAG (search + index) |
