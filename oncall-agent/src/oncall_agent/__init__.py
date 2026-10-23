"""On-call triage agent for the Orkes SaaS platform.

Listens on the Slack health-check alert channel, reads the failing health_check
execution, runs READ-ONLY agent-handler commands to investigate, and replies in
the alert thread with a root-cause hypothesis. Advisory only (dry-run) — it never
takes remediating action.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
