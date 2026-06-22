"""Allow running the CLI as ``python -m agentspan ...``.

Mirrors the ``agentspan`` console script (entry point ``agentspan.cli:main``) so the
CLI is reachable even when the install's Scripts/bin directory is not on ``PATH`` —
a common situation on Windows. ``python -m agentspan doctor`` is then equivalent to
``agentspan doctor``.
"""
from agentspan.cli import main

if __name__ == "__main__":
    main()
