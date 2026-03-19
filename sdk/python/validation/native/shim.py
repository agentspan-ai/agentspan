from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")


def _patch_runtime():
    """Monkey-patch AgentRuntime to bypass Conductor and run natively."""
    from agentspan.agents.frameworks.serializer import detect_framework
    from agentspan.agents.runtime.runtime import AgentRuntime
    from validation.native.adk_runner import (
        run_adk_native,
        run_adk_native_stream,
    )
    from validation.native.langgraph_runner import (
        run_langchain_native,
        run_langgraph_native,
    )
    from validation.native.openai_runner import (
        run_openai_native,
        run_openai_native_async,
        run_openai_native_stream,
    )

    def _init_noop(self, **kwargs):
        pass

    def _run_native(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        session_id = kwargs.get("session_id")
        if fw == "openai":
            return run_openai_native(agent, str(prompt))
        if fw == "google_adk":
            return run_adk_native(agent, str(prompt))
        if fw == "langgraph":
            return run_langgraph_native(agent, str(prompt), session_id=session_id)
        if fw == "langchain":
            return run_langchain_native(agent, str(prompt), session_id=session_id)
        raise ValueError(f"Native mode unsupported for framework: {fw!r}")

    async def _run_native_async(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        if fw == "openai":
            return await run_openai_native_async(agent, str(prompt))
        if fw == "langgraph":
            return run_langgraph_native(agent, str(prompt), session_id=kwargs.get("session_id"))
        if fw == "langchain":
            return run_langchain_native(agent, str(prompt), session_id=kwargs.get("session_id"))
        raise ValueError(f"Native mode unsupported for framework: {fw!r}")

    def _stream_native(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        if fw == "openai":
            return run_openai_native_stream(agent, str(prompt))
        if fw == "google_adk":
            return run_adk_native_stream(agent, str(prompt))
        raise ValueError(f"Native stream unsupported for framework: {fw!r}")

    def _noop(self, *args, **kwargs):
        pass

    def _enter(self):
        return self

    def _exit(self, *args):
        pass

    AgentRuntime.__init__ = _init_noop
    AgentRuntime.run = _run_native
    AgentRuntime.run_async = _run_native_async
    AgentRuntime.stream = _stream_native
    AgentRuntime.start = _noop
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

    # Execute the example script as __main__.
    # We exec directly into sys.modules["__main__"].__dict__ so that Pydantic
    # models defined in the example are registered in the real __main__ module.
    # Without this, TypeAdapter resolves forward references via
    # sys.modules["__main__"].__dict__ and fails to find sibling classes that
    # only exist in the exec namespace.
    with open(script) as f:
        code = compile(f.read(), script, "exec")
    main_ns = sys.modules["__main__"].__dict__
    main_ns["__file__"] = script
    exec(code, main_ns)


if __name__ == "__main__":
    main()
