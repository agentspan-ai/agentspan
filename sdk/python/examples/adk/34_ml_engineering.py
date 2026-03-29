# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK ML Engineering Pipeline — multi-agent ML workflow.

Mirrors the pattern from google/adk-samples/machine-learning-engineering (MLE-STAR).
Demonstrates:
    - SequentialAgent pipeline with distinct ML phases
    - ParallelAgent for concurrent model strategy exploration
    - LoopAgent for iterative refinement (ablation-style)
    - output_key for state passing between pipeline stages

Architecture:
    ml_pipeline (SequentialAgent)
      sub_agents:
        1. data_analyst       — Analyze dataset, identify features, recommend approaches
        2. parallel_modeling   — (ParallelAgent) Explore 3 model strategies concurrently
           - linear_modeler   — Linear/regularized model approach
           - tree_modeler     — Tree-based ensemble approach
           - nn_modeler       — Neural network approach
        3. evaluator          — Compare approaches, select best candidate
        4. refinement_loop    — (LoopAgent) Iterative hyperparameter optimization
           - write_refine     — (SequentialAgent)
             - optimizer      — Suggest improvements
             - validator      — Check if improvements are meaningful
        5. reporter           — Generate final summary report

Requirements:
    - pip install google-adk
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings


# ── Phase 1: Data Analysis ────────────────────────────────────────

data_analyst = Agent(
    name="data_analyst",
    model=settings.llm_model,
    instruction=(
        "You are a data scientist performing exploratory data analysis. "
        "Given a dataset description, analyze it and provide:\n"
        "1. Key features and their likely importance\n"
        "2. Data quality considerations (missing values, outliers, scaling)\n"
        "3. Recommended preprocessing steps\n"
        "4. Which model families are most promising and why\n\n"
        "Be concise and structured. Output a numbered analysis."
    ),
    output_key="data_analysis",
)


# ── Phase 2: Parallel Model Strategy Exploration ──────────────────

linear_modeler = Agent(
    name="linear_modeler",
    model=settings.llm_model,
    instruction=(
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
    name="tree_modeler",
    model=settings.llm_model,
    instruction=(
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
    name="nn_modeler",
    model=settings.llm_model,
    instruction=(
        "You are a machine learning engineer specializing in neural networks. "
        "Based on the data analysis in the conversation, propose a neural network approach:\n"
        "- Architecture choice (e.g., MLP, TabNet, FT-Transformer)\n"
        "- Input preprocessing and embedding strategy\n"
        "- Training considerations (learning rate, batch size, regularization)\n"
        "- Expected strengths and weaknesses\n"
        "Keep it to 4-5 bullet points."
    ),
)

parallel_modeling = ParallelAgent(
    name="model_exploration",
    sub_agents=[linear_modeler, tree_modeler, nn_modeler],
)


# ── Phase 3: Evaluation & Selection ──────────────────────────────

evaluator = Agent(
    name="evaluator",
    model=settings.llm_model,
    instruction=(
        "You are a senior ML engineer evaluating model proposals. "
        "Review the three modeling approaches (linear, tree-based, neural network) "
        "from the conversation and:\n"
        "1. Compare their expected performance on this specific dataset\n"
        "2. Consider training cost, interpretability, and maintenance\n"
        "3. Select the BEST approach with a clear justification\n"
        "4. Identify the top 3 hyperparameters to tune for the selected model\n\n"
        "Output your selection clearly as: 'Selected model: [name]' followed by reasoning."
    ),
    output_key="model_selection",
)


# ── Phase 4: Iterative Refinement (LoopAgent) ────────────────────

optimizer = Agent(
    name="optimizer",
    model=settings.llm_model,
    instruction=(
        "You are a hyperparameter optimization specialist. Based on the selected "
        "model and any previous optimization feedback in the conversation:\n"
        "1. Suggest specific hyperparameter values to try\n"
        "2. Explain the rationale (e.g., reduce overfitting, increase capacity)\n"
        "3. Predict the expected improvement\n\n"
        "If this is a subsequent iteration, refine based on the validator's feedback."
    ),
)

validator = Agent(
    name="validator",
    model=settings.llm_model,
    instruction=(
        "You are a model validation expert. Review the optimizer's suggestions:\n"
        "1. Are the hyperparameter choices reasonable?\n"
        "2. Is there risk of overfitting or underfitting?\n"
        "3. Suggest one additional tweak that could help\n\n"
        "Provide brief, actionable feedback."
    ),
)

refine_cycle = SequentialAgent(
    name="refine_cycle",
    sub_agents=[optimizer, validator],
)

refinement_loop = LoopAgent(
    name="refinement_loop",
    sub_agents=[refine_cycle],
    max_iterations=2,
)


# ── Phase 5: Final Report ────────────────────────────────────────

reporter = Agent(
    name="reporter",
    model=settings.llm_model,
    instruction=(
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

ml_pipeline = SequentialAgent(
    name="ml_pipeline",
    sub_agents=[
        data_analyst,
        parallel_modeling,
        evaluator,
        refinement_loop,
        reporter,
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.34_ml_engineering
        runtime.deploy(ml_pipeline)
        runtime.serve(ml_pipeline)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # ml_pipeline,
        # "Build a model to predict California housing prices. The dataset has 20,640 samples "
        # "with 8 features: MedInc, HouseAge, AveRooms, AveBedrms, Population, AveOccup, "
        # "Latitude, Longitude. Target: MedianHouseValue (continuous, in $100k units). "
        # "Metric: RMSE. Some features have skewed distributions.",
        # )
        # result.print_result()
