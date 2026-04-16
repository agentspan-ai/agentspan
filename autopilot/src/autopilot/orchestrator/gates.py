"""Validation gates for the Agentspan Claw creation pipeline.

Four gates run between creation steps to catch errors before deployment:

1. **Spec validation** — checks agent.yaml completeness and well-formedness.
2. **Code validation** — checks worker Python files compile and follow conventions.
3. **Integration validation** — checks all integration references resolve.
4. **Deploy validation** — dry-run load via the loader.

Each gate is a ``@tool``-decorated function returning ``'PASS'`` or
``'FAIL: <reasons>'``.  The ``run_all_gates`` helper runs all four in
sequence and returns a combined report.
"""

from __future__ import annotations

import ast
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import yaml

from agentspan.agents import tool

from autopilot.config import AutopilotConfig
from autopilot.registry import get_default_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

_VALID_TRIGGER_TYPES = {"cron", "daemon", "webhook"}

# Patterns flagged as security risks in generated worker code.
_SECURITY_PATTERNS = [
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\bsubprocess\.call\s*\("),
    re.compile(r"\bsubprocess\.Popen\s*\("),
    re.compile(r"\b__import__\s*\("),
]


def _get_config() -> AutopilotConfig:
    return AutopilotConfig.from_env()


def _agent_dir(agent_name: str, config: Optional[AutopilotConfig] = None) -> Path:
    if config is None:
        config = _get_config()
    return config.agents_dir / agent_name


def _load_agent_yaml(agent_name: str, config: Optional[AutopilotConfig] = None) -> dict:
    """Load and return the parsed agent.yaml dict for *agent_name*.

    Raises ``FileNotFoundError`` if the file does not exist and
    ``yaml.YAMLError`` if the YAML is invalid.
    """
    yaml_path = _agent_dir(agent_name, config) / "agent.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"agent.yaml not found for agent '{agent_name}' at {yaml_path}")
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"agent.yaml for '{agent_name}' is not a YAML mapping")
    return raw


# ---------------------------------------------------------------------------
# Gate 1 — Spec validation
# ---------------------------------------------------------------------------

@tool
def validate_spec(agent_name: str) -> str:
    """Validate an agent's specification is complete and well-formed.

    Checks: name, model, instructions, trigger type, cron schedule,
    tools references, credentials, and error_handling section.

    Returns 'PASS' or 'FAIL: <reasons>'.
    """
    try:
        raw = _load_agent_yaml(agent_name)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        return f"FAIL: {exc}"

    errors: List[str] = []

    # -- name --
    name = raw.get("name")
    if not name:
        errors.append("name is missing")
    elif not _NAME_RE.match(str(name)):
        errors.append(
            f"name '{name}' is invalid — must be alphanumeric with underscores/hyphens, "
            "starting with an alphanumeric character"
        )

    # -- model --
    if not raw.get("model"):
        errors.append("model is missing")

    # -- instructions --
    instructions = raw.get("instructions")
    if not instructions or (isinstance(instructions, str) and not instructions.strip()):
        errors.append("instructions are empty")

    # -- trigger --
    trigger = raw.get("trigger")
    if not isinstance(trigger, dict):
        errors.append("trigger section is missing or not a mapping")
    else:
        ttype = trigger.get("type")
        # Normalize common aliases the LLM uses
        _TRIGGER_ALIASES = {
            "scheduled": "cron",
            "schedule": "cron",
            "interval": "cron",
            "periodic": "cron",
            "always_on": "daemon",
            "continuous": "daemon",
            "event": "webhook",
            "file_watch": "daemon",
            "polling": "daemon",
        }
        if ttype in _TRIGGER_ALIASES:
            ttype = _TRIGGER_ALIASES[ttype]
        if ttype not in _VALID_TRIGGER_TYPES:
            errors.append(
                f"trigger type '{ttype}' is invalid — must be one of: "
                + ", ".join(sorted(_VALID_TRIGGER_TYPES))
            )
        if ttype == "cron" and not trigger.get("schedule"):
            errors.append("trigger type is 'cron' but no schedule expression provided")

    # -- tools --
    tools_list = raw.get("tools", [])
    if tools_list:
        registry = get_default_registry()
        known_integrations = set(registry.list_integrations())
        agent_workers_dir = _agent_dir(agent_name) / "workers"
        for ref in tools_list:
            if isinstance(ref, str) and ref.startswith("builtin:"):
                int_name = ref[len("builtin:"):]
                if int_name not in known_integrations:
                    errors.append(f"tool '{ref}' references unknown integration '{int_name}'")
            elif isinstance(ref, str):
                # Check if it's a known builtin integration (LLM often omits "builtin:" prefix)
                if ref in known_integrations:
                    pass  # It's a known integration, just missing the prefix — OK
                else:
                    # Check for individual tool names that belong to builtin integrations
                    is_known_tool = False
                    for int_name in known_integrations:
                        int_tools = registry.get_tools(int_name)
                        for t in int_tools:
                            if hasattr(t, "_tool_def") and t._tool_def.name == ref:
                                is_known_tool = True
                                break
                        if is_known_tool:
                            break
                    if not is_known_tool:
                        worker_file = agent_workers_dir / f"{ref}.py"
                        if not worker_file.exists():
                            errors.append(f"tool '{ref}' is not a known integration and no worker file exists")

    # -- credentials --
    # We only check that if tools need credentials, the credentials section
    # documents them.  The actual presence check is in validate_integrations.

    # -- error_handling --
    if "error_handling" not in raw:
        errors.append("error_handling section is missing")

    if errors:
        return "FAIL: " + "; ".join(errors)
    return "PASS"


# ---------------------------------------------------------------------------
# Gate 2 — Code validation
# ---------------------------------------------------------------------------

def _agent_has_only_builtin_tools(agent_name: str, config: Optional[AutopilotConfig] = None) -> bool:
    """Return True if all tool references in agent.yaml are builtin or known integrations."""
    try:
        raw = _load_agent_yaml(agent_name, config)
    except Exception:
        return False
    tools_list = raw.get("tools", [])
    if not tools_list:
        return True
    registry = get_default_registry()
    known_integrations = set(registry.list_integrations())
    for ref in tools_list:
        if not isinstance(ref, str):
            return False
        if ref.startswith("builtin:"):
            continue
        # Check if the bare name is a known integration (LLM may omit "builtin:")
        if ref in known_integrations:
            continue
        # Check if it's a known tool name belonging to an integration
        is_known = False
        for int_name in known_integrations:
            int_tools = registry.get_tools(int_name)
            for t in int_tools:
                if hasattr(t, "_tool_def") and t._tool_def.name == ref:
                    is_known = True
                    break
            if is_known:
                break
        if not is_known:
            return False
    return True


@tool
def validate_code(agent_name: str) -> str:
    """Validate an agent's worker code compiles and follows conventions.

    Checks every .py file in workers/: valid Python syntax, at least one
    @tool decorated function, type hints on function signatures, and no
    obvious security issues (os.system, eval, exec).

    If the agent only uses builtin integrations (no custom workers),
    returns PASS with a note rather than failing on missing .py files.

    Returns 'PASS' or 'FAIL: <reasons>'.
    """
    workers_dir = _agent_dir(agent_name) / "workers"

    # Check if agent only uses builtin tools — no custom workers expected
    builtin_only = _agent_has_only_builtin_tools(agent_name)

    if not workers_dir.exists():
        if builtin_only:
            return "PASS: no custom workers to validate — agent uses only builtin integrations"
        return "FAIL: workers/ directory does not exist"

    py_files = sorted(workers_dir.glob("*.py"))
    if not py_files:
        if builtin_only:
            return "PASS: no custom workers to validate — agent uses only builtin integrations"
        return "FAIL: no .py files found in workers/"

    errors: List[str] = []

    for py_file in py_files:
        fname = py_file.name
        source = py_file.read_text()

        # -- Syntax check via ast.parse --
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            errors.append(f"{fname}: syntax error — {exc.msg} (line {exc.lineno})")
            continue  # can't check further if it doesn't parse

        # -- At least one @tool decorated function --
        has_tool = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    # Covers both @tool and @tool(...)
                    if isinstance(dec, ast.Name) and dec.id == "tool":
                        has_tool = True
                    elif isinstance(dec, ast.Call):
                        func = dec.func
                        if isinstance(func, ast.Name) and func.id == "tool":
                            has_tool = True
        if not has_tool:
            errors.append(f"{fname}: no @tool decorated function found")

        # -- Type hints on @tool function signatures --
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                is_tool_fn = False
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == "tool":
                        is_tool_fn = True
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "tool":
                        is_tool_fn = True
                if is_tool_fn:
                    for arg in node.args.args:
                        if arg.arg == "self":
                            continue
                        if arg.annotation is None:
                            errors.append(
                                f"{fname}: @tool function '{node.name}' — "
                                f"parameter '{arg.arg}' is missing a type hint"
                            )

        # -- Security checks --
        for pattern in _SECURITY_PATTERNS:
            for match in pattern.finditer(source):
                line_num = source[:match.start()].count("\n") + 1
                errors.append(
                    f"{fname}: security issue — '{match.group().strip()}' at line {line_num}"
                )

    if errors:
        return "FAIL: " + "; ".join(errors)
    return "PASS"


# ---------------------------------------------------------------------------
# Gate 3 — Integration validation
# ---------------------------------------------------------------------------

@tool
def validate_integrations(agent_name: str) -> str:
    """Validate an agent's integration requirements are satisfiable.

    Checks that every builtin: tool reference resolves in the registry and
    that each credential is documented (present in agent.yaml or environment).

    Returns 'PASS' or 'FAIL: <reasons>'.
    """
    try:
        raw = _load_agent_yaml(agent_name)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        return f"FAIL: {exc}"

    errors: List[str] = []

    # -- Check builtin tool references resolve --
    registry = get_default_registry()
    tools_list = raw.get("tools", [])
    for ref in tools_list:
        if isinstance(ref, str) and ref.startswith("builtin:"):
            int_name = ref[len("builtin:"):]
            resolved = registry.get_tools(int_name)
            if not resolved:
                errors.append(f"builtin integration '{int_name}' not found in registry")

    # -- Check credentials --
    credentials_needed = raw.get("credentials", [])
    present: List[str] = []
    missing: List[str] = []
    for cred in credentials_needed:
        if os.environ.get(cred):
            present.append(cred)
        else:
            missing.append(cred)

    if missing:
        errors.append(f"missing credentials: {', '.join(missing)}")

    if errors:
        return "FAIL: " + "; ".join(errors)
    return "PASS"


# ---------------------------------------------------------------------------
# Gate 4 — Deploy validation (dry-run)
# ---------------------------------------------------------------------------

@tool
def validate_deployment(agent_name: str) -> str:
    """Dry-run agent deployment -- attempt to load and verify.

    Calls loader.load_agent() on the agent directory. If it loads
    successfully the agent definition is valid. Reports any LoaderError
    with an actionable message.

    Returns 'PASS' or 'FAIL: <reasons>'.
    """
    from autopilot.loader import LoaderError, load_agent

    agent_dir = _agent_dir(agent_name)
    if not agent_dir.exists():
        return f"FAIL: agent directory not found at {agent_dir}"

    try:
        agent = load_agent(agent_dir)
    except LoaderError as exc:
        return f"FAIL: LoaderError — {exc}"
    except Exception as exc:
        return f"FAIL: unexpected error — {type(exc).__name__}: {exc}"

    # Sanity: the returned agent should have a name.
    if not getattr(agent, "name", None):
        return "FAIL: loader returned an agent with no name"

    return "PASS"


# ---------------------------------------------------------------------------
# Gate 5 — Worker execution validation
# ---------------------------------------------------------------------------

@tool
def validate_worker_execution(agent_name: str) -> str:
    """Test-run each worker in the agent's workers/ directory.

    For each .py file: installs dependencies if requirements.txt exists,
    imports the module, finds the @tool function, calls it with a simple
    test argument, and verifies it returns a string without raising.

    Returns 'PASS' or 'FAIL: <reasons>'.
    """
    workers_dir = _agent_dir(agent_name) / "workers"
    if not workers_dir.exists():
        return "PASS: no workers/ directory — nothing to test-run"

    py_files = sorted(workers_dir.glob("*.py"))
    if not py_files:
        return "PASS: no .py files in workers/ — nothing to test-run"

    errors: List[str] = []

    # Install dependencies first if requirements.txt exists
    req_file = workers_dir / "requirements.txt"
    if req_file.exists():
        deps = [l.strip() for l in req_file.read_text().splitlines() if l.strip()]
        if deps:
            try:
                import shutil
                uv_path = shutil.which("uv")
                if uv_path:
                    subprocess.run(
                        [uv_path, "pip", "install", "--quiet"] + deps,
                        capture_output=True, text=True, timeout=60, check=True,
                    )
                else:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--quiet"] + deps,
                        capture_output=True, text=True, timeout=60, check=True,
                    )
            except Exception as exc:
                errors.append(f"failed to install dependencies: {exc}")
                return "FAIL: " + "; ".join(errors)

    for py_file in py_files:
        fname = py_file.name

        # Build a subprocess script that imports the module, finds
        # the @tool function, calls it with a simple test arg, and
        # verifies the result is a string.
        test_script = f"""
import sys, importlib.util, json
spec = importlib.util.spec_from_file_location("worker", {str(py_file)!r})
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as e:
    print(json.dumps({{"error": f"import failed: {{e}}"}}))
    sys.exit(0)

# Find functions with _tool_def attribute (the @tool decorator sets this)
tool_fns = [
    getattr(mod, name)
    for name in dir(mod)
    if callable(getattr(mod, name)) and hasattr(getattr(mod, name), "_tool_def")
]

if not tool_fns:
    print(json.dumps({{"error": "no @tool function found"}}))
    sys.exit(0)

for fn in tool_fns:
    try:
        import inspect
        sig = inspect.signature(fn)
        # Build default args: empty string for str, 0 for int, etc.
        kwargs = {{}}
        for pname, param in sig.parameters.items():
            if param.default is not inspect.Parameter.empty:
                kwargs[pname] = param.default
            elif param.annotation is str or param.annotation == "str":
                kwargs[pname] = ""
            elif param.annotation is int or param.annotation == "int":
                kwargs[pname] = 0
            elif param.annotation is float or param.annotation == "float":
                kwargs[pname] = 0.0
            elif param.annotation is bool or param.annotation == "bool":
                kwargs[pname] = False
            else:
                kwargs[pname] = ""
        result = fn(**kwargs)
        if not isinstance(result, str):
            print(json.dumps({{"error": f"{{fn.__name__}} returned {{type(result).__name__}}, expected str"}}))
            sys.exit(0)
    except Exception as e:
        print(json.dumps({{"error": f"{{fn.__name__}} raised: {{e}}"}}))
        sys.exit(0)

print(json.dumps({{"ok": True}}))
"""
        try:
            proc = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            import json
            for line in proc.stdout.strip().splitlines():
                try:
                    data = json.loads(line)
                    if "error" in data:
                        errors.append(f"{fname}: {data['error']}")
                except json.JSONDecodeError:
                    pass
            if proc.returncode != 0 and not any(fname in e for e in errors):
                stderr = proc.stderr.strip()[-200:] if proc.stderr else "unknown error"
                errors.append(f"{fname}: subprocess failed (rc={proc.returncode}): {stderr}")
        except subprocess.TimeoutExpired:
            errors.append(f"{fname}: timed out after 10s")
        except Exception as exc:
            errors.append(f"{fname}: {exc}")

    if errors:
        return "FAIL: " + "; ".join(errors)
    return "PASS"


# ---------------------------------------------------------------------------
# Combined runner
# ---------------------------------------------------------------------------

def run_all_gates(agent_name: str) -> str:
    """Run all four validation gates and return a combined report.

    Returns a multi-line report with each gate's result and an overall
    verdict of PASS (all gates passed) or FAIL.
    """
    results = {
        "spec": validate_spec(agent_name),
        "code": validate_code(agent_name),
        "integrations": validate_integrations(agent_name),
        "worker_execution": validate_worker_execution(agent_name),
        "deployment": validate_deployment(agent_name),
    }

    lines: List[str] = [f"Validation report for agent '{agent_name}':", ""]
    all_pass = True
    for gate_name, result in results.items():
        status = "PASS" if result.startswith("PASS") else "FAIL"
        if status == "FAIL":
            all_pass = False
        lines.append(f"  [{status}] {gate_name}: {result}")

    lines.append("")
    lines.append(f"Overall: {'PASS' if all_pass else 'FAIL'}")
    return "\n".join(lines)
