# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Hierarchical Agents — multi-level agent delegation.

Demonstrates:
    - Hierarchical multi-agent architecture
    - A top-level coordinator delegates to team leads
    - Team leads delegate to specialist agents with tools
    - Deep nesting of sub_agents

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


# ── Level 3: Specialist tools ─────────────────────────────────────────

def check_api_health(service: str) -> dict:
    """Check the health status of an API service.

    Args:
        service: Service name to check.

    Returns:
        Dictionary with health status and metrics.
    """
    services = {
        "auth": {"status": "healthy", "latency_ms": 45, "uptime": "99.99%"},
        "payments": {"status": "degraded", "latency_ms": 350, "uptime": "99.5%"},
        "users": {"status": "healthy", "latency_ms": 28, "uptime": "99.98%"},
    }
    return services.get(service.lower(), {"status": "unknown", "message": f"Service '{service}' not found"})


def check_error_logs(service: str, hours: int = 1) -> dict:
    """Check recent error logs for a service.

    Args:
        service: Service name.
        hours: Number of hours to look back.

    Returns:
        Dictionary with error log summary.
    """
    logs = {
        "auth": {"errors": 2, "warnings": 5, "top_error": "Token validation timeout"},
        "payments": {"errors": 47, "warnings": 120, "top_error": "Gateway timeout on /charge"},
        "users": {"errors": 0, "warnings": 1, "top_error": "None"},
    }
    return {"service": service, "period_hours": hours, **logs.get(service.lower(), {"errors": -1})}


def run_security_scan(target: str) -> dict:
    """Run a security vulnerability scan.

    Args:
        target: Target service or endpoint to scan.

    Returns:
        Dictionary with scan results.
    """
    return {
        "target": target,
        "vulnerabilities": {
            "critical": 0,
            "high": 1,
            "medium": 3,
            "low": 7,
        },
        "top_finding": "Outdated TLS 1.1 still enabled on /legacy endpoint",
        "recommendation": "Disable TLS 1.1, enforce TLS 1.3",
    }


def check_performance_metrics(service: str) -> dict:
    """Get performance metrics for a service.

    Args:
        service: Service name.

    Returns:
        Dictionary with performance data.
    """
    metrics = {
        "auth": {"p50_ms": 22, "p95_ms": 89, "p99_ms": 145, "rps": 1200},
        "payments": {"p50_ms": 180, "p95_ms": 450, "p99_ms": 1200, "rps": 300},
        "users": {"p50_ms": 15, "p95_ms": 45, "p99_ms": 78, "rps": 800},
    }
    return {"service": service, **metrics.get(service.lower(), {"error": "No data"})}


# ── Level 2: Team lead agents ─────────────────────────────────────────

ops_agent = Agent(
    name="ops_specialist",
    model=settings.llm_model,
    description="Monitors service health and investigates operational issues.",
    instruction="Check service health and error logs. Identify issues and their severity.",
    tools=[check_api_health, check_error_logs],
)

security_agent = Agent(
    name="security_specialist",
    model=settings.llm_model,
    description="Runs security scans and identifies vulnerabilities.",
    instruction="Run security scans and report findings with recommendations.",
    tools=[run_security_scan],
)

performance_agent = Agent(
    name="performance_specialist",
    model=settings.llm_model,
    description="Analyzes performance metrics and identifies bottlenecks.",
    instruction="Check performance metrics and identify latency issues.",
    tools=[check_performance_metrics],
)

# ── Level 1: Team leads ───────────────────────────────────────────────

reliability_lead = Agent(
    name="reliability_team_lead",
    model=settings.llm_model,
    description="Leads the reliability team covering ops and performance.",
    instruction=(
        "You lead the reliability team. Coordinate the ops specialist "
        "and performance specialist to investigate service issues. "
        "Provide a consolidated reliability report."
    ),
    sub_agents=[ops_agent, performance_agent],
)

security_lead = Agent(
    name="security_team_lead",
    model=settings.llm_model,
    description="Leads the security team for vulnerability assessment.",
    instruction=(
        "You lead the security team. Use the security specialist to "
        "assess vulnerabilities. Provide risk assessment and remediation priorities."
    ),
    sub_agents=[security_agent],
)

# ── Top level: Platform coordinator ──────────────────────────────────

coordinator = Agent(
    name="platform_coordinator",
    model=settings.llm_model,
    instruction=(
        "You are the platform engineering coordinator. When asked to assess "
        "platform health:\n"
        "1. Have the reliability team check service health and performance\n"
        "2. Have the security team assess vulnerabilities\n"
        "3. Compile a comprehensive platform status report\n\n"
        "Prioritize critical issues and provide an executive summary."
    ),
    sub_agents=[reliability_lead, security_lead],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        coordinator,
        "Give me a full platform health assessment. Focus on the payments service "
        "which seems to be having issues.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coordinator)
        # CLI alternative:
        # agentspan deploy --package examples.adk.10_hierarchical_agents
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coordinator)
