"""Agent Skills integration — load agentskills.io skill directories as Agents."""

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from agentspan.agents.agent import Agent


class SkillLoadError(Exception):
    """Raised when a skill directory cannot be loaded."""


def parse_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML frontmatter from SKILL.md content."""
    import yaml

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


SECTION_SPLIT_THRESHOLD = 50000  # characters (~15K tokens)


def slugify(text: str) -> str:
    """Slugify a heading: lowercase, spaces to hyphens, strip special chars."""
    slug = re.sub(r"[^a-z0-9\s-]", "", text.lower()).strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def split_into_sections(body: str) -> Dict[str, str]:
    """Split SKILL.md body into sections by ## headings.

    Returns:
        Ordered dict of slugified-section-name -> section content (heading + body).
    """
    sections: Dict[str, str] = {}
    parts = re.split(r"(?m)(?=^## )", body)
    for part in parts:
        trimmed = part.strip()
        if not trimmed.startswith("## "):
            continue  # skip preamble
        # Extract heading text (first line)
        first_line = trimmed.split("\n", 1)[0]
        heading_text = first_line[3:].strip()  # remove "## "
        slug = slugify(heading_text)
        if slug:
            sections[slug] = trimmed
    return sections


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


def format_skill_params(params: Dict[str, Any]) -> str:
    """Format skill parameters as a prompt prefix.

    Args:
        params: Key-value pairs to inject.

    Returns:
        Formatted string like ``[Skill Parameters]\\nkey: value\\n...``
        or empty string if params is empty.
    """
    if not params:
        return ""
    lines = [f"{k}: {v}" for k, v in params.items()]
    return "[Skill Parameters]\n" + "\n".join(lines)


def format_prompt_with_params(prompt: str, params: Dict[str, Any]) -> str:
    """Prepend skill parameters to the user prompt.

    Args:
        prompt: The original user prompt.
        params: Skill parameters to inject.

    Returns:
        The prompt with a ``[Skill Parameters]`` prefix followed by
        ``[User Request]``, or the original prompt when *params* is empty.
    """
    prefix = format_skill_params(params)
    if not prefix:
        return prompt
    return f"{prefix}\n\n[User Request]\n{prompt}"


def skill(
    path: Union[str, Path],
    model: Union[str, Any] = "",
    agent_models: Optional[Dict[str, str]] = None,
    search_path: Optional[List[str]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Agent:
    """Load an Agent Skills directory as an Agentspan Agent.

    Args:
        path: Path to skill directory containing SKILL.md.
        model: Model for the orchestrator agent. Also default for sub-agents.
        agent_models: Per-sub-agent model overrides.
        search_path: Additional directories to search for cross-skill references.
        params: Runtime parameter overrides. Merged on top of default
            ``params`` declared in the SKILL.md frontmatter.

    Returns:
        Agent that can be run, composed, deployed, and served.

    Raises:
        SkillLoadError: If the directory is not a valid skill.
    """
    path = Path(path).expanduser().resolve()

    # 1. Read SKILL.md (required)
    skill_md_path = path / "SKILL.md"
    if not skill_md_path.exists():
        raise SkillLoadError(
            f"Directory {path} is not a valid skill: SKILL.md not found"
        )
    skill_md = skill_md_path.read_text()
    frontmatter = parse_frontmatter(skill_md)
    name = frontmatter["name"]

    # 1b. Extract default params from frontmatter and merge overrides
    default_params: Dict[str, Any] = {}
    fm_params = frontmatter.get("params")
    if isinstance(fm_params, dict):
        for pname, pdef in fm_params.items():
            if isinstance(pdef, dict) and "default" in pdef:
                default_params[pname] = pdef["default"]
            else:
                # Bare value (e.g. params: {rounds: 3})
                default_params[pname] = pdef
    merged_params = {**default_params, **(params or {})}

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
                sorted(
                    str(f.relative_to(path)) for f in d.rglob("*") if f.is_file()
                )
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

    # 5b. Auto-split large SKILL.md bodies into sections
    body = extract_body(skill_md)
    skill_sections: Dict[str, str] = {}
    if len(body) > SECTION_SPLIT_THRESHOLD:
        skill_sections = split_into_sections(body)
        if skill_sections:
            # Add virtual section entries to resource_files
            for section_name in skill_sections:
                resource_files.append(f"skill_section:{section_name}")

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
        "defaultParams": default_params,
    }

    # 7. Return Agent with framework marker
    agent = Agent(name=name, model=model or "")
    agent._framework = "skill"
    agent._framework_config = raw_config
    agent._skill_path = path
    agent._skill_scripts = scripts
    agent._skill_sections = skill_sections
    agent._skill_params = merged_params
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
                ref_scripts: Dict[str, Dict[str, str]] = {}
                ref_scripts_dir = ref_dir / "scripts"
                if ref_scripts_dir.exists():
                    for f in sorted(ref_scripts_dir.iterdir()):
                        if f.is_file():
                            ref_scripts[f.stem] = {
                                "filename": f.name,
                                "language": detect_language(f),
                            }
                ref_resources: List[str] = []
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
    path = Path(path).expanduser().resolve()
    skills: Dict[str, Agent] = {}
    for d in sorted(path.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            overrides = (agent_models or {}).get(d.name, {})
            skills[d.name] = skill(d, model=model, agent_models=overrides)
    return skills


# ── Worker registration ─────────────────────────────────────────────


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
    skill_sections = getattr(agent, "_skill_sections", {})

    def make_read_func(
        sdir: Path, allowed: set, sections: Dict[str, str]
    ) -> Callable[..., str]:
        def read_skill_file(path: str = "") -> str:
            if path not in allowed:
                return f"ERROR: '{path}' not found. Available: {sorted(allowed)}"
            # Handle virtual skill_section:* paths
            if path.startswith("skill_section:"):
                section_name = path[len("skill_section:"):]
                if section_name in sections:
                    return sections[section_name]
                return f"ERROR: section '{section_name}' not found"
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
                func=make_read_func(skill_path, allowed_files, skill_sections),
            )
        )

    return workers
