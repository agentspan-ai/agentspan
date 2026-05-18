// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 07 — Output Key State
 *
 * <p>Java port of <code>sdk/python/examples/adk/07_output_key_state.py</code>.
 *
 * <p>Demonstrates: ADK's {@code output_key} for passing data between
 * sub-agents through shared session state. Java's {@link GoogleADKAgent}
 * builder does not expose {@code output_key} directly; the structural
 * pattern (coordinator → analyst + visualizer) is preserved via subAgents.
 */
public class Example07OutputKeyState {

    static class AnalystTools {
        @Tool(name = "analyze_data", value = "Analyze a dataset and return key statistics.")
        public Map<String, Object> analyzeData(@P("dataset") String dataset) {
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
    }

    static class VisualizerTools {
        @Tool(name = "generate_chart_description", value = "Generate a description for a chart visualization.")
        public Map<String, Object> generateChartDescription(
                @P("metric") String metric,
                @P("value") String value) {
            return Map.of(
                "chart_type", value.contains("%") ? "gauge" : "bar",
                "metric", metric,
                "value", value,
                "recommendation", "Track " + metric + " weekly for trend analysis."
            );
        }
    }

    public static void main(String[] args) {
        Agent analyst = GoogleADKAgent.builder()
            .name("data_analyst")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data analyst. Use the analyze_data tool to examine datasets. "
                + "Provide a clear summary of the key findings.")
            .tools(new AnalystTools())
            .build();

        Agent visualizer = GoogleADKAgent.builder()
            .name("chart_designer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data visualization expert. Based on the analysis results, "
                + "suggest appropriate visualizations. Use the generate_chart_description "
                + "tool for each key metric.")
            .tools(new VisualizerTools())
            .build();

        Agent coordinator = GoogleADKAgent.builder()
            .name("report_coordinator")
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
