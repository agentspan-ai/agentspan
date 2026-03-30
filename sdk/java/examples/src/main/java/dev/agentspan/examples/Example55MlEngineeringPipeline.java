// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 55 — ML Engineering Pipeline (multi-agent ML workflow)
 *
 * <p>Deploys a five-stage pipeline:
 * <ol>
 *   <li>Data analysis — analyze dataset, recommend approaches</li>
 *   <li>Model exploration — (parallel) linear, tree, neural network strategies</li>
 *   <li>Evaluation — compare and select best model</li>
 *   <li>Refinement — optimizer → validator × 2 rounds (sequential)</li>
 *   <li>Report — final executive summary</li>
 * </ol>
 *
 * <pre>
 * ml_pipeline (SEQUENTIAL)
 * ├── data_analyst
 * ├── model_exploration (PARALLEL)
 * │   ├── linear_modeler
 * │   ├── tree_modeler
 * │   └── nn_modeler
 * ├── evaluator
 * ├── refinement (SEQUENTIAL: optimizer_r1 → validator_r1 → optimizer_r2 → validator_r2)
 * └── reporter
 * </pre>
 */
public class Example55MlEngineeringPipeline {

    public static void main(String[] args) {
        // ── Phase 1: Data Analysis ─────────────────────────────────────────

        Agent dataAnalyst = Agent.builder()
            .name("data_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Analyze the dataset described. Provide: key features, data quality "
                + "issues, preprocessing steps, and which model families to try.")
            .build();

        // ── Phase 2: Parallel Model Exploration ────────────────────────────

        Agent modelExploration = Agent.builder()
            .name("model_exploration")
            .model(Settings.LLM_MODEL)
            .instructions("Coordinate parallel model exploration across three approaches.")
            .agents(
                Agent.builder()
                    .name("linear_modeler")
                    .model(Settings.LLM_MODEL)
                    .instructions("Propose a linear modeling approach (Ridge/Lasso/ElasticNet).")
                    .build(),
                Agent.builder()
                    .name("tree_modeler")
                    .model(Settings.LLM_MODEL)
                    .instructions("Propose a tree-based approach (XGBoost/LightGBM).")
                    .build(),
                Agent.builder()
                    .name("nn_modeler")
                    .model(Settings.LLM_MODEL)
                    .instructions("Propose a neural network approach (MLP/TabNet).")
                    .build()
            )
            .strategy(Strategy.PARALLEL)
            .build();

        // ── Phase 3: Evaluation ────────────────────────────────────────────

        Agent evaluator = Agent.builder()
            .name("evaluator")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Compare the three modeling approaches. Select the best. "
                + "Output: 'Selected model: [name]' with justification.")
            .build();

        // ── Phase 4: Iterative Refinement (SEQUENTIAL: 2 optimizer-validator rounds) ─

        Agent refinement = Agent.builder()
            .name("refinement")
            .model(Settings.LLM_MODEL)
            .instructions("Run iterative refinement cycles to improve the selected model.")
            .agents(
                Agent.builder()
                    .name("optimizer_r1")
                    .model(Settings.LLM_MODEL)
                    .instructions("Suggest hyperparameter values with rationale.")
                    .build(),
                Agent.builder()
                    .name("validator_r1")
                    .model(Settings.LLM_MODEL)
                    .instructions("Review suggestions. Provide actionable feedback.")
                    .build(),
                Agent.builder()
                    .name("optimizer_r2")
                    .model(Settings.LLM_MODEL)
                    .instructions("Refine based on feedback from the validator.")
                    .build(),
                Agent.builder()
                    .name("validator_r2")
                    .model(Settings.LLM_MODEL)
                    .instructions("Final recommendation: ready for deployment?")
                    .build()
            )
            .strategy(Strategy.SEQUENTIAL)
            .build();

        // ── Phase 5: Report ────────────────────────────────────────────────

        Agent reporter = Agent.builder()
            .name("reporter")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Write an executive summary of the full ML pipeline. Include: "
                + "dataset characteristics, selected model, final hyperparameters, "
                + "deployment recommendation.")
            .build();

        // ── Full pipeline ──────────────────────────────────────────────────

        Agent mlPipeline = Agent.builder()
            .name("ml_pipeline")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Run the full ML engineering pipeline: data analysis, parallel model "
                + "exploration, evaluation, iterative refinement, then final report.")
            .agents(dataAnalyst, modelExploration, evaluator, refinement, reporter)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(mlPipeline,
            "Build a churn prediction model for a SaaS company. "
            + "The dataset has 50,000 users with 20 features including usage metrics, "
            + "support tickets, billing history, and login frequency.");
        result.printResult();

        Agentspan.shutdown();
    }
}
