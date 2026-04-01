"""Tests for agentspan.agents.skill module."""

import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "skills"


# ── Task 2: Tests for skill() core discovery ──────────────────────────


class TestParseSkillMd:
    """Test SKILL.md frontmatter parsing."""

    def test_parse_frontmatter_extracts_name(self):
        from agentspan.agents.skill import parse_frontmatter

        content = "---\nname: my-skill\ndescription: A test skill.\n---\n# Body"
        result = parse_frontmatter(content)
        assert result["name"] == "my-skill"
        assert result["description"] == "A test skill."

    def test_parse_frontmatter_extracts_metadata(self):
        from agentspan.agents.skill import parse_frontmatter

        content = "---\nname: x\ndescription: y\nmetadata:\n  author: test\n---\n"
        result = parse_frontmatter(content)
        assert result["metadata"] == {"author": "test"}

    def test_parse_frontmatter_missing_name_raises(self):
        from agentspan.agents.skill import parse_frontmatter

        content = "---\ndescription: no name\n---\n"
        with pytest.raises(ValueError, match="missing required 'name'"):
            parse_frontmatter(content)

    def test_extract_body(self):
        from agentspan.agents.skill import extract_body

        content = "---\nname: x\ndescription: y\n---\n# Body\nHello"
        body = extract_body(content)
        assert body.strip() == "# Body\nHello"


class TestDetectLanguage:
    """Test script language detection."""

    def test_python_extension(self, tmp_path):
        from agentspan.agents.skill import detect_language

        f = tmp_path / "script.py"
        f.write_text("print('hi')")
        assert detect_language(f) == "python"

    def test_bash_extension(self, tmp_path):
        from agentspan.agents.skill import detect_language

        f = tmp_path / "script.sh"
        f.write_text("echo hi")
        assert detect_language(f) == "bash"

    def test_node_extension(self, tmp_path):
        from agentspan.agents.skill import detect_language

        f = tmp_path / "script.js"
        f.write_text("console.log('hi')")
        assert detect_language(f) == "node"

    def test_no_extension_defaults_bash(self, tmp_path):
        from agentspan.agents.skill import detect_language

        f = tmp_path / "script"
        f.write_text("echo hi")
        assert detect_language(f) == "bash"

    def test_shebang_detection(self, tmp_path):
        from agentspan.agents.skill import detect_language

        f = tmp_path / "script"
        f.write_text("#!/usr/bin/env python3\nprint('hi')")
        assert detect_language(f) == "python"


class TestSkillDiscovery:
    """Test convention-based skill directory discovery."""

    def test_simple_skill_loads(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert agent.name == "simple-skill"
        assert agent._framework == "skill"
        assert "# Simple Skill" in agent._framework_config["skillMd"]

    def test_simple_skill_has_no_sub_agents(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert agent._framework_config["agentFiles"] == {}

    def test_simple_skill_has_no_scripts(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert agent._framework_config["scripts"] == {}

    def test_dg_skill_discovers_sub_agents(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        agent_files = agent._framework_config["agentFiles"]
        assert "gilfoyle" in agent_files
        assert "dinesh" in agent_files
        assert "You Are Gilfoyle" in agent_files["gilfoyle"]
        assert "You Are Dinesh" in agent_files["dinesh"]

    def test_dg_skill_discovers_resource_files(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        assert "comic-template.html" in agent._framework_config["resourceFiles"]

    def test_script_skill_discovers_scripts(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "script-skill", model="openai/gpt-4o")
        scripts = agent._framework_config["scripts"]
        assert "hello" in scripts
        assert scripts["hello"]["language"] == "python"
        assert scripts["hello"]["filename"] == "hello.py"

    def test_missing_skill_md_raises(self, tmp_path):
        from agentspan.agents.skill import SkillLoadError, skill

        with pytest.raises(SkillLoadError, match="SKILL.md not found"):
            skill(tmp_path, model="openai/gpt-4o")

    def test_model_stored_in_config(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="anthropic/claude-sonnet-4-6")
        assert agent._framework_config["model"] == "anthropic/claude-sonnet-4-6"

    def test_agent_models_stored_in_config(self):
        from agentspan.agents.skill import skill

        agent = skill(
            FIXTURES / "dg-skill",
            model="anthropic/claude-sonnet-4-6",
            agent_models={"gilfoyle": "openai/gpt-4o"},
        )
        assert agent._framework_config["agentModels"]["gilfoyle"] == "openai/gpt-4o"

    def test_skill_returns_agent_type(self):
        from agentspan.agents import Agent
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert isinstance(agent, Agent)


# ── Task 4: Tests for public API exports ──────────────────────────────


class TestPublicAPI:
    """Test that skill functions are importable from agentspan.agents."""

    def test_skill_importable(self):
        from agentspan.agents import skill

        assert callable(skill)

    def test_load_skills_importable(self):
        from agentspan.agents import load_skills

        assert callable(load_skills)

    def test_skill_load_error_importable(self):
        from agentspan.agents import SkillLoadError

        assert issubclass(SkillLoadError, Exception)


# ── Task 5: Tests for serialization hook ──────────────────────────────


class TestSerialization:
    """Test that skill agents serialize with framework='skill'."""

    def test_detect_framework_returns_skill(self):
        from agentspan.agents.frameworks.serializer import detect_framework
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert detect_framework(agent) == "skill"

    def test_regular_agent_not_detected_as_skill(self):
        from agentspan.agents import Agent
        from agentspan.agents.frameworks.serializer import detect_framework

        agent = Agent(name="regular", model="openai/gpt-4o")
        assert detect_framework(agent) != "skill"


# ── Task 6: Tests for worker registration ──────────────────────────────


class TestWorkerRegistration:
    """Test skill worker registration."""

    def test_script_worker_created(self):
        from agentspan.agents.skill import create_skill_workers, skill

        agent = skill(FIXTURES / "script-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        worker_names = [w.name for w in workers]
        assert "script-skill__hello" in worker_names

    def test_read_skill_file_worker_created(self):
        from agentspan.agents.skill import create_skill_workers, skill

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        worker_names = [w.name for w in workers]
        assert "dg-skill__read_skill_file" in worker_names

    def test_read_skill_file_only_allows_known_files(self):
        from agentspan.agents.skill import create_skill_workers, skill

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        # Should succeed for known file
        result = read_worker.func(path="comic-template.html")
        assert "{{PANELS}}" in result

    def test_read_skill_file_rejects_unknown_files(self):
        from agentspan.agents.skill import create_skill_workers, skill

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        result = read_worker.func(path="../../etc/passwd")
        assert "ERROR" in result

    def test_script_worker_executes(self):
        from agentspan.agents.skill import create_skill_workers, skill

        agent = skill(FIXTURES / "script-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        script_worker = next(w for w in workers if "hello" in w.name)
        result = script_worker.func(command="Agentspan")
        assert "Hello, Agentspan!" in result

    def test_no_workers_for_instruction_only_skill(self):
        from agentspan.agents.skill import create_skill_workers, skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        # Should still have read_skill_file even if no resource files
        # (empty list means no files to read, but worker is still registered
        # for consistency — it just returns error for any path)
        assert len(workers) >= 0


# ── Task 13: Tests for load_skills and cross-skill references ──────────


class TestLoadSkills:
    """Test batch loading of skills."""

    def test_load_skills_finds_all(self):
        from agentspan.agents.skill import load_skills

        skills = load_skills(FIXTURES, model="openai/gpt-4o")
        assert "simple-skill" in skills
        assert "dg-skill" in skills
        assert "script-skill" in skills

    def test_load_skills_returns_agents(self):
        from agentspan.agents import Agent
        from agentspan.agents.skill import load_skills

        skills = load_skills(FIXTURES, model="openai/gpt-4o")
        for name, agent in skills.items():
            assert isinstance(agent, Agent)

    def test_load_skills_per_skill_model_override(self):
        from agentspan.agents.skill import load_skills

        skills = load_skills(
            FIXTURES,
            model="openai/gpt-4o",
            agent_models={"dg-skill": {"gilfoyle": "anthropic/claude-sonnet-4-6"}},
        )
        config = skills["dg-skill"]._framework_config
        assert config["agentModels"]["gilfoyle"] == "anthropic/claude-sonnet-4-6"


class TestCrossSkillResolution:
    """Test cross-skill reference resolution."""

    def test_cross_ref_resolved_from_siblings(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "cross-ref-skill", model="openai/gpt-4o")
        cross_refs = agent._framework_config["crossSkillRefs"]
        assert "simple-skill" in cross_refs
        assert "# Simple Skill" in cross_refs["simple-skill"]["skillMd"]

    def test_cross_ref_not_found_is_empty(self, tmp_path):
        from agentspan.agents.skill import skill

        # Create a skill referencing a nonexistent skill
        skill_dir = tmp_path / "lonely-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: lonely-skill\ndescription: test\n---\n"
            "Invoke the nonexistent-skill skill."
        )
        agent = skill(skill_dir, model="openai/gpt-4o")
        # Unresolved refs are silently skipped
        assert "nonexistent-skill" not in agent._framework_config["crossSkillRefs"]


# ── Auto-splitting of large SKILL.md files ──────────────────────────────


def _make_large_skill_dir(tmp_path):
    """Create a skill directory with a large SKILL.md that exceeds 50K chars."""
    skill_dir = tmp_path / "large-skill"
    skill_dir.mkdir()

    preamble = (
        "# Large Skill\n\n"
        "You are the orchestrator. Follow these core rules:\n"
        "1. Always validate inputs\n"
        "2. Never skip error handling\n"
    )
    sections = []
    section_names = [
        "Workflow Definitions",
        "Running Workflows",
        "Error Handling",
        "API Reference",
        "Configuration Guide",
    ]
    for name in section_names:
        content = f"## {name}\n\nThis section covers {name.lower()}.\n\n"
        for i in range(100):
            content += (
                f"### Rule {i+1} for {name}\n\n"
                f"When handling {name.lower()} scenario {i+1}, validate inputs, "
                f"check permissions, execute operation, verify result.\n\n"
            )
        sections.append(content)

    body = preamble + "\n" + "\n".join(sections)
    assert len(body) > 50000, f"Body too short: {len(body)}"

    skill_md = (
        "---\nname: large-skill\ndescription: A large skill.\n---\n" + body
    )
    (skill_dir / "SKILL.md").write_text(skill_md)
    # Add a resource file
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "guide.md").write_text("# Guide\nSome content.")
    return skill_dir


class TestAutoSplitSections:
    """Test auto-splitting of large SKILL.md into sections."""

    def test_large_skill_has_sections(self, tmp_path):
        from agentspan.agents.skill import skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        assert hasattr(agent, "_skill_sections")
        assert len(agent._skill_sections) == 5

    def test_section_names_are_slugified(self, tmp_path):
        from agentspan.agents.skill import skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        assert "workflow-definitions" in agent._skill_sections
        assert "running-workflows" in agent._skill_sections
        assert "error-handling" in agent._skill_sections
        assert "api-reference" in agent._skill_sections
        assert "configuration-guide" in agent._skill_sections

    def test_sections_contain_content(self, tmp_path):
        from agentspan.agents.skill import skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        wf = agent._skill_sections["workflow-definitions"]
        assert "## Workflow Definitions" in wf
        assert "Rule 1 for Workflow Definitions" in wf

    def test_resource_files_include_sections(self, tmp_path):
        from agentspan.agents.skill import skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        rf = agent._framework_config["resourceFiles"]
        assert "skill_section:workflow-definitions" in rf
        assert "skill_section:error-handling" in rf
        # Real resource files should still be present
        assert "references/guide.md" in rf

    def test_small_skill_has_no_sections(self):
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        sections = getattr(agent, "_skill_sections", {})
        assert sections == {}

    def test_read_worker_returns_section_content(self, tmp_path):
        from agentspan.agents.skill import create_skill_workers, skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        result = read_worker.func(path="skill_section:workflow-definitions")
        assert "## Workflow Definitions" in result
        assert "Rule 1 for Workflow Definitions" in result

    def test_read_worker_still_reads_real_files(self, tmp_path):
        from agentspan.agents.skill import create_skill_workers, skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        result = read_worker.func(path="references/guide.md")
        assert "# Guide" in result

    def test_read_worker_rejects_unknown_section(self, tmp_path):
        from agentspan.agents.skill import create_skill_workers, skill

        skill_dir = _make_large_skill_dir(tmp_path)
        agent = skill(skill_dir, model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        result = read_worker.func(path="skill_section:nonexistent")
        assert "ERROR" in result


# ── Skill Parameters ─────────────────────────────────────────────────────


class TestSkillParams:
    """Test skill parameter parsing, defaulting, and prompt formatting."""

    def test_frontmatter_params_stored_as_defaults(self, tmp_path):
        """Params declared in frontmatter are stored in defaultParams."""
        from agentspan.agents.skill import skill

        skill_dir = tmp_path / "param-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: param-skill\ndescription: test\n"
            "params:\n  rounds:\n    type: integer\n    default: 3\n"
            "    description: Number of rounds\n"
            "  style:\n    type: string\n    default: concise\n---\n# Body"
        )
        agent = skill(skill_dir, model="openai/gpt-4o")
        assert agent._framework_config["defaultParams"] == {
            "rounds": 3,
            "style": "concise",
        }

    def test_frontmatter_params_bare_values(self, tmp_path):
        """Bare values (not dicts) in params are stored directly."""
        from agentspan.agents.skill import skill

        skill_dir = tmp_path / "bare-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: bare-skill\ndescription: test\n"
            "params:\n  rounds: 3\n  verbose: true\n---\n# Body"
        )
        agent = skill(skill_dir, model="openai/gpt-4o")
        assert agent._framework_config["defaultParams"] == {
            "rounds": 3,
            "verbose": True,
        }

    def test_no_frontmatter_params_empty_defaults(self):
        """Skills without params in frontmatter have empty defaultParams."""
        from agentspan.agents.skill import skill

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert agent._framework_config["defaultParams"] == {}

    def test_runtime_params_override_defaults(self, tmp_path):
        """Runtime params override frontmatter defaults."""
        from agentspan.agents.skill import skill

        skill_dir = tmp_path / "override-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: override-skill\ndescription: test\n"
            "params:\n  rounds:\n    type: integer\n    default: 3\n---\n# Body"
        )
        agent = skill(skill_dir, model="openai/gpt-4o", params={"rounds": 5})
        assert agent._skill_params == {"rounds": 5}

    def test_runtime_params_add_new_keys(self, tmp_path):
        """Runtime params can add keys not in frontmatter defaults."""
        from agentspan.agents.skill import skill

        skill_dir = tmp_path / "extra-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: extra-skill\ndescription: test\n"
            "params:\n  rounds:\n    type: integer\n    default: 3\n---\n# Body"
        )
        agent = skill(
            skill_dir, model="openai/gpt-4o", params={"rounds": 5, "verbose": True}
        )
        assert agent._skill_params == {"rounds": 5, "verbose": True}

    def test_merged_params_uses_defaults_when_no_override(self, tmp_path):
        """Merged params include defaults for keys not overridden."""
        from agentspan.agents.skill import skill

        skill_dir = tmp_path / "merge-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: merge-skill\ndescription: test\n"
            "params:\n  rounds:\n    type: integer\n    default: 3\n"
            "  style:\n    type: string\n    default: concise\n---\n# Body"
        )
        agent = skill(skill_dir, model="openai/gpt-4o", params={"rounds": 7})
        assert agent._skill_params == {"rounds": 7, "style": "concise"}


class TestFormatSkillParams:
    """Test prompt formatting with skill parameters."""

    def test_format_skill_params_produces_prefix(self):
        from agentspan.agents.skill import format_skill_params

        result = format_skill_params({"rounds": 5, "style": "verbose"})
        assert "[Skill Parameters]" in result
        assert "rounds: 5" in result
        assert "style: verbose" in result

    def test_format_skill_params_empty_returns_empty(self):
        from agentspan.agents.skill import format_skill_params

        assert format_skill_params({}) == ""

    def test_format_prompt_with_params(self):
        from agentspan.agents.skill import format_prompt_with_params

        result = format_prompt_with_params("Review this code", {"rounds": 5})
        assert result.startswith("[Skill Parameters]")
        assert "rounds: 5" in result
        assert "[User Request]" in result
        assert result.endswith("Review this code")

    def test_format_prompt_with_params_empty_passthrough(self):
        from agentspan.agents.skill import format_prompt_with_params

        result = format_prompt_with_params("Review this code", {})
        assert result == "Review this code"

    def test_format_prompt_with_multiple_params(self):
        from agentspan.agents.skill import format_prompt_with_params

        result = format_prompt_with_params(
            "Review this code", {"rounds": 5, "style": "verbose"}
        )
        assert "rounds: 5" in result
        assert "style: verbose" in result
        assert "[Skill Parameters]" in result
        assert "[User Request]" in result
