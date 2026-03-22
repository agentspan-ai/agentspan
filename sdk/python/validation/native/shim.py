from __future__ import annotations

import os
import sys


def _patch_runtime():
    """Monkey-patch AgentRuntime to bypass Conductor and run natively."""
    from agentspan.agents.frameworks.serializer import detect_framework
    from agentspan.agents.runtime.runtime import AgentRuntime
    from validation.native.openai_runner import run_openai_native, run_openai_native_async
    from validation.native.langgraph_runner import run_langgraph_native, run_langchain_native

    def _init_noop(self, **kwargs):
        pass

    def _run_native(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        session_id = kwargs.get("session_id")
        if fw == "openai":
            return run_openai_native(agent, str(prompt))
        if fw == "langgraph":
            return run_langgraph_native(agent, str(prompt), session_id=session_id)
        if fw == "langchain":
            return run_langchain_native(agent, str(prompt), session_id=session_id)
        raise ValueError(f"Native mode unsupported for framework: {fw!r}")

    async def _run_native_async(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        session_id = kwargs.get("session_id")
        if fw == "openai":
            return await run_openai_native_async(agent, str(prompt))
        if fw in ("langgraph", "langchain"):
            # LangGraph/LangChain runners are sync — run in thread
            import asyncio
            runner = run_langgraph_native if fw == "langgraph" else run_langchain_native
            return await asyncio.to_thread(runner, agent, str(prompt), session_id=session_id)
        raise ValueError(f"Native mode unsupported for framework: {fw!r}")

    def _noop(self, *args, **kwargs):
        pass

    def _enter(self):
        return self

    def _exit(self, *args):
        pass

    AgentRuntime.__init__ = _init_noop
    AgentRuntime.run = _run_native
    AgentRuntime.run_async = _run_native_async
    AgentRuntime.start = _noop
    AgentRuntime.stream = _noop
    AgentRuntime.shutdown = _noop
    AgentRuntime.__enter__ = _enter
    AgentRuntime.__exit__ = _exit


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m validation.native.shim <example_script.py>", file=sys.stderr)
        sys.exit(1)

    script = sys.argv[1]

    # Add script's directory to sys.path so local imports (e.g. settings) work
    script_dir = os.path.dirname(os.path.abspath(script))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    _patch_runtime()

    # Execute the example script as __main__ using runpy for proper namespace handling
    # (exec() with a minimal dict breaks `from __future__ import annotations` + type hints)
    import runpy
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
