from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")


def _patch_runtime():
    """Monkey-patch AgentRuntime to bypass Conductor and run natively."""
    from agentspan.agents.frameworks.serializer import detect_framework
    from agentspan.agents.runtime.runtime import AgentRuntime
    from validation.native.openai_runner import run_openai_native, run_openai_native_async

    def _init_noop(self, **kwargs):
        pass

    def _run_native(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        if fw == "openai":
            return run_openai_native(agent, str(prompt))
        raise ValueError(f"Native mode unsupported for framework: {fw!r}")

    async def _run_native_async(self, agent, prompt="", **kwargs):
        fw = detect_framework(agent)
        if fw == "openai":
            return await run_openai_native_async(agent, str(prompt))
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

    # Execute the example script as __main__
    with open(script) as f:
        code = compile(f.read(), script, "exec")
    exec(code, {"__name__": "__main__", "__file__": script})


if __name__ == "__main__":
    main()
