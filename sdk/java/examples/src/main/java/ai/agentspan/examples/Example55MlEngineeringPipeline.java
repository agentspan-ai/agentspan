// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;

/**
 * Example 55 — ML Engineering Pipeline (multi-agent ML workflow)
 *
 * <p>Deploys a five-stage pipeline that flattens into 8 sequential agents,
 * matching Python's {@code >>} operator which inlines nested sequential chains:
 *
 * <pre>
 * ml_pipeline (SEQUENTIAL)
 * ├── data_analyst
 * ├── model_exploration (PARALLEL: linear, tree, nn)
 * ├── evaluator
 * ├── optimizer_r1
 * ├── validator_r1
 * ├── optimizer_r2
 * ├── validator_r2
 * └── reporter
 * </pre>
 *
 * <p>Note: Python's {@code >>} flattens nested sequential chains, so
 * {@code evaluator >> refinement >> reporter} inlines refinement's 4 sub-agents
 * directly into the top-level sequential list.
 */
public class Example55MlEngineeringPipeline {

    public static void main(String[] args) {
        // ── Phase 1: Data Analysis ─────────────────────────────────────────

        Agent dataAnalyst = Agent.builder()
            .name("data_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Analyze the dataset. Provide: key features, data quality issues, "
                + "preprocessing steps, and which model families to try.")
            .build();

        // ── Phase 2: Parallel Model Exploration ────────────────────────────

        Agent modelExploration = Agent.builder()
            .name("model_exploration")
            .model(Settings.LLM_MODEL)
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
                "Compare the three approaches. Select the best. "
                + "Output: 'Selected model: [name]' with justification.")
            .build();

        // ── Phase 4: Iterative Refinement — inlined 4 agents ──────────────
        // Python's >> flattens nested sequential chains, so these 4 agents
        // appear directly in the top-level sequential list.

        Agent optimizerR1 = Agent.builder()
            .name("optimizer_r1")
            .model(Settings.LLM_MODEL)
            .instructions("Suggest hyperparameter values with rationale.")
            .build();

        Agent validatorR1 = Agent.builder()
            .name("validator_r1")
            .model(Settings.LLM_MODEL)
            .instructions("Review suggestions. Provide actionable feedback.")
            .build();

        Agent optimizerR2 = Agent.builder()
            .name("optimizer_r2")
            .model(Settings.LLM_MODEL)
            .instructions("Refine based on feedback.")
            .build();

        Agent validatorR2 = Agent.builder()
            .name("validator_r2")
            .model(Settings.LLM_MODEL)
            .instructions("Final recommendation: ready for deployment?")
            .build();

        // ── Phase 5: Report ────────────────────────────────────────────────

        Agent reporter = Agent.builder()
            .name("reporter")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Write a concise ML pipeline report: dataset, selected model, "
                + "hyperparameters, expected performance, next steps. Under 200 words.")
            .build();

        // ── Full pipeline (flat 8-agent sequential list) ───────────────────

        Agent mlPipeline = Agent.builder()
            .name("ml_pipeline")
            .model(Settings.LLM_MODEL)
            .agents(dataAnalyst, modelExploration, evaluator,
                    optimizerR1, validatorR1, optimizerR2, validatorR2,
                    reporter)
            .strategy(Strategy.SEQUENTIAL)
            .timeoutSeconds(120000)
            .build();

        AgentResult result = Agentspan.run(mlPipeline,
            "Build a model for California housing prices...");
        result.printResult();

        Agentspan.shutdown();
    }
}
