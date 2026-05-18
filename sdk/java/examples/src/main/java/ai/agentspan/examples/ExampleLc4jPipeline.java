// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Lc4j 04 — LangChain4j Agent in a Sequential Pipeline
 *
 * <p>Demonstrates interoperability between a LangChain4j-backed agent and a
 * regular Agentspan agent inside a sequential pipeline (using {@link Agent#then}).
 *
 * <p>Pipeline stages:
 * <ol>
 *   <li><b>data_gatherer</b> — built from LangChain4j {@code @Tool} methods
 *       that look up product data. The LLM calls the tools and produces
 *       a structured data payload.</li>
 *   <li><b>report_writer</b> — a plain Agentspan agent (no tools) that
 *       receives the data payload as its input and writes a human-readable
 *       report.</li>
 * </ol>
 *
 * <p>This pattern shows that {@code LangChain4jAgent.from()} returns a standard
 * {@link Agent} — it composes naturally with any other Agentspan agent or
 * orchestration strategy.
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767}</li>
 *   <li>langchain4j on the classpath (see examples/build.gradle)</li>
 * </ul>
 */
public class ExampleLc4jPipeline {

    // ── LangChain4j tool class used in stage 1 ────────────────────────────────

    static class ProductDataTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "get_product_details",
            value = "Retrieve details for a product by SKU, including name, price, and category"
        )
        public java.util.Map<String, Object> getProductDetails(
                @dev.langchain4j.agent.tool.P("sku") String sku) {
            // Stub: in production this would query a database or API
            return java.util.Map.of(
                "sku", sku,
                "name", "Widget Pro 3000",
                "price_usd", 49.99,
                "category", "Electronics",
                "in_stock", true,
                "units_available", 142
            );
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_sales_stats",
            value = "Get 30-day sales statistics for a product SKU"
        )
        public java.util.Map<String, Object> getSalesStats(
                @dev.langchain4j.agent.tool.P("sku") String sku) {
            return java.util.Map.of(
                "sku", sku,
                "units_sold_30d", 380,
                "revenue_30d_usd", 18996.20,
                "avg_rating", 4.7,
                "top_region", "North America"
            );
        }
    }

    public static void main(String[] args) {
        // Stage 1: LangChain4j-backed agent — uses @Tool methods to gather product data.
        // LangChain4jAgent.from() wraps the POJO methods as Agentspan worker tools.
        Agent dataGatherer = LangChain4jAgent.from(
            "data_gatherer",
            Settings.LLM_MODEL,
            "You are a product data specialist. Use your tools to look up product details "
            + "and sales statistics, then output a compact JSON summary of everything you found.",
            new ProductDataTools()
        );

        // Stage 2: Plain Agentspan agent (no tools) — receives the data summary and writes a report.
        Agent reportWriter = Agent.builder()
            .name("report_writer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a business analyst. You receive structured product data and write "
                + "a concise executive summary report in plain English. "
                + "Highlight key metrics, stock status, and regional performance.")
            .build();

        // Chain into a sequential pipeline: data_gatherer → report_writer
        // The output of stage 1 becomes the input to stage 2.
        // LangChain4jAgent returns a standard Agent — .then() works identically.
        Agent pipeline = dataGatherer.then(reportWriter);

        System.out.println("Pipeline: " + pipeline.getName());
        System.out.println("Stages: " + pipeline.getAgents().size());

        AgentResult result = Agentspan.run(pipeline,
            "Generate a product report for SKU 'WDGT-3000'.");
        result.printResult();

        Agentspan.shutdown();
    }
}
