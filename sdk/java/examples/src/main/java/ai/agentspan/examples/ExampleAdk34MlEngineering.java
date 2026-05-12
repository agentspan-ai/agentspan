// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 34 — ML Engineering Pipeline
 *
 * <p>Java port of <code>sdk/python/examples/adk/34_ml_engineering.py</code>.
 *
 * <p>Demonstrates: a multi-agent ML workflow combining sequential, parallel,
 * and loop strategies. The Java port encodes the strategy semantics inline
 * (sub-agents with instructions describing parallel/loop intent) since the
 * {@link GoogleADKAgent} builder doesn't expose ParallelAgent/LoopAgent
 * primitives directly.
 */
public class ExampleAdk34MlEngineering {

    public static void main(String[] args) {
        // ── Phase 1: Data Analysis ────────────────────────────────────────
        Agent dataAnalyst = GoogleADKAgent.builder()
            .name("data_analyst")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data scientist performing exploratory data analysis. "
                + "Given a dataset description, analyze it and provide:\n"
                + "1. Key features and their likely importance\n"
                + "2. Data quality considerations (missing values, outliers, scaling)\n"
                + "3. Recommended preprocessing steps\n"
                + "4. Which model families are most promising and why\n\n"
                + "Be concise and structured. Output a numbered analysis.")
            .build();

        // ── Phase 2: Parallel Model Strategy Exploration ─────────────────
        Agent linearModeler = GoogleADKAgent.builder()
            .name("linear_modeler")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a machine learning engineer specializing in linear models. "
                + "Based on the data analysis in the conversation, propose a linear modeling approach:\n"
                + "- Model choice (e.g., Ridge, Lasso, ElasticNet, Logistic Regression)\n"
                + "- Feature engineering strategy\n"
                + "- Expected strengths and weaknesses\n"
                + "- Estimated performance range\n"
                + "Keep it to 4-5 bullet points.")
            .build();

        Agent treeModeler = GoogleADKAgent.builder()
            .name("tree_modeler")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a machine learning engineer specializing in tree-based models. "
                + "Based on the data analysis in the conversation, propose a tree-based approach:\n"
                + "- Model choice (e.g., Random Forest, XGBoost, LightGBM, CatBoost)\n"
                + "- Feature engineering strategy\n"
                + "- Key hyperparameters to tune\n"
                + "- Expected strengths and weaknesses\n"
                + "Keep it to 4-5 bullet points.")
            .build();

        Agent nnModeler = GoogleADKAgent.builder()
            .name("nn_modeler")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a machine learning engineer specializing in neural networks. "
                + "Based on the data analysis in the conversation, propose a neural network approach:\n"
                + "- Architecture choice (e.g., MLP, TabNet, FT-Transformer)\n"
                + "- Input preprocessing and embedding strategy\n"
                + "- Training considerations (learning rate, batch size, regularization)\n"
                + "- Expected strengths and weaknesses\n"
                + "Keep it to 4-5 bullet points.")
            .build();

        Agent parallelModeling = GoogleADKAgent.builder()
            .name("model_exploration")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate parallel model exploration. Dispatch the data analysis "
                + "to linear_modeler, tree_modeler, and nn_modeler concurrently and "
                + "aggregate their proposals.")
            .subAgents(linearModeler, treeModeler, nnModeler)
            .build();

        // ── Phase 3: Evaluation & Selection ──────────────────────────────
        Agent evaluator = GoogleADKAgent.builder()
            .name("evaluator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a senior ML engineer evaluating model proposals. "
                + "Review the three modeling approaches (linear, tree-based, neural network) "
                + "from the conversation and:\n"
                + "1. Compare their expected performance on this specific dataset\n"
                + "2. Consider training cost, interpretability, and maintenance\n"
                + "3. Select the BEST approach with a clear justification\n"
                + "4. Identify the top 3 hyperparameters to tune for the selected model\n\n"
                + "Output your selection clearly as: 'Selected model: [name]' followed by reasoning.")
            .build();

        // ── Phase 4: Iterative Refinement (LoopAgent intent) ─────────────
        Agent optimizer = GoogleADKAgent.builder()
            .name("optimizer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a hyperparameter optimization specialist. Based on the selected "
                + "model and any previous optimization feedback in the conversation:\n"
                + "1. Suggest specific hyperparameter values to try\n"
                + "2. Explain the rationale (e.g., reduce overfitting, increase capacity)\n"
                + "3. Predict the expected improvement\n\n"
                + "If this is a subsequent iteration, refine based on the validator's feedback.")
            .build();

        Agent validator = GoogleADKAgent.builder()
            .name("validator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a model validation expert. Review the optimizer's suggestions:\n"
                + "1. Are the hyperparameter choices reasonable?\n"
                + "2. Is there risk of overfitting or underfitting?\n"
                + "3. Suggest one additional tweak that could help\n\n"
                + "Provide brief, actionable feedback.")
            .build();

        Agent refinementLoop = GoogleADKAgent.builder()
            .name("refinement_loop")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate an iterative refinement loop. Run the cycle "
                + "[optimizer → validator] up to 2 times (max_iterations=2), "
                + "feeding the validator's feedback back to the optimizer.")
            .subAgents(optimizer, validator)
            .build();

        // ── Phase 5: Final Report ────────────────────────────────────────
        Agent reporter = GoogleADKAgent.builder()
            .name("reporter")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a technical writer producing an ML project summary. "
                + "Based on the entire conversation (data analysis, model exploration, "
                + "evaluation, and refinement), write a concise final report:\n\n"
                + "## ML Pipeline Report\n"
                + "- **Dataset**: Brief description\n"
                + "- **Selected Model**: Name and rationale\n"
                + "- **Key Hyperparameters**: Final recommended values\n"
                + "- **Expected Performance**: Estimated metrics\n"
                + "- **Next Steps**: 2-3 recommendations for production deployment\n\n"
                + "Keep the report under 200 words.")
            .build();

        // ── Full Pipeline ────────────────────────────────────────────────
        Agent mlPipeline = GoogleADKAgent.builder()
            .name("ml_pipeline")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate a full ML pipeline. Run the stages sequentially:\n"
                + "1. data_analyst — perform EDA\n"
                + "2. model_exploration — parallel proposals from 3 modelers\n"
                + "3. evaluator — pick the best approach\n"
                + "4. refinement_loop — iterative hyperparameter tuning (up to 2 cycles)\n"
                + "5. reporter — final summary report")
            .subAgents(dataAnalyst, parallelModeling, evaluator, refinementLoop, reporter)
            .build();

        AgentResult result = Agentspan.run(mlPipeline,
            "Build a model to predict California housing prices. The dataset has 20,640 samples "
            + "with 8 features: MedInc, HouseAge, AveRooms, AveBedrms, Population, AveOccup, "
            + "Latitude, Longitude. Target: MedianHouseValue (continuous, in $100k units). "
            + "Metric: RMSE. Some features have skewed distributions.");
        result.printResult();

        Agentspan.shutdown();
    }
}
