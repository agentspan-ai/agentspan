"""
Harness: serialize one LangGraph example and output worker count as JSON.
Usage: python tests/_worker_harness.py <example-file-path>
"""
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sdk_root = Path(__file__).parent.parent
sys.path.insert(0, str(sdk_root / "src"))

example_path = sys.argv[1] if len(sys.argv) > 1 else None
if not example_path:
    print(json.dumps({"error": "no file path"}))
    sys.exit(1)

os.environ.setdefault("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-fake")
os.environ.setdefault("GOOGLE_API_KEY", "fake")

captured = [None]

# Import the real serializer
from agentspan.agents.frameworks.serializer import serialize_agent

class MockResult:
    def __init__(self):
        self.status = "COMPLETED"
        self.output = {}
        self.messages = []
        self.tool_calls = []
    def print_result(self):
        pass

class MockRuntime:
    def __init__(self, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def run(self, agent, prompt="", **kwargs):
        try:
            captured[0] = serialize_agent(agent)
        except Exception:
            pass
        return MockResult()
    async def run_async(self, agent, prompt="", **kwargs):
        return self.run(agent, prompt, **kwargs)
    def plan(self, agent, **kwargs):
        try:
            captured[0] = serialize_agent(agent)
        except Exception:
            pass
        return MagicMock()
    def shutdown(self):
        pass
    def serve(self, *agents, **kwargs):
        for a in agents:
            try:
                captured[0] = serialize_agent(a)
            except Exception:
                pass

# Patch all import paths for AgentRuntime
with patch("agentspan.agents.runtime.runtime.AgentRuntime", MockRuntime), \
     patch("agentspan.agents.run._get_default_runtime", lambda: MockRuntime()), \
     patch("agentspan.agents.AgentRuntime", MockRuntime):

    module_name = Path(example_path).stem
    spec = importlib.util.spec_from_file_location(module_name, example_path)
    if spec and spec.loader:
        # Suppress stdout
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            module = importlib.util.module_from_spec(spec)
            module.__name__ = module_name
            spec.loader.exec_module(module)
        except (SystemExit, Exception):
            pass
        finally:
            sys.stdout.close()
            sys.stdout = old_stdout

        # If not captured via run(), try module-level graph
        if captured[0] is None:
            for attr_name in ("graph", "app", "agent", "workflow"):
                obj = getattr(module, attr_name, None)
                if obj is not None and not isinstance(obj, (str, int, float, bool)):
                    try:
                        captured[0] = serialize_agent(obj)
                    except Exception:
                        pass
                    if captured[0] is not None:
                        break

if captured[0] is not None:
    raw_config, workers = captured[0]
    graph_cfg = raw_config.get("_graph", {}) if isinstance(raw_config, dict) else {}
    nodes = graph_cfg.get("nodes", []) if isinstance(graph_cfg, dict) else []
    worker_names = []
    for w in workers:
        if isinstance(w, dict):
            worker_names.append(w.get("name", str(w)))
        elif hasattr(w, "name"):
            worker_names.append(w.name)
        else:
            worker_names.append(str(w))
    print(json.dumps({
        "workers": len(workers),
        "hasGraph": bool(graph_cfg),
        "workerNames": worker_names,
        "graphNodes": len(nodes) if isinstance(nodes, list) else 0,
    }))
else:
    print(json.dumps({"workers": 0, "hasGraph": False, "workerNames": [], "error": "no serialization"}))
