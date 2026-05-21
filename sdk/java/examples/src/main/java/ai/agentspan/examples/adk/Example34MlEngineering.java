// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 34 — ML Engineering Pipeline
 *
 * <p>Java port of <code>sdk/python/examples/adk/34_ml_engineering.py</code>.
 *
 * <p>Demonstrates: a multi-agent ML workflow combining sequential, parallel,
 * and loop strategies. The Java port encodes the strategy semantics inline
 * (sub-agents with instructions describing parallel/loop intent) since the
 * Agentspan {@link ai.agentspan.Agentspan#run(Object, String)} currently translates {@link LlmAgent}s with
 * sub-agents but does not extract {@code ParallelAgent}/{@code LoopAgent}
 * primitives directly.
 */
public class Example34MlEngineering {

    public static void main(String[] args) {
        // ── Phase 1: Data Analysis ────────────────────────────────────────
        LlmAgent dataAnalyst = LlmAgent.builder()
            .name("data_analyst")
            .description("Performs exploratory data analysis and recommends preprocessing steps.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a data scientist performing exploratory data analysis.
                Given a dataset description, analyze it and provide:
                1. Key features and their likely importance
                2. Data quality considerations (missing values, outliers, scaling)
                3. Recommended preprocessing steps
                4. Which model families are most promising and why

                Be concise and structured. Output a numbered analysis.
                """)
            .outputKey("data_analysis")
            .build();

        // ── Phase 2: Parallel Model Strategy Exploration ─────────────────
        LlmAgent linearModeler = LlmAgent.builder()
            .name("linear_modeler")
            .description("Proposes a linear-model approach (Ridge/Lasso/ElasticNet/Logistic).")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a machine learning engineer specializing in linear models.
                Based on the data analysis in the conversation, propose a linear modeling approach:
                - Model choice (e.g., Ridge, Lasso, ElasticNet, Logistic Regression)
                - Feature engineering strategy
                - Expected strengths and weaknesses
                - Estimated performance range
                Keep it to 4-5 bullet points.
                """)
            .build();

        LlmAgent treeModeler = LlmAgent.builder()
            .name("tree_modeler")
            .description("Proposes a tree-based approach (Random Forest, XGBoost, LightGBM, CatBoost).")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a machine learning engineer specializing in tree-based models.
                Based on the data analysis in the conversation, propose a tree-based approach:
                - Model choice (e.g., Random Forest, XGBoost, LightGBM, CatBoost)
                - Feature engineering strategy
                - Key hyperparameters to tune
                - Expected strengths and weaknesses
                Keep it to 4-5 bullet points.
                """)
            .build();

        LlmAgent nnModeler = LlmAgent.builder()
            .name("nn_modeler")
            .description("Proposes a neural-network approach (MLP, TabNet, FT-Transformer).")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a machine learning engineer specializing in neural networks.
                Based on the data analysis in the conversation, propose a neural network approach:
                - Architecture choice (e.g., MLP, TabNet, FT-Transformer)
                - Input preprocessing and embedding strategy
                - Training considerations (learning rate, batch size, regularization)
                - Expected strengths and weaknesses
                Keep it to 4-5 bullet points.
                """)
            .build();

        LlmAgent parallelModeling = LlmAgent.builder()
            .name("model_exploration")
            .description("Runs linear, tree, and neural-network modelers concurrently and aggregates proposals.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You orchestrate parallel model exploration. Dispatch the data analysis
                to linear_modeler, tree_modeler, and nn_modeler concurrently and
                aggregate their proposals.
                """)
            .subAgents(linearModeler, treeModeler, nnModeler)
            .outputKey("model_proposals")
            .build();

        // ── Phase 3: Evaluation & Selection ──────────────────────────────
        LlmAgent evaluator = LlmAgent.builder()
            .name("evaluator")
            .description("Compares model proposals and selects the best approach with justification.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a senior ML engineer evaluating model proposals.
                Review the three modeling approaches (linear, tree-based, neural network)
                from the conversation and:
                1. Compare their expected performance on this specific dataset
                2. Consider training cost, interpretability, and maintenance
                3. Select the BEST approach with a clear justification
                4. Identify the top 3 hyperparameters to tune for the selected model

                Output your selection clearly as: 'Selected model: [name]' followed by reasoning.
                """)
            .outputKey("selected_model")
            .build();

        // ── Phase 4: Iterative Refinement (LoopAgent intent) ─────────────
        LlmAgent optimizer = LlmAgent.builder()
            .name("optimizer")
            .description("Suggests hyperparameter values and refines based on validator feedback.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a hyperparameter optimization specialist. Based on the selected
                model and any previous optimization feedback in the conversation:
                1. Suggest specific hyperparameter values to try
                2. Explain the rationale (e.g., reduce overfitting, increase capacity)
                3. Predict the expected improvement

                If this is a subsequent iteration, refine based on the validator's feedback.
                """)
            .build();

        LlmAgent validator = LlmAgent.builder()
            .name("validator")
            .description("Reviews the optimizer's hyperparameter choices and gives actionable feedback.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a model validation expert. Review the optimizer's suggestions:
                1. Are the hyperparameter choices reasonable?
                2. Is there risk of overfitting or underfitting?
                3. Suggest one additional tweak that could help

                Provide brief, actionable feedback.
                """)
            .build();

        LlmAgent refinementLoop = LlmAgent.builder()
            .name("refinement_loop")
            .description("Iterative refinement loop: [optimizer → validator] for up to 2 cycles.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You orchestrate an iterative refinement loop. Run the cycle
                [optimizer → validator] up to 2 times (max_iterations=2),
                feeding the validator's feedback back to the optimizer.
                """)
            .subAgents(optimizer, validator)
            .outputKey("refined_hyperparameters")
            .build();

        // ── Phase 5: Final Report ────────────────────────────────────────
        LlmAgent reporter = LlmAgent.builder()
            .name("reporter")
            .description("Writes a concise final ML project summary report.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a technical writer producing an ML project summary.
                Based on the entire conversation (data analysis, model exploration,
                evaluation, and refinement), write a concise final report:

                ## ML Pipeline Report
                - **Dataset**: Brief description
                - **Selected Model**: Name and rationale
                - **Key Hyperparameters**: Final recommended values
                - **Expected Performance**: Estimated metrics
                - **Next Steps**: 2-3 recommendations for production deployment

                Keep the report under 200 words.
                """)
            .outputKey("final_report")
            .build();

        // ── Full Pipeline ────────────────────────────────────────────────
        LlmAgent mlPipeline = LlmAgent.builder()
            .name("ml_pipeline")
            .description("End-to-end ML pipeline orchestrating EDA, exploration, evaluation, refinement, and reporting.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You orchestrate a full ML pipeline. Run the stages sequentially:
                1. data_analyst — perform EDA
                2. model_exploration — parallel proposals from 3 modelers
                3. evaluator — pick the best approach
                4. refinement_loop — iterative hyperparameter tuning (up to 2 cycles)
                5. reporter — final summary report
                """)
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
