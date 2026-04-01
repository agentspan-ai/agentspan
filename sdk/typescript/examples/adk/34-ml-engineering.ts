/**
 * Google ADK ML Engineering Pipeline -- multi-agent ML workflow.
 *
 * Mirrors the pattern from google/adk-samples/machine-learning-engineering (MLE-STAR).
 * Demonstrates:
 *   - SequentialAgent pipeline with distinct ML phases
 *   - ParallelAgent for concurrent model strategy exploration
 *   - LoopAgent for iterative refinement (ablation-style)
 *   - outputKey for state passing between pipeline stages
 *
 * Architecture:
 *   ml_pipeline (SequentialAgent)
 *     sub_agents:
 *       1. data_analyst       -- Analyze dataset, identify features
 *       2. model_exploration  -- (ParallelAgent) 3 model strategies concurrently
 *          - linear_modeler
 *          - tree_modeler
 *          - nn_modeler
 *       3. evaluator          -- Compare approaches, select best
 *       4. refinement_loop    -- (LoopAgent) Iterative hyperparameter optimization
 *          - refine_cycle     -- (SequentialAgent)
 *            - optimizer
 *            - validator
 *       5. reporter           -- Generate final summary report
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, SequentialAgent, ParallelAgent, LoopAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Phase 1: Data Analysis ───────────────────────────────────────────

export const dataAnalyst = new LlmAgent({
  name: 'data_analyst',
  model,
  instruction:
    'You are a data scientist performing exploratory data analysis. ' +
    'Given a dataset description, analyze it and provide:\n' +
    '1. Key features and their likely importance\n' +
    '2. Data quality considerations (missing values, outliers, scaling)\n' +
    '3. Recommended preprocessing steps\n' +
    '4. Which model families are most promising and why\n\n' +
    'Be concise and structured. Output a numbered analysis.',
  outputKey: 'data_analysis',
});

// ── Phase 2: Parallel Model Strategy Exploration ─────────────────────

export const linearModeler = new LlmAgent({
  name: 'linear_modeler',
  model,
  instruction:
    'You are a machine learning engineer specializing in linear models. ' +
    'Based on the data analysis in the conversation, propose a linear modeling approach:\n' +
    '- Model choice (e.g., Ridge, Lasso, ElasticNet, Logistic Regression)\n' +
    '- Feature engineering strategy\n' +
    '- Expected strengths and weaknesses\n' +
    '- Estimated performance range\n' +
    'Keep it to 4-5 bullet points.',
});

export const treeModeler = new LlmAgent({
  name: 'tree_modeler',
  model,
  instruction:
    'You are a machine learning engineer specializing in tree-based models. ' +
    'Based on the data analysis in the conversation, propose a tree-based approach:\n' +
    '- Model choice (e.g., Random Forest, XGBoost, LightGBM, CatBoost)\n' +
    '- Feature engineering strategy\n' +
    '- Key hyperparameters to tune\n' +
    '- Expected strengths and weaknesses\n' +
    'Keep it to 4-5 bullet points.',
});

export const nnModeler = new LlmAgent({
  name: 'nn_modeler',
  model,
  instruction:
    'You are a machine learning engineer specializing in neural networks. ' +
    'Based on the data analysis in the conversation, propose a neural network approach:\n' +
    '- Architecture choice (e.g., MLP, TabNet, FT-Transformer)\n' +
    '- Input preprocessing and embedding strategy\n' +
    '- Training considerations (learning rate, batch size, regularization)\n' +
    '- Expected strengths and weaknesses\n' +
    'Keep it to 4-5 bullet points.',
});

export const parallelModeling = new ParallelAgent({
  name: 'model_exploration',
  subAgents: [linearModeler, treeModeler, nnModeler],
});

// ── Phase 3: Evaluation & Selection ──────────────────────────────────

export const evaluator = new LlmAgent({
  name: 'evaluator',
  model,
  instruction:
    'You are a senior ML engineer evaluating model proposals. ' +
    'Review the three modeling approaches (linear, tree-based, neural network) ' +
    'from the conversation and:\n' +
    '1. Compare their expected performance on this specific dataset\n' +
    '2. Consider training cost, interpretability, and maintenance\n' +
    '3. Select the BEST approach with a clear justification\n' +
    '4. Identify the top 3 hyperparameters to tune for the selected model\n\n' +
    "Output your selection clearly as: 'Selected model: [name]' followed by reasoning.",
  outputKey: 'model_selection',
});

// ── Phase 4: Iterative Refinement (LoopAgent) ────────────────────────

export const optimizer = new LlmAgent({
  name: 'optimizer',
  model,
  instruction:
    'You are a hyperparameter optimization specialist. Based on the selected ' +
    'model and any previous optimization feedback in the conversation:\n' +
    '1. Suggest specific hyperparameter values to try\n' +
    '2. Explain the rationale (e.g., reduce overfitting, increase capacity)\n' +
    '3. Predict the expected improvement\n\n' +
    "If this is a subsequent iteration, refine based on the validator's feedback.",
});

export const validator = new LlmAgent({
  name: 'validator',
  model,
  instruction:
    "You are a model validation expert. Review the optimizer's suggestions:\n" +
    '1. Are the hyperparameter choices reasonable?\n' +
    '2. Is there risk of overfitting or underfitting?\n' +
    '3. Suggest one additional tweak that could help\n\n' +
    'Provide brief, actionable feedback.',
});

export const refineCycle = new SequentialAgent({
  name: 'refine_cycle',
  subAgents: [optimizer, validator],
});

export const refinementLoop = new LoopAgent({
  name: 'refinement_loop',
  subAgents: [refineCycle],
  maxIterations: 2,
});

// ── Phase 5: Final Report ────────────────────────────────────────────

export const reporter = new LlmAgent({
  name: 'reporter',
  model,
  instruction:
    'You are a technical writer producing an ML project summary. ' +
    'Based on the entire conversation (data analysis, model exploration, ' +
    'evaluation, and refinement), write a concise final report:\n\n' +
    '## ML Pipeline Report\n' +
    '- **Dataset**: Brief description\n' +
    '- **Selected Model**: Name and rationale\n' +
    '- **Key Hyperparameters**: Final recommended values\n' +
    '- **Expected Performance**: Estimated metrics\n' +
    '- **Next Steps**: 2-3 recommendations for production deployment\n\n' +
    'Keep the report under 200 words.',
});

// ── Full Pipeline ────────────────────────────────────────────────────

export const mlPipeline = new SequentialAgent({
  name: 'ml_pipeline',
  subAgents: [dataAnalyst, parallelModeling, evaluator, refinementLoop, reporter],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(mlPipeline);
    // await runtime.serve(mlPipeline);
    // Direct run for local development:
    const result = await runtime.run(
    mlPipeline,
    'Build a model to predict California housing prices. The dataset has 20,640 samples ' +
    'with 8 features: MedInc, HouseAge, AveRooms, AveBedrms, Population, AveOccup, ' +
    'Latitude, Longitude. Target: MedianHouseValue (continuous, in $100k units). ' +
    'Metric: RMSE. Some features have skewed distributions.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('34-ml-engineering.ts') || process.argv[1]?.endsWith('34-ml-engineering.js')) {
  main().catch(console.error);
}
