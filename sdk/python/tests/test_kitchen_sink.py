# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Kitchen Sink test suite — structural + behavioral assertions.

Tests the kitchen sink structure using direct imports (no server required)
and the testing framework's assertion/validation tools.
"""

import os
import sys

import pytest

# Add examples to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from agentspan.agents import FinishReason, Status, Strategy
from agentspan.agents.testing import (
    CorrectnessEval,
    EvalCase,
    MockEvent,
    assert_guardrail_passed,
    assert_no_errors,
    assert_status,
    assert_tool_not_used,
    assert_tool_used,
    expect,
    mock_run,
    record,
    replay,
    validate_strategy,
)


class TestKitchenSinkStructure:
    """Structural tests — verify agent tree is correctly defined."""

    def test_full_pipeline_has_all_stages(self):
        from kitchen_sink import full_pipeline

        assert full_pipeline.name == "content_publishing_platform"
        assert len(full_pipeline.agents) == 8
        assert full_pipeline.strategy == Strategy.SEQUENTIAL

    def test_intake_uses_router_strategy(self):
        from kitchen_sink import intake_router

        assert intake_router.strategy == Strategy.ROUTER
        assert intake_router.router is not None
        assert intake_router.output_type is not None

    def test_research_uses_parallel_with_scatter_gather(self):
        from kitchen_sink import research_coordinator, research_team

        assert research_team.strategy == Strategy.PARALLEL
        assert research_coordinator.name == "research_coordinator"

    def test_writing_pipeline_is_sequential(self):
        from kitchen_sink import writing_pipeline

        assert writing_pipeline.strategy == Strategy.SEQUENTIAL

    def test_review_has_all_guardrail_types(self):
        from kitchen_sink import review_agent

        names = [g.name for g in review_agent.guardrails]
        assert "pii_blocker" in names  # regex
        assert "bias_detector" in names  # llm
        assert "fact_validator" in names  # custom
        assert "compliance_check" in names  # external

    def test_editorial_has_hitl_tools(self):
        from kitchen_sink import editorial_agent

        assert editorial_agent.strategy == Strategy.HANDOFF
        assert len(editorial_agent.tools) == 2  # publish_article + ask_editor

    def test_translation_swarm_has_handoffs(self):
        from kitchen_sink import translation_swarm

        assert translation_swarm.strategy == Strategy.SWARM
        assert len(translation_swarm.handoffs) == 3
        assert translation_swarm.allowed_transitions is not None

    def test_all_eight_strategies_exercised(self):
        from kitchen_sink import (
            editorial_agent,
            intake_router,
            manual_translation,
            publishing_pipeline,
            research_team,
            title_brainstorm,
            tone_debate,
            translation_swarm,
            writing_pipeline,
        )

        strategies = {
            intake_router.strategy,
            research_team.strategy,
            writing_pipeline.strategy,
            tone_debate.strategy,
            translation_swarm.strategy,
            title_brainstorm.strategy,
            manual_translation.strategy,
            publishing_pipeline.strategy,
            editorial_agent.strategy,
        }
        assert Strategy.ROUTER in strategies
        assert Strategy.PARALLEL in strategies
        assert Strategy.SEQUENTIAL in strategies
        assert Strategy.ROUND_ROBIN in strategies
        assert Strategy.SWARM in strategies
        assert Strategy.RANDOM in strategies
        assert Strategy.MANUAL in strategies
        assert Strategy.HANDOFF in strategies

    def test_publishing_has_gate_and_termination(self):
        from kitchen_sink import publishing_pipeline

        assert publishing_pipeline.termination is not None
        assert publishing_pipeline.gate is not None

    def test_analytics_has_all_advanced_features(self):
        from kitchen_sink import analytics_agent

        assert analytics_agent.code_execution_config is not None
        assert analytics_agent.cli_config is not None
        assert analytics_agent.thinking_budget_tokens == 2048
        assert analytics_agent.planner is True
        assert analytics_agent.include_contents == "default"
        assert analytics_agent.required_tools is not None
        assert "index_article" in analytics_agent.required_tools
        assert analytics_agent.metadata == {"stage": "analytics", "version": "1.0"}
        assert analytics_agent.output_type is not None

    def test_external_tool_is_marked(self):
        from agentspan.agents.tool import get_tool_def
        from kitchen_sink import external_research_aggregator

        td = get_tool_def(external_research_aggregator)
        assert td.tool_type == "worker"

    def test_external_agent_is_marked(self):
        from kitchen_sink import external_publisher

        assert external_publisher.external is True

    def test_gpt_assistant_agent_exists(self):
        from kitchen_sink import gpt_assistant

        assert gpt_assistant.name == "openai_research_assistant"

    def test_agent_tool_exists(self):
        from agentspan.agents.tool import get_tool_def
        from kitchen_sink import research_subtool

        td = get_tool_def(research_subtool)
        assert td.name == "quick_research"

    def test_credential_file_used(self):
        from agentspan.agents.tool import get_tool_def
        from kitchen_sink import research_database

        td = get_tool_def(research_database)
        assert td.credentials is not None


class TestKitchenSinkHelpers:
    """Test helper functions."""

    def test_contains_pii_ssn(self):
        from kitchen_sink_helpers import contains_pii

        assert contains_pii("My SSN is 123-45-6789")
        assert not contains_pii("No PII here")

    def test_contains_pii_credit_card(self):
        from kitchen_sink_helpers import contains_pii

        assert contains_pii("Card: 4532-0150-1234-5678")
        assert contains_pii("Card: 4532015012345678")

    def test_contains_sql_injection(self):
        from kitchen_sink_helpers import contains_sql_injection

        assert contains_sql_injection("DROP TABLE users")
        assert contains_sql_injection("' OR '1'='1'")
        assert not contains_sql_injection("normal search query")

    def test_classification_result_model(self):
        from kitchen_sink_helpers import ClassificationResult

        result = ClassificationResult(
            category="tech", priority=1, tags=["quantum"], metadata={}
        )
        assert result.category == "tech"
        assert result.priority == 1

    def test_article_report_model(self):
        from kitchen_sink_helpers import ArticleReport

        report = ArticleReport(
            word_count=1500,
            sentiment_score=0.8,
            readability_grade="B+",
            top_keywords=["quantum", "computing"],
        )
        assert report.word_count == 1500

    def test_callback_log(self):
        from kitchen_sink_helpers import callback_log

        callback_log.clear()
        callback_log.log("test_event", key="value")
        assert len(callback_log.events) == 1
        assert callback_log.events[0]["type"] == "test_event"
        assert callback_log.events[0]["key"] == "value"
        callback_log.clear()
        assert len(callback_log.events) == 0


class TestStrategyValidation:
    """Validate strategy configuration (feature #82)."""

    def test_validate_parallel_strategy(self):
        from kitchen_sink import research_team

        assert research_team.strategy == Strategy.PARALLEL

    def test_validate_sequential_strategy(self):
        from kitchen_sink import writing_pipeline

        assert writing_pipeline.strategy == Strategy.SEQUENTIAL

    def test_validate_swarm_strategy(self):
        from kitchen_sink import translation_swarm

        assert translation_swarm.strategy == Strategy.SWARM


class TestEvalRunner:
    """Correctness evaluation framework (feature #83)."""

    def test_eval_case_definition(self):
        eval_case = EvalCase(
            name="kitchen_sink_basic",
            prompt="Write a tech article about quantum computing",
            expect_output_contains=["quantum", "computing"],
        )
        assert eval_case.name == "kitchen_sink_basic"
