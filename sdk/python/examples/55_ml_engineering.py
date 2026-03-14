# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ML Engineering Pipeline — multi-agent ML workflow.

Native SDK version of ADK example 34. Demonstrates:
    - Sequential pipeline (>>) with distinct ML phases
    - Parallel strategy for concurrent model exploration
    - Iterative refinement via sequential chaining (2 rounds)
    - State passing through conversation context between stages

Architecture:
    ml_pipeline (sequential)
      1. data_analyst        — Analyze dataset, recommend approaches
      2. model_exploration   — (parallel) 3 model strategies concurrently
      3. evaluator           — Compare and select best model
      4. refinement rounds   — optimizer → validator × 2 rounds
      5. reporter            — Final summary report

Requirements:
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime
from settings import settings


# ── Phase 1: Data Analysis ────────────────────────────────────────

data_analyst = Agent(
    name="data_analyst_55",
    model=settings.llm_model,
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
    name="linear_modeler_55",
    model=settings.llm_model,
    instructions=(
        "You are a machine learning engineer specializing in linear models. "
        "Based on the data analysis in the conversation, propose a linear modeling approach:\n"
        "- Model choice (e.g., Ridge, Lasso, ElasticNet, Logistic Regression)\n"
        "- Feature engineering strategy\n"
        "- Expected strengths and weaknesses\n"
        "- Estimated performance range\n"
        "Keep it to 4-5 bullet points."
    ),
)

tree_modeler = Agent(
    name="tree_modeler_55",
    model=settings.llm_model,
    instructions=(
        "You are a machine learning engineer specializing in tree-based models. "
        "Based on the data analysis in the conversation, propose a tree-based approach:\n"
        "- Model choice (e.g., Random Forest, XGBoost, LightGBM, CatBoost)\n"
        "- Feature engineering strategy\n"
        "- Key hyperparameters to tune\n"
        "- Expected strengths and weaknesses\n"
        "Keep it to 4-5 bullet points."
    ),
)

nn_modeler = Agent(
    name="nn_modeler_55",
    model=settings.llm_model,
    instructions=(
        "You are a machine learning engineer specializing in neural networks. "
        "Based on the data analysis in the conversation, propose a neural network approach:\n"
        "- Architecture choice (e.g., MLP, TabNet, FT-Transformer)\n"
        "- Input preprocessing and embedding strategy\n"
        "- Training considerations (learning rate, batch size, regularization)\n"
        "- Expected strengths and weaknesses\n"
        "Keep it to 4-5 bullet points."
    ),
)

model_exploration = Agent(
    name="model_exploration_55",
    model=settings.llm_model,
    agents=[linear_modeler, tree_modeler, nn_modeler],
    strategy="parallel",
)


# ── Phase 3: Evaluation & Selection ──────────────────────────────

evaluator = Agent(
    name="evaluator_55",
    model=settings.llm_model,
    instructions=(
        "You are a senior ML engineer evaluating model proposals. "
        "Review the three modeling approaches (linear, tree-based, neural network) "
        "from the conversation and:\n"
        "1. Compare their expected performance on this specific dataset\n"
        "2. Consider training cost, interpretability, and maintenance\n"
        "3. Select the BEST approach with a clear justification\n"
        "4. Identify the top 3 hyperparameters to tune for the selected model\n\n"
        "Output your selection clearly as: 'Selected model: [name]' followed by reasoning."
    ),
)


# ── Phase 4: Iterative Refinement (loop) ─────────────────────────

optimizer_1 = Agent(
    name="optimizer_r1_55",
    model=settings.llm_model,
    instructions=(
        "You are a hyperparameter optimization specialist. Based on the selected "
        "model from the conversation:\n"
        "1. Suggest specific hyperparameter values to try\n"
        "2. Explain the rationale (e.g., reduce overfitting, increase capacity)\n"
        "3. Predict the expected improvement"
    ),
)

validator_1 = Agent(
    name="validator_r1_55",
    model=settings.llm_model,
    instructions=(
        "You are a model validation expert. Review the optimizer's suggestions:\n"
        "1. Are the hyperparameter choices reasonable?\n"
        "2. Is there risk of overfitting or underfitting?\n"
        "3. Suggest one additional tweak that could help\n\n"
        "Provide brief, actionable feedback."
    ),
)

optimizer_2 = Agent(
    name="optimizer_r2_55",
    model=settings.llm_model,
    instructions=(
        "You are a hyperparameter optimization specialist. Based on the validator's "
        "feedback from the previous round:\n"
        "1. Refine the hyperparameter values\n"
        "2. Explain what changed and why\n"
        "3. Predict the expected improvement over the previous round"
    ),
)

validator_2 = Agent(
    name="validator_r2_55",
    model=settings.llm_model,
    instructions=(
        "You are a model validation expert. Review the second round of optimization:\n"
        "1. Are the refined hyperparameters an improvement?\n"
        "2. Is the model ready for deployment or does it need more tuning?\n"
        "3. Give a final recommendation.\n\n"
        "Provide brief, actionable feedback."
    ),
)

# Two rounds: optimizer → validator → optimizer → validator
refinement_loop = optimizer_1 >> validator_1 >> optimizer_2 >> validator_2


# ── Phase 5: Final Report ────────────────────────────────────────

reporter = Agent(
    name="reporter_55",
    model=settings.llm_model,
    instructions=(
        "You are a technical writer producing an ML project summary. "
        "Based on the entire conversation (data analysis, model exploration, "
        "evaluation, and refinement), write a concise final report:\n\n"
        "## ML Pipeline Report\n"
        "- **Dataset**: Brief description\n"
        "- **Selected Model**: Name and rationale\n"
        "- **Key Hyperparameters**: Final recommended values\n"
        "- **Expected Performance**: Estimated metrics\n"
        "- **Next Steps**: 2-3 recommendations for production deployment\n\n"
        "Keep the report under 200 words."
    ),
)


# ── Full Pipeline ─────────────────────────────────────────────────

ml_pipeline = data_analyst >> model_exploration >> evaluator >> refinement_loop >> reporter

with AgentRuntime() as runtime:
    result = runtime.run(
        ml_pipeline,
        "Build a model to predict California housing prices. The dataset has 20,640 samples "
        "with 8 features: MedInc, HouseAge, AveRooms, AveBedrms, Population, AveOccup, "
        "Latitude, Longitude. Target: MedianHouseValue (continuous, in $100k units). "
        "Metric: RMSE. Some features have skewed distributions.",
    )
    result.print_result()
