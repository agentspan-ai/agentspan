"""Unit tests for pr-review-skill loading and structure.

Validates that the skill directory is correctly discovered by AgentSpan:
- Correct name from SKILL.md frontmatter
- All script tools discovered
- Params injected into the skill instructions

Run:
    cd sdk/python/examples/pr-review-skill
    pytest tests/test_skill_loads.py -v
"""
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parent.parent

# AgentSpan must be installed: pip install -e sdk/python
try:
    from agentspan.agents import skill as load_skill
    AGENTSPAN_AVAILABLE = True
except ImportError:
    AGENTSPAN_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not AGENTSPAN_AVAILABLE,
    reason="agentspan not installed — run: pip install -e sdk/python",
)

EXPECTED_SCRIPTS = {
    "get_pr_review_bundle",
    "find_files",
    "grep_in_file",
}


class TestSkillLoads:
    def test_skill_name_matches_frontmatter(self):
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        assert agent.name == "pr-reviewer"

    def test_skill_framework_is_skill(self):
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        assert agent._framework == "skill"

    def test_all_scripts_discovered(self):
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        scripts = agent._framework_config["scripts"]
        missing = EXPECTED_SCRIPTS - set(scripts.keys())
        assert not missing, f"Missing scripts: {missing}"

    def test_scripts_are_python(self):
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        scripts = agent._framework_config["scripts"]
        for name in EXPECTED_SCRIPTS:
            lang = scripts[name]["language"]
            assert lang == "python", f"{name} should be python, got {lang}"

    def test_skill_md_contains_review_strategy(self):
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        skill_md = agent._framework_config["skillMd"]
        assert "Total tool call budget: 2" in skill_md
        assert "get_pr_review_bundle" in skill_md
        assert "post_review_comment" in skill_md
        assert "grep_in_file" in skill_md

    def test_skill_md_contains_all_eight_review_criteria(self):
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        skill_md = agent._framework_config["skillMd"]
        assert "Logic Correctness" in skill_md
        assert "Code Quality" in skill_md
        assert "Security" in skill_md
        assert "PR Does What It Claims" in skill_md
        assert "Test Coverage" in skill_md
        assert "Performance" in skill_md
        assert "Error Handling" in skill_md
        assert "Observability" in skill_md

    def test_repo_param_injected_into_skill_md(self):
        agent = load_skill(
            SKILL_DIR,
            model="openai/gpt-4o-mini",
            params={"repo": "orkes-saas/orkes-saas", "repo_path": "/tmp/repo"},
        )
        skill_md = agent._framework_config["skillMd"]
        assert "orkes-saas/orkes-saas" in skill_md

    def test_repo_path_param_injected(self):
        agent = load_skill(
            SKILL_DIR,
            model="openai/gpt-4o-mini",
            params={"repo": "owner/repo", "repo_path": "/workspace/myproject"},
        )
        skill_md = agent._framework_config["skillMd"]
        assert "/workspace/myproject" in skill_md

    def test_skill_without_params_still_loads(self):
        """Skill should load even if no params are passed (uses defaults from frontmatter)."""
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        assert agent is not None
        assert agent.name == "pr-reviewer"

    def test_wrong_script_count_fails(self):
        """Meta-test: verify we'd catch a missing script."""
        agent = load_skill(SKILL_DIR, model="openai/gpt-4o-mini")
        scripts = agent._framework_config["scripts"]
        # Keep broad/debug scripts out of the active tool surface.
        assert set(scripts.keys()) == EXPECTED_SCRIPTS
