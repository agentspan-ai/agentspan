// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk34 — ML Engineering Pipeline.
//
// A multi-agent ML workflow combining sequential, parallel, and loop
// strategies. The strategy semantics are encoded inline (sub-agents
// with instructions describing parallel/loop intent).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var dataAnalyst = GoogleADKAgent.Builder()
    .Name("data_analyst")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a data scientist performing exploratory data analysis. " +
        "Given a dataset description, analyze it and provide:\n" +
        "1. Key features and their likely importance\n" +
        "2. Data quality considerations (missing values, outliers, scaling)\n" +
        "3. Recommended preprocessing steps\n" +
        "4. Which model families are most promising and why\n\n" +
        "Be concise and structured. Output a numbered analysis.")
    .Build();

var linearModeler = GoogleADKAgent.Builder()
    .Name("linear_modeler")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a machine learning engineer specializing in linear models. " +
        "Based on the data analysis in the conversation, propose a linear modeling approach:\n" +
        "- Model choice (e.g., Ridge, Lasso, ElasticNet, Logistic Regression)\n" +
        "- Feature engineering strategy\n" +
        "- Expected strengths and weaknesses\n" +
        "- Estimated performance range\n" +
        "Keep it to 4-5 bullet points.")
    .Build();

var treeModeler = GoogleADKAgent.Builder()
    .Name("tree_modeler")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a machine learning engineer specializing in tree-based models. " +
        "Based on the data analysis in the conversation, propose a tree-based approach:\n" +
        "- Model choice (e.g., Random Forest, XGBoost, LightGBM, CatBoost)\n" +
        "- Feature engineering strategy\n" +
        "- Key hyperparameters to tune\n" +
        "- Expected strengths and weaknesses\n" +
        "Keep it to 4-5 bullet points.")
    .Build();

var nnModeler = GoogleADKAgent.Builder()
    .Name("nn_modeler")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a machine learning engineer specializing in neural networks. " +
        "Based on the data analysis in the conversation, propose a neural network approach:\n" +
        "- Architecture choice (e.g., MLP, TabNet, FT-Transformer)\n" +
        "- Input preprocessing and embedding strategy\n" +
        "- Training considerations (learning rate, batch size, regularization)\n" +
        "- Expected strengths and weaknesses\n" +
        "Keep it to 4-5 bullet points.")
    .Build();

var parallelModeling = GoogleADKAgent.Builder()
    .Name("model_exploration")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate parallel model exploration. Dispatch the data analysis " +
        "to linear_modeler, tree_modeler, and nn_modeler concurrently and " +
        "aggregate their proposals.")
    .SubAgents(linearModeler, treeModeler, nnModeler)
    .Build();

var evaluator = GoogleADKAgent.Builder()
    .Name("evaluator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a senior ML engineer evaluating model proposals. " +
        "Review the three modeling approaches (linear, tree-based, neural network) " +
        "from the conversation and:\n" +
        "1. Compare their expected performance on this specific dataset\n" +
        "2. Consider training cost, interpretability, and maintenance\n" +
        "3. Select the BEST approach with a clear justification\n" +
        "4. Identify the top 3 hyperparameters to tune for the selected model\n\n" +
        "Output your selection clearly as: 'Selected model: [name]' followed by reasoning.")
    .Build();

var optimizer = GoogleADKAgent.Builder()
    .Name("optimizer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a hyperparameter optimization specialist. Based on the selected " +
        "model and any previous optimization feedback in the conversation:\n" +
        "1. Suggest specific hyperparameter values to try\n" +
        "2. Explain the rationale (e.g., reduce overfitting, increase capacity)\n" +
        "3. Predict the expected improvement\n\n" +
        "If this is a subsequent iteration, refine based on the validator's feedback.")
    .Build();

var validator = GoogleADKAgent.Builder()
    .Name("validator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a model validation expert. Review the optimizer's suggestions:\n" +
        "1. Are the hyperparameter choices reasonable?\n" +
        "2. Is there risk of overfitting or underfitting?\n" +
        "3. Suggest one additional tweak that could help\n\n" +
        "Provide brief, actionable feedback.")
    .Build();

var refinementLoop = GoogleADKAgent.Builder()
    .Name("refinement_loop")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate an iterative refinement loop. Run the cycle " +
        "[optimizer -> validator] up to 2 times (max_iterations=2), " +
        "feeding the validator's feedback back to the optimizer.")
    .SubAgents(optimizer, validator)
    .Build();

var reporter = GoogleADKAgent.Builder()
    .Name("reporter")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a technical writer producing an ML project summary. " +
        "Based on the entire conversation (data analysis, model exploration, " +
        "evaluation, and refinement), write a concise final report:\n\n" +
        "## ML Pipeline Report\n" +
        "- **Dataset**: Brief description\n" +
        "- **Selected Model**: Name and rationale\n" +
        "- **Key Hyperparameters**: Final recommended values\n" +
        "- **Expected Performance**: Estimated metrics\n" +
        "- **Next Steps**: 2-3 recommendations for production deployment\n\n" +
        "Keep the report under 200 words.")
    .Build();

var mlPipeline = GoogleADKAgent.Builder()
    .Name("ml_pipeline")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate a full ML pipeline. Run the stages sequentially:\n" +
        "1. data_analyst — perform EDA\n" +
        "2. model_exploration — parallel proposals from 3 modelers\n" +
        "3. evaluator — pick the best approach\n" +
        "4. refinement_loop — iterative hyperparameter tuning (up to 2 cycles)\n" +
        "5. reporter — final summary report")
    .SubAgents(dataAnalyst, parallelModeling, evaluator, refinementLoop, reporter)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(mlPipeline,
    "Build a model to predict California housing prices. The dataset has 20,640 samples " +
    "with 8 features: MedInc, HouseAge, AveRooms, AveBedrms, Population, AveOccup, " +
    "Latitude, Longitude. Target: MedianHouseValue (continuous, in $100k units). " +
    "Metric: RMSE. Some features have skewed distributions.");
result.PrintResult();
