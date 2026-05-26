// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 07 — Output Key State
 *
 * <p>Java port of <code>sdk/python/examples/adk/07_output_key_state.py</code>.
 *
 * <p>Demonstrates: ADK's {@code outputKey} for passing data between
 * sub-agents through shared session state.
 */
public class Example07OutputKeyState {

    @Schema(description = "Analyze a dataset and return key statistics.")
    public static Map<String, Object> analyzeData(
            @Schema(name = "dataset", description = "Dataset name") String dataset) {
        Map<String, Map<String, Object>> datasets = new LinkedHashMap<>();
        datasets.put("sales_q4", Map.of(
            "total_revenue", "$2.3M",
            "growth_rate", "12%",
            "top_product", "Widget Pro",
            "avg_order_value", "$156"));
        datasets.put("user_engagement", Map.of(
            "daily_active_users", "45,000",
            "avg_session_duration", "8.5 min",
            "retention_rate", "72%",
            "churn_rate", "5.2%"));
        return datasets.getOrDefault(dataset.toLowerCase(),
            Map.of("error", "Dataset '" + dataset + "' not found"));
    }

    @Schema(description = "Generate a description for a chart visualization.")
    public static Map<String, Object> generateChartDescription(
            @Schema(name = "metric", description = "Metric name") String metric,
            @Schema(name = "value", description = "Metric value") String value) {
        return Map.of(
            "chart_type", value.contains("%") ? "gauge" : "bar",
            "metric", metric,
            "value", value,
            "recommendation", "Track " + metric + " weekly for trend analysis."
        );
    }

    public static void main(String[] args) {
        LlmAgent analyst = LlmAgent.builder()
            .name("data_analyst")
            .description("Examines datasets with the analyze_data tool and summarizes key findings.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data analyst. Use the analyze_data tool to examine datasets. "
                + "Provide a clear summary of the key findings.")
            .tools(FunctionTool.create(Example07OutputKeyState.class, "analyzeData"))
            .outputKey("analysis_result")
            .build();

        LlmAgent visualizer = LlmAgent.builder()
            .name("chart_designer")
            .description("Suggests chart visualizations for the analyst's key metrics.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data visualization expert. Based on the analysis results, "
                + "suggest appropriate visualizations. Use the generate_chart_description "
                + "tool for each key metric.")
            .tools(FunctionTool.create(Example07OutputKeyState.class, "generateChartDescription"))
            .outputKey("visualization_result")
            .build();

        LlmAgent coordinator = LlmAgent.builder()
            .name("report_coordinator")
            .description("Orchestrates the analyst and chart designer to produce a final executive report.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a report coordinator. First, have the data analyst examine "
                + "the requested dataset. Then, have the chart designer suggest "
                + "visualizations. Provide a final executive summary.")
            .subAgents(analyst, visualizer)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Create a report on the sales_q4 dataset with visualization recommendations.");
        result.printResult();

        Agentspan.shutdown();
    }
}
