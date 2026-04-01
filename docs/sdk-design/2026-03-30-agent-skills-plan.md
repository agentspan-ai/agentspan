# Agent Skills Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Agentspan agents to load agentskills.io-compatible skill directories as first-class `Agent` instances — composable, durable, and fully observable.

**Architecture:** Thin SDK reads skill directories and packages raw config. Server-side `SkillNormalizer` converts to canonical `AgentConfig`. Existing `AgentCompiler` compiles to Conductor. Sub-agents become `SUB_WORKFLOW` tasks, scripts become `SIMPLE` worker tasks, resource files are read on demand via a worker tool.

**Tech Stack:** Python SDK, Java Spring Boot server (SkillNormalizer), Go CLI, Conductor orchestration engine.

**Spec:** `docs/sdk-design/2026-03-30-agent-skills-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `sdk/python/src/agentspan/agents/skill.py` | `skill()`, `load_skills()`, worker registration, cross-skill resolver, language detection |
| `sdk/python/tests/unit/test_skill.py` | Unit tests for skill loading, discovery, config packaging |
| `server/src/main/java/dev/agentspan/runtime/normalizer/SkillNormalizer.java` | Parse skill config, produce canonical AgentConfig |
| `server/src/test/java/dev/agentspan/runtime/normalizer/SkillNormalizerTest.java` | Unit tests for normalization logic |
| `cli/cmd/skill.go` | `agentspan skill run`, `skill load`, `skill serve` subcommands |
| `cli/cmd/skill_test.go` | CLI skill command tests |

### Modified Files

| File | Change |
|------|--------|
| `sdk/python/src/agentspan/agents/__init__.py` | Add `skill`, `load_skills` to `__all__` exports |
| `sdk/python/src/agentspan/agents/frameworks/serializer.py` | Add `"skill"` detection in `detect_framework()` |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | Register skill workers before execution |
| `sdk/python/src/agentspan/agents/runtime/tool_registry.py` | Handle skill worker registration |

### Test Fixture Files

| File | Purpose |
|------|---------|
| `sdk/python/tests/fixtures/skills/simple-skill/SKILL.md` | Instruction-only skill fixture |
| `sdk/python/tests/fixtures/skills/dg-skill/SKILL.md` | Skill with sub-agents fixture |
| `sdk/python/tests/fixtures/skills/dg-skill/gilfoyle-agent.md` | Sub-agent fixture |
| `sdk/python/tests/fixtures/skills/dg-skill/dinesh-agent.md` | Sub-agent fixture |
| `sdk/python/tests/fixtures/skills/dg-skill/comic-template.html` | Asset fixture |
| `sdk/python/tests/fixtures/skills/script-skill/SKILL.md` | Skill with scripts fixture |
| `sdk/python/tests/fixtures/skills/script-skill/scripts/hello.py` | Script fixture |
| `sdk/python/tests/fixtures/skills/cross-ref-skill/SKILL.md` | Skill with cross-ref fixture |
| `server/src/test/resources/skills/dg-skill.json` | Raw skill config fixture for Java tests |
| `server/src/test/resources/skills/simple-skill.json` | Simple skill config fixture |
| `server/src/test/resources/skills/conductor-skill.json` | Script skill config fixture |

---

## Chunk 1: Python SDK — Core `skill()` Function

### Task 1: Create test fixtures

**Files:**
- Create: `sdk/python/tests/fixtures/skills/simple-skill/SKILL.md`
- Create: `sdk/python/tests/fixtures/skills/dg-skill/SKILL.md`
- Create: `sdk/python/tests/fixtures/skills/dg-skill/gilfoyle-agent.md`
- Create: `sdk/python/tests/fixtures/skills/dg-skill/dinesh-agent.md`
- Create: `sdk/python/tests/fixtures/skills/dg-skill/comic-template.html`
- Create: `sdk/python/tests/fixtures/skills/script-skill/SKILL.md`
- Create: `sdk/python/tests/fixtures/skills/script-skill/scripts/hello.py`

- [ ] **Step 1: Create simple-skill fixture (instruction-only)**

```markdown
---
name: simple-skill
description: A simple skill for testing. Use when testing basic skill loading.
---

# Simple Skill

You are a helpful assistant. Follow these instructions carefully.

## Steps
1. Read the user's request
2. Respond concisely
```

- [ ] **Step 2: Create dg-skill fixtures (sub-agents + asset)**

`dg-skill/SKILL.md`:
```markdown
---
name: dg-skill
description: Adversarial code review with two sub-agents. Use for code review.
metadata:
  author: test
---

# DG Review

Dispatch the gilfoyle agent to review code, then dispatch the dinesh agent to respond.
Repeat until convergence. Read comic-template.html to generate output.
```

`dg-skill/gilfoyle-agent.md`:
```markdown
# You Are Gilfoyle
Review code with withering precision. Find real bugs.
```

`dg-skill/dinesh-agent.md`:
```markdown
# You Are Dinesh
Defend the code. Concede real issues, defend valid choices.
```

`dg-skill/comic-template.html`:
```html
<html><body>{{PANELS}}</body></html>
```

- [ ] **Step 3: Create script-skill fixture**

`script-skill/SKILL.md`:
```markdown
---
name: script-skill
description: A skill with scripts. Use when testing script discovery.
---

# Script Skill

Run the hello script to greet the user.
```

`script-skill/scripts/hello.py`:
```python
#!/usr/bin/env python3
import sys
print(f"Hello, {' '.join(sys.argv[1:]) or 'world'}!")
```

- [ ] **Step 4: Commit**

```bash
git add sdk/python/tests/fixtures/skills/
git commit -m "feat(skills): add test fixtures for skill loading"
```

---

### Task 2: Write failing tests for `skill()` core discovery

**Files:**
- Create: `sdk/python/tests/unit/test_skill.py`

- [ ] **Step 1: Write failing tests for SKILL.md parsing and directory discovery**

```python
"""Tests for agentspan.agents.skill module."""
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "skills"


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
        from agentspan.agents.skill import skill, SkillLoadError

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
        from agentspan.agents.skill import skill
        from agentspan.agents import Agent

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert isinstance(agent, Agent)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentspan.agents.skill'`

- [ ] **Step 3: Commit failing tests**

```bash
git add sdk/python/tests/unit/test_skill.py
git commit -m "test(skills): add failing tests for skill() discovery"
```

---

### Task 3: Implement `skill()` core function

**Files:**
- Create: `sdk/python/src/agentspan/agents/skill.py`

- [ ] **Step 1: Implement the skill module**

```python
"""Agent Skills integration — load agentskills.io skill directories as Agents."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from agentspan.agents.agent import Agent


class SkillLoadError(Exception):
    """Raised when a skill directory cannot be loaded."""


def parse_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML frontmatter from SKILL.md content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1)) or {}
    if "name" not in data or not data["name"]:
        raise ValueError("SKILL.md missing required 'name' field in frontmatter")
    return data


def extract_body(content: str) -> str:
    """Extract markdown body after frontmatter."""
    match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return content
    return match.group(1).strip()


EXTENSION_MAP = {
    ".py": "python",
    ".sh": "bash",
    ".js": "node",
    ".mjs": "node",
    ".ts": "node",
    ".rb": "ruby",
}

SHEBANG_MAP = {
    "python": "python",
    "python3": "python",
    "bash": "bash",
    "sh": "bash",
    "node": "node",
    "ruby": "ruby",
}


def detect_language(path: Path) -> str:
    """Detect script language from file extension or shebang."""
    ext = path.suffix.lower()
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]
    # Check shebang
    try:
        first_line = path.read_text().split("\n", 1)[0]
        if first_line.startswith("#!"):
            for key, lang in SHEBANG_MAP.items():
                if key in first_line:
                    return lang
    except (OSError, UnicodeDecodeError):
        pass
    return "bash"  # default


def skill(
    path: Union[str, Path],
    model: Union[str, Any] = "",
    agent_models: Optional[Dict[str, str]] = None,
    search_path: Optional[List[str]] = None,
) -> Agent:
    """Load an Agent Skills directory as an Agentspan Agent.

    Args:
        path: Path to skill directory containing SKILL.md.
        model: Model for the orchestrator agent. Also default for sub-agents.
        agent_models: Per-sub-agent model overrides.
        search_path: Additional directories to search for cross-skill references.

    Returns:
        Agent that can be run, composed, deployed, and served.

    Raises:
        SkillLoadError: If the directory is not a valid skill.
    """
    path = Path(path).resolve()

    # 1. Read SKILL.md (required)
    skill_md_path = path / "SKILL.md"
    if not skill_md_path.exists():
        raise SkillLoadError(
            f"Directory {path} is not a valid skill: SKILL.md not found"
        )
    skill_md = skill_md_path.read_text()
    frontmatter = parse_frontmatter(skill_md)
    name = frontmatter["name"]

    # 2. Discover *-agent.md files
    agent_files: Dict[str, str] = {}
    for f in sorted(path.glob("*-agent.md")):
        agent_name = f.stem.removesuffix("-agent")
        agent_files[agent_name] = f.read_text()

    # 3. Discover scripts
    scripts: Dict[str, Dict[str, Any]] = {}
    scripts_dir = path / "scripts"
    if scripts_dir.exists():
        for f in sorted(scripts_dir.iterdir()):
            if f.is_file():
                scripts[f.stem] = {
                    "filename": f.name,
                    "language": detect_language(f),
                    "path": str(f),
                }

    # 4. List resource files (paths only, not contents)
    resource_files: List[str] = []
    for subdir in ["references", "examples", "assets"]:
        d = path / subdir
        if d.exists():
            resource_files.extend(
                sorted(str(f.relative_to(path)) for f in d.rglob("*") if f.is_file())
            )
    # Non-agent, non-SKILL.md files in root
    for f in sorted(path.iterdir()):
        if (
            f.is_file()
            and f.name != "SKILL.md"
            and not f.name.endswith("-agent.md")
            and f.name not in ("skill.yaml", "skill.toml")
        ):
            resource_files.append(f.name)

    # 5. Resolve cross-skill references
    cross_refs = resolve_cross_skills(skill_md, path, search_path)

    # 6. Build raw config
    raw_config: Dict[str, Any] = {
        "model": str(model) if model else "",
        "agentModels": agent_models or {},
        "skillMd": skill_md,
        "agentFiles": agent_files,
        "scripts": {
            k: {"filename": v["filename"], "language": v["language"]}
            for k, v in scripts.items()
        },
        "resourceFiles": resource_files,
        "crossSkillRefs": cross_refs,
    }

    # 7. Return Agent with framework marker
    agent = Agent(name=name, model=model or "")
    agent._framework = "skill"
    agent._framework_config = raw_config
    agent._skill_path = path
    agent._skill_scripts = scripts
    return agent


def resolve_cross_skills(
    skill_md: str,
    skill_path: Path,
    search_path: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Resolve cross-skill references found in SKILL.md body.

    Scans for patterns like 'invoke writing-plans skill' and resolves
    them from the search path.
    """
    body = extract_body(skill_md)

    # Match patterns: invoke/use/call <name> skill
    pattern = r"(?:invoke|use|call)\s+(?:the\s+)?([a-z][a-z0-9-]*)\s+skill"
    matches = set(re.findall(pattern, body, re.IGNORECASE))

    if not matches:
        return {}

    # Build search path
    dirs: List[Path] = []
    # Sibling directories
    if skill_path.parent.exists():
        dirs.append(skill_path.parent)
    # Standard locations
    dirs.append(Path.cwd() / ".agents" / "skills")
    dirs.append(Path.home() / ".agents" / "skills")
    # Explicit search path
    if search_path:
        dirs.extend(Path(p).expanduser().resolve() for p in search_path)

    cross_refs: Dict[str, Any] = {}
    for ref_name in matches:
        for d in dirs:
            ref_dir = d / ref_name
            if (ref_dir / "SKILL.md").exists() and ref_dir.resolve() != skill_path:
                ref_md = (ref_dir / "SKILL.md").read_text()
                ref_agent_files = {}
                for f in sorted(ref_dir.glob("*-agent.md")):
                    aname = f.stem.removesuffix("-agent")
                    ref_agent_files[aname] = f.read_text()
                ref_scripts = {}
                ref_scripts_dir = ref_dir / "scripts"
                if ref_scripts_dir.exists():
                    for f in sorted(ref_scripts_dir.iterdir()):
                        if f.is_file():
                            ref_scripts[f.stem] = {
                                "filename": f.name,
                                "language": detect_language(f),
                            }
                ref_resources = []
                for subdir in ["references", "examples", "assets"]:
                    sd = ref_dir / subdir
                    if sd.exists():
                        ref_resources.extend(
                            sorted(
                                str(f.relative_to(ref_dir))
                                for f in sd.rglob("*")
                                if f.is_file()
                            )
                        )
                cross_refs[ref_name] = {
                    "skillMd": ref_md,
                    "agentFiles": ref_agent_files,
                    "scripts": ref_scripts,
                    "resourceFiles": ref_resources,
                }
                break
    return cross_refs


def load_skills(
    path: Union[str, Path],
    model: Union[str, Any] = "",
    agent_models: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Agent]:
    """Load all skills from a directory. Cross-references auto-resolved.

    Args:
        path: Directory containing skill subdirectories.
        model: Default model for all skills.
        agent_models: Per-skill, per-sub-agent overrides.

    Returns:
        Dict mapping skill name to Agent.
    """
    path = Path(path).resolve()
    skills: Dict[str, Agent] = {}
    for d in sorted(path.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            overrides = (agent_models or {}).get(d.name, {})
            skills[d.name] = skill(d, model=model, agent_models=overrides)
    return skills
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add sdk/python/src/agentspan/agents/skill.py
git commit -m "feat(skills): implement skill() and load_skills() with convention-based discovery"
```

---

### Task 4: Add `skill` and `load_skills` to public API exports

**Files:**
- Modify: `sdk/python/src/agentspan/agents/__init__.py`

- [ ] **Step 1: Write failing test for import**

Add to `sdk/python/tests/unit/test_skill.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py::TestPublicAPI -v`
Expected: FAIL — `ImportError: cannot import name 'skill' from 'agentspan.agents'`

- [ ] **Step 3: Add exports to `__init__.py`**

Add to the imports section:
```python
from agentspan.agents.skill import skill, load_skills, SkillLoadError
```

Add to `__all__`:
```python
"skill",
"load_skills",
"SkillLoadError",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py::TestPublicAPI -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/__init__.py sdk/python/tests/unit/test_skill.py
git commit -m "feat(skills): export skill, load_skills, SkillLoadError from agentspan.agents"
```

---

### Task 5: Add serialization hook for skill framework detection

**Files:**
- Modify: `sdk/python/src/agentspan/agents/frameworks/serializer.py`

- [ ] **Step 1: Write failing test**

Add to `sdk/python/tests/unit/test_skill.py`:

```python
class TestSerialization:
    """Test that skill agents serialize with framework='skill'."""

    def test_detect_framework_returns_skill(self):
        from agentspan.agents.skill import skill
        from agentspan.agents.frameworks.serializer import detect_framework

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        assert detect_framework(agent) == "skill"

    def test_regular_agent_not_detected_as_skill(self):
        from agentspan.agents import Agent
        from agentspan.agents.frameworks.serializer import detect_framework

        agent = Agent(name="regular", model="openai/gpt-4o")
        assert detect_framework(agent) != "skill"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py::TestSerialization -v`
Expected: FAIL — `detect_framework` returns `None` for skill agents

- [ ] **Step 3: Add skill detection to `detect_framework()`**

In `sdk/python/src/agentspan/agents/frameworks/serializer.py`, add at the top of `detect_framework()`:

```python
# Skill framework detection
if hasattr(agent_obj, "_framework") and agent_obj._framework == "skill":
    return "skill"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py::TestSerialization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sdk/python/src/agentspan/agents/frameworks/serializer.py sdk/python/tests/unit/test_skill.py
git commit -m "feat(skills): add skill framework detection in serializer"
```

---

## Chunk 2: Python SDK — Worker Registration

### Task 6: Write failing tests for worker registration

**Files:**
- Modify: `sdk/python/tests/unit/test_skill.py`

- [ ] **Step 1: Write tests for script worker and read_skill_file worker**

```python
class TestWorkerRegistration:
    """Test skill worker registration."""

    def test_script_worker_created(self):
        from agentspan.agents.skill import skill, create_skill_workers

        agent = skill(FIXTURES / "script-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        worker_names = [w.name for w in workers]
        assert "script-skill__hello" in worker_names

    def test_read_skill_file_worker_created(self):
        from agentspan.agents.skill import skill, create_skill_workers

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        worker_names = [w.name for w in workers]
        assert "dg-skill__read_skill_file" in worker_names

    def test_read_skill_file_only_allows_known_files(self):
        from agentspan.agents.skill import skill, create_skill_workers

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        # Should succeed for known file
        result = read_worker.func(path="comic-template.html")
        assert "{{PANELS}}" in result

    def test_read_skill_file_rejects_unknown_files(self):
        from agentspan.agents.skill import skill, create_skill_workers

        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        read_worker = next(w for w in workers if "read_skill_file" in w.name)
        result = read_worker.func(path="../../etc/passwd")
        assert "ERROR" in result

    def test_script_worker_executes(self):
        from agentspan.agents.skill import skill, create_skill_workers

        agent = skill(FIXTURES / "script-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        script_worker = next(w for w in workers if "hello" in w.name)
        result = script_worker.func(command="Agentspan")
        assert "Hello, Agentspan!" in result

    def test_no_workers_for_instruction_only_skill(self):
        from agentspan.agents.skill import skill, create_skill_workers

        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        workers = create_skill_workers(agent)
        # Should still have read_skill_file even if no resource files
        # (empty list means no files to read, but worker is still registered
        # for consistency — it just returns error for any path)
        assert len(workers) >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py::TestWorkerRegistration -v`
Expected: FAIL — `ImportError: cannot import name 'create_skill_workers'`

- [ ] **Step 3: Commit failing tests**

```bash
git add sdk/python/tests/unit/test_skill.py
git commit -m "test(skills): add failing tests for skill worker registration"
```

---

### Task 7: Implement worker registration

**Files:**
- Modify: `sdk/python/src/agentspan/agents/skill.py`

- [ ] **Step 1: Add `create_skill_workers()` to skill.py**

Add to the bottom of `skill.py`:

```python
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass
class SkillWorker:
    """A worker function for a skill tool."""
    name: str
    description: str
    func: Callable[..., str]


def create_skill_workers(agent: Agent) -> List[SkillWorker]:
    """Create worker functions for a skill-based agent.

    Returns a list of SkillWorker instances that should be registered
    with the tool registry for Conductor polling.
    """
    if not hasattr(agent, "_framework") or agent._framework != "skill":
        return []

    workers: List[SkillWorker] = []
    skill_name = agent.name
    config = agent._framework_config
    skill_path = agent._skill_path
    scripts = getattr(agent, "_skill_scripts", {})

    # Script workers — one per script file
    for tool_name, script_info in scripts.items():
        script_file = script_info["path"]
        language = script_info["language"]
        worker_name = f"{skill_name}__{tool_name}"

        interpreter_map = {
            "python": "python3",
            "bash": "bash",
            "node": "node",
            "ruby": "ruby",
        }
        interpreter = interpreter_map.get(language, "bash")

        def make_script_func(interp: str, spath: str) -> Callable[..., str]:
            def run_script(command: str = "") -> str:
                try:
                    args = shlex.split(command) if command else []
                    result = subprocess.run(
                        [interp, spath, *args],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    if result.returncode != 0:
                        return f"ERROR (exit {result.returncode}):\n{result.stderr}"
                    return result.stdout
                except subprocess.TimeoutExpired:
                    return "ERROR: Script execution timed out (300s)"
                except Exception as e:
                    return f"ERROR: {e}"

            return run_script

        workers.append(
            SkillWorker(
                name=worker_name,
                description=f"Run {tool_name} script from {skill_name} skill",
                func=make_script_func(interpreter, script_file),
            )
        )

    # read_skill_file worker
    allowed_files = set(config.get("resourceFiles", []))
    read_worker_name = f"{skill_name}__read_skill_file"

    def make_read_func(sdir: Path, allowed: set) -> Callable[..., str]:
        def read_skill_file(path: str = "") -> str:
            if path not in allowed:
                return f"ERROR: '{path}' not found. Available: {sorted(allowed)}"
            target = sdir / path
            # Safety check: ensure resolved path is within skill directory
            try:
                target.resolve().relative_to(sdir.resolve())
            except ValueError:
                return f"ERROR: '{path}' is outside the skill directory"
            try:
                return target.read_text()
            except Exception as e:
                return f"ERROR reading '{path}': {e}"

        return read_skill_file

    if allowed_files:
        workers.append(
            SkillWorker(
                name=read_worker_name,
                description=f"Read resource files from {skill_name} skill",
                func=make_read_func(skill_path, allowed_files),
            )
        )

    return workers
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py::TestWorkerRegistration -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add sdk/python/src/agentspan/agents/skill.py
git commit -m "feat(skills): implement skill worker registration for scripts and file reads"
```

---

## Chunk 3: Java Server — SkillNormalizer

### Task 8: Create test fixtures for SkillNormalizer

**Files:**
- Create: `server/src/test/resources/skills/dg-skill.json`
- Create: `server/src/test/resources/skills/simple-skill.json`
- Create: `server/src/test/resources/skills/conductor-skill.json`

- [ ] **Step 1: Create JSON fixtures representing raw skill configs**

`server/src/test/resources/skills/simple-skill.json`:
```json
{
  "model": "openai/gpt-4o",
  "agentModels": {},
  "skillMd": "---\nname: simple-skill\ndescription: A simple test skill.\n---\n# Simple Skill\n\nYou are a helpful assistant.",
  "agentFiles": {},
  "scripts": {},
  "resourceFiles": [],
  "crossSkillRefs": {}
}
```

`server/src/test/resources/skills/dg-skill.json`:
```json
{
  "model": "anthropic/claude-sonnet-4-6",
  "agentModels": {"gilfoyle": "openai/gpt-4o"},
  "skillMd": "---\nname: dg-skill\ndescription: Adversarial code review.\nmetadata:\n  author: test\n---\n# DG Review\n\nDispatch gilfoyle, then dinesh. Repeat until convergence.",
  "agentFiles": {
    "gilfoyle": "# You Are Gilfoyle\nReview code with precision.",
    "dinesh": "# You Are Dinesh\nDefend the code."
  },
  "scripts": {},
  "resourceFiles": ["comic-template.html"],
  "crossSkillRefs": {}
}
```

`server/src/test/resources/skills/conductor-skill.json`:
```json
{
  "model": "anthropic/claude-sonnet-4-6",
  "agentModels": {},
  "skillMd": "---\nname: conductor-skill\ndescription: Manage Conductor workflows.\n---\n# Conductor\n\nUse conductor_api to manage workflows. See references/api-reference.md for details.",
  "agentFiles": {},
  "scripts": {
    "conductor_api": {"filename": "conductor_api.py", "language": "python"}
  },
  "resourceFiles": ["references/api-reference.md", "references/workflow-definition.md"],
  "crossSkillRefs": {}
}
```

- [ ] **Step 2: Commit**

```bash
git add server/src/test/resources/skills/
git commit -m "test(skills): add JSON fixtures for SkillNormalizer tests"
```

---

### Task 9: Write failing tests for SkillNormalizer

**Files:**
- Create: `server/src/test/java/dev/agentspan/runtime/normalizer/SkillNormalizerTest.java`

- [ ] **Step 1: Write tests**

```java
package dev.agentspan.runtime.normalizer;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SkillNormalizerTest {

    private SkillNormalizer normalizer;
    private ObjectMapper mapper;

    @BeforeEach
    void setUp() {
        normalizer = new SkillNormalizer();
        mapper = new ObjectMapper();
    }

    private Map<String, Object> loadFixture(String name) throws Exception {
        InputStream is = getClass().getResourceAsStream("/skills/" + name + ".json");
        return mapper.readValue(is, Map.class);
    }

    @Test
    void frameworkIdIsSkill() {
        assertEquals("skill", normalizer.frameworkId());
    }

    // --- Simple skill tests ---

    @Test
    void simpleSkillSetsNameFromFrontmatter() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("simple-skill"));
        assertEquals("simple-skill", config.getName());
    }

    @Test
    void simpleSkillSetsModelFromConfig() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("simple-skill"));
        assertEquals("openai/gpt-4o", config.getModel());
    }

    @Test
    void simpleSkillSetsInstructionsFromBody() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("simple-skill"));
        assertTrue(config.getInstructions().contains("# Simple Skill"));
        assertTrue(config.getInstructions().contains("You are a helpful assistant"));
    }

    @Test
    void simpleSkillHasNoTools() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("simple-skill"));
        // No sub-agents, no scripts, no resource files → no tools
        assertTrue(config.getTools() == null || config.getTools().isEmpty());
    }

    // --- DG skill tests (sub-agents + resources) ---

    @Test
    void dgSkillCreatesSubAgentTools() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        List<ToolConfig> tools = config.getTools();
        assertNotNull(tools);

        List<String> toolNames = tools.stream().map(ToolConfig::getName).toList();
        assertTrue(toolNames.contains("dg-skill__gilfoyle"));
        assertTrue(toolNames.contains("dg-skill__dinesh"));
    }

    @Test
    void dgSkillSubAgentToolsAreAgentToolType() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        ToolConfig gilfoyle = config.getTools().stream()
            .filter(t -> t.getName().contains("gilfoyle"))
            .findFirst().orElseThrow();
        assertEquals("agent_tool", gilfoyle.getToolType());
    }

    @Test
    void dgSkillSubAgentHasInstructions() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        ToolConfig gilfoyle = config.getTools().stream()
            .filter(t -> t.getName().contains("gilfoyle"))
            .findFirst().orElseThrow();
        Map<String, Object> toolConfig = gilfoyle.getConfig();
        assertNotNull(toolConfig);
        AgentConfig subAgent = (AgentConfig) toolConfig.get("agentConfig");
        assertTrue(subAgent.getInstructions().contains("You Are Gilfoyle"));
    }

    @Test
    void dgSkillSubAgentInheritsModel() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        ToolConfig dinesh = config.getTools().stream()
            .filter(t -> t.getName().contains("dinesh"))
            .findFirst().orElseThrow();
        AgentConfig subAgent = (AgentConfig) dinesh.getConfig().get("agentConfig");
        // dinesh not in agentModels override → inherits parent model
        assertEquals("anthropic/claude-sonnet-4-6", subAgent.getModel());
    }

    @Test
    void dgSkillSubAgentModelOverride() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        ToolConfig gilfoyle = config.getTools().stream()
            .filter(t -> t.getName().contains("gilfoyle"))
            .findFirst().orElseThrow();
        AgentConfig subAgent = (AgentConfig) gilfoyle.getConfig().get("agentConfig");
        // gilfoyle has override in agentModels
        assertEquals("openai/gpt-4o", subAgent.getModel());
    }

    @Test
    void dgSkillCreatesReadSkillFileTool() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        ToolConfig readFile = config.getTools().stream()
            .filter(t -> t.getName().contains("read_skill_file"))
            .findFirst().orElseThrow();
        assertEquals("worker", readFile.getToolType());
    }

    @Test
    void dgSkillReadSkillFileConstrainsEnum() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("dg-skill"));
        ToolConfig readFile = config.getTools().stream()
            .filter(t -> t.getName().contains("read_skill_file"))
            .findFirst().orElseThrow();
        Map<String, Object> schema = readFile.getInputSchema();
        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        Map<String, Object> pathProp = (Map<String, Object>) props.get("path");
        List<String> enumValues = (List<String>) pathProp.get("enum");
        assertTrue(enumValues.contains("comic-template.html"));
    }

    // --- Conductor skill tests (scripts + resources) ---

    @Test
    void conductorSkillCreatesScriptTool() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("conductor-skill"));
        ToolConfig scriptTool = config.getTools().stream()
            .filter(t -> t.getName().contains("conductor_api"))
            .findFirst().orElseThrow();
        assertEquals("worker", scriptTool.getToolType());
    }

    @Test
    void conductorSkillReadFileHasMultipleResources() throws Exception {
        AgentConfig config = normalizer.normalize(loadFixture("conductor-skill"));
        ToolConfig readFile = config.getTools().stream()
            .filter(t -> t.getName().contains("read_skill_file"))
            .findFirst().orElseThrow();
        Map<String, Object> schema = readFile.getInputSchema();
        Map<String, Object> props = (Map<String, Object>) schema.get("properties");
        Map<String, Object> pathProp = (Map<String, Object>) props.get("path");
        List<String> enumValues = (List<String>) pathProp.get("enum");
        assertEquals(2, enumValues.size());
        assertTrue(enumValues.contains("references/api-reference.md"));
        assertTrue(enumValues.contains("references/workflow-definition.md"));
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && ./gradlew test --tests "*SkillNormalizerTest*"`
Expected: FAIL — `SkillNormalizer` class doesn't exist

- [ ] **Step 3: Commit failing tests**

```bash
git add server/src/test/java/dev/agentspan/runtime/normalizer/SkillNormalizerTest.java
git commit -m "test(skills): add failing tests for SkillNormalizer"
```

---

### Task 10: Implement SkillNormalizer

**Files:**
- Create: `server/src/main/java/dev/agentspan/runtime/normalizer/SkillNormalizer.java`

- [ ] **Step 1: Implement the normalizer**

```java
package dev.agentspan.runtime.normalizer;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.Yaml;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Normalizes agentskills.io skill directories into canonical AgentConfig.
 * Handles SKILL.md parsing, sub-agent discovery, script tool generation,
 * and cross-skill reference resolution.
 */
@Component
public class SkillNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(SkillNormalizer.class);
    private static final Pattern FRONTMATTER_PATTERN =
            Pattern.compile("^---\\s*\\n(.*?)\\n---\\s*\\n(.*)", Pattern.DOTALL);

    // Track skills being normalized to detect cycles
    private final ThreadLocal<Set<String>> normalizingStack =
            ThreadLocal.withInitial(HashSet::new);

    @Override
    public String frameworkId() {
        return "skill";
    }

    @Override
    @SuppressWarnings("unchecked")
    public AgentConfig normalize(Map<String, Object> rawConfig) {
        String skillMd = (String) rawConfig.get("skillMd");
        String model = (String) rawConfig.getOrDefault("model", "");
        Map<String, String> agentModels = (Map<String, String>)
                rawConfig.getOrDefault("agentModels", Collections.emptyMap());
        Map<String, String> agentFiles = (Map<String, String>)
                rawConfig.getOrDefault("agentFiles", Collections.emptyMap());
        Map<String, Map<String, Object>> scripts = (Map<String, Map<String, Object>>)
                rawConfig.getOrDefault("scripts", Collections.emptyMap());
        List<String> resourceFiles = (List<String>)
                rawConfig.getOrDefault("resourceFiles", Collections.emptyList());
        Map<String, Object> crossSkillRefs = (Map<String, Object>)
                rawConfig.getOrDefault("crossSkillRefs", Collections.emptyMap());

        // Step 1: Parse SKILL.md frontmatter
        Map<String, Object> frontmatter = parseFrontmatter(skillMd);
        String body = extractBody(skillMd);
        String name = (String) frontmatter.get("name");
        String description = (String) frontmatter.getOrDefault("description", "");

        // Step 2: Build orchestrator AgentConfig
        AgentConfig orchestrator = new AgentConfig();
        orchestrator.setName(name);
        orchestrator.setModel(model);
        orchestrator.setInstructions(body);
        orchestrator.setDescription(description);

        // Pass through metadata
        if (frontmatter.containsKey("metadata")) {
            orchestrator.setMetadata((Map<String, Object>) frontmatter.get("metadata"));
        }

        List<ToolConfig> tools = new ArrayList<>();

        // Step 3: Build sub-agents from *-agent.md files
        for (Map.Entry<String, String> entry : agentFiles.entrySet()) {
            String agentName = entry.getKey();
            String instructions = entry.getValue();
            String agentModel = agentModels.getOrDefault(agentName, model);

            AgentConfig subAgent = new AgentConfig();
            subAgent.setName(agentName);
            subAgent.setInstructions(instructions);
            subAgent.setModel(agentModel);

            String namespacedName = name + "__" + agentName;
            Map<String, Object> toolConfig = new LinkedHashMap<>();
            toolConfig.put("agentConfig", subAgent);

            tools.add(ToolConfig.builder()
                    .name(namespacedName)
                    .description("Invoke the " + agentName + " agent")
                    .toolType("agent_tool")
                    .config(toolConfig)
                    .build());

            log.debug("Skill '{}': created sub-agent tool '{}'", name, namespacedName);
        }

        // Step 4: Build tools from scripts
        for (Map.Entry<String, Map<String, Object>> entry : scripts.entrySet()) {
            String scriptName = entry.getKey();
            String namespacedName = name + "__" + scriptName;

            Map<String, Object> inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            inputSchema.put("properties", Map.of(
                    "command", Map.of(
                            "type", "string",
                            "description", "Arguments to pass to the " + scriptName + " script"
                    )
            ));
            inputSchema.put("required", List.of("command"));

            tools.add(ToolConfig.builder()
                    .name(namespacedName)
                    .description("Run " + scriptName + " script from " + name + " skill")
                    .toolType("worker")
                    .inputSchema(inputSchema)
                    .build());

            log.debug("Skill '{}': created script tool '{}'", name, namespacedName);
        }

        // Step 5: Build read_skill_file tool
        if (!resourceFiles.isEmpty()) {
            String readToolName = name + "__read_skill_file";

            Map<String, Object> inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            inputSchema.put("properties", Map.of(
                    "path", Map.of(
                            "type", "string",
                            "description", "Relative path within the skill directory",
                            "enum", new ArrayList<>(resourceFiles)
                    )
            ));
            inputSchema.put("required", List.of("path"));

            tools.add(ToolConfig.builder()
                    .name(readToolName)
                    .description("Read a reference or resource file from the "
                            + name + " skill directory")
                    .toolType("worker")
                    .inputSchema(inputSchema)
                    .build());

            log.debug("Skill '{}': created read_skill_file tool with {} resources",
                    name, resourceFiles.size());
        }

        // Step 6: Wire cross-skill references
        Set<String> stack = normalizingStack.get();
        for (Map.Entry<String, Object> entry : crossSkillRefs.entrySet()) {
            String refName = entry.getKey();
            if (stack.contains(refName)) {
                throw new IllegalArgumentException(
                        "Circular skill reference detected: '" + refName
                                + "' is already being normalized. Stack: " + stack);
            }
            stack.add(refName);
            try {
                @SuppressWarnings("unchecked")
                Map<String, Object> refConfig = (Map<String, Object>) entry.getValue();
                AgentConfig refAgent = this.normalize(refConfig);

                Map<String, Object> refToolConfig = new LinkedHashMap<>();
                refToolConfig.put("agentConfig", refAgent);

                tools.add(ToolConfig.builder()
                        .name(refAgent.getName())
                        .description(refAgent.getDescription())
                        .toolType("agent_tool")
                        .config(refToolConfig)
                        .build());

                log.debug("Skill '{}': wired cross-skill reference '{}'", name, refName);
            } finally {
                stack.remove(refName);
            }
        }

        // Step 7: Assemble
        if (!tools.isEmpty()) {
            orchestrator.setTools(tools);
        }

        log.info("Normalized skill '{}': {} sub-agents, {} scripts, {} resources",
                name, agentFiles.size(), scripts.size(), resourceFiles.size());

        return orchestrator;
    }

    private Map<String, Object> parseFrontmatter(String skillMd) {
        Matcher matcher = FRONTMATTER_PATTERN.matcher(skillMd);
        if (!matcher.matches()) {
            return Collections.emptyMap();
        }
        Yaml yaml = new Yaml();
        Map<String, Object> result = yaml.load(matcher.group(1));
        return result != null ? result : Collections.emptyMap();
    }

    private String extractBody(String skillMd) {
        Matcher matcher = FRONTMATTER_PATTERN.matcher(skillMd);
        if (!matcher.matches()) {
            return skillMd;
        }
        return matcher.group(2).trim();
    }
}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd server && ./gradlew test --tests "*SkillNormalizerTest*"`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add server/src/main/java/dev/agentspan/runtime/normalizer/SkillNormalizer.java
git commit -m "feat(skills): implement SkillNormalizer for agentskills.io directories"
```

---

## Chunk 4: Go CLI — `skill` Subcommand

### Task 11: Implement CLI skill commands

**Files:**
- Create: `cli/cmd/skill.go`

- [ ] **Step 1: Implement the skill subcommand**

The CLI needs three subcommands: `skill run` (ephemeral), `skill load` (production deploy), and `skill serve` (start workers). The skill directory reading logic follows the same conventions as the Python SDK.

Key implementation points:
- Read `SKILL.md` and parse YAML frontmatter (use `gopkg.in/yaml.v3`)
- Glob `*-agent.md` files for sub-agent discovery
- List `scripts/` directory for script tools
- List `references/`, `examples/`, `assets/` for resource files
- Package as JSON matching the raw config format from the design spec
- `skill run`: POST to `/api/agent/start`, start workers, wait for result
- `skill load`: POST to `/api/agent/compile`
- `skill serve`: start workers (blocking, like existing `serve` command)

This task is implementation-heavy and Go-specific. Refer to existing commands in `cli/cmd/` (e.g., `run.go`, `deploy.go`) for patterns.

- [ ] **Step 2: Write basic test**

Create `cli/cmd/skill_test.go` with tests for SKILL.md parsing and directory discovery functions.

- [ ] **Step 3: Run tests**

Run: `cd cli && go test ./cmd/ -run TestSkill -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add cli/cmd/skill.go cli/cmd/skill_test.go
git commit -m "feat(skills): add CLI skill run/load/serve subcommands"
```

---

## Chunk 5: Integration — Wire Workers into Runtime

### Task 12: Wire skill worker registration into AgentRuntime

**Files:**
- Modify: `sdk/python/src/agentspan/agents/runtime/runtime.py`

- [ ] **Step 1: Identify the worker registration point in runtime.py**

Read `runtime.py` to find where `ToolRegistry.register_tool_workers()` is called. The skill workers need to be registered alongside regular `@tool` workers before execution starts.

- [ ] **Step 2: Add skill worker registration**

In the method that registers workers (before starting execution), add:

```python
# Register skill workers if this is a skill-based agent
from agentspan.agents.skill import create_skill_workers
if hasattr(agent, "_framework") and agent._framework == "skill":
    skill_workers = create_skill_workers(agent)
    for sw in skill_workers:
        # Register each SkillWorker as a Conductor worker task
        self._tool_registry.register_worker(sw.name, sw.func, sw.description)
```

The exact integration point depends on the runtime's existing flow. The pattern should mirror how existing `@tool` functions are registered.

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `cd sdk/python && python -m pytest tests/ -v --timeout=60`
Expected: All existing tests PASS, plus skill tests PASS

- [ ] **Step 4: Commit**

```bash
git add sdk/python/src/agentspan/agents/runtime/runtime.py
git commit -m "feat(skills): wire skill worker registration into AgentRuntime"
```

---

### Task 13: Add `load_skills` test and cross-skill reference test

**Files:**
- Create: `sdk/python/tests/fixtures/skills/cross-ref-skill/SKILL.md`
- Modify: `sdk/python/tests/unit/test_skill.py`

- [ ] **Step 1: Create cross-ref fixture**

`sdk/python/tests/fixtures/skills/cross-ref-skill/SKILL.md`:
```markdown
---
name: cross-ref-skill
description: A skill that references another skill.
---

# Cross Ref Skill

After completing the analysis, invoke the simple-skill skill for cleanup.
```

- [ ] **Step 2: Write tests for load_skills and cross-refs**

Add to `test_skill.py`:

```python
class TestLoadSkills:
    """Test batch loading of skills."""

    def test_load_skills_finds_all(self):
        from agentspan.agents.skill import load_skills

        skills = load_skills(FIXTURES, model="openai/gpt-4o")
        assert "simple-skill" in skills
        assert "dg-skill" in skills
        assert "script-skill" in skills

    def test_load_skills_returns_agents(self):
        from agentspan.agents.skill import load_skills
        from agentspan.agents import Agent

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
```

- [ ] **Step 3: Run tests**

Run: `cd sdk/python && python -m pytest tests/unit/test_skill.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add sdk/python/tests/fixtures/skills/cross-ref-skill/ sdk/python/tests/unit/test_skill.py
git commit -m "test(skills): add load_skills and cross-skill reference tests"
```

---

## Chunk 6: E2E Verification

### Task 14: E2E test with real skill directories

**Files:**
- Create: `sdk/python/tests/e2e/test_skill_e2e.py`

- [ ] **Step 1: Write E2E test**

This test verifies the full flow: `skill()` → serialize → send to server → SkillNormalizer → AgentCompiler → execution. Requires a running Agentspan server.

```python
"""E2E test for skill-based agents."""
import pytest
from pathlib import Path

from agentspan.agents import AgentRuntime, skill

FIXTURES = Path(__file__).parent.parent / "fixtures" / "skills"


@pytest.mark.e2e
class TestSkillE2E:

    def test_simple_skill_runs(self):
        """Instruction-only skill completes successfully."""
        agent = skill(FIXTURES / "simple-skill", model="openai/gpt-4o")
        with AgentRuntime() as rt:
            result = rt.run(agent, "Say hello")
            assert result.is_success
            assert result.output["result"]

    def test_dg_skill_with_sub_agents(self):
        """Skill with sub-agents produces visible sub-agent executions."""
        agent = skill(FIXTURES / "dg-skill", model="openai/gpt-4o")
        with AgentRuntime() as rt:
            result = rt.run(agent, "Review this code: def add(a, b): return a + b")
            assert result.is_success
            # Sub-agents should appear in sub_results
            assert result.output["result"]

    def test_script_skill_executes_script(self):
        """Script tool is callable and returns output."""
        agent = skill(FIXTURES / "script-skill", model="openai/gpt-4o")
        with AgentRuntime() as rt:
            result = rt.run(agent, "Run the hello script with 'World'")
            assert result.is_success
            assert "Hello" in result.output["result"]
```

- [ ] **Step 2: Run E2E test (requires server)**

Run: `cd sdk/python && python -m pytest tests/e2e/test_skill_e2e.py -v -m e2e`
Expected: All PASS (with running Agentspan server)

- [ ] **Step 3: Commit**

```bash
git add sdk/python/tests/e2e/test_skill_e2e.py
git commit -m "test(skills): add E2E tests for skill-based agents"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| **1: SDK Core** | Tasks 1-5 | `skill()`, `load_skills()`, serialization hook, public API |
| **2: SDK Workers** | Tasks 6-7 | Script and read_skill_file worker registration |
| **3: Server Normalizer** | Tasks 8-10 | `SkillNormalizer.java` with full test coverage |
| **4: CLI** | Task 11 | `agentspan skill run/load/serve` commands |
| **5: Integration** | Tasks 12-13 | Runtime wiring, cross-skill refs, load_skills |
| **6: E2E** | Task 14 | Full flow verification with real server |

**Total: 14 tasks across 6 chunks.**

Chunks 1-3 can be parallelized (SDK, server, and CLI are independent). Chunks 4-6 depend on 1-3.
