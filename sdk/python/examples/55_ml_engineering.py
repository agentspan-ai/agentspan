#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ML Engineering Pipeline — multi-agent ML workflow.

Builds a five-stage pipeline:
  1. Data analysis — analyze dataset, recommend approaches
  2. Model exploration — (parallel) linear, tree, neural network strategies
  3. Evaluation — compare and select best model
  4. Refinement — optimizer → validator × 2 rounds
  5. Report — final summary

Run:
    python 55_ml_engineering.py

Requirements:
    - Agentspan server running
    - OPENAI_API_KEY stored: agentspan credentials set --name OPENAI_API_KEY
"""

import os
from agentspan.agents import Agent, AgentRuntime

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")

# ── Phase 1: Data Analysis ────────────────────────────────────────

data_analyst = Agent(
    name="data_analyst",
    model=MODEL,
    instructions=(
        "Analyze the dataset. Provide: key features, data quality issues, "
        "preprocessing steps, and which model families to try."
    ),
)

# ── Phase 2: Parallel Model Exploration ───────────────────────────

model_exploration = Agent(
    name="model_exploration",
    model=MODEL,
    agents=[
        Agent(name="linear_modeler", model=MODEL,
              instructions="Propose a linear modeling approach (Ridge/Lasso/ElasticNet)."),
        Agent(name="tree_modeler", model=MODEL,
              instructions="Propose a tree-based approach (XGBoost/LightGBM)."),
        Agent(name="nn_modeler", model=MODEL,
              instructions="Propose a neural network approach (MLP/TabNet)."),
    ],
    strategy="parallel",
)

# ── Phase 3: Evaluation ──────────────────────────────────────────

evaluator = Agent(
    name="evaluator",
    model=MODEL,
    instructions=(
        "Compare the three approaches. Select the best. "
        "Output: 'Selected model: [name]' with justification."
    ),
)

# ── Phase 4: Iterative Refinement ─────────────────────────────────

refinement = (
    Agent(name="optimizer_r1", model=MODEL,
          instructions="Suggest hyperparameter values with rationale.")
    >> Agent(name="validator_r1", model=MODEL,
             instructions="Review suggestions. Provide actionable feedback.")
    >> Agent(name="optimizer_r2", model=MODEL,
             instructions="Refine based on feedback.")
    >> Agent(name="validator_r2", model=MODEL,
             instructions="Final recommendation: ready for deployment?")
)

# ── Phase 5: Report ──────────────────────────────────────────────

reporter = Agent(
    name="reporter",
    model=MODEL,
    instructions=(
        "Write a concise ML pipeline report: dataset, selected model, "
        "hyperparameters, expected performance, next steps. Under 200 words."
    ),
)

# ── Full Pipeline ─────────────────────────────────────────────────

ml_pipeline = data_analyst >> model_exploration >> evaluator >> refinement >> reporter

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(ml_pipeline, "Build a model for California housing prices...", timeout=120000)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(ml_pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.55_ml_engineering
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(ml_pipeline)
