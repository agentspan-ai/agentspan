# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Output Key — state management via output_key.

Demonstrates:
    - Using output_key to store agent responses in session state
    - Multiple agents that pass data through shared state
    - Instruction templating with {variable} syntax for state injection

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def analyze_data(dataset: str) -> dict:
    """Analyze a dataset and return key statistics.

    Args:
        dataset: Name of the dataset to analyze.

    Returns:
        Dictionary with analysis results.
    """
    datasets = {
        "sales_q4": {
            "total_revenue": "$2.3M",
            "growth_rate": "12%",
            "top_product": "Widget Pro",
            "avg_order_value": "$156",
        },
        "user_engagement": {
            "daily_active_users": "45,000",
            "avg_session_duration": "8.5 min",
            "retention_rate": "72%",
            "churn_rate": "5.2%",
        },
    }
    return datasets.get(dataset.lower(), {"error": f"Dataset '{dataset}' not found"})


def generate_chart_description(metric: str, value: str) -> dict:
    """Generate a description for a chart visualization.

    Args:
        metric: The metric being visualized.
        value: The current value of the metric.

    Returns:
        Dictionary with chart configuration.
    """
    return {
        "chart_type": "bar" if "%" not in value else "gauge",
        "metric": metric,
        "value": value,
        "recommendation": f"Track {metric} weekly for trend analysis.",
    }


# Analyst agent — stores its findings in state via output_key
analyst = Agent(
    name="data_analyst",
    model=settings.llm_model,
    instruction=(
        "You are a data analyst. Use the analyze_data tool to examine datasets. "
        "Provide a clear summary of the key findings."
    ),
    tools=[analyze_data],
    output_key="analysis_results",
)

# Visualizer agent — reads from state
visualizer = Agent(
    name="chart_designer",
    model=settings.llm_model,
    instruction=(
        "You are a data visualization expert. Based on the analysis results, "
        "suggest appropriate visualizations. Use the generate_chart_description "
        "tool for each key metric."
    ),
    tools=[generate_chart_description],
)

# Coordinator delegates to both
coordinator = Agent(
    name="report_coordinator",
    model=settings.llm_model,
    instruction=(
        "You are a report coordinator. First, have the data analyst examine "
        "the requested dataset. Then, have the chart designer suggest "
        "visualizations. Provide a final executive summary."
    ),
    sub_agents=[analyst, visualizer],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        coordinator,
        "Create a report on the sales_q4 dataset with visualization recommendations.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coordinator)
        # CLI alternative:
        # agentspan deploy --package examples.adk.07_output_key_state
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coordinator)
