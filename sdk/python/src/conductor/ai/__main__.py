"""Allow running the CLI as ``python -m conductor.ai ...``.

Mirrors the ``agentspan`` console script (entry point ``conductor.ai.cli:main``) so the
CLI is reachable even when the install's Scripts/bin directory is not on ``PATH`` —
a common situation on Windows. ``python -m conductor.ai doctor`` is then equivalent to
``agentspan doctor``.
"""
from conductor.ai.cli import main

if __name__ == "__main__":
    main()
