// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// ML Engineering Pipeline — multi-agent ML workflow.
//
// Builds a five-stage pipeline:
//   1. data_analyst — analyzes dataset, recommends approaches
//   2. model_exploration — (parallel) linear, tree, neural strategies
//   3. evaluator — selects best model
//   4. refinement — optimizer → validator × 2 rounds
//   5. reporter — final summary
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Phase 1: Data Analysis ────────────────────────────────────

var dataAnalyst = new Agent("data_analyst_55")
{
    Model        = Settings.LlmModel,
    Instructions =
        "Analyze the dataset. Provide: key features, data quality issues, " +
        "preprocessing steps, and which model families to try.",
};

// ── Phase 2: Parallel Model Exploration ──────────────────────

var modelExploration = new Agent("model_exploration_55")
{
    Agents = [
        new Agent("linear_modeler_55")
        {
            Model        = Settings.LlmModel,
            Instructions = "Propose a linear modeling approach (Ridge/Lasso/ElasticNet).",
        },
        new Agent("tree_modeler_55")
        {
            Model        = Settings.LlmModel,
            Instructions = "Propose a tree-based approach (XGBoost/LightGBM).",
        },
        new Agent("nn_modeler_55")
        {
            Model        = Settings.LlmModel,
            Instructions = "Propose a neural network approach (MLP/TabNet).",
        },
    ],
    Strategy = Strategy.Parallel,
};

// ── Phase 3: Evaluation ───────────────────────────────────────

var evaluator = new Agent("evaluator_55")
{
    Model        = Settings.LlmModel,
    Instructions =
        "Compare the three approaches. Select the best. " +
        "Output: 'Selected model: [name]' with justification.",
};

// ── Phase 4: Iterative Refinement ────────────────────────────

var refinement =
    new Agent("optimizer_r1_55") { Model = Settings.LlmModel, Instructions = "Suggest hyperparameter values with rationale." }
    >> new Agent("validator_r1_55") { Model = Settings.LlmModel, Instructions = "Review suggestions. Provide actionable feedback." }
    >> new Agent("optimizer_r2_55") { Model = Settings.LlmModel, Instructions = "Refine based on feedback." }
    >> new Agent("validator_r2_55") { Model = Settings.LlmModel, Instructions = "Final recommendation: ready for deployment?" };

// ── Phase 5: Report ───────────────────────────────────────────

var reporter = new Agent("reporter_55")
{
    Model        = Settings.LlmModel,
    Instructions =
        "Write a concise ML pipeline report: dataset, selected model, " +
        "hyperparameters, expected performance, next steps. Under 200 words.",
};

// ── Full Pipeline ─────────────────────────────────────────────

var mlPipeline = dataAnalyst >> modelExploration >> evaluator >> refinement >> reporter;

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    mlPipeline,
    "Build a model for California housing prices with features: " +
    "median income, house age, average rooms, latitude, longitude.");

result.PrintResult();
