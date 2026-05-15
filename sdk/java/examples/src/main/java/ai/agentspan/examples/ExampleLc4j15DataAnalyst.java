// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Lc4j 15 — Data Analyst
 *
 * <p>Java port of <code>sdk/python/examples/langchain/15_data_analyst.py</code>.
 *
 * <p>Demonstrates: CSV parsing, descriptive statistics, sorting, and outlier
 * detection (IQR method) over a sales dataset.
 */
public class ExampleLc4j15DataAnalyst {

    /** Minimal CSV → list-of-maps parser. Assumes first row is the header. */
    private static List<Map<String, String>> parseCsv(String csvData) {
        List<Map<String, String>> rows = new ArrayList<>();
        if (csvData == null) return rows;
        String[] lines = csvData.trim().split("\\r?\\n");
        if (lines.length == 0) return rows;
        String[] headers = lines[0].split(",");
        for (int i = 0; i < headers.length; i++) headers[i] = headers[i].trim();
        for (int li = 1; li < lines.length; li++) {
            String line = lines[li];
            if (line.trim().isEmpty()) continue;
            String[] cells = line.split(",", -1);
            Map<String, String> row = new LinkedHashMap<>();
            for (int i = 0; i < headers.length; i++) {
                row.put(headers[i], i < cells.length ? cells[i].trim() : "");
            }
            rows.add(row);
        }
        return rows;
    }

    static class DataAnalystTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "analyze_column",
            value = "Compute descriptive statistics for a numeric column in CSV data. "
                  + "Args: csv_data: CSV-formatted string with headers in the first row. "
                  + "column_name: The column header to analyze."
        )
        public String analyzeColumn(
                @dev.langchain4j.agent.tool.P("csv_data") String csvData,
                @dev.langchain4j.agent.tool.P("column_name") String columnName) {
            try {
                List<Map<String, String>> rows = parseCsv(csvData);
                List<Double> values = new ArrayList<>();
                for (Map<String, String> row : rows) {
                    String v = row.getOrDefault(columnName, "").trim();
                    if (!v.isEmpty()) values.add(Double.parseDouble(v));
                }
                if (values.isEmpty()) {
                    return "Column '" + columnName + "' not found or has no numeric values.";
                }
                int n = values.size();
                double sum = 0;
                double min = values.get(0);
                double max = values.get(0);
                for (double v : values) { sum += v; if (v < min) min = v; if (v > max) max = v; }
                double mean = sum / n;
                List<Double> sorted = new ArrayList<>(values);
                java.util.Collections.sort(sorted);
                double median = (n % 2 != 0)
                    ? sorted.get(n / 2)
                    : (sorted.get(n / 2 - 1) + sorted.get(n / 2)) / 2.0;
                // Sample stdev to match Python statistics.stdev
                double sqDiff = 0;
                for (double v : values) sqDiff += (v - mean) * (v - mean);
                double stdev = n > 1 ? Math.sqrt(sqDiff / (n - 1)) : 0.0;

                return String.format(
                    "Column '%s': n=%d, mean=%.2f, median=%.2f, stdev=%.2f, min=%.2f, max=%.2f",
                    columnName, n, mean, median, stdev, min, max);
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "find_top_rows",
            value = "Return the top N rows sorted by a numeric column (descending). "
                  + "Args: csv_data: CSV-formatted string with headers. "
                  + "column_name: The column to sort by. "
                  + "n: Number of top rows to return (default 3)."
        )
        public String findTopRows(
                @dev.langchain4j.agent.tool.P("csv_data") String csvData,
                @dev.langchain4j.agent.tool.P("column_name") String columnName,
                @dev.langchain4j.agent.tool.P("n") int n) {
            try {
                int take = n <= 0 ? 3 : n;
                List<Map<String, String>> rows = parseCsv(csvData);
                List<Map<String, String>> filtered = new ArrayList<>();
                for (Map<String, String> row : rows) {
                    String v = row.getOrDefault(columnName, "").trim();
                    if (!v.isEmpty()) filtered.add(row);
                }
                filtered.sort((a, b) -> {
                    double av = Double.parseDouble(a.get(columnName));
                    double bv = Double.parseDouble(b.get(columnName));
                    return Double.compare(bv, av);
                });
                if (filtered.isEmpty()) return "";
                List<String> headers = new ArrayList<>(filtered.get(0).keySet());
                StringBuilder sb = new StringBuilder();
                sb.append(String.join(", ", headers)).append("\n");
                int limit = Math.min(take, filtered.size());
                for (int i = 0; i < limit; i++) {
                    Map<String, String> row = filtered.get(i);
                    List<String> cells = new ArrayList<>();
                    for (String h : headers) cells.add(row.get(h));
                    sb.append(String.join(", ", cells));
                    if (i < limit - 1) sb.append("\n");
                }
                return sb.toString().trim();
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "detect_outliers",
            value = "Detect outliers in a numeric column using the IQR method. "
                  + "Args: csv_data: CSV-formatted string with headers. "
                  + "column_name: The column to check for outliers."
        )
        public String detectOutliers(
                @dev.langchain4j.agent.tool.P("csv_data") String csvData,
                @dev.langchain4j.agent.tool.P("column_name") String columnName) {
            try {
                List<Map<String, String>> rows = parseCsv(csvData);
                List<Double> values = new ArrayList<>();
                for (Map<String, String> row : rows) {
                    String v = row.getOrDefault(columnName, "").trim();
                    if (!v.isEmpty()) values.add(Double.parseDouble(v));
                }
                if (values.size() < 4) {
                    return "Not enough data points for outlier detection (need at least 4).";
                }
                java.util.Collections.sort(values);
                int n = values.size();
                double q1 = values.get(n / 4);
                double q3 = values.get(3 * n / 4);
                double iqr = q3 - q1;
                double lower = q1 - 1.5 * iqr;
                double upper = q3 + 1.5 * iqr;
                List<Double> outliers = new ArrayList<>();
                for (double v : values) {
                    if (v < lower || v > upper) outliers.add(v);
                }
                if (outliers.isEmpty()) {
                    return String.format("No outliers detected in '%s' (IQR bounds: [%.2f, %.2f]).",
                        columnName, lower, upper);
                }
                return String.format("Outliers in '%s': %s (IQR bounds: [%.2f, %.2f]).",
                    columnName, outliers.toString(), lower, upper);
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }
    }

    private static final String SALES_DATA = "product,units_sold,revenue,margin\n"
            + "Widget A,150,4500.00,0.35\n"
            + "Widget B,89,2670.00,0.42\n"
            + "Gadget Pro,312,15600.00,0.28\n"
            + "Gadget Lite,201,6030.00,0.31\n"
            + "Premium Kit,45,9000.00,0.55\n"
            + "Basic Kit,520,7800.00,0.18\n"
            + "Super Widget,8,400.00,0.50";

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "data_analyst_agent",
            Settings.LLM_MODEL,
            "You are a data analyst. Analyze the provided data using statistical tools "
            + "and present your findings clearly with insights and recommendations.",
            new DataAnalystTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Analyze this sales data. What are the revenue statistics, the top 3 products by revenue, "
            + "and any outliers?\n\n" + SALES_DATA
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
