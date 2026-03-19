# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Prompt Templates — using ChatPromptTemplate for structured agent prompts.

Demonstrates:
    - Building a ChatPromptTemplate with system + human messages
    - Using PromptTemplate for tool descriptions
    - Passing a custom system prompt to create_agent via state_modifier
    - Practical use case: persona-based agent with a specialized domain prompt

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ── System prompt template ────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """You are {persona_name}, an expert {domain} consultant.
Your communication style is {style}.
Always structure your responses with:
1. A brief direct answer
2. Key supporting details
3. A practical next step

Current date context: 2025
"""

system_prompt = PromptTemplate(
    input_variables=["persona_name", "domain", "style"],
    template=SYSTEM_TEMPLATE,
)

# Fill the template for a specific persona
filled_system = system_prompt.format(
    persona_name="Dr. Data",
    domain="data engineering",
    style="concise and technical",
)


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def explain_concept(concept: str) -> str:
    """Provide a technical explanation of a data engineering concept."""
    explanations = {
        "etl": "Extract, Transform, Load — a pipeline that pulls data from sources, transforms it, and loads into a target.",
        "data lake": "A centralized repository storing raw data at any scale in its native format.",
        "data warehouse": "A structured analytical database optimized for querying and reporting (e.g., BigQuery, Redshift).",
        "streaming": "Real-time data processing as events occur, using tools like Kafka, Flink, or Spark Streaming.",
        "dbt": "Data Build Tool — SQL-based transformation framework for analytics engineering.",
        "airflow": "Apache Airflow — workflow orchestration platform for scheduling and monitoring data pipelines.",
    }
    key = concept.lower().strip()
    return explanations.get(key, f"Concept '{concept}' is a data engineering term. Please consult official docs for details.")


@tool
def recommend_tool(use_case: str) -> str:
    """Recommend a data engineering tool for a given use case."""
    recommendations = {
        "batch processing": "Apache Spark or dbt for large-scale batch transformations.",
        "stream processing": "Apache Kafka + Flink or AWS Kinesis for real-time streaming.",
        "orchestration": "Apache Airflow, Prefect, or Dagster for workflow scheduling.",
        "storage": "Snowflake or BigQuery for warehousing; S3 or GCS for data lake storage.",
        "transformation": "dbt (SQL) or Spark (Python) for data transformations.",
    }
    key = use_case.lower().strip()
    for k, v in recommendations.items():
        if k in key or key in k:
            return v
    return f"For '{use_case}', consider evaluating Apache Spark, dbt, or Airflow based on your scale requirements."


# ── Agent with custom system prompt ──────────────────────────────────────────

graph = create_agent(
    llm,
    tools=[explain_concept, recommend_tool],
    name="prompt_template_agent",
    system_prompt=filled_system,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What tool should I use for batch processing, and can you explain ETL?",
        )
        print(f"Status: {result.status}")
        result.print_result()
