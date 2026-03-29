# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ML Engineering Pipeline — agent definitions.

Architecture:
    ml_pipeline (sequential)
      1. data_analyst        — Analyze dataset, recommend approaches
      2. model_exploration   — (parallel) 3 model strategies concurrently
      3. evaluator           — Compare and select best model
      4. refinement rounds   — optimizer → validator × 2 rounds
      5. reporter            — Final summary report
"""

import os

MODEL = os.environ.get("AGENT_LLM_MODEL", "openai/gpt-4o-mini")


# ── Phase 1: Data Analysis ────────────────────────────────────────

from agentspan.agents import Agent

data_analyst = Agent(
    name="data_analyst",
    model=MODEL,
    instructions=(
        "You are a data scientist performing exploratory data analysis. "
        "Given a dataset description, analyze it and provide:\n"
        "1. Key features and their likely importance\n"
        "2. Data quality considerations (missing values, outliers, scaling)\n"
        "3. Recommended preprocessing steps\n"
        "4. Which model families are most promising and why\n\n"
        "Be concise and structured. Output a numbered analysis."
    ),
)


# ── Phase 2: Parallel Model Strategy Exploration ──────────────────

linear_modeler = Agent(
    name="linear_modeler",
    model=MODEL,
    instructions=(
        "You are a machine learning engineer specializing in linear models. "
        "Based on the data analysis, propose a linear modeling approach:\n"
        "- Model choice (e.g., Ridge, Lasso, ElasticNet)\n"
        "- Feature engineering strategy\n"
        "- Expected strengths and weaknesses\n"
        "Keep it to 4-5 bullet points."
    ),
)

tree_modeler = Agent(
    name="tree_modeler",
    model=MODEL,
    instructions=(
        "You are a machine learning engineer specializing in tree-based models. "
        "Based on the data analysis, propose a tree-based approach:\n"
        "- Model choice (e.g., XGBoost, LightGBM, CatBoost)\n"
        "- Key hyperparameters to tune\n"
        "- Expected strengths and weaknesses\n"
        "Keep it to 4-5 bullet points."
    ),
)

nn_modeler = Agent(
    name="nn_modeler",
    model=MODEL,
    instructions=(
        "You are a machine learning engineer specializing in neural networks. "
        "Based on the data analysis, propose a neural network approach:\n"
        "- Architecture choice (e.g., MLP, TabNet)\n"
        "- Training considerations\n"
        "- Expected strengths and weaknesses\n"
        "Keep it to 4-5 bullet points."
    ),
)

model_exploration = Agent(
    name="model_exploration",
    model=MODEL,
    agents=[linear_modeler, tree_modeler, nn_modeler],
    strategy="parallel",
)


# ── Phase 3: Evaluation & Selection ──────────────────────────────

evaluator = Agent(
    name="evaluator",
    model=MODEL,
    instructions=(
        "You are a senior ML engineer evaluating model proposals. "
        "Review the three approaches and:\n"
        "1. Compare expected performance\n"
        "2. Consider cost, interpretability, maintenance\n"
        "3. Select the BEST approach with justification\n"
        "4. Identify top 3 hyperparameters to tune\n\n"
        "Output: 'Selected model: [name]' followed by reasoning."
    ),
)


# ── Phase 4: Iterative Refinement ─────────────────────────────────

optimizer_1 = Agent(
    name="optimizer_r1",
    model=MODEL,
    instructions=(
        "You are a hyperparameter optimization specialist. "
        "Suggest specific hyperparameter values with rationale."
    ),
)

validator_1 = Agent(
    name="validator_r1",
    model=MODEL,
    instructions=(
        "You are a model validation expert. "
        "Review the optimizer's suggestions and provide actionable feedback."
    ),
)

optimizer_2 = Agent(
    name="optimizer_r2",
    model=MODEL,
    instructions=(
        "You are a hyperparameter specialist. "
        "Refine values based on validator feedback."
    ),
)

validator_2 = Agent(
    name="validator_r2",
    model=MODEL,
    instructions=(
        "You are a validation expert. "
        "Give a final recommendation: ready for deployment or needs more tuning."
    ),
)

refinement_loop = optimizer_1 >> validator_1 >> optimizer_2 >> validator_2


# ── Phase 5: Final Report ────────────────────────────────────────

reporter = Agent(
    name="reporter",
    model=MODEL,
    instructions=(
        "You are a technical writer. Write a concise ML pipeline report:\n"
        "- Dataset, Selected Model, Key Hyperparameters\n"
        "- Expected Performance, Next Steps\n"
        "Keep under 200 words."
    ),
)


# ── Full Pipeline ─────────────────────────────────────────────────

ml_pipeline = data_analyst >> model_exploration >> evaluator >> refinement_loop >> reporter
